---
name: dab-data-agent-prompt-repair
description: Use when a meta-agent must repair a DAB/DataAgentBench data-agent by editing the data-agent prompt, especially for PATENTS failures. Guides Qwen/Codex to translate runtime evidence, generated_solve.py failures, stage traces, and primary signals into minimal prompt-level patch_specs without editing generated code, analyzers, logs, archive files, or project source.
---

# DAB Data-Agent Prompt Repair

Use this skill to produce a prompt-level repair candidate for a DAB data agent.
The repair target is the parent prompt, not `generated_solve.py`.

## Scope

Allowed target:

- `prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt`

Forbidden targets:

- `generated_solve.py`
- `adapters/feedback/**`
- `experiments/analyze_agent_error.py`
- `experiments/extract_primary_signal.py`
- `logs/**`
- `candidates/**`
- `archive/**`
- `trajectories/**`

If the failure requires editing a forbidden target, output `no_op_failed`.

## Evidence rules

Use these only as evidence:

- `agent_error_summary.json`
- `stage_trace.json`
- `generated_solve.py`
- `final_answer.txt`
- repair seed / selected signal

Do not use evidence text as a patch anchor. The patch anchor must be exact text from the parent prompt.

## Repair strategy

Translate code-level or runtime failures into durable prompt instructions.

Good prompt repair:

- Adds a short instruction that future generated code should follow.
- Targets the causal failure mode, not a single observed stack trace.
- Preserves existing runtime-observer and answer-contract requirements.
- Avoids hard-coding expected answers, CPC lists, exact counts, or benchmark ground truth.

Bad prompt repair:

- Pastes Python implementation code into the prompt.
- Uses `generated_solve.py` as the anchor.
- Rewrites a large prompt section.
- Makes the data agent depend on analyzer internals.
- Tells the agent to output a known answer.

## PATENTS failure mapping

When the selected signal is `cpc_definition_invalid_parents_json`, instruct future generated code to robustly parse CPC definition hierarchy fields from SQL-dump formats and to fall back to metadata-grounded hierarchy logic rather than heuristic string truncation.

When the selected signal is `granularity_mapping` or strict validation shows many extra deep CPC codes, instruct future generated code to return canonical metadata-defined level-5 CPC symbols only, and to avoid deeper raw publication codes unless metadata confirms they are the requested level.

When the selected signal is `metadata_parser` / `no_years_found`, instruct future generated code to validate filing-date parsing before EMA calculation and to log/repair empty year extraction before writing the answer.

When the selected signal is `missing_final_answer_file_or_empty_answer`, instruct future generated code to always write `FINAL_ANSWER_PATH` after execution, even when no candidates survive, while still logging the empty-answer cause.

When the selected signal is `agent_code_execution_error`, prefer prompt instructions that reduce memory-heavy parsing, excessive event logging, or brittle parsing assumptions. Do not patch generated code directly.

## Patch spec rules

Output strict JSON only.

Use this shape:

```json
{
  "status": "patch_spec",
  "repair_profile": "data_agent_prompt_repair",
  "target_files": ["prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt"],
  "edits": [
    {
      "file": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
      "operation": "insert_after_anchor",
      "anchor": "exact text copied from parent prompt",
      "intended_change": "short prompt instruction to insert",
      "rationale": "why this is a minimal prompt-level repair"
    }
  ],
  "risk_scope": "minimal/local/data_agent_prompt_only",
  "public_functions_to_preserve": [],
  "forbidden_actions_ack": {
    "no_feedback_analyzer_changes": true,
    "no_hardcoded_answer": true,
    "no_broad_refactor": true
  }
}
```

Prefer `insert_after_anchor` or `append_text`. Avoid `replace_text_once` unless the replacement is very small and anchored in the parent prompt.

Use valid JSON escaping for all quotes and newlines inside strings.

## Candidate quality bar

A candidate is useful only if it:

- Produces a non-empty prompt diff.
- Touches only the allowed prompt file.
- Does not introduce answer hard-coding.
- Allows child eval to run.
- Improves DAB validation, or at least avoids worse failures such as execution crashes and less-specific selected signals.

If the best available change cannot meet this bar, output `no_op_failed`.
