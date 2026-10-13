"""Minimal JSON event logging with a fixed, non-sensitive field allowlist."""
from datetime import datetime, timezone
import json
import logging
import math
import re
import sys

_logger = logging.getLogger("novamind.events")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not any(getattr(handler, "_novamind_json", False) for handler in _logger.handlers):
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _handler._novamind_json = True
    _logger.addHandler(_handler)

_STATUS = frozenset({"generating", "completed", "failed", "incomplete", "retrying", "warning"})
_CATEGORIES = frozenset({
    "authentication", "authorization", "throttling", "timeout", "network",
    "validation", "stream", "provider", "internal", "cancelled", "metrics",
})


def safe_error_category(code=None, exception_type=None):
    """Collapse provider diagnostics to a small safe category vocabulary."""
    value = str(code or exception_type or "").lower()
    if "throttl" in value or "throughput" in value or "rate limit" in value:
        return "throttling"
    if "timeout" in value or "timedout" in value:
        return "timeout"
    if "connection" in value or "endpoint" in value or "incompleteread" in value:
        return "network"
    if "accessdenied" in value or "unauthorized" in value or "forbidden" in value:
        return "authorization"
    if "validation" in value or "invalid" in value or "malformed" in value:
        return "validation"
    if "stream" in value or "event" in value:
        return "stream"
    if "auth" in value:
        return "authentication"
    return "provider" if value else "internal"


def log_event(*, request_id, event_type, provider, model=None, duration_ms=0,
              status, error_category=None, attempt=None):
    """Emit one JSON line; deliberately accepts no exception or user-content fields."""
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "request_id": request_id if isinstance(request_id, str) and re.fullmatch(r"[0-9a-f-]{32,36}", request_id) else "unknown",
        "event_type": event_type if isinstance(event_type, str) and re.fullmatch(r"[a-z0-9_.-]{1,64}", event_type) else "application.event",
        "provider": provider if isinstance(provider, str) and provider in {"Amazon Bedrock", "Amazon Cognito", "Groq Cloud"} else "unknown",
        "model": model[:128] if isinstance(model, str) else None,
        "duration_ms": round(duration_ms, 2) if isinstance(duration_ms, (int, float)) and math.isfinite(duration_ms) and duration_ms >= 0 else None,
        "status": status if isinstance(status, str) and status in _STATUS else "failed",
        "error_category": error_category if isinstance(error_category, str) and error_category in _CATEGORIES else None,
    }
    if type(attempt) is int and attempt > 0:
        event["attempt"] = attempt
    try:
        _logger.info(json.dumps(event, ensure_ascii=True, separators=(",", ":")))
    except Exception:
        # Logging must never alter authentication, streaming, or persistence behavior.
        pass
