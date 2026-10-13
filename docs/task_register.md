# Task register — Tasks 1A–3B

As of Task 3B, this register covers **16 tasks**. Tasks 1A–2C are implemented
with source/test evidence below. The latest **350/350 passing offline tests**
is user-reported after Task 2C; no suite was executed during this documentation
review. Source inspection is not an independent test pass or live AWS verification.
Task 2D is documentation-complete, awaiting user review.

Historical user-reported aggregate baselines: after 1D 153; 1E 196; 1F 228;
1G 256; 1H 284; 1I 307; 1J 332; 2A 340; 2B 347; 2C 350.
Task 2C removed ten nested suite wrappers and added thirteen tests; the totals
are discovery counts, not evidence of additional independent coverage from nested runs.

## Implemented tasks and evidence

- **1A — HTML escaping: implemented.** Escapes user-controlled values in custom HTML. Source: [novamind/ui/](../novamind/ui/); regression evidence: [test_1a_html_escaping.py](../tests/test_1a_html_escaping.py).
- **1B — Document names: implemented.** Neutral API names are separate from display names. Source: [services/document_service.py](../services/document_service.py); regression evidence: [test_1b_document_validation.py](../tests/test_1b_document_validation.py).
- **1C — File validation: implemented.** Image size/dimension/decode checks and upload routing. Source: [services/image_service.py](../services/image_service.py); regression evidence: [test_1c_file_validation.py](../tests/test_1c_file_validation.py).
- **1D — Model fallback: implemented.** Only Nova Pro has the approved single fallback candidate. Source: [services/bedrock_service.py](../services/bedrock_service.py); regression evidence: [test_1d_model_fallback.py](../tests/test_1d_model_fallback.py).
- **1E — Streaming integrity: implemented.** Completed/failed/incomplete outcomes, stream cleanup and safe model history. Source: [services/bedrock_service.py](../services/bedrock_service.py); regression evidence: [test_1e_stream_integrity.py](../tests/test_1e_stream_integrity.py).
- **1F — Usage accounting: implemented.** Metadata-based per-attempt tokens and frozen configured-rate estimates. Source: [services/usage_accounting.py](../services/usage_accounting.py); regression evidence: [test_1f_usage_accounting.py](../tests/test_1f_usage_accounting.py).
- **1G — Upload lifecycle: implemented.** Replace/remove/send/new-chat resets and rerun validation caching. Source: [novamind/orchestration/uploads.py](../novamind/orchestration/uploads.py); regression evidence: [test_1g_upload_lifecycle.py](../tests/test_1g_upload_lifecycle.py).
- **1H — Parser resources: implemented.** Fail-closed dependencies, bounded PDF/Office workers and image budgets. Source: [services/document_parser.py](../services/document_parser.py); regression evidence: [test_1h_parser_limits.py](../tests/test_1h_parser_limits.py).
- **1I — Request limits: implemented.** Full-history context/payload/count/output admission checks. Source: [services/request_limits.py](../services/request_limits.py); regression evidence: [test_1i_request_limits.py](../tests/test_1i_request_limits.py).
- **1J — AWS configuration: implemented.** Pinned local profile/region, container-role mode and explicit live diagnostics. Source: [services/aws_config.py](../services/aws_config.py); regression evidence: [test_1j_aws_configuration.py](../tests/test_1j_aws_configuration.py).
- **2A — Streamlit modularization: implemented.** UI/config/domain/orchestration split with compatible launcher. Source: [novamind/](../novamind/); regression evidence: [test_2a_modularization.py](../tests/test_2a_modularization.py).
- **2B — Python and dependencies: implemented.** Windows x64 CPython 3.14.6 baseline; exact dependency pins. Source: [requirements.txt](../requirements.txt); regression evidence: [test_2b_dependencies.py](../tests/test_2b_dependencies.py).
- **2C — Testing foundation: implemented.** Single discovery, shared offline guards and stronger assertions; also test_2c_streamlit_interactions.py for real widgets. Source: [tests/run_offline.py](../tests/run_offline.py); regression evidence: [test_2c_testing_foundation.py](../tests/test_2c_testing_foundation.py).
- **2D — Documentation/task tracking: documentation complete; user review pending.**
  Evidence: [README](../README.md), [setup](setup.md), [architecture](../architecture.md),
  [deployment](../deployment.md), [troubleshooting](../troubleshooting.md),
  [model selection](../model_selection.md), and this register. No application code
  changes or test execution. Verification is local document/source/link inspection.

## Task 3A — implemented, user verification pending

Cognito login, SMS/TOTP MFA, authoritative access-token checks, logout, session
timeouts/ownership, and guarded Bedrock/data boundaries are implemented. Demo
authentication requires explicit local opt-in and a logged-in session. New mocked
AWS and Streamlit tests are authored but **not run**; 350/350 remains the incoming
user-reported baseline. No AWS operations, provisioning, installations or pushes.
See [Task 3A details and changed files](task_3a_cognito_auth.md).

## Task 3B — implemented, user verification pending

Verified-session ownership now protects conversation, attachment, service and
export access. Server-generated resource IDs, detached snapshots and stale-work
checks prevent foreign or retired resources from being adopted by the current
session. Local demo sessions remain isolated. The 27 new regression test methods
and adapted existing fixtures have **not been run**. Syntax and whitespace checks
passed; no AWS calls, installations or deployments occurred.
See [Task 3B details and changed files](task_3b_authorization.md). Stop after Task 3B.

## Qualification and remaining work

- 1F costs use unverified project pricing; metadata absence remains unknown.
- 1H/2B optional legacy Office support and clean dependency installation are not
  validated by this review; the Linux deployment target requires separate work.
- 1J task-role mode excludes EC2 IMDS. No AWS access or deployment is established
  by passing offline tests.
- 2C guards are process-local, not a hard egress sandbox. AppTest does not cover
  browser layout, real login security or live model behavior.
- Production identity integration is implemented in Task 3A but not live-verified.
  Durable history, deployment infrastructure, structured observability and optional
  RAG remain proposals in [architecture](../architecture.md).
  This register does not authorize or assign completion status to those future tasks.

Acceptance checks for 2D: current credential policy, exact byte limits, narrow
fallback, supported Python target, current module paths, explicit diagnostic flags,
and current/proposed separation are documented. User verification command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\codex-projetc\Chatbot_text_image\scripts\run_offline_tests.ps1"
```
