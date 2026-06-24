# Candidate Card Schema

Minimal fields:

- `candidate_id`: stable unique id.
- `candidate_type`: e.g. `feedback_analyzer_repair`, `protocol_smoke`,
  `data_agent_repair`.
- `parent_agent_id`: source checkpoint/protocol if known.
- `status`: final review state.
- `changed_files`: project files changed by the candidate patch.
- `artifacts`: manifest, patch, validation, child-eval, promotion review refs.
- `eval_summary`: compact gate / validation / child-eval results.
- `promotion`: merge recommendation and scope note.

