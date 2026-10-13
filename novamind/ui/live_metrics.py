"""Compact user-facing measurements for the latest request in this session."""
from decimal import Decimal
import html

from services.auth_service import protect_state


def _value(value, suffix="", digits=1):
    if value is None:
        return "Unavailable"
    if isinstance(value, Decimal):
        return f"${value:.8f} estimate"
    return f"{value:.{digits}f}{suffix}"


def _markup(metrics, session_cost):
    provider = html.escape(str(metrics.get("provider") or "Unavailable"))
    model = html.escape(str(metrics.get("model") or "Unavailable"))
    status = html.escape(str(metrics.get("status") or "idle"))
    speed = metrics.get("tokens_per_second")
    request_cost = metrics.get("cost_usd")
    session_text = "Unavailable" if session_cost is None else f"${session_cost:.8f} estimate"
    cells = (
        ("Provider / model", f"{provider} · {model}"),
        ("Request", status.title()),
        ("Total latency", _value(metrics.get("latency_ms"), " ms")),
        ("First token", _value(metrics.get("time_to_first_token_ms"), " ms")),
        ("Tokens in / out", f"{_value(metrics.get('input_tokens'), digits=0)} / {_value(metrics.get('output_tokens'), digits=0)}"),
        ("Generation speed", _value(speed, " tokens/s")),
        ("Request cost", _value(request_cost)),
        ("Session cost", session_text),
    )
    entries = "".join(
        f'<div class="nm-metric"><span>{html.escape(label)}</span><strong>{value}</strong></div>'
        for label, value in cells)
    return ('<section class="nm-live-metrics" aria-label="Live AI metrics">'
            '<div class="nm-metrics-heading"><strong>Live AI metrics</strong>'
            '<span>Current session · costs are estimates</span></div>'
            f'<div class="nm-metrics-grid">{entries}</div></section>')


def render_live_metrics(state):
    protect_state(state)
    from novamind.config.settings import MODEL_OPTIONS, MODEL_PROVIDERS
    model_id = MODEL_OPTIONS.get(state.selected_model_label, "Unavailable")
    metrics = state.ai_metrics or {
        "provider": ("Groq Cloud" if MODEL_PROVIDERS.get(model_id) == "groq" else "Amazon Bedrock"),
        "model": model_id, "status": "idle",
        "latency_ms": None, "time_to_first_token_ms": None,
        "input_tokens": None, "output_tokens": None,
        "tokens_per_second": None, "cost_usd": None,
    }
    from novamind.domain import usage
    session_cost = usage._session_cost(state) if state.usage_ledger else None
    return _markup(metrics, session_cost)
