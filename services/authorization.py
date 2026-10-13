"""Authorization for the current in-memory conversation, never a global ID lookup.

Only trusted server code creates scopes and publishes data. Browser IDs are
selectors to compare with that scope, not credentials or ownership declarations.
"""
from copy import deepcopy
from dataclasses import dataclass, field, replace
from uuid import uuid4

from services.auth_service import AuthenticationError, protect_state


class AuthorizationError(AuthenticationError):
    """Use one static error for missing, foreign and stale resources."""


PRIVATE_FIELDS = frozenset({
    "chat_history", "bedrock_history", "usage_ledger", "pending_image",
    "pending_document", "bedrock_service", "upload_generation", "upload_identity",
    "upload_error", "attachment_id", "aws_status",
    "persistence_version", "ai_metrics",
})


@dataclass(frozen=True, repr=False)
class DataScope:
    session: object
    principal: tuple
    conversation_id: str = field(default_factory=lambda: uuid4().hex)
    values: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True, repr=False)
class AttachmentSelection:
    scope: DataScope
    image: object
    document: object


def capture_attachments(state):
    scope = capture_scope(state)
    return AttachmentSelection(scope, state.get("pending_image"), state.get("pending_document"))


def _principal(session):
    return (session.config.mode, session.config.issuer, session.subject)


def establish_scope(state, session):
    """Called only after successful login verification; no client owner argument."""
    scope = DataScope(session, _principal(session))
    session._data_scope = scope
    state["conversation_id"] = scope.conversation_id


def validate_scope(state, session):
    scope = session._data_scope
    if (not isinstance(scope, DataScope) or scope.session is not session
            or scope.principal != _principal(session)
            or state.get("conversation_id") != scope.conversation_id):
        raise AuthorizationError("This resource is not available to this session.")
    # A relabelled/transplanted list, attachment or service is not adopted into
    # this scope. Missing registered fields are unauthorized deletions as well.
    for key in PRIVATE_FIELDS:
        if (key in state) != (key in scope.values):
            raise AuthorizationError("This resource is not available to this session.")
        if key in state and state[key] is not scope.values[key]:
            raise AuthorizationError("This resource is not available to this session.")
    service = scope.values.get("bedrock_service")
    if service is not None and getattr(service, "_auth_session", None) is not session:
        raise AuthorizationError("This resource is not available to this session.")
    return scope


def capture_scope(state, conversation_id=None):
    session = protect_state(state)
    scope = session._data_scope
    if conversation_id is not None and (not isinstance(conversation_id, str) or conversation_id != scope.conversation_id):
        raise AuthorizationError("This resource is not available to this session.")
    return scope


def check_scope(state, expected):
    """Recheck after slow work; same user in a new login/chat is still stale."""
    current = capture_scope(state)
    if current is not expected:
        raise AuthorizationError("This resource is not available to this session.")
    return current


def publish_data(state, *, expected=None, **values):
    """Internal server write boundary, not a browser-supplied update endpoint.

    Inputs are freshly constructed/validated by application code. No caller may
    choose the owner or register data under another conversation ID.
    """
    scope = capture_scope(state) if expected is None else check_scope(state, expected)
    if not values.keys() <= PRIVATE_FIELDS:
        raise ValueError("Unsupported private data field")
    service = values.get("bedrock_service")
    if service is not None and getattr(service, "_auth_session", None) is not scope.session:
        raise AuthorizationError("This resource is not available to this session.")
    scope.values.update(values)
    for key, value in values.items():
        state[key] = value


def rotate_conversation(state):
    scope = capture_scope(state)
    fresh = replace(scope, conversation_id=uuid4().hex, values=dict(scope.values))
    fresh.values.pop("_turn_active", None)
    scope.session._data_scope = fresh
    state["conversation_id"] = fresh.conversation_id


def restore_conversation(state, expected, conversation_id, **values):
    """Adopt a record only after a verified, owner-scoped database read."""
    check_scope(state, expected)
    if (not isinstance(conversation_id, str) or len(conversation_id) != 32
            or any(c not in "0123456789abcdef" for c in conversation_id)
            or not values.keys() <= PRIVATE_FIELDS):
        raise AuthorizationError("This resource is not available to this session.")
    fresh_values = dict(expected.values)
    fresh_values.pop("_turn_active", None)
    fresh_values.update(values)
    fresh = replace(expected, conversation_id=conversation_id, values=fresh_values)
    expected.session._data_scope = fresh
    state["conversation_id"] = conversation_id
    for key, value in values.items():
        state[key] = value


def conversation_snapshot(state, conversation_id=None):
    scope = capture_scope(state, conversation_id)
    # No live mutable lists escape a read/export API.
    result = deepcopy(scope.values.get("chat_history", []))
    check_scope(state, scope)
    return result


def export_conversation(state, conversation_id=None):
    from utils.validators import export_conversation_as_text
    scope = capture_scope(state, conversation_id)
    result = export_conversation_as_text(conversation_snapshot(state, conversation_id),
                                         bot_name=state.get("bot_name", "NovaMind"))
    check_scope(state, scope)
    return result


def attachment_snapshot(state, attachment_id):
    scope = capture_scope(state)
    if not isinstance(attachment_id, str) or not attachment_id or attachment_id != scope.values.get("attachment_id"):
        raise AuthorizationError("This resource is not available to this session.")
    result = deepcopy(scope.values.get("pending_image") or scope.values.get("pending_document"))
    if result is None:
        raise AuthorizationError("This resource is not available to this session.")
    check_scope(state, scope)
    return result
