# Experiment Ledger

This ledger records observed results, not causal claims. “Strict” uses the denominator shown for that line.

## Research Graph baseline line (current)

All rows use the same frozen 56-task, base-description, no-hint protocol and a 1200-second per-task wall limit unless explicitly noted. Primary metric is strict/56.

| Gen | Ended / completed / timeout / other | Strict/56 | Mechanism evidence | Status and source |
| --- | --- | ---: | --- | --- |
| G0 | 56 / 50 / 6 / 0 | 33/56 | root control | Verified: `g000_evidence.json` |
| G1 | 56 / 54 / 0 / 2 | 30/56 | reserve bound 5/56 | Verified: `g001_evidence.json` |
| G2 | 56 / 54 / 2 / 0 | 30/56 | lifecycle localization untested for pre-event failure | Verified: `g002_graph.json` |
| G3 | 56 / 54 / 2 / 0 | 35/56 | supported structural concordance | Verified: `g003_safe_snapshot/g003_evidence.json`; attempt 1 DNS incident preserved |
| G4 | 56 / 53 / 3 / 0 | 34/56 | contradicted alignment prediction | Verified: `g004_safe_snapshot/g004_evidence.json` |
| G5 | 56 / 51 / 5 / 0 | 30/56 | supported diagnostics; reason-code subclaim remained untested | Verified: `g005_safe_snapshot/g005_evidence.json` |
| G6 | 56 / 53 / 3 / 0 | 37/56 | supported coarse timeout localization | Verified: `g006_safe_snapshot/g006_evidence.json`; highest observed score, not causal |
| G7 | 56 / 52 / 4 / 0 | 32/56 | supported last-pre-exec elapsed localization | Verified: `g007_safe_snapshot/g007_graph.json` |
| G8 | 56 / 53 / 3 / 0 | 35/56 | supported preterminal audit structure | Verified: `g008_safe_snapshot/g008_evidence.json` |
| G9 | 56 / 54 / 2 / 0 | 35/56 | supported later-turn gate structure | Verified: `g009_safe_snapshot/g009_evidence.json` |
| G10 | repaired view 56 / 55 / 1 / 0 | 32/56 supplementary; original 27/56 | contradicted directional outcome | Verified: `g010_safe_snapshot/g010_evidence.json`; user-authorized two-run repair, not one valid uninterrupted run |
| G11 | 56 / 53 / 3 / 0 | 35/56 | **untested**: authored record 0, guidance binding 0 | Verified: `g011_solution_loop_safe_snapshot/g011_solution_loop_evidence.json` |
| G12 | 56 / 51 / 5 / 0 | 30/56 | **untested**: record attempts 0, accepted records 0, visible refs 0, directives 0 | Verified: `g012_safe_snapshot/g012_evidence.json`; independent review passed and Graph closed |

G0-G13 Graphs are closed and immutable. G13 has one completed formal attempt, independently validated Evidence, and a four-node Graph appended to `research_graph_memory_v17.json`.

## G12 no-task evidence

- Interface investigation 1: 26 passed; bounded substrate feasible, action-specific interface still open.
- Interface investigation 2: 41 passed; structured action/status/opaque target visible in synthetic fixtures; real-model behavior unknown.
- Formal candidate full suite: 149 passed.
- Focused G12 suite: 33 passed.
- Candidate surface: 37/37 hashes independently rechecked; combined SHA matched.
- Formal run/benchmark/deployment: none. Provider/network access occurred only for the bounded synthetic admission described next.

Runtime admission history on 2026-10-20:

- Attempt 002 is preserved as an invalid probe attempt: its control detector included inherited G11 generic guidance and its 3-call live path ended without a valid record. It is not a G12 mechanism result.
- Attempts 003 and 004 failed in preflight before any provider call and remain preserved in the remote synthetic scratch.
- Attempt 005 passed in 3 real DeepSeek calls with no benchmark or database access: record attempts 1, accepted records 1, visible unique refs 1, directives 1. The directive was strictly parsed, exactly matched the runtime text and sidecar fields, and carried `acquire_evidence / empty_step / accepted / step / step_2 / none / evidence_gap / current`.
- The first classifiable post-directive action was `acquisition`, classified `consistent`. This is structural behavior only, not semantic correctness or benchmark benefit.
- The programmed enabled/disabled control matched dispatch arguments/results, termination, final result, and LLM-call count. Scoring did not run; the mechanism initiated zero tool calls; no answer was forced; no wall timeout was extended. Timing remains measurement-only.
- Sidecar, summary, and receipt privacy scans passed. Raw synthetic context remains only in isolated remote base logs and was not copied into the research package.
- Recheck: 149 focused passes; child full suite 302 passes and 5 failures; parent full suite 269 passes and the same 5 failures. No new test failure was introduced.

Status: **bounded no-task runtime admission passed; not benchmark-evaluated and not promoted**. Sources: both G12 `independent_verification.json` files, the formal `implementation_manifest.json`, source admission 001, and runtime admission 005.

Independent research control subsequently reviewed `g012_admission_005` and accepted the bounded no-benchmark admission as PASSED. This acceptance does not authorize or imply a formal 56-task evaluation, benchmark effect, Graph promotion, or G13 implementation.

## G12 formal evaluation

The separately authorized unique attempt `g012_formal_001` ran the frozen child once on the frozen 56-task base/no-hint protocol with a 1200-second per-task limit, four workers, same-dataset serialization, DeepSeek `deepseek-flash`, and the explicit `--enable-g012-uncertainty-gap-action` flag.

- Binding: child tree `47dbf42636bbaa234c5f58256a37821a2ac891d29b34fcce13fe350207e7e344`; task manifest `576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7`; launch manifest `f63ada35052b8d08ca6186ab2658ca3483f78f9b8c400b529dad9a883f5ce93c`.
- Outcome: 56 ended, 51 completed, 5 runner wall timeouts, 0 other or detected infrastructure failures; 30 strict pass, 18 known strict fail, 3 completed strict-verdict unknown. Primary result: **30/56 strict**.
- Runtime structural totals: 1,381 recorded LLM calls; model-authored record attempts 0, accepted records 0, visible unique references 0, directives 0, consistent actions 0, contradictory actions 0, mechanism-initiated tool calls 0. Independent review corrected an earlier misstatement: the five cohort rows sum to 0 `guidance_suppressed_no_state_count`; 1,381 is not a suppression count.
- Pre-registered extractor result: structural binding `untested`, real-model adoption `untested`, behavioral action choice `untested`, overall `untested`. Zero activation is not refutation or confirmation.
- Integrity: no scoring change, wall-timeout extension, mechanism-initiated call, forced answer, provider/connection failure, second arm, resume, selected rerun, or second formal attempt was observed.
- Privacy/export audit passed. The local postrun package contains only allow-listed content-blind summaries and hashes; raw task/answer/SQL/tool content remains isolated remotely.
- Terminal receipt SHA-256: `86ac90a7b925daf58a7f9453619cad258b0df54c4ba4f1ffb3d064a6821a8fb1`. Evidence SHA-256: `5030d3901b764624053f0d5147257b2bb5ea24386e5231f4029e7fc547801bdd`; Graph SHA-256: `790282ece9c81abad1b239c629cd622681162fcf94523b45c81df9de0fae9076`; memory v12 SHA-256: `80eda89e3664128d092d7374cbb2a0f74e040c3d37bbbd77a531f31b158de544`.
- The specialized extractor fields `formal_run_performed=false` and `evaluation_run=false` are mechanism-only/no-claim fields. Formal completion is established by the terminal receipt and Evidence draft together; these fields cannot independently deny or prove that the formal run occurred.

Status: **formal execution complete; Evidence independently validated; G12 four-node Graph closed and appended to the two-layer memory; no G13 run was started by closure**.

## G13 Research Meta attempts

The G13 Research Meta input packet was deterministically built from the closed G0-G12 formal Graphs and `research_graph_memory_v12.json`. Packet SHA-256: `f87082ddac735ccdba4701c2d81464097620c300b75c9daaf36e91dbcc259f81`. Mechanical prechecks found generations 0-12, 26 symmetric formal facts, 20 preserved incubation nodes, the G12 promotion edge, and 13 Graph-bound code-parent entries. The solution-loop contract suite passed 7 tests.

Three provider-complete Research Meta attempts were retained, but all are invalid workflow outputs:

- `_001`, SHA-256 `0b462e8f64138be9d4a8779e2b6bbb059f63c6a8fd20fc7c3acc9a54c1e86975`: observations, counterexamples, and unknowns were strings instead of citation-bearing objects.
- `_002`, SHA-256 `6f08ea6a2bac7152cc235d889281ec720595dc58132572c097b2e0abdda14b9c`: historical-scan row shape was repaired, but every mechanism candidate omitted required non-empty `minimum_no_task_check` and `interface_status` fields.
- `_003`, SHA-256 `57fae282f550fe4cd479f227232912262ad14c9aa12306aaa982ff10cf09a8cc`: candidate fields were repaired, but the complete top-level `unknowns` section was omitted.

