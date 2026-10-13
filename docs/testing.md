# Offline testing foundation

Run from PowerShell (any working directory):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\codex-projetc\Chatbot_text_image\scripts\run_offline_tests.ps1"
```

The wrapper uses the project's `.venv`, invokes `tests.run_offline`, and preserves
its exit code. That runner installs deterministic process-local AWS settings and
network/AWS guards **before discovery**, discovers each test once, rejects duplicate
IDs, and fails on swallowed forbidden calls as well as ordinary test failures.
Use this entry point instead of bare unittest discovery, which lacks suite-wide
guards. Do not use the live diagnostic script to run regression tests.

The guards cover SDK client creation, credential resolution and API invocation,
TCP connections/sends, DNS resolution and UDP sends. Tests replace service/client
boundaries with explicit mocks. Guards are process-local regression safeguards,
not an OS sandbox: isolated document parser subprocesses and native libraries
are not instrumented. Use a network-denied host/container for a hard egress boundary.

Task 2C removes ten wrapper tests that recursively executed earlier suites; their
underlying tests remain in normal discovery. Image validation assertions now require
the expected success/error types rather than conditionally checking results.

New Streamlit tests run the actual launcher with `AppTest`, real widget state,
callbacks and reruns. They exercise chat/follow-up, incomplete streaming, blank
input, upload replacement/removal/consumption, new chat and session isolation.
Only the AWS client boundary is mocked; no Streamlit server or browser is launched.
They use an authenticated local demo fixture. Task 3A adds mocked Cognito and
real Streamlit login/logout tests in `test_3a_cognito_auth.py`; these new tests have
not been run. CSS/browser layout and live Cognito remain outside offline coverage.
Use the pinned Streamlit version, which exposes uploader interaction APIs.

Task 3B adds `test_3b_authorization.py` with 27 mocked offline test methods for
ownership, ID tampering, read/write/delete/export isolation and stale operations.
Existing fixtures seed server-owned state through the authorization boundary.
These tests have not been run; use the same guarded full-suite command above.

The user subsequently reported **350/350 tests passed** after Task 2C. Task 2D
did not rerun them. See [the task register](task_register.md) for status and evidence.
