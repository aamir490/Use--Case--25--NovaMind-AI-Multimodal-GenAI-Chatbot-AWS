"""Owner-scoped DynamoDB snapshots; no client IDs are trusted as owners."""
import hashlib
import json
import os
import re
from dataclasses import asdict
from decimal import Decimal

from botocore.exceptions import BotoCoreError, ClientError

from novamind.config.settings import MODEL_OPTIONS, LANGUAGE_OPTIONS, PROMPT_TEMPLATES
from services.aws_config import bedrock_options
from services.conversation_memory import complete_pairs, MAX_CONTEXT_MESSAGES
from services.auth_service import require_session
from services.authorization import (
    AuthorizationError, capture_scope, check_scope, publish_data, restore_conversation,
)
from services.aws_config import create_aws_client
from services.usage_accounting import UsageRecord
from services import attachment_store
from services.aws_retries import retry_read

MAX_MESSAGES = 40
MAX_TEXT = 8000
MAX_PAYLOAD_BYTES = 200_000
DENIED = "This resource is not available to this session."


def readable_title(text, fallback="New conversation"):
    text = " ".join("".join(c for c in str(text) if c.isprintable() or c.isspace()).split())
    return (text[:77] + "…" if len(text) > 80 else text) or fallback


def conversation_title(state):
    capture_scope(state)
    for message in state.chat_history:
        if message.get("role") == "user":
            return readable_title(message.get("text", ""),
                                  readable_title(message.get("file_name", "")))
    return "New conversation"


def _signature(state):
    values = [state.chat_history, state.bedrock_history,
              {key: state.get(key) for key in ("selected_model_label", "system_prompt",
               "temperature", "max_tokens", "selected_language", "selected_template")}]
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=lambda value:
        hashlib.sha256(value).hexdigest() if isinstance(value, bytes) else str(value)
    ).encode("utf-8")).hexdigest()


def has_unsaved_changes(state):
    scope = capture_scope(state)
    if state.pending_image is not None or state.pending_document is not None:
        return True
    saved = scope.values.get("_saved_signature")
    return (_signature(state) != saved if saved is not None else
            bool(state.chat_history or state.bedrock_history))


class PersistenceError(Exception):
    """Safe user-facing failure without SDK response details."""


class VersionConflict(PersistenceError):
    pass


def enabled():
    return bool(os.environ.get("NOVAMIND_DYNAMODB_TABLE"))


def _table():
    name = os.environ.get("NOVAMIND_DYNAMODB_TABLE", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,255}", name):
        raise PersistenceError("Configure a valid NOVAMIND_DYNAMODB_TABLE name.")
    return name


def _identity(state):
    session = require_session(state, online=True)
    if session.config.mode != "cognito":
        raise PersistenceError("Saved conversations require Cognito sign-in.")
    scope = capture_scope(state)
    principal = json.dumps(scope.principal, separators=(",", ":"))
    return scope, hashlib.sha256(principal.encode("utf-8")).hexdigest()


def _client(client):
    return client if client is not None else create_aws_client("dynamodb")


def _message(message):
    if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
        return None
    result = {"role": message["role"], "text": str(message.get("text", ""))[:MAX_TEXT]}
    for key in ("status", "type", "file_name", "stop_reason", "error_code", "error_message"):
        if isinstance(message.get(key), str):
            result[key] = message[key][:256]
    return result


def _context(history):
    # Only text-only model turns can be resumed without retaining attachment bytes.
    result = []
    messages = history[-MAX_MESSAGES:]
    for index in range(0, len(messages) - 1, 2):
        pair = messages[index:index + 2]
        if [part.get("role") if isinstance(part, dict) else None for part in pair] != ["user", "assistant"]:
            continue
        blocks = [part.get("content") for part in pair]
        if any(not isinstance(content, list) or not content or
               any(not isinstance(block, dict) or set(block) != {"text"} or
                   not isinstance(block["text"], str) for block in content)
               for content in blocks):
            continue
        result.extend({"role": part["role"], "content": [
            {"text": block["text"][:MAX_TEXT]} for block in content]}
            for part, content in zip(pair, blocks))
    return result


