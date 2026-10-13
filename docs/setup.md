# Local setup

## Supported baseline

Use standard (non-free-threaded) CPython 3.14.6 on Windows x64. Follow
[dependencies.md](dependencies.md) for fresh-environment creation and pinned
installation. Do not recreate an existing `.venv` in place. No packages were
installed as part of Task 2D. The launcher is `mod_chatbot_frontend.py`; historical
`chatbot_frontend2.py` instructions no longer apply.

## Configuration

`services/aws_config.py` is authoritative: `load_aws_config` (line 35),
`create_aws_session` (line 51), and `bedrock_options` (line 79).
Local mode is the default and explicitly selects `novamind`, even when profile
variables are absent. It never silently selects the default profile.

```powershell
Set-Location 'E:\codex-projetc\Chatbot_text_image'
$env:NOVAMIND_AWS_MODE = 'local'
$env:AWS_PROFILE = 'novamind'
$env:AWS_DEFAULT_PROFILE = 'novamind'
$env:AWS_REGION = 'us-east-1'
$env:AWS_DEFAULT_REGION = 'us-east-1'
.\.venv\Scripts\python.exe -B scripts/bedrock_model_access_check.py
```

This diagnostic is offline by default. It checks required module availability,
configuration and the selected model policy, not credentials or model access.
Conflicting profile/region selectors and nonempty static credential environment
variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`,
`AWS_SECURITY_TOKEN`) are rejected. Use a clean process environment; never paste
credentials into the app, documentation, logs or a support request.

Provision the named profile separately through your organization's approved AWS
credential process. For an already configured SSO profile, an explicitly approved
live sign-in uses `aws sso login --profile novamind --region us-east-1`.
No live sign-in or AWS operation is part of offline setup/verification.

Bedrock options use explicit service arguments, then environment, then defaults:
`BEDROCK_MODEL_ID=amazon.nova-pro-v1:0`, `BEDROCK_MAX_TOKENS=2048`,
`BEDROCK_TEMPERATURE=0.7`, and a built-in system prompt. Set
`BEDROCK_SYSTEM_PROMPT` explicitly to override that prompt. UI settings remain in
the session after initialization. `.env.example` is reference material; copying
it to `.env` does not load it. The UI supports only its three configured model choices.

## Run and verify

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_offline_tests.ps1
$env:NOVAMIND_AUTH_MODE = 'demo'  # Explicit loopback-only development opt-in
.\.venv\Scripts\python.exe -m streamlit run mod_chatbot_frontend.py --server.address 127.0.0.1
```

Open localhost:8501 and sign in with `demo / demo1234`. Demo configuration lives
in `novamind/config/settings.py` and is restricted to local development. Without
explicit demo opt-in, Cognito configuration is required and missing settings block
login. See [Task 3A](task_3a_cognito_auth.md) for Cognito configuration and sessions.
Sending chat, requesting summaries or pressing the labelled live Bedrock check
can invoke AWS and incur charges. Offline tests replace that boundary with mocks.

Diagnostic flags, only for a separately approved live check:

- `--live-check`: STS identity and Bedrock model catalog calls.
- `--live-check --live-inference`: additionally sends generated text/image/PDF
  fixtures through inference in explicit local demo mode; programmatic Cognito
  diagnostics require an authenticated session. Catalog success alone does not prove invocation access.
- `--live-inference` alone is invalid (exit 2); check failures return 1; success returns 0.

See [deployment](../deployment.md) for the distinct task-role mode.
