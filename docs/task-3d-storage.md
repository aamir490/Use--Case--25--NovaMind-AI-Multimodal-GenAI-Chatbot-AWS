# Task 3D: private saved attachments

Set NOVAMIND_S3_BUCKET to an existing private bucket in us-east-1 alongside
NOVAMIND_DYNAMODB_TABLE. AWS clients retain the novamind profile / task-role
policy. Storage runs only when explicitly saving a Cognito conversation.
Pending uploads remain session-local until submitted into model history.
Without the bucket setting, Task 3C text-only snapshots continue unchanged.

Server-side Cognito verification derives the owner hash from mode, issuer and
subject. DynamoDB reads select that owner before any S3 retrieval. Keys use
attachments/<owner hash>/<conversation ID>/<SHA256>. No client owner, arbitrary
key, ACL, presigned URL or public media URL is accepted. Uploads request AES256
encryption. Restores bound reads, close bodies, check size/hash/expiry and rerun
file validation before atomically publishing restored model history. Document
names are neutral. Expired or missing files fail the entire restore, preserving
the current conversation. Attachments remain in model history for follow-up
questions; restored thumbnails and pending uploader selections are not recreated.

Limits: existing 3.75 MiB image / 4.5 MiB document validation, 20 MiB aggregate
saved attachment bytes, 40 context messages, and existing 200 KB JSON limit.
References expire after 30 days. Explicit saving renews retention.

Required operator configuration before enabling storage (not provisioned here):

- S3 Block Public Access, bucket-owner-enforced ownership, TLS-only access and
  an IAM policy restricted to this application's bucket/prefix. The application
  role needs GetObject, PutObject, DeleteObject and prefix-limited ListBucket.
- Lifecycle expiration after 30 days for attachments/, including noncurrent
  version expiration and expired delete markers if versioning is enabled.
  S3 lifecycle execution is asynchronous; reference expiry blocks reads first.
- DynamoDB requires GetItem, PutItem, Query and UpdateItem, using the existing
  owner_key / conversation_id schema. Do not TTL-delete deletion tombstones.

Deletion first conditionally tombstones the DynamoDB record, blocking restores
and stale saves, then removes all S3 objects under its owner/conversation prefix.
Only after successful cleanup is the transcript removed. Incomplete deletion
stays visible as 'Deletion pending' so the delete button can retry. A minimal
tombstone prevents resurrection. Clear/New only clears the local session; use
Delete selected saved conversation to delete persisted data.

S3 and DynamoDB have no shared transaction. Content-addressed keys avoid duplicate
objects on retries. Abandoned, superseded or late in-flight uploads are bounded
by the mandatory lifecycle rule; immediate cleanup after process death cannot
be guaranteed. Ambiguous DynamoDB outcomes never trigger unsafe rollback of
potentially committed objects. Versioned buckets need lifecycle cleanup of old
versions. Runtime does not inspect bucket policies/lifecycle, and operators must
verify them before enabling this feature. No AWS resources or calls were made
while implementing this task.

Offline validation (not executed by Codex):

```powershell
python -m tests.run_offline
```
