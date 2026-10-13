# Configured models and fallback

This document describes local code, not current AWS availability, pricing or model
entitlements. No live model catalog or account access was checked.

The UI choices in `novamind/config/settings.py` are:

- Amazon Nova Pro: `amazon.nova-pro-v1:0` (default).
- Amazon Nova Lite: `amazon.nova-lite-v1:0`.
- Claude 3.5 Sonnet: `anthropic.claude-3-5-sonnet-20241022-v2:0`.

`BedrockService._build_candidate_list` (`services/bedrock_service.py`, line 339)
adds exactly one candidate for the Nova Pro base ID: `us.amazon.nova-pro-v1:0`.
`stream_response` retries that candidate only after an initial SDK ClientError
with code `AccessDeniedException`, before output has started and before a stop
event. There is no automatic model substitution for Nova Lite or Claude, no
fallback after partial output, and no generic capacity/throttling fallback.
SDK total attempts are configured to one; the explicit Pro fallback is separate.
The configured model ID remains unchanged; usage records identify the model actually invoked.

The profile is not a fourth UI model. Although service policies recognize it,
setting it as the UI default is rejected by the current UI model mapping.
Do not treat the fallback as proof of cross-region permissions or availability.

`services/request_limits.py:MODEL_POLICIES` sets local context budgets of 128,000
for both Nova models/Profile and 64,000 for Claude, each reserving up to 8,192 output
tokens. It currently permits the application's image/document formats for all
configured policies. These are conservative local admission rules, not independently
verified provider capability claims. Retained history is checked when switching
and again before sending; incompatible/oversized context is rejected without trimming.

`services/usage_accounting.py:MODEL_PRICING` contains unverified project rates.
Actual Bedrock token metadata plus a frozen rate produces a configured-rate cost
estimate. Missing usage or unsupported pricing remains unknown. New models, regions,
rates or capabilities need separate review and offline tests before use.
