# G13.2 Task Workspace Agent

G13.2 is a task-facing successor to G13's requirement-observation coverage
mechanism. It retains explicit requirements, evidence references, unresolved
gap selection and bounded actions, while removing the opaque carrier and
Graph/audit restrictions that prevented the formal G13 model from using the
mechanism.

The implementation is not prompt-only:

- `manage_task_workspace` stores semantic requirements, sufficiency criteria,
  evidence findings, contradictions, status and next actions;
- database and Python calls must bind to an existing requirement and declare
  their information-gain purpose;
- evidence references are accepted only when they were produced by a task tool
  for that requirement;
- exact successful repetitions and twice-unchanged failed actions are blocked;
- old raw tool messages are compacted only after their evidence has been
  absorbed into the persistent workspace;
- a finite run enters synthesis with reserved turns remaining, allows a bounded
  final verification budget, and then exposes only `return_answer`.

The workspace remains model-authored and is not a semantic verifier. Its role is
to make decomposition, evidence use, contradiction handling and termination
operationally available to the DataAgent.

The dedicated launcher is `experiments/run_dab_tool_agent_g0132_workspace.py`.
It defaults to 40 model turns rather than the 20-turn cost-screen boundary used
for G13.1. Provider, database and benchmark execution remain separate
authorization boundaries.
