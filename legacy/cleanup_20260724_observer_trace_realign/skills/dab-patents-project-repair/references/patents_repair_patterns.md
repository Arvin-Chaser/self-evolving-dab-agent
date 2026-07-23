# PATENTS repair patterns

Use this reference only when the active repair seed concerns PATENTS data-agent failures.

## Actionable mechanisms

- Exact CPC lookup: check raw publication CPC against metadata `symbol` before normalization.
- Parents traversal: if raw symbol is deeper than target level, walk metadata `parents` and select ancestor with requested `level`.
- Fallback safety: only use transformed symbols if the transformed symbol exists in metadata; log raw->matched samples and coverage delta.
- EMA axis: build a sorted year axis from filing years; do not iterate CPC-code keys as years.
- Missing/extra diagnosis: for partial answers, log why missing gold-like families were excluded and why extra candidates survived.

## Anti-patterns

- Repeating an existing prompt instruction.
- Adding a final strict filter that can turn a partial answer into empty output without diagnosing mapping/ranking cause.
- Parser rewrite when trace proves 260k rows and nonzero parents mappings.
- Hardcoding CPC answers, counts, or benchmark-specific expected lists.

## Routing examples

- `AttributeError: 'code' object has no attribute 'strip'` while walking CPC parents: target generated-code pattern/type-safety. Prefer prompt/runtime guardrails that require parent entries to be strings or to extract target symbols from dict/list objects before normalization. Also check runtime observer exception logging signatures if traceback is masked.
- `TypeError: log_exception() missing 1 required positional argument: 'exc'`: target runtime observer API usage. Prefer prompt guidance or source-side contract examples that enforce `log_exception("event_name", exc)`.
- Parser trace shows `rows_parsed` and `symbols_with_parents` are non-zero: do not spend the repair on COPY parser bootstrapping; move to mapping coverage, year extraction, EMA, or answer-delta diagnostics.
- Analyzer fails before selecting a useful signal: target feedback analyzer infrastructure, not the data-agent prompt.

