# Task 1F: usage and cost accounting

The service reads the trailing ConverseStream `metadata.usage` snapshot after
`messageStop`, while retaining Task 1E's complete/failed/incomplete behavior.
Only completed responses enter AI context. Accounting is independent: an
unsuccessful response can still have reported usage and a cost estimate.

## Service interface

`stream_response` still yields strings. Its generator return is a
`GenerationResult`, with stop reason and immutable `usage_records`.
`GenerationError.result` carries the same accounting records on failure.
Both `stream_response` and `invoke_response` accept:

- `operation="chat"` or `operation="summary"`.
- `usage_records=[]`, a caller-owned sink receiving one frozen record per
  invocation attempt, including failures and cancellation. This is useful for
  ordinary `for` loops, which discard generator return values.

`invoke_response` continues to return a string. Consumers abandoning a stream
must close the generator. Accounting finalization and SDK stream cleanup then
run together. A process crash cannot guarantee finalization.

Each record captures a local request ID, attempt number, actual invoked model
or inference-profile ID, source region, operation, outcome, stop reason,
reported input/output/total tokens, rate snapshot, estimated USD cost, and
unknown-cost reason. Fallback attempts share a request ID. The profile ID is the
invoked resource; it does not claim to identify AWS's destination region.

## Pricing and unknown values

`services/usage_accounting.py` contains the existing project's rates, explicitly
scoped to `us-east-1` and USD per 1,000 tokens. The approved Nova Pro US inference
profile uses the same configured rate as its base model. These rates are
**unverified configuration**, not a current AWS pricing quote or invoice.
Arithmetic uses Decimal and the rate is captured before invocation. Changing
model selection or pricing cannot recalculate historical request costs.

No default price is substituted for unknown models/regions. Missing, malformed,
duplicate, or inconsistent metadata cannot produce an exact cost. Valid zero
token counts remain zero. Reported counts are not inferred from text length.
Missing totalTokens does not prevent pricing when input/output are present.
Cache usage and nonstandard latency/service tiers have unknown costs because
their pricing is not configured. Taxes, discounts, and other AWS charges are
outside these inference estimates.

An attempt without usage metadata has unknown cost, including access-denied
fallback attempts; the app does not assume zero billing. Known subtotals remain
visible while the overall total is unknown.

## Frontend behavior

Chat and summary requests use one session-state ledger. Request details show
each attempt and distinguish invocation outcome from UI response outcome.
Rendering failure can exclude a completed response from context without losing
its received usage. Rerendering does not add accounting records.

Totals are conversation-scoped and clear with the existing clear-conversation
action. An existing session with legacy history/estimates receives an unknown
accounting marker; old character estimates are not presented as actual tokens.
The ledger is in-memory and is not a persistent billing system.

## Offline validation

The baseline was 196 passing tests. Task 1F regressions cover usage extraction,
all outcomes, fallback, summaries, missing/invalid metadata, pricing scope,
model/rate changes, cancellation, renderer failures, clear, and rerendering.
Tests fake Bedrock and Streamlit and block AWS credentials/client creation and
network access. No live AWS validation is included.