All three attempts repeatedly named `mech_requirement_observation_coverage`, but no attempt passed `validate_solution_loop_result(...)`; therefore none was an admitted selection, research target, Graph node, or implementation authorization.

An independent, read-only contract audit showed that the revision prompts omitted parts of the unchanged schema. Pure in-memory shape probes exposed the remaining missing fields without admitting any research content. One schema-complete, mechanism-neutral retry was authorized:

- `_004`, raw output SHA-256 `6609b286be192258ab0cb3ccace712139896cd80534be74d9bc71a1576bed071`: used the frozen packet and immutable `_003` as data; provider returned valid JSON; the complete output passed the original `validate_solution_loop_result(...)` without post-processing or code-side field repair.
- Valid target: `mech_requirement_observation_coverage`; primary lens `task_representation_decomposition`; related lenses `evidence_acquisition_grounding`, `state_memory_belief_update`, and `action_tool_policy_recovery`; state `interface_investigation`.
- Research scope only: requirement-to-observation carrier, coverage transitions, freshness, fault states, structural next-action sensitivity, no-leak boundary, real-model authorship, and action compliance remain unverified. Code parent is not frozen.

No benchmark, candidate implementation, formal Experiment, launch, or evaluation occurred. Status: **packet valid; three schema failures preserved; fourth bounded Research Meta output mechanically validated; G13 target admitted for interface investigation only**.

## G13 interface investigation 001

`g013_interface_investigation_001` tested only the validated Research Meta target's structural interface with synthetic, no-task fixtures.

- Result: 49 independently replayed tests passed.
- Verified: strict opaque row carrier; consecutive revisions; duplicate handling; uncovered/observed/ambiguous/failed/unavailable/unknown transitions; current/stale behavior; later-observation updates; instrumentation missing/truncated/malformed preserved as unknown; structural next-action differentiation; disabled, one-action-cap, and 180-second deadline-guard inertness; aggregate-only export.
- Boundary: no benchmark, database, provider, code-parent selection, formal Experiment, candidate, launch, score, forced answer, forced tool dispatch, or wall-time extension.
- Unknown: real-model row authorship, visible opaque-reference copying, provider and production response-boundary acceptance, and real-model action compliance. Programmed fixture sensitivity is not real-model evidence.
- Artifact hashes: manifest `f5fd8fa52df71196f101686c33f2569f22e28a354ab08b97e44eeeb6f3391db7`; independent verification `8f95b4cfc9c8a29f1e2419e45382a766446c3dce3ccc1449ed5e1b6468003f6b`; memory v13 `e44ab7a0fbefa3e8689f37663d33c231dfb7318c0fcc82f17fa733c269170f94`.

Status: **bounded structural interface verified; real-model behavior unknown; finding appended to incubation; return to Research Meta**.

## G13 post-interface Research Meta 001-002

The post-interface packet binds the closed G0-G12 formal history, all 23 incubation nodes through `interface_finding:g013:001`, and the verified target/finding artifacts. Packet SHA-256: `69f6ed15d6d536987d17ac647af22409e4385273281d64f7e60a88de618f1fdd`.

- Attempt `_001` returned valid JSON and chose `interface_investigation`, but failed the unchanged mechanical validator because `next_interface_investigation.source_scope` was a string instead of a non-empty string array. It remains invalid workflow output. Raw SHA-256: `602799cf51954315229758f5a7d7097e3d5accd5bf77dabe09b3ae0770afcdd9`.
- Attempt `_002` was one bounded full-object serialization repair. It preserved the prior mechanism, state, and substantive decision, converted the source boundary to the required array, and passed the unchanged validator. Raw SHA-256: `10ea715d6c05a7c0c5fd1b489ec5933e4a274c6765e473c1a36bce21fc783f39`.
- Valid decision: keep `mech_requirement_observation_coverage` in `interface_investigation`. The next discriminating question is whether the already-tested opaque carrier can pass a synthetic real-provider and production-response-boundary round trip with exact opaque-token preservation, explicit unknown for missing/malformed/truncated/rejected input, zero prohibited-content persistence, and inert enabled/disabled control flow.
- Boundaries: no benchmark, database, formal Experiment, code parent, candidate, implementation, launch, score, or benefit claim was produced. Real-model row authorship and action compliance remain untested and are not assumed by the requested boundary check.
- Append-only memory: `research_graph_memory_v14.json`, SHA-256 `ecdec2bbe36dc83ecb6cd5242cd5344829a03febe5f4570b1e48e480766eed22`, contains 24 incubation nodes and adds only `research_target:g013:002` plus its revision/finding edges.

Status: **post-interface decision validated; second bounded interface investigation required; not experiment-ready**.

## G13 provider/production-boundary investigation 001-002

The second bounded G13 interface investigation used only generated opaque tokens and the source-grounded production `record_self_observation` tool schema plus the DeepSeek `choices[0].message.tool_calls` response boundary.

- Attempt `_001` made one pre-registered request, but DeepSeek thinking mode rejected forced function `tool_choice` before a model response was produced. The failure is preserved; no retry occurred inside that attempt and no tool was dispatched.
- Attempt `_002` removed the unsupported forced selector and used the production-compatible automatic tool path. Its separate cap was one call; the real provider accepted the production tool schema and returned exactly one strict carrier with both opaque tokens copied exactly.
- Cumulative provider requests: 2; accepted synthetic round trips: 1. This count includes the provider-rejected `_001` request.
- Missing, malformed, truncated, and provider-rejected boundary fixtures all remained explicit `unknown`; none became resolved or genuine evidence absence.
- Enabled/disabled comparison preserved zero mechanism tool dispatch, forced answer, scoring mutation, and wall-timeout extension.
- The isolated raw synthetic response was not copied into the research export. Independent privacy scans found zero credential, SQL, benchmark-path, and task-identifier matches. The exported receipt and findings are aggregate-only.
- Formal real-model authorship rate, formal action compliance, semantic coverage, task-bearing no-leak behavior, runtime attachment, benchmark effect, and code parent remain untested or unfrozen.
- Verification: `12 passed`; receipt SHA-256 `1eb66dcabf19bfad3802a54095bf480e0ea546fe6694a65f3015795cca8d0963`; findings SHA-256 `2e6ada16d49a46a12b605a35b2931f61527c3966a7a1e85532e494a6b243f89b`; manifest SHA-256 `9e5fca88d8ae5c23ea155bf564a0a4ab9793c0a3b4a11ce2b6361fad3a63da73`; independent verification SHA-256 `3f1b9512085b9475f7feff6da14124683ce528be9f9904356c27b0bf8135bcdb`; memory v15 SHA-256 `4206f1706eafbcd12bf318fed01acb0bac6f2a17843f216b310f1af9ad35429b`.

Status: **synthetic real-provider and production-response-boundary interface verified; formal endpoints untested; finding appended; return to Research Meta**.

## G13 post-finding Research Meta 001-002

The post-finding packet binds G0-G12, all 26 incubation nodes through `interface_finding:g013:002`, both valid prior Meta decisions, both verified interface chains, and the synthetic provider receipt. Packet SHA-256: `40c6b556a561e54c1beb71484783c8f873c4ab8d86eac24bca3aa325640cc393`.

- Attempt `_001` returned valid JSON, selected `experiment_ready`, and chose verified G7 tree `572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac`. It was mechanically invalid because it used alias keys for `fixed_protocol` and `structural_binding_endpoint`. Raw SHA-256: `17dcbde71f9b6c3adbb0d4f76d207fb02bac90230da30bb027f468f8961d8695`.
- The validator's initial failure on boolean `no_forced_action=true` was a local type-check bug; `true` is the required safe value. After correcting that type check, an in-memory normalization found exactly the two remaining serialization aliases and no hidden content error.
- Attempt `_002` was a bounded full-object serialization revision. It preserved the research judgment and all substantive fields, changed only the audited key shapes, was exactly equal to the normalized `_001` object, and passed the validator. Raw SHA-256: `0e01fa9290e8ecf722a3e3092e60b74c335b15f439811774cb0c4bb4210bf3b1`.
- Valid decision: `mech_requirement_observation_coverage` is `experiment_ready`. Separate endpoints cover structural binding, model authorship, structural coverage state, behavioral action choice, and strict outcome; zero activation remains untested rather than refuted. The fixed protocol is exactly 56 tasks, base/no-hint, 1200 seconds per task, one arm, strict pass over 56.
- Parent: G7 was selected as the last verified mechanism-neutral structural-instrumentation parent before later audit/checklist/ledger/uncertainty mechanisms. This is a Research Meta selection, not an implementation convenience claim.
- Frozen contract SHA-256: `5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c`. Memory v16 SHA-256: `fc206dac718781d9e3d9eb0dc79e2f6593e98d5e25cb9be3448124c8e15fe54e`.
- No candidate, implementation, admission, benchmark, launch, score, benefit, or causal claim was produced.