def _usage(ledger):
    result = []
    if len(ledger) > MAX_MESSAGES:
        result.append({"timestamp": "", "operation": "older saved usage",
                       "status": "unknown", "attempts": []})
    for entry in ledger[-(MAX_MESSAGES - len(result)):]:
        if not isinstance(entry, dict):
            continue
        attempts = [asdict(record) for record in entry.get("attempts", ())
                    if isinstance(record, UsageRecord)]
        result.append({
            "timestamp": str(entry.get("timestamp", ""))[:40],
            "operation": str(entry.get("operation", ""))[:40],
            "status": str(entry.get("status", ""))[:40],
            "attempts": attempts[:4],
        })
    return result


def _payload(state, attachment_history=None):
    messages = [_message(m) for m in state.chat_history[-MAX_MESSAGES:]]
    messages = [m for m in messages if m is not None]
    payload = {
        "chat_history": messages,
        "bedrock_history": (_context(state.bedrock_history) if attachment_history is None else attachment_history),
        "usage_ledger": _usage(state.usage_ledger),
        "model_label": state.selected_model_label,
        "total_input_tokens": state.total_input_tokens,
        "total_output_tokens": state.total_output_tokens,
        "memory_settings": {key: state[key] for key in (
            "system_prompt", "temperature", "max_tokens", "selected_language", "selected_template")},
    }
    if payload["model_label"] not in MODEL_OPTIONS:
        raise PersistenceError("Select a supported model before saving.")
    encoded = json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise PersistenceError("Conversation is too large to save. Start a new conversation.")
    return encoded


def _get(client, table, owner, conversation_id):
    response = retry_read(lambda: client.get_item(TableName=table, Key={
        "owner_key": {"S": owner}, "conversation_id": {"S": conversation_id},
    }, ConsistentRead=True))
    return response.get("Item")


