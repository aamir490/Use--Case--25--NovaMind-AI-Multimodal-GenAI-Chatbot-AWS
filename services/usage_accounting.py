"""Offline usage snapshots. Configured-rate costs are estimates, not AWS bills."""

from dataclasses import dataclass
from decimal import Decimal


# Existing project rates, USD per 1,000 tokens. Not independently verified.
# Scope is deliberately explicit; unknown models/regions never inherit a rate.
PRICING_SOURCE = "Project configured rates (unverified), USD per 1,000 tokens"
MODEL_PRICING = {
    ("us-east-1", "amazon.nova-pro-v1:0"): ("0.0008", "0.0032"),
    ("us-east-1", "us.amazon.nova-pro-v1:0"): ("0.0008", "0.0032"),
    ("us-east-1", "amazon.nova-lite-v1:0"): ("0.00006", "0.00024"),
    ("us-east-1", "anthropic.claude-3-5-sonnet-20241022-v2:0"): ("0.003", "0.015"),
}


@dataclass(frozen=True)
class UsageRecord:
    """One invocation attempt, frozen at completion (including failures)."""

    request_id: str
    attempt: int
    operation: str
    model_id: str
    region: str
    status: str
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    input_rate: Decimal | None
    output_rate: Decimal | None
    cost_usd: Decimal | None
    cost_status: str
    pricing_source: str | None
    unknown_reason: str | None


def token_count(usage: dict, key: str) -> int | None:
    value = usage.get(key)
    return value if type(value) is int and value >= 0 else None


def make_usage_record(*, request_id, attempt, operation, model_id, region,
                      status, stop_reason, metadata, rates) -> UsageRecord:
    metadata = metadata if isinstance(metadata, dict) else {}
    usage = metadata.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    inp = token_count(usage, "inputTokens")
    out = token_count(usage, "outputTokens")
    total = token_count(usage, "totalTokens")
    performance = metadata.get("performanceConfig", {})
    tier = metadata.get("serviceTier", {})
    reason = None
    if inp is None or out is None:
        reason = "Missing or invalid usage metadata"
    elif "totalTokens" in usage and (total is None or total != inp + out):
        reason = "Inconsistent usage metadata"
    elif any(usage.get(k, 0) != 0 for k in ("cacheReadInputTokens", "cacheWriteInputTokens")) or usage.get("cacheDetails"):
        reason = "Cache pricing is not configured"
    elif (not isinstance(performance, dict) or not isinstance(tier, dict)
          or performance.get("latency", "standard") != "standard"
          or tier.get("type", "default") != "default"):
        reason = "Nonstandard inference pricing is not configured"
    if rates is None:
        reason = reason or "Pricing unavailable for invoked model and region"
    input_rate = output_rate = None
    if rates is not None:
        try:
            input_rate, output_rate = (Decimal(str(value)) for value in rates)
            if not all(value.is_finite() and value >= 0 for value in (input_rate, output_rate)):
                raise ValueError("Invalid rate")
        except (ValueError, ArithmeticError, TypeError):
            input_rate = output_rate = None
            reason = reason or "Invalid configured pricing"
    cost = None if reason else (inp * input_rate + out * output_rate) / Decimal(1000)
    return UsageRecord(
        request_id, attempt, operation, model_id, region, status, stop_reason,
        inp, out, total, input_rate, output_rate, cost,
        "unknown" if cost is None else "configured_rate_estimate",
        PRICING_SOURCE if input_rate is not None else None, reason,
    )
