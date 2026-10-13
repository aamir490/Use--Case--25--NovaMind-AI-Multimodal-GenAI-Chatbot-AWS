# Task 3A — Cognito authentication

Implemented in source; **tests have not been run**. The incoming baseline is the
user-reported 350/350 tests. No AWS calls, provisioning, package installation,
Git push, or deployment was performed. Stop scope: Task 3A only.

## Configuration and prerequisites

Authentication defaults to `cognito`, including on a local workstation. Missing
or invalid configuration fails closed; it never falls back to demo credentials.
Set these process environment variables using your existing resource IDs:

```powershell
$env:NOVAMIND_AUTH_MODE = 'cognito'
$env:COGNITO_USER_POOL_ID = '<existing us-east-1 user-pool ID>'
$env:COGNITO_APP_CLIENT_ID = '<existing app-client ID>'
$env:NOVAMIND_SESSION_MAX_SECONDS = '3600'
$env:NOVAMIND_SESSION_IDLE_SECONDS = '900'
```

The placeholders intentionally are not working IDs. Configure the existing pool
in the intended account `357001292388`, region `us-east-1`; neither ownership nor
resource existence was verified. The app client must be **without a client secret**,
enable `ALLOW_USER_PASSWORD_AUTH`, and issue access tokens with
`aws.cognito.signin.user.admin` and readable `sub`. Enable token revocation and user
existence error suppression. Confirm account/password policies and MFA externally.
No pool or app client is created by this change.

Cognito sign-in uses `InitiateAuth` and supports SMS/TOTP MFA via
`RespondToAuthChallenge`. New-password, account confirmation, MFA enrollment,
password recovery, federated sign-in, custom challenges, and email MFA are not
implemented here. They fail closed and require an external setup/recovery process.

For a deployed workload, set `NOVAMIND_AWS_MODE=task-role`, remove both AWS profile
selectors and static key variables, and use the existing container-role credential
boundary for Bedrock. Recognized deployment environment markers reject local mode.
Local approved AWS operations continue to use only profile `novamind` in `us-east-1`.
Public Cognito user APIs use an unsigned SDK client and user credentials/tokens;
they do not authorize using IAM keys. The endpoint is fixed HTTPS with bounded
timeouts and no automatic retries. See AWS's [GetUser authorization contract](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_GetUser.html).

## Local development

For the explicitly local demo, set both modes and bind to loopback:

```powershell
$env:NOVAMIND_AWS_MODE = 'local'
$env:NOVAMIND_AUTH_MODE = 'demo'
.\.venv\Scripts\python.exe -m streamlit run mod_chatbot_frontend.py --server.address 127.0.0.1
```

Log in with `demo / demo1234`. Demo credentials appear only in demo mode. A valid
demo session is still required at service and data boundaries. Do not expose this
mode publicly. Starting the UI and signing in to demo does not call AWS; sending
chat, summaries, and live diagnostics does. Such operations still require approval.

The standalone diagnostic remains offline by default. For previously approved
local inference diagnostics, the existing two live flags plus explicit demo mode
create a local diagnostic identity. Programmatic Cognito diagnostics must pass an
authenticated `auth_session` to `run_live_checks`; the CLI does not accept tokens
or passwords as command-line arguments. No diagnostic command was run for Task 3A.

## Security and session behavior

- Access-token decoding is a strict **rejection filter**, not signature proof.
  `GetUser` must accept the exact token before login or online authorization can
  succeed. Wrong issuer, app client, token use, algorithm, scope, subject, username,
  expiration, or timestamps are rejected. Returned Cognito identity must match.
  Signature validation and revocation enforcement are delegated to Cognito.
- The page gate, upload callback, and each Bedrock invocation (including fallback)
  verify online. Other data boundaries check the established session, current
  configuration, ownership, and expiration locally to avoid duplicate API calls.
  No positive verification cache crosses reruns. A visible-page watchdog checks
  every 30 seconds without refreshing idle time.
- The `logged_in` Boolean and display name are compatibility fields, never proof
  of identity. Session data is bound to the verified subject. Login clears prior
  history, uploads, usage, widget state, and cached clients before establishing a
  new identity. Account switches and owner/configuration mismatches clear data.