Status: **Research Meta decision validated; G13 formal contract frozen; implementation not started**.

## G13 Formal Implementation Meta 002-003

Implementation Meta used the frozen G7 parent tree `572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac` and G13 contract `5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c` in the fresh isolated `g013_formal_implementation_002` workspace. The invalid manual `_001` directory was excluded and not used.

- Initial implementation added the G13 structural module, aggregate extractor, focused tests, and four allowed integrations. Local tests passed, but independent `source_review_001.json` rejected admission: the strict carrier could persist through inherited `agent_self_observations.jsonl`, `llm_calls.jsonl`, messages, and final state. The initial manifest SHA-256 was `40064be4fe97655224807c47b8123ffea8e4fca7e7a09ec4e33f6e176970e944`.
- Revision 003 retained transient parsing at `choices[0].message.tool_calls` but inserted fixed content-blind handling at provider logging, inherited record-tool dispatch, self-observation, persistent model-view, and final-state boundaries. It added a provider-shaped end-to-end fixture covering every materialized log/export surface.
- Revised manifest SHA-256: `96e8874152ed3f8be070c37731bf906b556bdc27ca10fe5eaa4bef8b371c88ce`; child tree SHA-256: `998efc2abc946276df6aa58a7b8a6e04d8aa6f2c719608d21702d3523a1a7da3`.
- Independent replay: 82 focused G13+G7 tests passed. Candidate full suite: 200 passed, 5 failed. Parent G7 control: 153 passed, 5 failed. The five failing nodeids are identical inherited `test_tool_failure_recovery.py` failures, so new failure count is zero.
- Privacy fixture: one accepted structural record and exact opaque binding remained observable in aggregate counters; requirement/observation sentinels had zero hits across LLM/tool/self-observation logs, final state, G13 sidecar, normalized copies, trace, analyzer, aggregate, and evidence-pack surfaces.
- No provider, network, database, benchmark, formal evaluator, launch, or formal Graph mutation occurred.

Status: **local implementation and revised independent source review passed; bounded runtime admission not run; formal G13 generation not evaluated**.

## G13 bounded runtime admission 001-003

Three immutable admission attempts were created; none authorizes a formal run.

- `_001` stopped before a provider call because the frozen candidate carries only the two hash-bound official upstream files and the local import lacked the rest of `common_scaffold.tools`.
- `_002` stopped before a provider call after binding the complete local official upstream tree because the local Python environment lacked its Docker executor dependency.
- `_003` used the verified remote project venv and complete official upstream tree. Three real DeepSeek calls used automatic tool selection. The model authored one strict carrier, copied one genuinely visible opaque observation token exactly, and caused one structural view to be delivered. Producer-boundary privacy passed with zero requirement/observation-token hits in persisted LLM/tool/self-observation/final-state/sidecar surfaces.
- `_003` nevertheless failed the critical production boundary. G13 sanitizes record-call arguments in persistent assistant history and the content-blind proxy omits `reasoning_content`; the DeepSeek adapter binds authentic reasoning to the raw `tool_calls` value. The next request therefore failed locally with `Unbound historical DeepSeek reasoning; no fabricated replay` before contacting the provider. The post-view action endpoint is `unknown`, not consistent or contradictory.
- The initial `_003` driver also had three probe defects: an invalid missing-carrier fixture, an asymmetric early-stop enabled/disabled control, and a TMP directory nested under pytest's removable `basetemp`. These are explicitly separated from the candidate failure. A clean independent full-suite replay restored the verified candidate/parent comparison: candidate `200 passed, 5 failed`, parent `153 passed, 5 failed`, with the same inherited nodeids and zero new test failures.
- Evidence: `g013_admission_001/failure_receipt.json`, `g013_admission_002/failure_receipt.json`, `g013_admission_003/admission_result.json`, and `g013_admission_003/independent_failure_review.json`.

Status: **runtime admission rejected; real carrier authorship/binding and persistence privacy observed, but multi-turn DeepSeek reasoning continuity failed; return to Implementation Meta for a bounded privacy-compatible reasoning-binding repair**.

## G13 bounded native-reasoning repair 004

The same frozen Formal Implementation Meta continued from the admission-003 failure in a new immutable `g013_formal_implementation_003` workspace. It did not change the G7 parent, G13 contract, DeepSeek adapter, mechanism, scoring, provider/model, timeout, or formal protocol.

- Repair: capture the exact native record assistant message and authentic reasoning in process-local state keyed by provider tool-call identity; persist only the fixed content-blind proxy; hydrate only a deep-copied next request. No reasoning is fabricated or serialized.
- Fail-closed cases: missing binding, provider-ID mismatch, duplicate/ambiguous identity, conflicting history/tool calls, persistent reasoning content, and malformed native reasoning.
- Child tree SHA-256: `b0acbc351292ba5653032eeda9dbf9191b855144211c2cf4813478e0f12aa351`.
- Manifest revision 3 SHA-256: `2f9bb26d6cbe60a8d6440e68d69361b215a277bb6517afa4f2ff29dc0c223fa4`.
- Independent source review SHA-256: `2574020cf1faa6ff69e80e9c5a3399d0278417965e6f8e6d5ba25b28eb34a741`.
- Tests: G13+G7 `86 passed`; candidate full `204 passed, 5 failed`; G7 parent `153 passed, 5 failed`; identical inherited failures, new failures zero.
- Privacy: 309 generated artifacts scanned with zero carrier/token/reasoning sentinel or `reasoning_content` persistence hits.
- Probe correction: a fresh attempt-004 probe now represents missing carrier correctly, consumes an equal programmed control sequence, keeps TMP outside pytest basetemp, and audits persisted reasoning fields. Local execution stopped before probe logic because optional upstream dependencies are absent; no provider request was made and this is not admission evidence.

Status: **bounded implementation repair and independent source review passed; runtime readmission not run; no benchmark, database, formal launch, score, or Graph update**.

## G13 bounded runtime admission 004

Attempt `_004` bound the exact G7 parent, G13 contract, revision-3 child, manifest, source review, and corrected probe/driver before copying the frozen child into a new remote synthetic scratch. It did not access benchmark tasks or a database and did not create a launch claim.

- Two real DeepSeek calls used automatic tool selection. The model authored one accepted carrier, copied one visible opaque token exactly, received one structural directive, and selected `acquire_evidence`. No mechanism-initiated tool call, forced tool/answer, scoring mutation, or timeout extension occurred.
- Privacy passed: persisted sensitive-token hits and persisted `reasoning_content` field hits were both zero; raw general synthetic context remained only in the remote scratch and was not copied into the research artifact.
- Admission was blocked before behavioral consistency could be observed. A content-blind structural audit showed that the real provider tool call contained keys `function/id/index/type`, while the persistent proxy contained `function/id/type`. Dropping `index` made the exact process-local native binding reject the history as conflicting; action consistency is `unknown`.
- The fault fixture was fail-closed but did not satisfy the explicit category gate: `{}` was counted as malformed, so missing/malformed/truncated/provider-rejected counts were `0/2/1/1`.
- The driver used test temporary roots inside the candidate tree and reported candidate `198 passed, 11 failed`, retaining only an output hash. An independent replay with basetemp outside the candidate tree restored candidate `204 passed, 5 failed` versus G7 parent `153 passed, 5 failed`; the five nodeids are the same inherited `test_tool_failure_recovery.py` failures, so clean-replay new failures are zero. The extra six failures' exact cause remains unknown, and the driver result is not valid comparison evidence.
- Evidence: `g013_admission_004/admission_result.json`; independent failure review SHA-256 `2be712a20c4a3a84cdc326fb16b1b0671509a68269b0f7a5424794b427310ff3`.

Status: **runtime admission blocked; no formal G13 launch; bounded Implementation Meta and probe revision required**.

## G13 interrupted bounded revision after admission 004

The first bounded revision attempt after admission 004 was interrupted by a Codex desktop/process crash. The preserved directories are `g013_formal_implementation_004` and `g013_formal_implementation_meta_005`.

