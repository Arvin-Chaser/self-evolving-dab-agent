# Independent DeepSeek Meta workflow

Active defaults: official `deepseek-flash`, `https://api.deepseek.com/v1`, high
reasoning. Data uses native Chat Completions with real reasoning history; Meta
uses native Responses with the official, separately installed CLI 0.162.0.
No global PATH, desktop configuration, ACL, firewall, approval or managed
requirements changes. Keys remain in the existing local private file and enter
only the explicitly bound child environment. No key upload was performed.

## One Meta entry

`experiments/dab_meta_pipeline_v2.py` is the new Meta-side entry. The previous
GPT-specific v1 and historical launch commands are preserved as evidence, not
future entry points. Do not run historical generation launchers to change API.

The chain is health → independent review → original validated Graph append →
independent full-Graph selector → sealed intent → independent implementation →
unchanged source/compatibility checks → up to two independent same-intent
candidate repairs → original admission → Data handoff. Review/candidate modes
require the appropriate recorded campaign stage and explicit generation
authority. The orchestrator supplies no algorithm, parent choice or review.

Use the bundled Python with this entry and `--start --campaign <campaign>
--run <campaign>/meta_workflows/<fresh-name> --mode review_then_candidate
--authority <explicit-human-scope> --review-generation N --candidate-generation
N+1`. Choose `review` or `candidate` when only that scope is authorized.
This is an example of the interface, NOT authorization to run a new generation.
`--status --campaign <campaign>` is model-free. No desktop shutdown is required
by this workflow. Normally reviewed tool execution remains required by the host.

Completed stages have immutable intents and artifact-bound receipts. Unknown
dispatch, failed transport/security, abandoned locks or changed evidence stop
without replay. Only a failed candidate validation returns bounded synthetic
diagnostics to a distinct independent Meta session, preserving the sealed
intent and failed source. No permission weakening or automatic provider retry.

## Verified independent runtime

Installed under the visualization workspace, not the desktop installation.
Dedicated configuration: `configs/deepseek_meta_standalone_v2`.
Executable SHA, profile/catalog bytes and non-project policy are checked.
Only trust-only project records may be created by the CLI; workflow receipts
check exact newly prepared directories. Other project overrides fail closed.
Explicit supported MXC process sandbox has no legacy/full-access fallback.

Actual tests while the desktop remained open:

- sandbox read/write and PowerShell pass; read-only write and tool network denied;
- `tmp/meta_deepseek_standalone_probe_v1/report.json`: one native coding session,
  three successful shell commands, one completed apply_patch, exact fixture and
  output verified, 11.716 seconds;
- `tmp/meta_deepseek_schema_probe_v1/report.json`: original read-only structured
  selector/review invocation, one successful shell command, exact JSON verified,
  6.434 seconds;
- both actual durable sessions independently bind DeepSeek provider/model,
  restricted tool networking, on-request/auto-review and no command grants.

Both proofs are required before a paid research stage. These are synthetic
integration evidence, not a completed research generation or speed/quality
claim. Future model/candidate failures remain possible and are preserved.

## Data entry and handoff

`experiments/run_dab_deepseek_data_v2.py` fixes future Data endpoint/model/key env,
uses the existing native adapter, overrides stale GPT environment defaults,
sets unbounded turns and disables SDK/agent request retries. It grants no remote
launch or key-upload authority. Frozen benchmark batches require a NEW
candidate-specific runtime and local/remote compatibility/input audit before
one exclusive dispatch. No GPT checkpoint is migrated or continued on DeepSeek.

Shared defaults: `configs/dab_active_api_route.json`; immutable standalone route:
`configs/dab_deepseek_standalone_route_v2.json`. Historical candidate/source,
intent, result, Graph, trusted tests and validator artifacts remain unchanged.
No Gen9 rerun, Gen10, formal result, review or Graph action was launched during
this installation. Gen9 GPT has 9 normal tasks (6 strict, 3 normal wrong), 8
provider overload failures; it is not a healthy full17 eligible result.

## Verification

81 offline tests cover old and new workflows/routing/native metadata. New files:
`tests/test_dab_meta_pipeline_v2.py`, `tests/test_deepseek_standalone_routing_v2.py`,
`tests/test_dab_native_meta_audit_v4.py`. No original tests were edited.

Official implementation references:
https://learn.chatgpt.com/docs/windows/windows-sandbox
https://api-docs.deepseek.com/guides/responses_api/
