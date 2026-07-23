---
name: dab-tool-agent-zero-start-repair
description: Use when Codex-Qwen repairs the new zero-start DAB-style multi-turn tool-agent workflow using structured observations and evidence packs.
---

# DAB Tool-Agent Zero-Start Repair

This skill applies to the upstream DAB-style DataAgent workflow: repeated LLM calls choose among `list_db`, `query_db`, `execute_python`, and `return_answer`. `zero-start` constrains the initial DataAgent capabilities only; the meta-agent is expected to use this skill, archive evidence, structured observations, and project scaffolding to evolve the DataAgent.

## Allowed Repair Intent

Prefer minimal repairs that improve the workflow policy or its reusable local infrastructure. Safe targets include:

- DAB tool-agent prompt policy overlay at `prompts/dab/dab_tool_agent_policy_zero_start.txt`;
- DAB tool-agent prompts or prompt glue under `prompts/dab/` when available;
- evolvable helper modules under `adapters/dab_tool_agent_helpers/*.py` plus registry updates in `adapters/dab_tool_agent_helpers/registry.py`;
- wrapper/tool-policy code under `experiments/`;
- generic observers/analyzers/evidence builders under `adapters/` or `experiments/`;
- model/client glue such as `llm_client.py` only when the evidence proves it is causal.

The meta-agent may propose new generic helper/tool infrastructure if the workflow evidence justifies it, but should not preload old PATENTS/CPC answer helpers as seed capability. Repeated SQL/schema/data-processing failures are evidence that a reusable script/tool may be a better evolution target than another prompt-only policy paragraph.

Important: do not confuse "forbidden initial domain helpers" with "forbidden evolution targets." A newly proposed helper/tool/script is allowed during evolution when it is derived from the current evidence, keeps a clear local interface, avoids hardcoded answers, and includes an integration path for the DataAgent.

## Evidence-to-Repair Routing

Route by active workflow observations:

- `missing_final_answer` + `max_iterations`: consider tool policy, answer-submission guidance, or iteration-budget-aware planning; if editing prompt policy, target `prompts/dab/dab_tool_agent_policy_zero_start.txt`.
- `only_list_db_no_query_db` or `query_db_never_called`: consider prompt/tool policy that moves from schema inspection to targeted retrieval.
- failed SQL/tool calls: consider guidance for inspecting error messages, quoting identifiers, retrying minimally, or logging the failed-call consequence. If the same failure pattern recurs across attempts, consider a reusable schema-grounding/query-helper tool instead of prompt-only advice.
- huge query results or timeout-prone Python execution: consider bounded retrieval, aggregation in SQL, chunking, staged `execute_python` checks, or a reusable data-processing helper callable by the DataAgent.
- `execute_python` runtime errors: consider prompt/tool policy for validating stored result structure, printing diagnostics, preserving variables before reuse, or extracting fragile repeated Python logic into a helper/tool with an explicit local interface contract.
- weak evidence localization: consider improving workflow analyzer/evidence pack construction rather than data-agent answer logic.

## Evolvable Helper / Tool Path

When choosing a reusable helper/tool repair, use this local interface:

- create or update an import-safe helper module under `adapters/dab_tool_agent_helpers/`;
- update `adapters/dab_tool_agent_helpers/registry.py` with a `HELPERS` entry;
- helper functions must accept `payload: dict` and `inputs: dict[str, object]` and return JSON-serializable output;
- the DataAgent sees registered helpers through the `run_evolved_helper` tool installed by `experiments/run_dab_tool_agent.py`;
- proposed contracts should mention child-observable evidence such as `run_evolved_helper` appearing in `tool_calls.jsonl`, the helper output key entering `result_storage`, or fewer repeated SQL/Python failures.

Prompt-only patches are a fallback, not the default, when repeated SQL/schema/data-processing failures appear in the evidence.

## Candidate Quality Bar

A useful patch_spec should state:

- what the active zero-start parent did correctly;
- what concrete workflow failure remains;
- why the selected target file is the correct layer;
- whether the failure is best repaired by policy text, reusable script/tool capability, logging/evidence construction, or no-op;
- what child-observable behavior should change;
- how validation or child eval should detect the change.

Reject broad rewrites, benchmark-data edits, hardcoded answers, exact expected CPC lists, or changes that depend on internet access during benchmark execution. Prompt-only repairs are allowed, but if the evidence shows repeated local interface or data-processing failures, the patch_spec must explicitly justify why a reusable helper/tool is not the better target.

If no minimal safe patch can improve the observed workflow, output `no_op_failed` with a reason based only on the active zero-start evidence, not on older generated_solve lineage assumptions.
