"""Bounded saved-chat pages owned by the authenticated server scope."""
from services.authorization import capture_scope

MAX_SAVED_ROWS = 100


def saved_page(state):
    return capture_scope(state).values.get("_saved_navigation", {"items": [], "next_key": None})


def set_saved_page(state, page, *, append=False):
    scope = capture_scope(state)
    rows = saved_page(state)["items"] if append else []
    # DynamoDB pages can overlap during updates. Keep one row per conversation.
    unique = {row["conversation_id"]: dict(row) for row in rows + page["items"]}
    items = list(unique.values())[:MAX_SAVED_ROWS]
    scope.values["_saved_navigation"] = {
        "items": items, "next_key": page.get("next_key") if len(items) < MAX_SAVED_ROWS else None}
