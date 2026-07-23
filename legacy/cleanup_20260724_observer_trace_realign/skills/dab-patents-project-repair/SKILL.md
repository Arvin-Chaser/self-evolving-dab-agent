---
name: dab-patents-project-repair
description: Use when Codex-Qwen is acting as a DAB/DataAgentBench PATENTS meta-agent and may repair project source files beyond the data-agent prompt. Guides structured patch_specs for safe project-level repairs using repair_seed, stage_trace, generated_solve evidence, archive parent context, and PATENTS answer-delta signals while avoiding control artifacts, benchmark data, broad rewrites, and hardcoded answers.
---

# DAB PATENTS Project Repair

Use this skill when prompt-only repair is too weak and the meta-agent may edit project source.
The goal is still a minimal candidate patch, not a broad refactor.

## Allowed repair intent

Prefer the smallest source change that improves the next data-agent run or the repair loop itself.
Useful targets include:

- DAB prompt text under `prompts/dab/`
- feedback/analyzer code under `adapters/`
- loop/repair/evaluation code under `experiments/`
- model/client glue such as `llm_client.py` when the active failure proves it is causal

Forbidden targets:

- `logs/**`, `candidates/**`, `archive/**`, `trajectories/**`, `reports/**`
- benchmark/data files under `benchmarks/**` or external DataAgentBench datasets
- `.git/**`, `.venv/**`, `.codex/**`, caches, generated run artifacts
- hardcoded PATENTS ground-truth answers or exact expected CPC lists

If the safest repair would require forbidden targets, output `no_op_failed`.



## Tool-first repair policy

Prefer reusable helper modules over prompt growth when the same generated-code failure recurs. For PATENTS data-agent repair, first consider whether the failure can be converted into a small helper under `adapters/patents/`, then add only minimal prompt glue so future `generated_solve.py` imports or follows the helper contract.

Good helper candidates:

- CPCDefinition COPY header/data parsing;
- `symbol -> level` and `symbol -> parents` construction;
- raw CPC symbol to requested-level ancestor mapping;
- filing-year extraction;
- EMA/best-year calculation;
- answer coverage diagnostics and validation helpers.

Prompt-only repair is a fallback, not the default. Use it only when a helper would be unnecessary or unsafe, and state why.

## Error-to-target routing

Use the repair seed's `repair_routing` first. If it is absent, route by the concrete failure:

- Feedback/analyzer exceptions (`ImportError`, `UnboundLocalError`, `RecursionError`, `common_trace_checks`, `dab_patents_checks`): prefer `adapters/feedback/common_trace_checks.py`, `adapters/feedback/dab_patents_checks.py`, `experiments/analyze_agent_error.py`, and `experiments/extract_primary_signal.py`. Do not repair these by changing the data-agent prompt.
- Meta-agent protocol failures (`protocol_failed_*`, empty patch, invalid patch_spec, first-action gate, launcher validation): prefer `experiments/run_codex_qwen_repair_launcher.py`, `experiments/run_meta_agent_evolution_loop.py`, or structured patch-spec helpers. Do not repair these by changing PATENTS prompt text.
- Generated `generated_solve.py` runtime tracebacks or runtime observer API misuse: prefer durable generation guardrails in `prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt`, `adapters/runtime_observer.py`, `experiments/run_dab_agent.py`, or `experiments/build_meta_agent_evidence_pack.py`. A prompt-only patch is weak unless it directly prevents the concrete traceback pattern.
- Parser/hierarchy succeeds but answer overlap is poor: prefer answer-delta-guided prompt/source changes around canonicalization, fallback coverage, EMA year axis, ranking, tie handling, and diagnostics. Do not rewrite parser bootstrapping.
- `no_years_found`, empty EMA input, or filing-year extraction failures: prefer year-axis and date-extraction guidance/guardrails, not CPC hierarchy rewrites.

For every patch_spec, explicitly name the selected repair layer, why the target file is the right layer, and why prompt-only is sufficient or insufficient.

## PATENTS computation path

Treat this as the expected reasoning path:

1. Parse CPCDefinition PostgreSQL `COPY public.cpc_definition (...) FROM stdin;` header.
2. Build `symbol -> level` and `symbol -> parents` from metadata.
3. Read patent publication CPC codes and filing dates.
4. Try exact raw CPC symbol lookup first.
5. If the exact symbol is deeper than the requested level, use metadata `parents` to find the requested-level ancestor.
6. Use only metadata-confirmed normalization/fallback, and log coverage before/after.
7. Aggregate counts by filing year and canonical CPC symbol.
8. Compute EMA over filing years, not over CPC-code keys.
9. Select canonical symbols whose best EMA year matches the query.
10. Write `FINAL_ANSWER_PATH` and emit useful trace events.

## Signal-to-repair policy

When `symbols_with_parents == 0` or parent parsing evidence shows escaped parent lists, repair parents parsing or prompt guidance for escaped COPY newlines.

When `mapped_count` is low or many publication codes are unmapped, repair exact lookup and metadata-confirmed normalization; do not blindly strip zeros, slash groups, or decimal-like suffixes.

When the parent has a non-empty partial answer with missing/extra sets, do not repair parser bootstrapping. Focus on canonicalization, fallback-derived extras, EMA year-axis construction, ranking/tie handling, or final validation diagnostics.

When final answer is empty, inspect trace first: parser failure, mapping zero, no years found, EMA empty, or answer writing failure require different repairs.

When Qwen is unsure of a domain term, prefer local evidence and metadata. If the active environment explicitly permits web search, it may propose adding a prompt instruction to consult authoritative sources for unclear domain concepts, but generated code must not require internet access during benchmark execution.

## Candidate quality bar

A project-level patch must state:

- what the parent already does correctly;
- what concrete failure remains;
- why the edited file is the right layer;
- why this is smaller or safer than a prompt-only repair;
- how validation will detect improvement.

Reject shallow patches that only restate existing rules, such as:

- ?use metadata level? without a mechanism;
- ?check level == 5? without explaining exact lookup, parents traversal, or fallback behavior;
- duplicate prompt bullets;
- formatting-only edits;
- empty-answer pseudo-fixes.

## Patch spec discipline

Output strict JSON only. Use `patch_spec` with anchor-based edits.
Use at most a small number of files. Keep total changed lines small.
Use exact anchors from context. If source context is insufficient for a safe anchor, output `no_op_failed` rather than guessing.

Required acknowledgements for project-level repair:

```json
{
  "no_control_artifact_changes": true,
  "no_benchmark_data_changes": true,
  "no_hardcoded_answer": true,
  "no_broad_refactor": true
}
```