- The candidate source in `g013_formal_implementation_004` remained byte-equivalent to the admitted-source revision-3 candidate; no new child tree or manifest revision was produced.
- Its copied `implementation_manifest.json` remains the revision-3 manifest with SHA-256 `2f9bb26d6cbe60a8d6440e68d69361b215a277bb6517afa4f2ff29dc0c223fa4`.
- The Meta event stream contains no terminal completion. It ended after the external-temp baseline test (`204 passed, 5 failed`) and before implementation, independent review, or a new admission probe.
- Neither directory is a valid implementation candidate, source-admission result, or runtime-admission result. Both are retained unchanged as interruption evidence and must not be resumed or overwritten.
- A post-crash process audit found no remaining local or remote G13 implementation, probe, admission, or formal-run process.

Status: **interrupted before candidate creation; preserved for audit; restart only in a new immutable attempt**.

The first post-crash restart, `g013_formal_implementation_005` / `g013_formal_implementation_meta_006`, also ended without terminal Meta completion. It had begun a revision-4 patch, but no completed turn or independent review existed; it is preserved as a second interrupted attempt and was not used as a source for the valid candidate.

## G13 bounded native-shape repair revision 4

A second clean restart copied the exact revision-3 child into `g013_formal_implementation_006`. The same frozen Implementation Meta completed terminal attempt `g013_formal_implementation_meta_007` and changed only `experiments/g013_requirement_coverage.py`, `tests/test_g013_requirement_coverage.py`, and the manifest.

- The persistent content-blind proxy now preserves provider-native `id`, `type`, optional `index`, and `function.name`; `function.arguments` remains the fixed marker and authentic reasoning stays process-local.
- Exact structural comparison still fails closed for missing or mismatched index, duplicate/ambiguous/conflicting calls, persistent reasoning, and absent bindings. The unchanged DeepSeek adapter retains its no-fabrication guard.
- Probe-facing parsing now classifies genuinely absent arguments/null freeform as `missing` while preserving `{}` as `malformed`.
- Revision-4 child tree: `e966e07211bae0d8ddea96af8d88143b47af40db40567161d2d8391abfc7591c`; manifest: `0c939b2afd6c51163e9b1702052f882fd9e5f0651234ab20e2cf0c9b9d0e9ff2`.
- Independent focused replay: `98 passed`. Candidate full: `216 passed, 5 failed`. Frozen G7 parent full: `153 passed, 5 failed`. The five failing nodeids are identical inherited `test_tool_failure_recovery.py` failures; new failure count is zero.
- All temporary/cache roots were outside the candidate. An initial reviewer replay with a conflicting `PYTHONPYCACHEPREFIX` produced one harness-only compile failure and was discarded; a clean replay produced the result above.
- Independent privacy scan: 768 materialized files, zero exact sensitive carrier/token/reasoning or persisted `reasoning_content` hits. Source/privacy review SHA-256: `235b54b132fb8eb44020a0f5f5fa47834712b0cd37101a4d616f0cb94177d4a0`.
- A new non-overwriting attempt-005 probe/driver was prepared with explicit missing versus malformed fixtures, external-only test roots, and exact failing-nodeid capture. Probe SHA-256: `69321239f600581a999c98407a6b129a3eef8a0a40324cf448f0947a5aa3febc`; driver SHA-256: `4387878b77501f4c12093931442a583c3252008450c34f179ab11ffbb8c7eac0`; preflight SHA-256: `d509c885eae66a25c708b6ffa494e467ea52b855c4b82404cae23ed000931463`. It has not been run.

Status before runtime attempt 005: **revision 4 independently source/privacy admitted; no benchmark, database, formal launch, score, or Graph update**.

## G13 bounded runtime admission attempt 005

Attempt 005 ran once against revision-4 child `e966e07211bae0d8ddea96af8d88143b47af40db40567161d2d8391abfc7591c` with the prepared probe and driver hashes. The remote source verification matched and no formal benchmark or database boundary was crossed.

- Three automatic DeepSeek calls produced one accepted model-authored carrier, one exact visible opaque-token copy, one delivered directive, and one post-view action classified `consistent`; the selected structural action was `acquire_evidence`.
- Missing, malformed, truncated, and provider-rejected fixtures remained fail-closed. Enabled/disabled control passed with zero mechanism-initiated tool calls, forced tools/answers, scoring mutations, or timeout extensions.
- Focused tests: `98 passed`. Candidate full: `216 passed, 5 failed`. Parent full: `153 passed, 5 failed`. Exact failing nodeids matched and all temporary roots were outside the candidate, so new failure count was zero.
- The privacy gate failed: one accepted opaque requirement token appeared once in the isolated `agent_self_observations.jsonl`. Redacted structural inspection localized it to `line_3.payload.what_i_know[0]` in a `tool_action_sidecar` attached to the post-view `query_db` call. The generic self-observation writer persisted this optional model-authored sidecar without G13 sanitization. Persisted `reasoning_content` hits were zero and every other scanned persistence surface had zero sensitive-token hits.
- No raw token or raw synthetic context was copied into the research artifact. No formal launch claim, Graph mutation, or provider rerun after failure occurred.

Evidence: admission result SHA-256 `b9e23a8adc7b1839b80305ff374a98eb454624032362a4b99f67b2f8b018ebc7`; privacy scan SHA-256 `c19210a05a7cea5bfc9d986ed3255fdc9a9c1b541f28c5b4d1769e8a94b7a25e`; independent failure review SHA-256 `45092cf1790edb234cfce2a208718857a6d8137f4103f05b462bf7a45d2dacec`.

Status: **blocked by a confirmed persistence-boundary privacy failure; the mechanism and behavior subgates passing does not authorize formal evaluation**.

## Older half-56 campaign (historical)

Campaign: `dataset17_half56_deepseek_v1_20261011`. Its historical reporting often used strict/non-timeout-completed; do not compare those rates directly with strict/56 above.

| Run | Result | Main interpretation |
| --- | --- | --- |
| Baseline v2 | 53 completed; 3 operator-terminated IMDb tasks; 33 strict, 50 strict-evaluated | Historical control; 33/53 user denominator or 33/56 all-task denominator must be labeled |
| Gen1 | 50 completed, 6 timeout; 33/47 strict-evaluated | No task gain |
| Gen2 | 52 completed, 4 timeout; 29/49 strict | SQL memo replayed 0 times; integrated but not activated |
| Gen3 | 52 completed, 4 timeout; 30/49 strict | Error-observation-triggered repair; first candidate violated the sealed scope and was revised before evaluation |
| Gen4 | 52 completed, 4 timeout; 27/49 strict | Ledger active, but 493 extraction fail-opens and very large contexts |
| Gen5 | 51 completed, 5 timeout; 27/48 strict | Six provider/protocol errors |
| Gen6 | 50 completed, 6 timeout; 35/47 strict; 35/50 user denominator | Historical best of this campaign; protocol fixed, but long trajectories remained |
| Gen7 | 52 completed, 4 timeout; 32/50 strict | Governor reached only 7/52; source guard missed the known long case |
| Gen8 | 50 completed, 6 timeout; 27/50 strict user denominator | Cost-normalized trigger; repair count 0; worse than Gen6 |
| Gen9 | 48 completed, 8 timeout; 30/48 strict user denominator | 1 mechanism trigger in 2,673 checks; 62.5% |
| Gen10 | 51 completed, 5 timeout; 34/51 strict | 0 usable labels/mismatches/notes; integrated not activated |
| Gen11 | 50 completed, 6 timeout; 35/50 strict | Historical tie with Gen6 on user denominator |
| Gen12 | 49 completed, 7 timeout; 33/46 strict-evaluated | Referent-scoped dispatch obligation; did not exceed Gen6/Gen11 on the fixed cohort |
| Gen13 | 50 completed, 6 timeout; 31/50 strict | 150 probes, 34 literals, 0 confirmed; no gain |
| Gen14 | 52 completed, 4 timeout; 32/52 strict | Runtime recovery activated, but below baseline; separate hint ablation is not no-hint Graph evidence |
| Gen15 original | 56 completed, 0 timeout; 5/56 strict | Handoff mechanism effectively did not operate: 0 context rebuilds/composition requests in the original run |
| Gen16 | 48 completed, 8 timeout; 28/48 strict | Digest mechanism; no validated gain |
| Gen17 | 48 completed, 8 timeout; 29/48 strict | Referent materialization observed but no validated gain |
| Gen18 | 50 completed, 6 timeout; 32/50 strict | Corrected re-execution count 0 |
| Gen19 | 48 completed, 8 timeout; 32/48 strict | 2,312 observations mined, 228 failures, 0 repairs/re-executions |

Sources: current `generations/gen_XXX/result.json` files and session checkpoints `S:21792`, `S:30590`, `S:33437`, `S:41464`, `S:42907`, `S:46874`, `S:49382`, `S:52505`. Status: **historical artifact-backed**, but not re-run during migration.