def save_conversation(state, *, client=None, request_id=None, s3_client=None):
    scope, owner = _identity(state)
    table = _table()
    version = state.persistence_version
    if type(version) is not int or version < 0:
        raise AuthorizationError(DENIED)
    if request_id is not None and (not isinstance(request_id, str) or
            not re.fullmatch(r"[0-9a-f]{32}", request_id)):
        raise PersistenceError("Invalid save request.")
    _payload(state)  # Validate text payload before uploading anything.
    attachment_history = None
    if attachment_store.enabled():
        try:
            attachment_history = attachment_store.freeze(
                state, scope, owner, state.bedrock_history[-MAX_MESSAGES:], client=s3_client)
        except attachment_store.AttachmentError as exc:
            raise PersistenceError(str(exc)) from None
    payload = _payload(state, attachment_history)
    if request_id is None:
        request_id = hashlib.sha256(
            f"{owner}:{scope.conversation_id}:{version}:{payload}".encode("utf-8")
        ).hexdigest()[:32]
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise PersistenceError("Invalid save request.")
    check_scope(state, scope)
    db = _client(client)
    item = {
        "owner_key": {"S": owner}, "conversation_id": {"S": scope.conversation_id},
        "version": {"N": str(version + 1)}, "request_id": {"S": request_id},
        "model_id": {"S": MODEL_OPTIONS[state.selected_model_label]},
        "title": {"S": conversation_title(state)},
        "payload": {"S": payload},
    }
    try:
        conditions = {"ConditionExpression": "attribute_not_exists(owner_key)"} if version == 0 else {
            "ConditionExpression": "#v = :expected AND owner_key = :owner AND attribute_not_exists(deleted)",
            "ExpressionAttributeNames": {"#v": "version"},
            "ExpressionAttributeValues": {
                ":expected": {"N": str(version)}, ":owner": {"S": owner}},
        }
        db.put_item(TableName=table, Item=item, **conditions)
    except (BotoCoreError, ClientError) as exc:
        conditional_conflict = (isinstance(exc, ClientError) and
                                exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException")
        try:
            existing = _get(db, table, owner, scope.conversation_id)
        except (BotoCoreError, ClientError):
            raise PersistenceError("Conversation save failed. Please retry.") from None
        if (existing and "deleted" not in existing and existing.get("request_id", {}).get("S") == request_id
                and existing.get("payload", {}).get("S") == payload):
            saved_version = int(existing["version"]["N"])
            check_scope(state, scope)
            publish_data(state, expected=scope, persistence_version=saved_version)
            scope.values["_saved_signature"] = _signature(state)
            return saved_version
        if conditional_conflict:
            raise VersionConflict("This conversation changed in another session. Reload it before saving.") from None
        raise PersistenceError("Conversation save failed. Please retry.") from None
    check_scope(state, scope)
    publish_data(state, expected=scope, persistence_version=version + 1)
    scope.values["_saved_signature"] = _signature(state)
    return version + 1


def list_conversations(state, *, client=None, start_key=None):
    scope, owner = _identity(state)
    if start_key is not None and (not isinstance(start_key, dict) or
            start_key.get("owner_key", {}).get("S") != owner):
        raise AuthorizationError(DENIED)
    try:
        query = dict(
            TableName=_table(), KeyConditionExpression="owner_key = :owner",
            ExpressionAttributeValues={":owner": {"S": owner}},
            ProjectionExpression="conversation_id, title, model_id, #v, deleted, cleanup_complete",
            ExpressionAttributeNames={"#v": "version"}, Limit=25,
        )
        if start_key is not None:
            query["ExclusiveStartKey"] = start_key
        db = _client(client)
        response = retry_read(lambda: db.query(**query))
    except (BotoCoreError, ClientError):
        raise PersistenceError("Saved conversations could not be listed.") from None
    check_scope(state, scope)
    return {
        "items": [{"conversation_id": item["conversation_id"]["S"],
                   "title": ("Deletion pending — retry delete" if "deleted" in item
                             else readable_title(item.get("title", {}).get("S", ""), "Conversation"))}
                  for item in response.get("Items", [])
                  if not item.get("cleanup_complete", {}).get("BOOL", False)
                  if re.fullmatch(r"[0-9a-f]{32}", item.get("conversation_id", {}).get("S", ""))],
        "next_key": response.get("LastEvaluatedKey"),
    }


def load_conversation(state, conversation_id, *, client=None, s3_client=None):
    scope, owner = _identity(state)
    if not isinstance(conversation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", conversation_id):
        raise AuthorizationError(DENIED)
    try:
        item = _get(_client(client), _table(), owner, conversation_id)
    except (BotoCoreError, ClientError):
        raise PersistenceError("Conversation load failed. Please retry.") from None
    if (not item or "deleted" in item or item.get("owner_key", {}).get("S") != owner or
            item.get("conversation_id", {}).get("S") != conversation_id):
        raise AuthorizationError(DENIED)
    try:
        if len(item["payload"]["S"].encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise ValueError
        data = json.loads(item["payload"]["S"])
        version = int(item["version"]["N"])
        if (version < 1 or data["model_label"] not in MODEL_OPTIONS or
                not isinstance(data["chat_history"], list) or
                not isinstance(data["bedrock_history"], list) or
                not isinstance(data["usage_ledger"], list)):
            raise ValueError
        if len(data["bedrock_history"]) > MAX_CONTEXT_MESSAGES or not complete_pairs(data["bedrock_history"]):
            raise ValueError
        settings = data.get("memory_settings")
        if settings is None:  # Legacy snapshots must not inherit another chat's persona.
            defaults = bedrock_options()
            settings = {"system_prompt": defaults["system_prompt"],
                        "temperature": defaults["temperature"], "max_tokens": defaults["max_tokens"],
                        "selected_language": "English", "selected_template": "🤖 Default Assistant"}
        if (not isinstance(settings, dict) or
                settings.get("selected_language") not in LANGUAGE_OPTIONS or
                settings.get("selected_template") not in PROMPT_TEMPLATES):
            raise ValueError
        bedrock_options(model_id=MODEL_OPTIONS[data["model_label"]],
                        system_prompt=settings["system_prompt"],
                        temperature=settings["temperature"], max_tokens=settings["max_tokens"])
        ledger = []
        for entry in data["usage_ledger"]:
            attempts = []
            for record in entry["attempts"]:
                for key in ("input_rate", "output_rate", "cost_usd"):
                    if record[key] is not None:
                        record[key] = Decimal(record[key])
                attempts.append(UsageRecord(**record))
            ledger.append({**entry, "attempts": tuple(attempts)})
        messages = [_message(m) for m in data["chat_history"][-MAX_MESSAGES:]]
        if any(m is None for m in messages):
            raise ValueError
        if any("attachment" in block.get(kind, {})
               for turn in data["bedrock_history"] for block in turn["content"]
               for kind in ("image", "document")):
            history = attachment_store.thaw(
                state, scope, owner, conversation_id, data["bedrock_history"], client=s3_client)
        else:
            history = _context(data["bedrock_history"])
        input_total = int(data["total_input_tokens"])
        output_total = int(data["total_output_tokens"])
        if min(input_total, output_total) < 0:
            raise ValueError
    except attachment_store.AttachmentError as exc:
        raise PersistenceError(str(exc)) from None
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise PersistenceError("Saved conversation is invalid.") from None
    check_scope(state, scope)
    restore_conversation(
        state, scope, conversation_id, chat_history=messages,
        bedrock_history=history, usage_ledger=ledger, persistence_version=version,
        pending_image=None, pending_document=None, attachment_id=None,
        ai_metrics=None,
        upload_generation=state.upload_generation + 1, upload_identity=None,
        upload_error=None, bedrock_service=None, aws_status=None,
    )
    state.selected_model_label = data["model_label"]
    for key in ("system_prompt", "temperature", "max_tokens", "selected_language", "selected_template"):
        state[key] = settings[key]
    state.total_input_tokens = input_total
    state.total_output_tokens = output_total
    state["_trigger_summary"] = False
    capture_scope(state).values["_saved_signature"] = _signature(state)
    return version


def delete_conversation(state, conversation_id, *, client=None, s3_client=None):
    """Tombstone first; failed S3 cleanup stays retryable and cannot be loaded."""
    scope, owner = _identity(state)
    if not isinstance(conversation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", conversation_id):
        raise AuthorizationError(DENIED)
    db, table = _client(client), _table()
    try:
        item = _get(db, table, owner, conversation_id)
        if (not item or item.get("owner_key", {}).get("S") != owner or
                item.get("conversation_id", {}).get("S") != conversation_id):
            raise AuthorizationError(DENIED)
        check_scope(state, scope)
        db.update_item(TableName=table, Key={"owner_key": {"S": owner},
                       "conversation_id": {"S": conversation_id}},
                       UpdateExpression="SET deleted = :yes",
                       ConditionExpression="#v = :version",
                       ExpressionAttributeNames={"#v": "version"},
                       ExpressionAttributeValues={":yes": {"BOOL": True},
                                                  ":version": item["version"]})
        if attachment_store.enabled():
            attachment_store.cleanup(state, scope, owner, conversation_id, client=s3_client)
        elif '"attachment":' in item.get("payload", {}).get("S", ""):
            raise PersistenceError("Configure attachment storage before retrying deletion.")
        # Keep a minimal tombstone to prevent stale/new writers resurrecting this ID.
        check_scope(state, scope)
        db.update_item(TableName=table, Key={"owner_key": {"S": owner},
                       "conversation_id": {"S": conversation_id}},
                       UpdateExpression="SET cleanup_complete = :yes REMOVE payload, title, model_id, request_id",
                       ConditionExpression="deleted = :yes",
                       ExpressionAttributeValues={":yes": {"BOOL": True}})
    except (BotoCoreError, ClientError, attachment_store.AttachmentError):
        raise PersistenceError("Conversation deletion incomplete. Retry deletion.") from None
