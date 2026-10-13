# Troubleshooting

Use the project's interpreter from `E:\codex-projetc\Chatbot_text_image`.
Start with the offline diagnostic, not a live AWS call:

```powershell
.\.venv\Scripts\python.exe -B scripts/bedrock_model_access_check.py
```

It checks imports/configuration/model policy only. It does not check credentials,
network access or inference entitlement. See [setup](docs/setup.md) for explicit
live flags and exit codes. Never include credentials or full service responses in
support reports.

## Configuration or credential failure

Local mode requires profile `novamind` and region `us-east-1`. Remove conflicting
profile/region selectors from the launching process. Nonempty static credential
environment variables are rejected, including session tokens. Reauthenticate the
named profile through the approved credential process when expired; do not create
new keys or fall back to the default profile as a troubleshooting shortcut.
`.env` is not automatically loaded. Task-role mode rejects profile selectors and
uses container credentials only; ordinary EC2 IMDS credentials are unsupported.

## Access denied, unavailable model or throttling

Check the selected model ID and account-specific IAM/model access through a
separately approved live check. Broad full-access policies are not the default fix.
Only Nova Pro has the narrow, pre-output AccessDenied fallback documented in
[model selection](model_selection.md). Throttling and other failures do not trigger
model substitution. Catalog success does not prove inference permission.

## Missing imports or parser APIs

Use CPython 3.14.6 Windows x64 and the pinned environment from
[dependencies](docs/dependencies.md). Install through the same `.venv` interpreter
when separately performing setup; do not upgrade individual packages ad hoc.
Pillow is mandatory for image validation and pypdf for PDFs. Missing validation
APIs fail closed. DOC/XLS needs optional `requirements-legacy.txt`; its real-file
compatibility remains unverified. DOCX/XLSX does not require that optional package.

## File rejected or context too large

Image ceilings are 3.75 MiB (3,932,160 bytes), 8,000 pixels per side and 16 million
pixels, with additional animation budgets. Document ceiling is 4.5 MiB
(4,718,592 bytes). PDF/Office corruption, decompression limits, memory ceilings or
worker timeout can reject a smaller file. Re-export a known valid file or reduce
its size/complexity locally; renaming the extension is not a repair.

Valid upload does not guarantee a valid full request. Retained files count toward
20 images/5 documents, the 20 MiB serialized payload ceiling and context budget.
Export the transcript if needed, then explicitly start a new chat, reduce the
attachment or lower output reservation. The app does not silently discard history.
Removing a pending attachment does not erase it from previously completed turns.

## Incomplete response or unknown cost

Missing stream termination, generation errors and `max_tokens` stops are unsuccessful
outcomes. Partial output can remain visible but does not enter future AI context.
Increase the output setting only within policy and retry explicitly if appropriate;
no fallback is attempted after output starts. A failed send consumes its pending
attachment, so reattach deliberately when retrying.

Unknown usage/cost is not zero. It can mean absent/inconsistent metadata or unsupported
pricing. Known costs are estimates from project rates, not AWS bills. Model changes
do not reprice historical requests. Diagnostics may incur usage outside the ledger.

## Streamlit and tests

Launch with `.\.venv\Scripts\python.exe -m streamlit run mod_chatbot_frontend.py`,
not by executing the launcher as a plain Python script. If port 8501 is busy, stop
your own running instance or select another port; do not kill unrelated processes.
Unexpected ScriptRunContext warnings need investigation outside test harnesses.
A server restart or lost session can lose history; no saved-chat database exists.

Use [the guarded test runner](docs/testing.md), not bare unittest discovery.
Dependency-baseline failures indicate an interpreter or package mismatch. AppTest
checks widgets/session behavior, not browser visuals or live AWS access. A failure
must be investigated; do not bypass network guards to make tests pass.
