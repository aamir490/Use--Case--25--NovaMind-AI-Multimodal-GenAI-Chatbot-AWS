# Task 2A: Streamlit modularization

The launcher remains `streamlit run mod_chatbot_frontend.py`. It delegates to
`novamind.ui.app.main`. Importing the launcher no longer renders a page;
`main()` applies page configuration on every Streamlit rerun.

## Function ownership

- `novamind/config/settings.py`: model choices, languages, prompt templates,
  existing demo authentication configuration, and the project asset root.
- `novamind/domain/session.py`: initialization, uploader generation/key/reset,
  and conversation clearing. Functions receive session state explicitly.
- `novamind/domain/usage.py`: request ledger updates and cost aggregation,
  also receiving state explicitly.
- `novamind/orchestration/bedrock.py`: service reuse, settings, retained-context
  checks, and explicitly requested live connection diagnostics.
- `novamind/orchestration/uploads.py`: upload identity, validation, and stale
  widget callback rejection, without Streamlit imports.
- `novamind/ui/state.py`: thin adapters passing the current Streamlit session
  into domain and orchestration functions.
- `novamind/ui/styles.py`: CSS and logo loading, using the original project root.
- `novamind/ui/auth.py`: existing demo login screen and authentication gate.
- `novamind/ui/sidebar.py`: model/settings controls and conversation actions.
- `novamind/ui/attachments.py`: uploader and pending-attachment previews.
- `novamind/ui/usage.py`: usage display and request details.
- `novamind/ui/chat.py`: chat rendering, streaming display, send/summary UI
  handlers, and welcome content.
- `novamind/ui/app.py`: page configuration and application flow.

Existing `services/` and `utils/` interfaces are unchanged. Session-state keys,
widget keys, upload generations, model routing, history commit rules, usage
accounting, and explicit live-check behavior are preserved. No session state is
stored in module-level variables. Demo authentication remains demo-only.

## Offline verification

Existing frontend tests use `tests/frontend_support.py` to import fresh modules
with mocked Streamlit and patch their actual dependency owners. Source checks
read the extracted package rather than the compatibility launcher. The new
`tests/test_2a_modularization.py` covers launcher behavior, page setup on rerun,
layer boundaries, session isolation, cached services, assets, and main dispatch.

Tests were intentionally not run for Task 2A. Only static syntax/name checks
were performed. The baseline reported before this refactor was 332 tests.

Run from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\codex-projetc\Chatbot_text_image\scripts\run_offline_tests.ps1"
```

The runner uses the existing `.venv`, isolates configuration in its Python
process, blocks AWS client creation/credential resolution and socket access in
the test process, and returns a nonzero exit code on failure. Parser workers
remain the existing local subprocesses. No packages are installed. Browser
smoke testing of login, upload/remove, chat, summary, and new chat remains useful
after the offline suite passes.
