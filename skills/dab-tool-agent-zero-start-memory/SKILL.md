---
name: dab-tool-agent-zero-start-memory
description: Use when Codex-Qwen acts as the meta-agent for the zero-start DAB-style multi-turn tool-agent line. Provides memory isolation from the older generated_solve/PATENTS lineage and keeps parent assumptions aligned with workflow evidence.
---

# DAB Tool-Agent Zero-Start Project Memory

Use this memory only for the new DAB-style multi-turn DataAgent evolution line.
This line starts from upstream `common_scaffold/DataAgent.py` behavior plus local wrapper/logging/evidence infrastructure.

## Zero-Start Scope

`zero-start` applies to the DataAgent capability state, not to the meta-agent scaffold.

The DataAgent should start without task-specific PATENTS/CPC helper capabilities. The meta-agent may still use project memory, repair skills, archive evidence, structured patch specs, fine-grained workflow observations, child eval, and candidate selection machinery. Those meta-agent scaffolds are part of the experimental method, not preloaded DataAgent solving capability.

The new DAB tool-agent line has an explicit evolution socket: `adapters/dab_tool_agent_helpers/registry.py` starts empty, and `experiments/run_dab_tool_agent.py` exposes registered helpers as the `run_evolved_helper` tool. This socket is infrastructure, not a preloaded domain helper.

## Lineage Boundary

Do not import assumptions from the older generated_solve.py PATENTS lineage.
In particular, do not assume the parent already has:

- a non-empty partial answer;
- working CPCDefinition parser helpers;
- existing CPC/EMA helper scripts wired into the agent;
- iter021 or later archive state as the current parent.

For this line, the active parent state must be read from the DAB tool-agent run summary and workflow observations in the repair seed/evidence pack.

## Current Zero-Start Parent Interpretation

If the active seed has schema `dab_tool_agent_meta_agent_seed_v001` or feedback type `dab_tool_agent_workflow_feedback`, treat it as a workflow-agent parent, not as a generated_solve.py parent.

Important fields:

- `final_answer_nonempty` indicates whether the workflow reached `return_answer`.
- `terminate_reason=max_iterations` means workflow control/tool policy may be causal.
- `tool_counts` reveals whether the agent overuses schema inspection, data retrieval, Python execution, or answer submission.
- failed/empty tool observations are first-class evidence.

## No-Op Discipline

Do not output `no_op_failed` because of older partial-answer anti-regression rules.
A no-op is appropriate only when the active zero-start evidence itself is insufficient, contradictory, outside scope, or would require forbidden benchmark/data edits.

If the active evidence shows empty final answer, max-iteration termination, failed tool calls, empty query results, or repeated Python execution failures, consider minimal repairs to prompt/tool policy/tool schema/reusable local tooling/workflow logging/evidence construction before no-op.

## Research Goal

The goal is to test whether fine-grained workflow feedback helps the meta-agent evolve useful DataAgent capabilities. Prefer changes whose effect can be observed in the next child run, such as:

- earlier transition from schema inspection to targeted `query_db`;
- smaller/bounded data retrieval before `execute_python`;
- better handling of failed SQL/tool results;
- more robust use of stored tool-result files inside `execute_python`;
- explicit `return_answer` behavior after computation;
- reusable helper or tool capabilities that the DataAgent can call in later iterations, when repeated trace failures show that prompt-only guidance is not enough;
- logging/evidence improvements that let future meta-agent iterations localize failures.

Do not hardcode benchmark answers, expected counts, or query-specific ground truth.

## Evolution Target Clarification

Forbidden initial domain helpers are not forbidden evolution targets. If the active fine-grained feedback shows repeated schema grounding, CPC hierarchy, date parsing, or data-processing failures, the meta-agent may propose a new helper/tool/script from scratch, as long as it is benchmark-safe, evidence-justified, and not copied from a previous non-zero-start parent.
