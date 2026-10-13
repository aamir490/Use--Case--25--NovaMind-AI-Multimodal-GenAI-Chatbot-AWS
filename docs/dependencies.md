# Python and dependency baseline (Task 2B)

The supported local target is **standard CPython 3.14.6, Windows x64**,
matching the existing environment. The latest user-reported result is 350/350
offline tests after Task 2C; see [the task register](task_register.md). `.python-version` records that interpreter version; Python's Windows
launcher does not enforce this file automatically. Other Python versions and
free-threaded builds need separate validation. The container uses the separate
`requirements-linux.txt` exact-version closure; Linux installation and image
build remain unverified until the Docker checks in [docker.md](docker.md) pass.
Task 2B did not install packages, run tests, or access AWS.

`requirements.in` records the five direct runtime dependencies. `requirements.txt`
pins their complete default dependency closure using installed distribution
metadata for this target. `requirements_new.txt` includes that lock so existing
installation commands remain compatible. No test framework package is needed:
the offline suite uses standard-library `unittest`. Its dependency checks use
`packaging`, already pinned as part of Streamlit's required dependency closure.

- boto3 and botocore: AWS clients, configuration and exception handling; their
  pinned versions satisfy boto3's declared botocore range.
- Streamlit: the frontend and its transitive rendering/server dependencies.
- Pillow: required image validation, decoding, transformation and previews.
- pypdf: required PDF validation, including the resource-limit APIs used by the
  isolated parser. Missing validation dependencies reject files safely.

LangChain packages, PyYAML and python-dotenv have no active application imports
and were removed from the declarations. Existing environments are not uninstalled
or changed. Requests remains as a pinned Streamlit dependency. `.env` files are
not loaded automatically by the application.

Legacy `.doc`/`.xls` validation additionally needs `olefile`, declared in
`requirements-legacy.txt`. Its 0.47 pin is a proposed optional baseline, not a
version verified in the current environment (where it is absent). Legacy files
continue to fail closed without it. `.docx`/`.xlsx` validation uses the standard
library and does not need this extra. Before enabling legacy support, validate
the optional installation and representative valid and corrupt legacy files.

For AWS settings and launcher behavior, see [setup](setup.md).

## Reproduce in PowerShell

These are instructions for the user, not commands executed during Task 2B.
Use a fresh checkout/directory without an existing `.venv`; do not overwrite an
environment you need to keep. Install standard Windows x64 CPython 3.14.6 first.

```powershell
Set-Location 'E:\codex-projetc\Chatbot_text_image'
py -3.14 -c "import sys, struct; assert sys.version_info[:3] == (3, 14, 6) and struct.calcsize('P') == 8, 'Use CPython 3.14.6 x64'"
# Continue only if that check succeeds and this directory has no .venv.
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_offline_tests.ps1
.\.venv\Scripts\python.exe -m streamlit run mod_chatbot_frontend.py
```

For optional legacy support, substitute `requirements-legacy.txt` in the install
command. No AWS credentials or live access are needed to install or run the
offline suite. Launching the application retains Task 1J's AWS configuration
policy: local profile `novamind`, region `us-east-1`; deployed task-role mode is
separate. No AWS calls are authorized by this document.

## Updating and limits

The lock removes version drift; it is not a hash-verified artifact lock or a
security vulnerability audit. Package availability and a clean installation
remain unverified. Pip/build-tool versions are not part of the application
lock. Prefer wheels; source builds require separately controlled build tools.

Do not run an unfiltered `pip freeze`: the current environment contains unused
LangChain dependencies. For updates, change the direct pins in a disposable
environment, resolve their default transitive dependencies, update the full lock,
inspect metadata compatibility, run `pip check`, and run the offline suite before
acceptance. Revalidate parser resource APIs and Streamlit behavior when upgrading.
Do not claim an old lower bound or an automatic latest-version upgrade is safe.
The Linux lock is derived from the pinned runtime closure with Windows-only
Colorama omitted. It pins versions, not package hashes. Validate Linux wheel
availability and the clean image build before deployment.
