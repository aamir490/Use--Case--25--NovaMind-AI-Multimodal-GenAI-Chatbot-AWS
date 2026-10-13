"""domain / usage responsibilities extracted from the Streamlit launcher."""
from services.auth_service import protect_state
from decimal import Decimal
from datetime import datetime


def _record_usage(state, records, status: str, operation: str) -> None:
    """Append one request once, with immutable invocation/pricing snapshots."""
    protect_state(state)
    state.usage_ledger.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "operation": operation, "status": status, "attempts": tuple(records),
    })
    state.total_input_tokens += sum(r.input_tokens or 0 for r in records)
    state.total_output_tokens += sum(r.output_tokens or 0 for r in records)


def _usage_totals(state) -> dict:
    protect_state(state)
    ledger = state.usage_ledger
    records = [r for request in ledger for r in request["attempts"]]
    missing_attempts = sum(not request["attempts"] for request in ledger)
    return {
        "known_cost": sum((r.cost_usd for r in records if r.cost_usd is not None), Decimal(0)),
        "unknown_cost": missing_attempts + sum(r.cost_usd is None for r in records),
        "unknown_usage": missing_attempts + sum(
            r.input_tokens is None or r.output_tokens is None for r in records),
    }


def _session_cost(state) -> Decimal | None:
    """Unknown if any invocation lacks usage or applicable pricing."""
    protect_state(state)
    totals = _usage_totals(state)
    return None if totals["unknown_cost"] else totals["known_cost"]
