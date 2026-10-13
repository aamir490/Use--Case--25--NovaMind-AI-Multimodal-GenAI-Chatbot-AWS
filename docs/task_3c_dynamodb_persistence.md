# Task 3C — DynamoDB conversation persistence

Set `NOVAMIND_DYNAMODB_TABLE` to an existing DynamoDB table with string partition key
`owner_key` and string sort key `conversation_id` in `us-east-1`. The authenticated
sidebar then offers Save, Browse, and Load. Cognito sign-in is required; the demo
mode cannot persist conversations. The application uses its existing `novamind`
local profile or deployment task role. Grant that identity `dynamodb:PutItem`,
`dynamodb:GetItem`, and `dynamodb:Query` on the table. No table is created by the app.

The owner key is a SHA-256 digest of verified authentication mode, Cognito issuer,
and subject. Browser-supplied identity is never used. Every read is scoped to that
partition and strongly consistent. Writes use a conditional version check; a
stale save fails with a reload instruction. Retrying the same save after a lost
response returns the existing version without another write.

Snapshots retain at most 40 display messages, 40 usage entries, and 40 model
messages. Each text block is capped at 8,000 characters; the full payload is
limited to 200 KB. Binary attachments, thumbnails, credentials, and tokens are
never stored. Saving is explicit. Only complete text-only turns resume as Bedrock context after load;
prior image/document context is unavailable. Persisted costs retain the project's
configured-rate estimate semantics. Saving is explicit and a clear/new action
does not delete an existing saved record.

Run offline tests in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\codex-projetc\Chatbot_text_image\scripts\run_offline_tests.ps1"
```

The new DynamoDB tests are mocked and have not been run. Live IAM, table schema,
latency, and multi-session behavior remain unverified.
