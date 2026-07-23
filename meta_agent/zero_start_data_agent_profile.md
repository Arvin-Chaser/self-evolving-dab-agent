# Zero-Start DAB DataAgent Profile

This profile defines the clean starting point for the new DAB-style DataAgent evolution line. The zero-start constraint applies to the DataAgent's initial solving capabilities, not to the meta-agent's experimental scaffold.

The research goal is to test whether fine-grained feedback helps a skill-guided, archive-aware meta-agent evolve useful DataAgent capabilities over multiple iterations. Therefore the initial DataAgent must not receive task-specific helper scripts that already encode PATENTS/CPC solving knowledge, while the meta-agent may still use skills, structured patch specs, child eval, archive selection, and feedback analyzers.

## Initial DataAgent Capabilities

The zero-start DataAgent may use only generic workflow capabilities:

- `list_db`: inspect available tables or collections.
- `query_db`: retrieve evidence from configured databases.
- `execute_python`: run local data-processing code in the DAB Docker sandbox.
- `return_answer`: submit a final answer.
- generic workflow logging and artifact normalization.
- generic trace analysis that converts run artifacts into observations.

## Allowed Local Infrastructure

These components may exist at the start because they support running, observing, or evaluating the agent rather than solving a domain problem directly:

- DAB tool-agent wrapper: `experiments/run_dab_tool_agent.py`.
- PostgreSQL bridge for local benchmark data: `tools/psql_via_docker.sh`.
- generic workflow observer interface: `adapters/workflow_observer.py`.
- generic DAB workflow trace analyzer: `experiments/analyze_dab_tool_agent_trace.py`.
- archive, candidate, evidence-pack, and meta-agent orchestration infrastructure.

## Forbidden Initial Domain Helpers

The zero-start DataAgent must not be preloaded with helpers that directly encode PATENTS/CPC task knowledge, including but not limited to:

- CPC level parsers or CPC hierarchy helpers.
- EMA-specific calculators for PATENTS queries.
- PATENTS schema shortcuts or metadata parser helpers.
- query-specific answer repair scripts.
- any helper generated in previous non-zero-start iterations that directly improves PATENTS solving.

These scripts are evolution-eligible, but they must be proposed or created by the meta-agent during later iterations. This means they are forbidden as initial preloaded DataAgent capabilities, not forbidden as future candidate patches.

## Evolution-Eligible Targets

During evolution, the meta-agent may propose or modify:

- prompt instructions;
- generic helper tools;
- tool registration logic;
- workflow logging points;
- trace analyzers;
- evidence-pack construction;
- archive observation and parent-selection logic;
- eventually, domain helpers such as CPC or EMA tools, if justified by observed failures.

When repeated trace failures point to brittle SQL/schema/data-processing logic, the meta-agent should consider creating or registering reusable scripts/tools rather than only adding more prompt text. The default target for such tools is `adapters/dab_tool_agent_helpers/` plus `registry.py`; registered helpers are exposed to the DataAgent as `run_evolved_helper`.

## Feedback Principle

Fine-grained feedback should provide evidence, not fixed repair decisions.

The analyzer may say, for example, that a run reached `max_iterations`, never called `query_db`, or ignored a failed tool result. The meta-agent should decide whether this implies a prompt change, a tool change, a logging change, or no change.

## Experimental Comparison

Recommended experimental groups:

1. `no_feedback`: final pass/fail or final answer only.
2. `coarse_feedback`: final metrics and a coarse failure signal.
3. `fine_grained_feedback`: workflow trace plus structured observations.
4. `fine_grained_feedback_plus_evolvable_tools`: same as group 3, while allowing the meta-agent to create and register new tools.

Key outcome measures:

- validation pass rate;
- answer precision/recall/F1;
- valid candidate rate;
- iterations to first improvement;
- no-op or interface-mismatch candidate rate;
- whether the meta-agent creates new useful helper scripts;
- whether the meta-agent modifies logging or feedback components.


## Script-first meta-agent repair preference

When repeated workflow or answer-quality evidence indicates missing capability, the meta-agent should first consider creating or registering an executable helper/script/tool, runner glue, workflow observer, or evidence-pack improvement. Prompt edits should normally be minimal glue that helps the DataAgent discover and use that executable capability. A prompt-only candidate should explain why no script/tool/runner repair was the right minimal move for the evidence.

## Boundary Evidence Logging for Future Meta-Agent Repair

When the workflow produces candidate answer items, the DataAgent should leave generic evidence that helps a later meta-agent understand boundary errors without seeing hidden ground truth. Useful evidence includes:

- what candidate items were generated or retrieved;
- which items were filtered, ranked, merged, or excluded;
- the reason or uncertainty behind important keep/drop decisions;
- which intermediate result directly fed the final answer;
- any uncertainty about schema grounding, normalization, grouping, or answer formatting.

Use the generic self-observation/logging channel when available. Keep this evidence domain-neutral: do not mention expected counts, benchmark answers, validator-only missing items, or hidden ground truth. The purpose is to support later near-miss causal diagnosis, where the meta-agent compares post-run missing/extra samples against workflow artifacts and infers whether items were never generated, generated but dropped, or present but malformed.
