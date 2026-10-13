"""Bounded recent complete turns; no generated summaries or shared user cache."""
from functools import wraps

from services.authorization import capture_scope
from services.request_limits import RequestLimitError, validate_request

MAX_CONTEXT_MESSAGES = 40
MAX_DISPLAY_MESSAGES = 200
TRIMMABLE = {"RequestContextBudget", "RequestPayloadBudget", "RequestAttachmentCount",
             "RequestMessageBudget"}


def complete_pairs(history):
    return (isinstance(history, list) and len(history) % 2 == 0 and
            all(isinstance(turn, dict) and turn.get("role") ==
                ("user" if index % 2 == 0 else "assistant")
                for index, turn in enumerate(history)))


def request_history(service, history, content):
    """Choose a suffix for this request; caller commits it only on success.

    Capability, settings and malformed-content failures are never trimmed away.
    All routes share the same suffix and reserve their configured output budget.
    """
    if not complete_pairs(history):
        return list(history)  # Existing admission remains authoritative.
    candidates = service._build_candidate_list()
    # Validate each pair alone first so trimming cannot hide invalid old content.
    for index in range(0, len(history), 2):
        for model in candidates:
            try:
                validate_request(model, service.system_prompt, service.max_tokens,
                                 service.temperature, history[index:index + 2] +
                                 [{"role": "user", "content": content}])
            except RequestLimitError as exc:
                if exc.code not in TRIMMABLE:
                    raise
    retained = list(history[-(MAX_CONTEXT_MESSAGES - 2):])
    while True:
        try:
            for model in candidates:
                validate_request(model, service.system_prompt, service.max_tokens,
                                 service.temperature, retained +
                                 [{"role": "user", "content": content}])
            return retained
        except RequestLimitError as exc:
            if exc.code not in TRIMMABLE or not retained:
                raise
            retained = retained[2:]


def single_turn(handler):
    """Reject reentrant submissions in this scope, including identical text.

    Repeating a question after completion is intentional and remains supported.
    Scope rotation makes a switched conversation independent of an old request.
    """
    @wraps(handler)
    def guarded(*args, **kwargs):
        st = handler.__globals__.get("st")
        if st is None:
            import streamlit as st
        scope = capture_scope(st.session_state)
        if scope.values.get("_turn_active"):
            return False
        scope.values["_turn_active"] = True
        try:
            return handler(*args, **kwargs)
        finally:
            scope.values.pop("_turn_active", None)
    return guarded
