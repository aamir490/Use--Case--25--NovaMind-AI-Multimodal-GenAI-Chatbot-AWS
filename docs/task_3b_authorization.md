# Task 3B — User authorization and data isolation

Implemented for the current in-memory Streamlit application. Runtime verification
is pending: tests were authored but not run. No AWS calls, installations or
deployments were performed. Work stops after Task 3B.

## Ownership and access boundaries

After successful authentication, the server creates a scope bound to the exact
authentication session and its verified `(mode, issuer, subject)` identity.
Cognito `sub` comes from Task 3A's verified access token and GetUser response.
Display names, `user_id`, `owner_id`, upload file IDs and requested resource IDs
cannot select an owner. Local demo uses its authenticated local identity and a
separate scope for every login, including two tabs using the same demo account.

Conversation and attachment IDs are server-generated. Read/export/delete
selectors must match the current scope; unknown, foreign and stale IDs receive
the same static denial. There is no cross-session ID lookup or shared data cache.
New/Clear rotates the conversation ID; replacement/removal invalidates the old
pending attachment ID. Upload widget keys include the conversation ID to reject
callbacks left over from a previous conversation or login.

The scope registers histories, usage ledger, pending attachments, cached service
and upload state. Ordinary state-field replacement, relabelling or deletion is
rejected rather than adopted as the current user's data. Cached services must
belong to the same authentication session. Invalid session state is cleared;
cleanup does not close a foreign client planted in an ordinary state field.
Snapshot APIs return detached copies. Transcript export uses the guarded scope
and remains inline in the authenticated response, as established by Task 3A.

Uploads, service creation, diagnostics and streaming retain the initiating scope.
They recheck it after slow work and before publishing results. Inference checks
also run after online authentication, during streaming and after stream cleanup.
Stale output cannot be committed or accounted to a newer conversation. UI error
handlers recheck before displaying failed output; stale operations do not erase
a newer valid login or conversation.

## Changed files for Task 3B

This includes changes recovered from the interrupted Task 3B session, rather than
all uncommitted work in the repository.

Runtime:

- `services/authorization.py` (new), `services/auth_service.py`,
  `services/bedrock_service.py`
- `novamind/domain/session.py`
- `novamind/orchestration/uploads.py`, `novamind/orchestration/bedrock.py`
- `novamind/ui/app.py`, `novamind/ui/chat.py`, `novamind/ui/sidebar.py`,
  `novamind/ui/state.py`

Tests and fixtures:

- `tests/test_3b_authorization.py` (new, 27 test methods)
- `tests/frontend_support.py`, `tests/test_1f_usage_accounting.py`,
  `tests/test_1g_upload_lifecycle.py`, `tests/test_2a_modularization.py`,
  `tests/test_3a_cognito_auth.py`

Documentation:

- `docs/task_3b_authorization.md` (new), `docs/task_register.md`, `docs/testing.md`
- `README.md`, `architecture.md`

## User verification

The focused regressions cover verified identity, tampered IDs/owners, foreign
histories/attachments/services, unauthorized reads/writes/deletes/exports,
detached snapshots, same-user separate sessions, demo isolation, expired/logged-out
access, old upload callbacks, delayed parsing/service creation, stale streams,
online-verification and cleanup delays, diagnostic cleanup and stale error output.
AWS boundaries are mocked under the existing offline guards.

Run the full suite from PowerShell to check Tasks 1A–3B together:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\codex-projetc\Chatbot_text_image\scripts\run_offline_tests.ps1"
```

Only AST syntax inspection and `git diff --check` were performed during this
continuation. No test discovery or test execution occurred. The incoming 350/350
user-reported baseline predates Tasks 3A and 3B; it is not a result for this change.

## Remaining limits

- Ownership applies to the current in-memory session. Saved chats, DynamoDB/S3
  policies, shared resources and organization roles remain unimplemented.
- These are application boundaries, not a sandbox against arbitrary Python code
  running inside the server. Trusted code can mutate lists in place and call the
  internal `publish_data` API. Never expose it or raw Bedrock/history helpers as
  browser-controlled endpoints; new endpoints need explicit scope checks.
- The workflow uses Streamlit's session execution model, not database transactions
  or locks for arbitrary concurrent worker threads. Any future background workers
  or persistence need atomic ownership checks at their storage boundary.
- Already delivered content cannot be recalled, and an already submitted model
  invocation may incur usage even when its stale result is discarded. Such usage
  is deliberately not attributed to a newer user's conversation ledger.
- Live Cognito, deployment TLS/rate controls and production infrastructure remain
  unverified. Task 3A's remote-revocation and logout limitations still apply.