### Gen15 repair-branch lessons

- r1 was stopped after widespread DeepSeek 503; it is invalid infrastructure evidence, not a formal score.
- r2: 12/52 strict; r4: 9/56; r5: 16/56; r6: 12/55; r7: 12/55; r8: 12/54.
- Repairs progressively established seal/rebuild, Phase B delivery, bounded verification compression, and protocol invariants, but task performance stayed poor.
- The result overturned the belief that making a complex handoff mechanism reachable necessarily improves answers.

Sources: session `S:52505`, `S:56491`, `S:59494`, `S:60790`, `S:61923`, `S:63129`, `S:64125`. Status: **historical, completed/invalid status preserved per branch**.

## Invalid or special cases that must remain separate

- G3 attempt 1: DNS/API connection failure; hypothesis not tested.
- G10 original: five pre-model PostgreSQL load failures; original score preserved; repaired view explicitly supplementary.
- Gen15 r1: provider 503 and manual stop; no terminal formal result.
- Official-hint ablation: separate input ablation, not part of no-hint Research Graph evidence.
- Any mixed recovery or selected rerun must not replace the original frozen run.

## G13 bounded sidecar-privacy repair revision 5

The first attempt, `g013_formal_implementation_007` / `g013_formal_implementation_meta_008`, was interrupted after partial edits and tests. It lacks `turn.completed`, `final_raw.txt`, a final child binding, and independent review; it is preserved and excluded.

The clean restart `g013_formal_implementation_008` / `g013_formal_implementation_meta_009` reached terminal completion from the exact revision-4 child. It applied one G13-aware content-blind projection to all persisted open self-observation producers, including the previously missed `tool_action_sidecar`, without changing actual dispatch, non-G13 observations, provider selection, answer/scoring/timeout behavior, or process-local reasoning binding.

- Child tree: `64004f8ef66cb3b8071f8eef1f0bd48b3b0bdf931b64e95467c7412a591ef218`.
- Manifest: `98424bc0d4d257c82997d348f45bea0d5924e94d9aac323eb1506725ad68a2cd`.
- Independent review: `2e320a6a2a40cc6b6da8c7d71c114145cd434c09aa9c4742ad833776a176887b`.
- Focused G13+G7: `100 passed`.
- Candidate full: `218 passed, 5 failed`; G7 parent: `153 passed, 5 failed`; identical inherited nodeids, new failures zero.
- Independent privacy replay: 768 files, zero exact sensitive sentinel hits, zero persisted `reasoning_content` fields.
- Attempt-006 probe SHA-256: `fa81cf06c15847b90ac3c61c5b6ddfb5443679ac43df56c6ef6597f696785edd`; driver SHA-256: `eeb8f047f1a0569c5aa70f78acffca022e074881988140046fa71a79a7a6e2a2`.

Status: **source/privacy admitted; runtime admission 006 prepared but not run; no formal evaluation or launch**.

## G13 no-benchmark runtime admission 006

- Artifact: `experiments/research_graph_baseline_20261016/g013_admission_006`.
- Binding: revision-5 child `64004f8ef66cb3b8071f8eef1f0bd48b3b0bdf931b64e95467c7412a591ef218`, manifest `98424bc0d4d257c82997d348f45bea0d5924e94d9aac323eb1506725ad68a2cd`, independent source review `2e320a6a2a40cc6b6da8c7d71c114145cd434c09aa9c4742ad833776a176887b`.
- Real provider: three automatic DeepSeek calls; one accepted model-authored carrier; one exact visible opaque-token copy; one delivered directive; post-view action `consistent/acquire_evidence`.
- Passed subgates: fault fixtures, enabled/disabled inertness, native reasoning continuity, frozen source, `100 passed` focused tests, zero prohibited actions or mutations, and zero persisted `reasoning_content` fields.
- Full tests: candidate `218 passed, 5 failed`; G7 parent `153 passed, 5 failed`; failed-nodeid arrays are exactly equal, so the five failures are inherited. The driver incorrectly returned an indeterminate new-failure count because it hard-coded the older `216 passed` count.
- Blocking privacy result: six exact sensitive-token hits in the single remote-isolated `record_self_observation` row of `provider/tool_calls.jsonl`: three token slots under `args.freeform` and the same three under `val_args.freeform`. The source path proxy was bypassed by upstream built-in `open(path)`. Raw values were not exported to the research artifact.
- Admission result SHA-256: `bed421c07aff99debbc948ff31877069c71ca25f3de26ce3e7aba5294bb57f54`.
- Privacy scan SHA-256: `4e929311b420f041fed9293157cce03cb62d70c8c89ccfd4edcee388d877a06d`.
- Independent failure review SHA-256: `4227f8bfb97d5e59cdd727ee0d65fc7d28e25abf2ffbbe6aed7dc8105f1e3b39`.
- Execution boundary: no benchmark, database, formal evaluator, launch claim, Graph mutation, or candidate mutation; no residual matching remote process.

Status: **blocked by a confirmed raw tool-log persistence failure; formal launch prohibited**.

## G13 bounded BaseTool persistence repair revision 6

- Artifact: `g013_formal_implementation_009`; terminal Meta: `g013_formal_implementation_meta_010`.
- Child tree: `31277b0514798b52b7547bb5cc12900c63d556fca0fc4919bff0b8be4902322c`.
- Manifest: `d8bd9714718343c51b30290e4ab1b8c8db5a077543a128f163cd48c34e36b5e1`.
- Independent review: `095d36fa7b32a4f0b4b9f6bb048dffacacb9274574b8d993ac4566dee4629880`.
- Repair: only the G13-active record tool passes a content-blind argument copy to inherited `BaseTool.exec`; exact model-authored carrier validation and execution remain transient. The validated row is projected before built-in-open serialization. No global builtins patch, upstream edit, or non-G13 behavior change was made.
- Independent tests: focused G13+G7 `102 passed`; candidate `220 passed, 5 failed`; parent `153 passed, 5 failed`; exact shared failed-nodeid set and zero new failures.
- Independent privacy scan: 773 external materialized files, zero exact sensitive-token or persisted `reasoning_content` hits; candidate generated state zero.
- Admission 007 tooling is prepared with exact hash bindings and pass-count-independent failed-nodeid comparison. No provider, benchmark, database, formal evaluator, launch, or Graph mutation occurred in this revision.

Status: **source/privacy admitted; runtime admission 007 prepared but not run; no formal evaluation or launch**.

## G13 no-benchmark runtime admission 007

- Artifact: `experiments/research_graph_baseline_20261016/g013_admission_007`.
- Binding: revision-6 child `31277b0514798b52b7547bb5cc12900c63d556fca0fc4919bff0b8be4902322c`, manifest `d8bd9714718343c51b30290e4ab1b8c8db5a077543a128f163cd48c34e36b5e1`, and source review `095d36fa7b32a4f0b4b9f6bb048dffacacb9274574b8d993ac4566dee4629880`.
- Real provider: three automatic DeepSeek calls; one accepted model-authored carrier; one exact visible opaque-token copy; one directive; post-view action `consistent/acquire_evidence`.
- Passed subgates: explicit missing/malformed/truncated/provider-rejected fail-closed fixtures, native reasoning continuity, enabled/disabled inertness, one-action/deadline limits, zero prohibited actions or mutations, frozen source hashes, and privacy/export isolation.
- Privacy: zero sensitive-token and zero persisted `reasoning_content` hits across the five scanned remote surfaces. Raw synthetic context remained in the remote scratch and was not exported.
- Independent replay: focused `102 passed`; candidate `220 passed, 5 failed`; parent `153 passed, 5 failed`; identical five inherited failed nodeids and zero new failures.
- Admission result SHA-256: `2f1759d93ef77337e88a501b7b286b381fb4860ef421dfe94f32ef84741bae5e`.
- Privacy scan SHA-256: `a3f51902ed2d7020aaf9bf8fd85bd0b7d0091f32a3cfe8c29bb430ccbec61445`.
- Independent review SHA-256: `8d499cd636b651dc30faf7b83b8bc0180a2d599f2650f6246898025233926341`.
- Execution boundary: no benchmark, database, formal evaluator, launch claim, Graph mutation, or candidate mutation; no residual matching remote process.

Status: **bounded no-benchmark runtime admission passed and independently reviewed; formal launch readiness remains a separate gate**.

## G13 formal run 001 launch and active checkpoint

