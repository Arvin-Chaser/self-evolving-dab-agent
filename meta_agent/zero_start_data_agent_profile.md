# Zero-Start DAB DataAgent Profile

This profile defines the clean starting point for the new DAB-style DataAgent evolution line.

The research goal is to test whether fine-grained feedback helps a meta-agent evolve useful DataAgent capabilities over multiple iterations. Therefore the initial DataAgent must not receive task-specific helper scripts that already encode PATENTS/CPC solving knowledge.

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

These scripts are evolution-eligible, but they must be proposed or created by the meta-agent during later iterations.

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
