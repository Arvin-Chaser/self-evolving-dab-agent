# Agent Card Schema

Minimal fields:

- `agent_id`: stable unique id.
- `agent_type`: e.g. `data_agent`, `feedback_analyzer`, `meta_agent_protocol`.
- `status`: e.g. `active_baseline`, `historical`, `promoted_review`.
- `source_refs`: prompt, runner, feedback analyzer, protocol, or candidate refs.
- `capabilities`: short capability labels.
- `known_failures`: known failure modes or benchmark cases.
- `evals`: compact case-level evaluation summaries.
- `lineage`: parent agent/candidate relationship.
- `evolve_policy`: whether/how this agent can be used as a future parent.