- Remote attempt: `/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g013_formal_001`; run ID `g013_requirement_coverage_nohint_56_v1`; PID `709990`.
- Immutable launch bindings: claim SHA-256 `b3ec584af47e8f680b1ed085ebc7a01d2aedd84e1d0bf716b3cbb7a772e2facb`; launch manifest SHA-256 `7d9a854b4eb3c3bedf4918a1041701b4d78a9156659291c2c5b2805ec19b85a7`; finalizer binding SHA-256 `4e59acae484ac070c39f85b57a516eb4a06f82bf1a1fd996313e9964b56a4dcc`.
- Prepare-only SHA-256 `e3873e96c3fa536e2fcff351d1e789e6897e9df6dd5b44327677791cb42d1572`: exactly 56/56 tasks prepared, `base_no_hint`, one arm, 1200 seconds per task, four workers, same-family serialization enabled. Launch free space was `16,694,403,072` bytes.
- Provider-route boundary: the expected bundled Python SHA-256 `b07b03b9ba866a341a3c13ee69710fbc8d43d4ce2523dee13f6df5c25378d15b` changed to `7c4ee3011932a75b30db176f35fb91b28f0b299e608eaf643fb1bf36ed5ace99`. Codex and PowerShell bindings still matched. Because the formal evaluator does not invoke Meta/Codex, a bounded formal-provider-only review was recorded in `g013_formal_001/formal_provider_route_review.json`; it does not change or waive the Meta runtime binding.
- Active checkpoint at `2026-10-21T04:26:23Z`: `8/56 completed`, runner active, summary absent, `16,491,847,680` bytes free, exactly one launch claim. No failure or timeout had appeared in the content-blind status counts at that checkpoint.
- Monitoring/export boundary: the monitor reads only statuses, counts, hashes, scheduler state, and disk. It does not read task identity or raw content. Do not duplicate or restart the run. After natural exit, require 56 terminal progress and summary rows before invoking the bound finalizer once; export only `postrun/` content-blind artifacts.

Status: **formal run launched and active; outcome unknown.** No score, formal Evidence, mechanism endpoint conclusion, promotion, or closed G13 Graph is claimed by this checkpoint.

## G13 formal run 001 terminal state and finalizer failure

The one authorized runner exited naturally at `2026-10-21T06:08:12Z`. Content-blind monitoring recorded exactly 56 terminal rows, partitioned as 52 completed and 4 task timeouts. It observed no duplicate launch or non-task infrastructure status. The immutable terminal files are:

- progress SHA-256 `c6750f0d2d127d817dbfa76e4f79e1b1609527baa0f77826918b79296d5202f2`;
- summary SHA-256 `1e05433f487322b642316548b93d168c6a7ad6c405e796da88cf8cc426b3478c`.

After the runner became inactive and the exact-56 precondition passed, the bound finalizer was invoked exactly once. It exited 1 before entering its binding, exact-56, privacy, or Evidence gates. The frozen `load_module()` dynamically loaded `source/experiments/g013_evidence_extractor.py` without adding `ATTEMPT/source` to `sys.path`; that module's absolute import of `experiments.g013_requirement_coverage` raised `ModuleNotFoundError`.

Read-only diagnosis verified matching deployed hashes for finalizer `3ef3d9c2e8c1886683daf410aa57863b2d4069a967adaf6b90d902f3a00be428`, finalizer binding `4e59acae484ac070c39f85b57a516eb4a06f82bf1a1fd996313e9964b56a4dcc`, extractor `59c25c1235a78bc410d613a14ec750a665c1a13760c1ab99c8b489731fe29ebd`, and requirement module `4312c9607020872a0fa853f2840b158b7eb9c0da1199e7f69e90763efd68f929`. Without a source-path binding, `experiments` did not resolve; with the exact deployed source root supplied, it resolved to the frozen module. This is a finalizer launch-environment defect, not evidence that the formal evaluation or frozen extractor changed.

No `postrun/` directory or derived artifact was produced. The strict score, privacy gate, formal Evidence, mechanism endpoints, closure input, and promotion remain unknown. No formal evaluation was rerun, no finalizer retry occurred, and no Graph mutation or G14 work started.

Status: **formal execution terminal; first bound finalization rejected before gates; recovery requires a separately bound and independently authorized invocation environment.**

## G13 finalizer recovery attempt 002 (2026-10-21)

- Scope: one environment-only recovery invocation after the first finalizer failed before gates. Formal evaluation was not rerun; frozen source, extractor, finalizer, summary, and progress were unchanged.
- Recovery input: exact frozen source root supplied as `PYTHONPATH`; finalizer SHA-256 `3ef3d9c2e8c1886683daf410aa57863b2d4069a967adaf6b90d902f3a00be428`; summary `1e05433f487322b642316548b93d168c6a7ad6c405e796da88cf8cc426b3478c`; progress `c6750f0d2d127d817dbfa76e4f79e1b1609527baa0f77826918b79296d5202f2`.
- Result: original finalizer generated a complete content-blind six-file postrun set and reported `complete_pending_independent_review`.
- Draft outcome: 31 strict pass, 18 known strict fail, 3 completed strict-verdict unknown, 4 timeout, 0 other terminal failure; fixed denominator 56.
- Draft mechanism result: 0 records, 0 accepted records, 0 directives, and 0 consistent/contradictory actions; all mechanism endpoints `untested`.
- Draft privacy: passed, with no raw run tree copied to the research export. Independent review remains mandatory.
- Hashes: terminal receipt `a9f7ad3152116cd8b117f7705980b289f785f26fe0146258669f54c19e141b62`; Evidence draft `cca47010fe711b2de4aa4f190fcd4d415d47baa59d7016c396ad1c6c5a3797f5`; specialized Evidence `5961a68f3641380b717f07c09792c2d904ccf2827b7e56492e6ca60f12576afb`; outcome `c4bdcb7f23682d286b15e5003ff6ba9dc74413564220e04157954c1cab5f29f3`; privacy `0e18d16a35ee581e7cab5ed4b17185fe1bfde9c852846eb7f6000d1cf067f1b3`; closure draft `b146f7aeb62159b144aa2b1e1b26ccc631ae27eec349de3b1d640d81cffe4b69`.
- Recovery anomaly: the outer command wrapper returned 1 after the original finalizer completed because PowerShell interpolation corrupted the shell exit-code capture. The preserved finalizer stdout reports completion, stderr is empty, and the finalizer was not invoked again.
- Binding anomaly: the exact interpreter path was used and later observed at expected Python SHA-256 `3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66`, but its SHA was omitted from the pre-execution recovery binding. This remains an explicit independent-review item.
- Status: **recovered drafts produced; pending independent review; no Graph closure or G14 work**.

## G13 independent Evidence validation and Graph closure (2026-10-21)

- Independent review verified the unique launch, 56 terminal rows, frozen hash chain, six postrun files, and privacy boundary. It accepted the wrapper exit-code anomaly as a transport capture error after finalizer completion and retained the non-pre-bound interpreter SHA as a procedural limitation.
- Formal outcome: 31/56 strict; 31 strict pass, 18 known strict fail, 3 completed strict-verdict unknown, 4 timeout, and 0 other/provider/infrastructure terminal failure.
- Mechanism result: 0 record attempts, accepted records, directives, views, or actions. Structural binding, authorship, coverage-state behavior, behavioral action choice, and overall status are `untested`.
- Safe snapshot: review SHA-256 `3e6249178e8a5aedcd88023468e8da8c361402d40d9207284cdd0202d4fb72c7`; Evidence `8dfdcaa180e2641475e5c481f98f612f788eea6f8bd82070f87bd85b4f83bcb7`; Graph `a231eff12aad1d850b79b89e791bd1c8bd8d43d4941ff28c684cc8a4ff2b32b6`; closure receipt `d77aa4e00511992ef78bc0b884faec047073dba5d4118807f6839c5f1a27a480`.
- `research_graph_memory_v17.json` SHA-256 `176d91bca69138088353be80735c9ce8c93d36bf8b661ca57d10cd3bf88cd648` contains formal G0-G13, preserves 27 incubation nodes, and adds only the G13 target-to-experiment promotion edge.
- Status: **formally evaluated, independently validated, and closed; mechanism untested; no G14 work started**.

## G14 Research Meta solution-loop selection (2026-10-21)

