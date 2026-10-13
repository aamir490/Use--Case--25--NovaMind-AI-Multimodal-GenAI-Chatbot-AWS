"""Private, server-mediated attachment snapshots. Never issues public URLs."""
import hashlib
import os
import re
import time

from botocore.exceptions import BotoCoreError, ClientError
from services.aws_config import create_aws_client
from services.authorization import check_scope
from services.aws_retries import retry_read

MAX_TOTAL_BYTES = 20 * 1024 * 1024
RETENTION_SECONDS = 30 * 86400
FORMATS = {"image": {"jpeg", "png", "gif", "webp"},
           "document": {"pdf", "csv", "doc", "docx", "xls", "xlsx", "html", "txt", "md"}}


class AttachmentError(Exception):
    pass


def enabled():
    return bool(os.environ.get("NOVAMIND_S3_BUCKET"))


def _bucket():
    bucket = os.environ.get("NOVAMIND_S3_BUCKET", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise AttachmentError("Configure a valid private NOVAMIND_S3_BUCKET.")
    return bucket


def prefix(owner, conversation_id):
    if not re.fullmatch(r"[0-9a-f]{64}", owner) or not re.fullmatch(r"[0-9a-f]{32}", conversation_id):
        raise AttachmentError("Attachment is unavailable.")
    return f"attachments/{owner}/{conversation_id}/"


def _validate(kind, fmt, raw):
    from utils.validators import validate_file_upload
    from services.image_service import ImageResult
    from services.document_service import DocumentResult
    limit = int((3.75 if kind == "image" else 4.5) * 1024 * 1024)
    if (kind not in FORMATS or fmt not in FORMATS[kind] or
            not isinstance(raw, bytes) or not 0 < len(raw) <= limit):
        raise AttachmentError("Attachment is invalid or too large.")
    result = validate_file_upload(raw, "attachment." + fmt)
    expected = ImageResult if kind == "image" else DocumentResult
    if not isinstance(result, expected) or not result.is_valid:
        raise AttachmentError("Attachment validation failed.")


def _read_object(s3, bucket, key, expected_size):
    def read_once():
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            if response["ContentLength"] != expected_size:
                raise AttachmentError("Saved attachment is invalid.")
            return body.read(expected_size + 1)
        finally:
            body.close()
    return retry_read(read_once)


def freeze(state, scope, owner, history, *, client=None):
    """Upload only on explicit save; immutable content keys make retries safe.

    Lifecycle expiration bounds unreferenced objects after crashes, conflicts,
    and ambiguous DynamoDB responses. Never delete on an ambiguous commit.
    """
    s3 = client
    total = 0
    output = []
    for turn in history:
        content = []
        for block in turn["content"]:
            if set(block) == {"text"}:
                content.append({"text": block["text"][:8000]})
                continue
            kind = next((k for k in FORMATS if set(block) == {k}), None)
            if kind is None or turn["role"] != "user":
                raise AttachmentError("Unsupported saved attachment context.")
            data = block[kind]
            fmt, raw = data.get("format"), data.get("source", {}).get("bytes")
            _validate(kind, fmt, raw)
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise AttachmentError("Saved attachments exceed the conversation size limit.")
            digest = hashlib.sha256(raw).hexdigest()
            key = prefix(owner, scope.conversation_id) + digest
            check_scope(state, scope)
            s3 = s3 if s3 is not None else create_aws_client("s3")
            try:
                s3.put_object(Bucket=_bucket(), Key=key, Body=raw,
                              ContentType="application/octet-stream",
                              ServerSideEncryption="AES256",
                              Metadata={"sha256": digest})
            except (BotoCoreError, ClientError):
                raise AttachmentError("Attachment save failed. Please retry.") from None
            check_scope(state, scope)
            content.append({kind: {"format": fmt, "attachment": {
                "key": key, "sha256": digest, "size": len(raw),
                "expires_at": int(time.time()) + RETENTION_SECONDS}}})
        output.append({"role": turn["role"], "content": content})
    return output


def thaw(state, scope, owner, conversation_id, history, *, client=None):
    s3 = client
    total = 0
    output = []
    for turn in history:
        content = []
        for block in turn["content"]:
            if set(block) == {"text"}:
                content.append({"text": block["text"][:8000]})
                continue
            kind = next((k for k in FORMATS if set(block) == {k}), None)
            if kind is None or turn["role"] != "user":
                raise AttachmentError("Saved attachment is invalid.")
            data = block[kind]
            ref = data["attachment"]
            digest, size = ref["sha256"], ref["size"]
            if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or ref["key"] != prefix(owner, conversation_id) + digest
                    or type(size) is not int or not 0 < size <= int(4.5 * 1024 * 1024)
                    or type(ref["expires_at"]) is not int or ref["expires_at"] <= time.time()):
                raise AttachmentError("Saved attachment is unavailable or expired.")
            total += size
            if total > MAX_TOTAL_BYTES:
                raise AttachmentError("Saved attachments exceed the conversation size limit.")
            check_scope(state, scope)
            s3 = s3 if s3 is not None else create_aws_client("s3")
            try:
                raw = _read_object(s3, _bucket(), ref["key"], size)
            except (BotoCoreError, ClientError):
                raise AttachmentError("Saved attachment is unavailable.") from None
            check_scope(state, scope)
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
                raise AttachmentError("Saved attachment is invalid.")
            _validate(kind, data["format"], raw)
            restored = {"format": data["format"], "source": {"bytes": raw}}
            if kind == "document":
                restored["name"] = "Attachment"
            content.append({kind: restored})
        output.append({"role": turn["role"], "content": content})
    return output


def cleanup(state, scope, owner, conversation_id, *, client=None):
    s3 = client if client is not None else create_aws_client("s3")
    folder = prefix(owner, conversation_id)
    try:
        # Re-list from the start after each batch; no continuation skips deletes.
        while True:
            check_scope(state, scope)
            page = retry_read(lambda: s3.list_objects_v2(
                Bucket=_bucket(), Prefix=folder, MaxKeys=1000))
            objects = page.get("Contents", [])
            if not objects:
                break
            for obj in objects:
                if not obj["Key"].startswith(folder):
                    raise AttachmentError("Attachment cleanup failed.")
                check_scope(state, scope)
                s3.delete_object(Bucket=_bucket(), Key=obj["Key"])
    except (BotoCoreError, ClientError):
        raise AttachmentError("Attachment cleanup failed. Retry deletion.") from None
