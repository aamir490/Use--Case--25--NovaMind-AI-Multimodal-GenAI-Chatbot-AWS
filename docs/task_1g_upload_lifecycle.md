# Task 1G: upload lifecycle and input validation

The frontend owns one pending attachment and a generation-keyed Streamlit
uploader. It never assigns a value to an instantiated file-uploader widget.

- Upload/replacement: clear the previous pending attachment before reading or
  validating the new selection. A validation/read failure leaves no attachment
  pending and keeps an error visible on subsequent reruns.
- Rerun: cache validation by Streamlit's upload ID. Recreated UploadedFile
  objects and changed read cursors do not cause repeated decoding or document
  naming. File-like callers without IDs use a filename/content fingerprint.
- Native uploader remove: synchronize an empty widget value to empty pending
  state, including clearing the old error.
- Remove button, send, clear, and new chat: clear pending state and rotate the
  uploader key. The next rerun renders an empty uploader. Retired-widget
  callbacks are ignored.
- Send: snapshot the attachment locally, then consume the selection before
  rendering or invoking Bedrock. A failed or interrupted send cannot silently
  reattach it. Users can explicitly upload again to retry.
- Blank input: sanitize first; reject an empty result without invoking Bedrock,
  adding history/usage, consuming the attachment, or hiding the warning behind
  an immediate rerun. File-only submissions require a nonblank prompt.

Successfully sent attachments remain in completed conversation history for
follow-up questions. Removing a pending upload does not redact older messages.
New chat clears that history through the existing clear-conversation path.

Image/document validation rules, neutral document API names, and Bedrock
payload construction are unchanged. The uploader's image-size help text now
matches the existing 3.75 MB validator limit.

Validation is offline: real file validators and service payload construction,
fake Bedrock streams, and a keyed Streamlit widget simulation. This does not
replace a browser smoke test of file selection, replacement, remove, and send.
No AWS calls, deployments, or package installations are needed by these tests.
