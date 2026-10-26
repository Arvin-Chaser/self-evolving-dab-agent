# Codex Context Cost Audit — 2026-10-21

This is a cold operational evidence record. Do not read it during ordinary startup. It explains why the repository uses bounded hot memory and Agent orchestration guardrails.

## Scope and method

- Read-only inspection of local Codex rollout JSONL associated with `C:\Users\34934\source\text2sql`.
- Counted individual `token_usage_record.usage` values rather than cumulative `token_count` events.
- Used `response_id` and tool-call IDs to check for duplicate records across rollout files.
- Did not call a research provider, run a benchmark, contact the remote server, modify credentials, or inspect credential values.
- Local usage is best-effort operational evidence, not a final CRS invoice. Active writes, cross-day files, and CRS-only aggregation can cause differences.

## Observed snapshot

The bounded local snapshot contained:

- 2,105 model requests;
- 251,057,417 input tokens;
- 245,332,096 cached input tokens, or 97.72% of input;
- 5,725,321 non-cached input tokens;
- 729,086 output tokens, including 148,005 reasoning-output tokens;
- 119,267 average input tokens per request;
- 110,376 median, 197,440 p90, 228,387 p99, and 243,726 maximum input tokens per request;
- 46 unique compaction-related events in the inspected rollout collection.

The user's CRS observation was more than 280 million total tokens with about 97% cache reads. The local snapshot corroborates the shape and most of the magnitude but does not establish the final billed total.

## Attribution

Two long-running delegated/derived threads dominated the local snapshot:

- session `01a15895-c0e3-7991-90d2-c4691aff2cbf`, titled `检查 DAB 研究进度`: 1,784 requests, 196,552,052 input tokens, and 191,996,160 cached tokens;
- session `01a15a19-a211-7ac2-9588-9b296c3ca976`, titled `DAB G12 正式 56-task 执行`: 239 requests, 45,134,827 input tokens, and 44,629,632 cached tokens.

Together they accounted for about 96.3% of locally attributable input tokens.

Unique orchestration/tool calls in the inspected records included 1,664 execution calls, 199 ordinary waits, 195 Agent waits, 116 Agent messages, 44 Agent spawns, 17 Agent-list calls, and 11 follow-up assignments. A tool return normally led to another model step carrying the accumulated context.

Tool-call arguments repeatedly referenced the main cold memory files: `CURRENT_STATE.md` 155 times, `HANDOFF.md` 156, `EXPERIMENTS.md` 122, `DECISIONS.md` 104, and Research Graph memory v18 33 times. These counts show repeated routing through the files; they do not prove that every reference was a complete read.

## Finding

The incident was primarily a context-read amplification failure:

`large retained context × many model/tool cycles × delegated thread lifetime`

Prompt caching worked, but cached reads were still counted and billed. The main failure was not a low cache-hit rate. It was continuing thousands of model steps while the median request already carried more than 110,000 input tokens and the largest requests approached the context limit.

Full-memory startup, repeated cold-memory retrieval, Agent polling, long inherited histories, and repeated compaction were secondary multipliers.

## Adopted controls

- One bounded hot state file plus a small routing index.
- Cold records excluded from default startup.
- Targeted retrieval by stable IDs instead of complete memory reads.
- Single-Agent default; explicitly authorized child Agents receive no inherited history and a packet no larger than 8 KB.
- No nested delegation or tight wait polling.
- Stop-and-handoff boundary at 30 model/tool cycles, two compactions, or reported input context above 100,000 tokens.
- Deterministic validation for memory sizes, JSON routing, hashes, Git state, manifests, and schemas.
- No automatic per-turn memory synchronization.

The enforceable policy is `docs/agent_memory/MEMORY_POLICY.md`; this audit remains evidence and should not be copied into the hot state.

## Policy supersession - 2026-10-22

The fixed 30-cycle, two-compaction, and numeric context-threshold stop rule recorded above is retained only as historical evidence. The user withdrew that rule on 2026-10-22 because it rotated conversations too frequently. Current policy leaves routine conversation rotation to the user and permits the Agent to recommend, but not automatically create or hand off to, a fresh conversation when context pressure creates a material reliability or cost risk. See `docs/agent_memory/MEMORY_POLICY.md` and `AGENTS.md` for the enforceable wording.