- Packet: `research_graph_solution_loop_meta_packet_g014_v1.json`; SHA-256 `0e4525b5f8378f536eb68fa36125d076f319b08ecd6dc60a80625a4824711b04`; G0-G13, 28 symmetric facts, 27 incubation nodes, 14 verified parents.
- Attempt 001: stopped before provider invocation because the bundled Python hash differed from the frozen Meta runtime binding. No Research Meta output exists for this attempt.
- Runtime rebind: only the bundled Python hash changed from `b07b03...d15b` to `7c4ee3...ace99`; Codex, PowerShell, route, profile, catalog, and policy remained bound. Audit: `g014_meta_runtime_rebind_001/audit.json`.
- Attempt 002: provider-complete JSON, raw SHA-256 `27a11e301d206b007d23663f75ffa93b56a0c5f3688ea389e44f36e105ac4642`; invalid only because `feasibility_after_selection.minimum_de_risking` was a string instead of an array. A pure in-memory shape probe found no later validator failure; this did not validate its research content.
- Attempt 003: one mechanism-neutral complete-object schema revision; passed the unchanged validator. Raw SHA-256 `5a5d53429db99b5437bb4ac5aff3a34c4f34386cc3fc67872daf0609e8f0c7ad`.
- Selected mechanism: `mech_progressive_query_probing`; primary lens `action_tool_policy_recovery`; state `interface_investigation`; code parent not frozen.
- Memory: `research_graph_memory_v18.json`, SHA-256 `51c2283f77db70185790b6d660e6b00d3c55a83ed2523d3a27746554cac3fe8b`; appends `research_target:g014:001` only.
- Boundary: no implementation, provider task run, benchmark, database access, formal launch, or score claim occurred.
- Status: **valid G14 Research Meta target selected; bounded no-task interface investigation required**.

## G14 interface investigation 001 and rejected-finding append (2026-10-21)

- Revision manifests: SHA-256 `8f8c42f0997f78f637d549f37abae9d165200bc0eae5697b1002814433d38ee4`, `d4c9b6ed8cc4f73b90455b29145172b644d8ff53cfb718b5aa3d9f9d83f0b5ad`, and `22d1e78f44c54fd2143b758c473d3eb677f8c087b208009618d71233d9c4a04b`.
- Scoped suites passed 40, 64, and 100 tests respectively, but independent reviews found bool/int and caller-bound bypasses, direct dataclass-construction bypass, and numeric-subclass comparison bypass.
- Final review: `rejected_bounded_stop_return_to_research_control`; SHA-256 `c4c8c947b0a2b04ad0b822b50693c44f0f5206014e20fcd8a1b9118993766a51`.
- A direct script invocation failed before mutation with `ModuleNotFoundError: No module named 'experiments'`. After review, one module invocation used the unchanged finalizer and the exact bound v18/review/manifest hashes.
- Result: `research_graph_memory_v19.json`, SHA-256 `6415bd199798b4c54100afdb81874bd2eca5049a8e24a8aca4ed6694f3f74504`; 14 formal generations, 30 incubation nodes, 48 incubation edges. Formal layer and cross-layer edges are unchanged from v18; deterministic validation passed.
- No provider, benchmark, database, server, formal candidate, or formal experiment operation occurred.
- Status: **rejected finding recorded; awaiting a new post-interface Research Meta decision**.

## G14 post-interface Research Meta selection (2026-10-21)

- Packet: `research_graph_solution_loop_meta_packet_g014_post_interface_v1.json`, SHA-256 `d492489c4fdea1a96dde961aaf056e46082c3ac2023200d333ac7f141eeea19b`; 14 formal generations and 30 incubation nodes.
- Exactly one provider call ran through `deepseek-standalone-dab` / `deepseek-flash`; no retry occurred. Usage: 113,131 input, 4,736 cached input, 20,339 output, and 12,146 reasoning-output tokens.
- Raw output SHA-256 `9bc2052b7086ba9339d6b89868ba7531c4ffbdb349e1cdccace43199a494d85c` failed only because `minimum_de_risking` was a scalar string. A recorded one-item-array normalization passed the full validator; final SHA-256 `087017c5d3cea41538d0715fbb3f672b239bdc6b1cd750b13a67108b4cb59226`.
- Selected `mech_discriminating_observation_portfolio`, primary lens `hypothesis_search`, state `interface_investigation`.
- No Implementation Meta, benchmark, database, server, candidate, admission, or formal evaluation action occurred.
- Status: **validated research target; interface investigation required**.

## G13 intent-first paired prepare-only (2026-10-21)

- Purpose: test G13's requirement/evidence planning intent without its carrier, sidecar, self-observation, evolved-helper, or admission interfaces.
- Frozen exploratory batch: `g013_intent_first_smoke_v1_20261021`, SHA-256 `2760ab461936334cd683244964b2e31868e3a341a7be50fe23584d81e6123242`. Stage 1 selects only `crmarenapro/query1`; answer correctness was not used for selection.
- Pair controls: base/no-hint, 20 turns per arm, one worker, one application attempt, zero SDK retries, observer skipped, helper and self-observation tools disabled. Only the policy differs.
- Offline verification: 11 tests plus 2 subtests passed. Both prepare-only arms completed with status `prepared` and identical controls. The first local attempt failed before child execution with `WinError 193`; binding the current Windows Python fixed it.
- Budget: hard ceiling 40 model turns for the real pair; historical baseline 11 calls; historical token count unavailable.
- Boundary: **no model/provider, database, remote-server, benchmark, strict evaluation, or formal Graph action occurred**. Await quota-safe authorization boundary before real execution.

## G13 intent-first Stage-1 paired execution (2026-10-21)

- Task/protocol: `crmarenapro/query1`, base/no-hint, DeepSeek Flash, 20 turns per arm, one worker, one application attempt, zero SDK retries, observer/helper/self-observation tools disabled.
- Invalid v1: both arms failed before any model/tool call with `ModuleNotFoundError: No module named 'adapters'`; this is preserved as an infrastructure failure and excluded from comparison.
- Valid v2 baseline: strict pass, `return_answer`, 12 model calls, 15 tools, 85,609 total tokens; 8 `query_db`, 6 `execute_python`, 1 `return_answer`.
- Valid v2 intent-first: strict pass, `return_answer`, 9 model calls, 12 tools, 70,621 total tokens; 9 `query_db`, 2 `execute_python`, 1 `return_answer`.
- Paired difference: strict tie; intent-first used 3 fewer model calls, 3 fewer tools, and 14,988 fewer total tokens (-17.51%), but 870 more completion tokens.
- Behavioral observation: after similar initial probes, intent-first used targeted database evidence queries where baseline performed repeated Python extraction. Both retained redundant early broad/bounded probing.
- Evidence boundary: **one task and one stochastic sample per arm support feasibility and a trajectory difference only; they do not establish accuracy gain, general efficiency, or a causal reinterpretation of formal G13**.
- Artifacts: `experiments/g013_intent_first_eval_20261021/paired_result_summary.json` and `RESULT.md`. No Graph mutation, Meta call, additional panel task, commit, or push occurred.

## G13 intent-first three-task small-scale panel (2026-10-21)

- Valid pairs: `crmarenapro/query1`, `PATENTS/query1`, and `civic_unstructured/query1`; identical base/no-hint 20-turn controls with only the policy changed.
- Aggregate: baseline 1/3 strict, 49 model calls, 62 tools, 896,475 total tokens; intent-first 1/3 strict, 49 model calls, 62 tools, 1,086,425 total tokens. Intent delta: +189,950 tokens (+21.19%), no strict gain, one fewer returned answer, one additional turn-cap termination.
- CRM: pass/pass; intent-first used 70,621 versus 85,609 tokens and showed more targeted evidence acquisition.
- PATENTS: fail/fail; baseline returned at 17 calls and 344,315 tokens, while intent-first hit 20 calls and 602,026 tokens. Invalid PATENTS v1/v2 pre-model infrastructure failures are preserved and excluded.
- Civic: fail/fail at 20 calls; intent-first used 413,778 versus 466,551 tokens but ended with eight consecutive Python actions and did not converge.
- Stop: `agnews/query1` was not run under the announced cost guard after two hard-task failures established the non-convergence boundary.
- Status: **small-scale evidence rejects a 56-task run of the current policy**. No formal Graph mutation, Meta call, commit, or push occurred.

## G13.1 convergent-policy matched replay (2026-10-21)

- Design: candidate-only replay on the three frozen panel tasks; same base/no-hint, DeepSeek Flash, 20-turn, one-worker, one-attempt, zero-SDK-retry controls. Frozen baseline artifacts were reused to avoid another 896,475 control tokens.
- Aggregate: 1/3 strict, 2/3 returned answers, 39 model calls, 56 tools, and 663,391 total tokens. This is -26.00% versus the frozen baseline and -38.94% versus G13 intent-first, with no strict gain.
- CRM: strict pass, `return_answer`, 7 model calls, 12 tools, 50,407 tokens.
- PATENTS: strict fail, `no_tool_call`, returned answer, 12 model calls, 22 tools, 269,272 tokens, answer F1 0.5976.
- Civic: strict fail, `max_iterations`, no answer, 20 model calls, 22 tools, 343,712 tokens; 15 `execute_python` calls violated the policy's normal three-call guidance.
- Interpretation: prompt-level convergence guidance shapes cost on some tasks but is not an enforceable controller. A runtime action/synthesis budget is the next bounded mechanism.
- Artifacts: `experiments/g013_intent_first_eval_20261021/g0131_small_scale_summary.json` and `G0131_SMALL_SCALE_REPORT.md`.
- Status: **reject 56-task scaling; no fresh paired replicate yet**. No formal Graph mutation, Meta call, commit, or push occurred.