- Access tokens live only in server-side session memory and are excluded from
  object representations. Password/MFA widgets are cleared in submission callbacks.
  ID/refresh tokens are discarded; sessions do not refresh silently. Session
  duration is bounded by access-token expiry and the configured absolute/idle
  limits. Local expiration is also enforced while consuming a Bedrock stream.
- Logout clears and invalidates the local session first, closes the cached client,
  and requests Cognito `GlobalSignOut`. This signs out the Cognito user across
  devices, not just this tab. A failed remote sign-out is reported without exposing
  SDK details; local access stays closed. See [GlobalSignOut semantics](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_GlobalSignOut.html).
- Private thumbnails are inline PNG data instead of separately served media URLs.
  Transcript export is a gated copyable text view instead of a public download URL.
  Text formatting, attachment validation, model fallback, context admission, and
  usage accounting remain the existing Task 1A–2D implementations.

## Offline verification

Run from PowerShell when ready:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\codex-projetc\Chatbot_text_image\scripts\run_offline_tests.ps1"
```

The canonical runner strips AWS/auth environment settings, sets explicit local demo
mode for historical tests, and blocks sockets/SDK operations. The new Cognito tests
override that environment and mock every Cognito response. Existing fixtures now
perform real local demo login rather than setting an authentication Boolean.
The new module contains 32 test methods. Coverage includes invalid tokens, signature rejection by Cognito, expiry/revocation,
MFA, session ownership, logout failure, cached service denial, fallback denial,
midstream expiry, protected data, and real Streamlit login/logout/export widgets.
Only Python syntax/source inspection was performed during implementation.

## Remaining risks and rollout checks

- Live Cognito behavior and the expanded offline suite are unverified. Account
  ownership, app-client settings, user provisioning and MFA enrollment need an
  approved live acceptance check before production rollout.
- Verification depends on Cognito availability, latency, and API quotas. Failures
  sign users out. Revocation is checked at the next online gate/watchdog; a stream
  already in flight checks local expiry/logout, not remote revocation per token.
- TLS ingress, secure WebSocket/proxy routing, Streamlit XSRF/CORS protections,
  abuse/rate controls and session affinity remain deployment responsibilities.
  Keep SDK debug logging disabled because it can expose authentication requests.
- Already delivered browser content cannot be recalled. Browser suspension may
  delay the watchdog; new protected actions still check expiration. Disconnects,
  restarts and replicas use in-memory sessions; there is no durable user-data store
  or multi-tenant resource authorization in this phase.
- Failed global sign-out can leave other sessions/tokens active until Cognito
  revocation or expiry. Automatic refresh is deliberately absent. MFA/account
  setup and recovery must be supplied outside this UI.

## Files changed for Task 3A

Runtime:

- `services/auth_service.py` (new), `services/bedrock_service.py`
- `novamind/domain/session.py`, `novamind/domain/usage.py`
- `novamind/orchestration/bedrock.py`, `novamind/orchestration/uploads.py`
- `novamind/ui/auth.py`, `novamind/ui/app.py`, `novamind/ui/state.py`
- `novamind/ui/chat.py`, `novamind/ui/sidebar.py`, `novamind/ui/attachments.py`
- `novamind/ui/usage.py`, `novamind/ui/private_media.py` (new)
- `scripts/bedrock_model_access_check.py`

Tests and fixtures:

- `tests/test_3a_cognito_auth.py` (new)
- `tests/offline_support.py`, `tests/frontend_support.py`
- `tests/test_bedrock_service_baseline.py`, `tests/test_1b_document_validation.py`
- `tests/test_1d_model_fallback.py`, `tests/test_1e_stream_integrity.py`
- `tests/test_1j_aws_configuration.py`, `tests/test_2a_modularization.py`
- `tests/test_2c_streamlit_interactions.py`

Documentation:

- `README.md`, `architecture.md`, `deployment.md`, `docs/setup.md`
- `docs/testing.md`, `docs/task_register.md`, `docs/task_3a_cognito_auth.md` (new)

The workspace already contained uncommitted Task 1A–2D files. This list identifies
this task's edits; it is not a claim that every file in `git status` belongs to 3A.