## G13.2 Civic runtime-budget closure (2026-10-22)

- Classification: non-formal, candidate-only exploration; not admission and not G14 Evidence.
- Remote root: `/srv/text2sql/evolution_runtime/g0132_budget_eval_20261022`; run ID `g0132_civic_q1_v1`.
- One bounded read-only verification found PID `767770` absent and the run summary status `completed`; no signal, retry, provider call, or new run occurred.
- Model calls, tool calls, tokens, cost, process exit code, and strict result remain unknown because no such fields were emitted by the bounded aggregate scan.
- Closure manifest SHA-256: `497c137b3c390023021a203bcf4063d9375c45b5cf2c3675cd954d1e911dff61`; receipt SHA-256: `e3583435be166da2fd8930e0ba81477eb78bdf3d226b3dd6bb5105927b09d214`.
- Status: **closed and preserved; no causal-benefit claim**.

## Controller-authored G11-G13 mechanism synthesis (2026-10-22)

- Inputs: immutable formal G11, G12, and G13 manifests, Evidence, summaries, and bounded aggregate trace artifacts; no raw full-log or full-trace ingestion.
- Proposed loop: G11 revisioned lifecycle -> G13 requirement/observation coverage -> G12 uncertainty/fault classification and one bounded action view -> model action -> revision.
- Evidence manifest SHA-256: `2734f865f1516bb34d7d0e2e6a472337f54a0097d2586e21379eb3e9394de8ed`; intent draft SHA-256: `434da42dd62e7d7d2254eabb09e8c289ff239fd62ccfde123b9b6fafd7e81144`; implementation contract SHA-256: `a346f79c0035c6d7a591918cca37d2044fbb7a95e693bafcda01054e790312f8`.
- Boundary: controller-authored draft only; not Research Meta, Graph mutation, admission, implementation, benchmark, or causal evidence.
- Status: **accepted for isolated implementation and local contract testing**.

## Integrated G11-G13 candidate local implementation (2026-10-22)

- New candidate module, launcher, compact policy, focused tests, and minimal runner/analyzer/evidence-pack telemetry wiring were implemented against the accepted contract.
- Provider-free focused suite: 25 passed. Focused plus current G13/G13.1/G13.2/batch-runner regression selection: 45 passed.
- Two archived snapshot collections failed before candidate execution because the archived copies omit package roots or generated fixtures; no retry occurred and they are excluded from the regression claim.
- Implementation manifest SHA-256: `993d3fe1f62948291554959eb16ac7b329050a4ca53afd48335d1290542f0223`; validation manifest SHA-256: `20d6606eb8dcdebb2c2f36439805d986ef5fe9b89a9911f1306b235d58034865`.
- Boundary: no provider, database, benchmark, admission, formal evaluation, Meta call, or Graph mutation.
- Status: **local contracts pass; pending independent source/privacy/contract review**.

## Integrated G11-G13 candidate independent review 001 (2026-10-22)

- Status: `rejected`; review stopped before pytest after mandatory P1/privacy/invariant findings.
- Findings: invisible provenance accepted; telemetry export not strict-schema fail-closed; repeated installer can nest controllers; activation-miss recorder not invoked.
- Review JSON SHA-256: `c753a9983ff7084908d95eb8b631b29558be855b88e5785113cc600db21280a4`; review Markdown SHA-256: `10961f0e2f458b4e21421c90788d2b3ccc7052bed0b21ae62de4e2ec217fbb29`.
- No provider, database, benchmark, Meta, Graph, admission, or formal-evaluation action occurred.
- Status: **repair required; external evaluation prohibited**.

## Integrated G11-G13 candidate repair 001 (2026-10-22)

- Fixed only review findings F01-F04: visible provenance, strict telemetry schema, installer idempotence/conflict rejection, and exact activation-miss recording.
- Provider-free focused suite: 38 passed; selected current-mainline regression suite: 58 passed. Complete outputs and exit codes are stored under `experiments/g011_g013_integrated_implementation_20261022/repair_001/`.
- Repaired source SHA-256: `c16b09d13f30acb8aa6539d7993d1c9cf30f94f75f0b430371d1449fd60f79a7`; repair manifest SHA-256: `7e919fc80c8bbdcbd93653cf8d80026bab42929b7e91e01f215cde46ccafe5c4`.
- No network, provider, database, benchmark, Meta, Graph, admission, or formal-evaluation action occurred.
- Status: **locally verified; superseded by accepted independent review 002**.

## Integrated G11-G13 candidate independent review 002 (2026-10-22)

- Scope: independent source/privacy/contract review of repair 001, including F01-F04, runner/analyzer/evidence-pack wiring, disabled inertness, no forced action, and privacy/no-leak behavior.
- Hash gate: all six authoritative inputs and all three unchanged wiring files matched their declared SHA-256 values.
- Findings: F01-F04 are `resolved_verified`; no new P0/P1 or privacy/protocol/invariant issue was found.
- Provider-free execution: the focused suite passed 38/38 and the selected current-mainline regression suite passed 58/58; each declared command ran exactly once and complete outputs were preserved.
- Artifacts: review SHA-256 `ff901bc92c30702f59f0e76c533500be3f4a30bb663097e0abed3bef647a657d`; validation SHA-256 `36a26e2a45bfc0c06e02bb54c0e89a75804b97e5d1bf719ad8c564c77407e527`; artifact inventory SHA-256 `f5195fda889d081d16234aaeec0aa11cbe4ccc2e479a3106e0a5d040f143085e`.
- Boundary: no network, provider, SSH, database, benchmark, Meta, PATENTS, Civic, six-question panel, frozen-56 run, commit, push, or Graph mutation occurred.
- Status: **accepted local engineering gate; next freeze the six-question small-panel manifest and protocol without executing it**.

## Integrated G11-G13 six-question panel freeze (2026-10-22)

- Source selection: exact G13 56-task manifest SHA-256 `576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7`; completed summary SHA-256 `1e05433f487322b642316548b93d168c6a7ad6c405e796da88cf8cc426b3478c`.
- A read-only content-minimized mapping verified 56 unique indices and the G13 `31 strict pass / 18 known strict fail / 3 strict-verdict unknown / 4 timeout` partition without exporting task identifiers, task text, answers, messages, or tool content.
- SHA-256 cohort ranking selected zero-based indices `18,21,27,37,38,41`, satisfying the exact `3 fail + 1 unknown + 1 timeout + 1 pass guardrail` quota.
- Frozen protocol: base/no-hint, DeepSeek Flash, same provider/database/evaluator family, 1200 seconds per task, one worker, one candidate attempt, one model attempt per turn, zero SDK retries, no second arm, and the exact contract go/no-go metrics.
- Freeze manifest SHA-256: `c09f2577f587e654f9aabe5aa3dcc1c28a202962432f87336045c31ae3eff0c1`; validation SHA-256: `3e8966f483a70beb9c381d41e00811872eda938114f4376a060e53fd68f25b37`; artifact inventory SHA-256: `2476e06d4d101987e7729fa30ac31e23d177a05d503a3c4136b8ea3a1899c467`.
- Launch-readiness finding: the current generic multi-query runner does not enable the integrated child path. An isolated reviewed batch launcher and provider-free prepare-only gate are required before execution.
- Status: **selection and protocol frozen; no prepare-only, provider, database, benchmark, panel, Meta, Graph, commit, or push action occurred**.

## Integrated G11-G13 panel runtime repairs and pause (2026-10-22)

- Attempts `001`-`005` remain preserved and invalid for expansion: credential transport, pre-task database reload, an upstream metadata bug, and an unbounded PostgreSQL statement each prevented a complete qualifying panel.
- Receipt-bound preloading fixed the reload boundary. Panel `006` completed two rows, then its third child hit the 1200-second run wall after a successful preload; a read-only probe established that upstream's explicit PostgreSQL URL options had overridden batch `PGOPTIONS` and left `statement_timeout` at zero.
- Repair `002` binds the existing 300-second statement limit directly to the upstream query/list connection URL. The local focused launcher/preload suite passed 20/20 and the remote read-only tool-path probe confirmed enforcement.
- Panel `008` began after the repair and produced two completed rows, then was terminated by the user's request to pause this line. It is incomplete, not a panel result, not admission Evidence, and does not authorize a 56-task run.
