# Current Research State

> Cold detailed record. Do not read this file during default session startup. Start with `CURRENT_STATE_BRIEF.md` and use `MEMORY_INDEX.json` for targeted retrieval.

Verified on 2026-10-21. This file is a state snapshot, not permission to run an experiment.

## Repository

- Branch: `repair/patents-feedback-analyzer-v4`.
- HEAD: `2ec626da9bdfb9982bc2f1358b7047f1041a8373` (`checkpoint DAB research graph through G12 admission`); the configured upstream was independently verified at ahead/behind `0/0` after push.
- Worktree before this documentation phase: 823 status entries: 20 tracked changes and 803 untracked paths.
- Most September/October research artifacts are untracked; Git history alone is not the research record.
- Do not reset, clean, checkout, commit, or push as part of memory restoration.

Status: **verified** from Git. Conflict note: root `CURRENT_STATE.md` and `PROJECT_HANDOFF.md` describe the older 17-task campaign as current; they were accurate on 2026-10-10 but are now stale relative to `experiments/research_graph_baseline_20261016/`.

## Authoritative research boundary

G0-G13 in `experiments/research_graph_baseline_20261016/` have completed four-node Graphs. The fixed metric is strict pass over all 56 frozen tasks; 1200-second timeouts are failures and do not shrink the denominator. Missing completed-task strict verdicts remain unknown.

The best observed score in this line is G6: 37/56 strict. It is an unpaired observation, not a proven causal improvement. G8, G9, and G11 each recorded 35/56. G11's mechanism was **untested** because all 53 completed tasks had zero model-authored records and zero guidance binding.

Evidence: G0-G13 evidence JSON files; especially `g006_safe_snapshot/g006_evidence.json`, `g011_solution_loop_safe_snapshot/g011_solution_loop_evidence.json`, `g012_safe_snapshot/g012_evidence.json`, and `g013_safe_snapshot/g013_evidence.json`. Status: **formally evaluated and artifact-verified**.

## G12 current state

Selected mechanism: `mech_uncertainty_typed_evidence_state_and_gap_action`.

Research progression:

1. Research Meta selected an interface investigation target.
2. Interface investigation 1 passed 26 no-task tests and established a bounded substrate, while leaving the action interface open.
3. Interface investigation 2 passed 41 no-task tests and verified a conditional structured action/status/opaque-target interface; real-model behavior remained unknown.
4. Post-interface Research Meta produced an `experiment_ready` specification.
5. Formal Implementation Meta produced a local candidate patch.

Current implementation manifest:

- Path: `experiments/research_graph_baseline_20261016/g012_formal_implementation_002/candidate_patch/implementation_manifest.json`.
- File SHA-256: `20d71e71ddfdae7f6a23001407d46c9a718ada6572f055e4ea3d60d258579516`.
- Status: `no_task_implementation_complete_formal_admission_blocked`.
- Tests recorded in the manifest: 149 passed full inherited+G12 suite; 33 passed focused G12 suite.
- Source surface: 37 files; 28 unchanged parent files, 2 modified files, 7 new files.
- Independent recheck during migration: 37/37 individual hashes matched and combined surface SHA matched `686adca6d2303c432ed7cf9251a49a42a492dcef75469a7f4c78db8f3813a1ca`.
- No provider call, network request, benchmark access, deployment, launch, Graph promotion, score claim, or formal run occurred.

Status: **locally implemented and independently hash-verified; not admitted; not formally evaluated**. Evidence: the G12 manifest, both `independent_verification.json` files, `research_graph_memory_v11.json`, session `S:90137`.

Subsequent deterministic source admission and bounded runtime admission now add:

- Complete parent tree SHA-256 `7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac` and child tree SHA-256 `47dbf42636bbaa234c5f58256a37821a2ac891d29b34fcce13fe350207e7e344` were rechecked after the runtime probe.
- Source admission recorded 149 focused passes. The complete child suite recorded 302 passes and the same five inherited failures as the 269-pass parent control.
- `g012_admission_005` passed the bounded no-benchmark runtime gate against the real DeepSeek provider and real upstream DataAgent boundaries in 3 provider calls: one schema-valid record attempt was accepted, one genuine visible reference resolved unique, exactly one strict G12 directive reached provider call 3, and the first classified action was `consistent` / `acquisition` for `action=acquire_evidence`.
- The directive fields matched the runtime sidecar exactly: `reason=empty_step`, `record_status=accepted`, `target_scope=step`, opaque `target=step_2`, `target_status=none`, `category=evidence_gap`, and `freshness=current`.
- The programmed enabled/disabled control preserved dispatch arguments/results, termination, final result, and LLM-call count outside the directive channel. It recorded no scoring execution, forced answer, wall-timeout extension, or mechanism-initiated tool call. Timing is measurement-only, not a strict equality claim.
- G12 sidecar, summary, and receipt scans passed. Base `llm_calls.jsonl` and `final_agent.json` contain raw synthetic context but remain isolated in the remote scratch and were not copied into the research artifact or read by the research export.
- Failed probe/preflight attempts 002-004 are preserved. Attempt 002 was an invalid probe result, and attempts 003-004 stopped before any provider call.

Status before formal execution: **bounded no-task runtime admission passed**. Evidence: `experiments/research_graph_baseline_20261016/g012_admission_005/`.

The separately authorized, unique formal attempt then completed in `experiments/research_graph_baseline_20261016/g012_formal_001/`:

- Frozen child tree `47dbf42636bbaa234c5f58256a37821a2ac891d29b34fcce13fe350207e7e344`, frozen task manifest `576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7`, and launch manifest `f63ada35052b8d08ca6186ab2658ca3483f78f9b8c400b529dad9a883f5ce93c` were bound before launch.
- The single fixed base/no-hint 56-task run naturally ended: 51 completed, 5 runner wall timeouts, 0 other or detected infrastructure failures; 30 strict pass, 18 known strict fail, and 3 completed strict-verdict unknown. Primary result: **30/56 strict**.
- Across the run there were 0 model-authored record attempts, 0 accepted records, 0 visible unique references, 0 directives, and 0 consistent or contradictory post-directive actions. Structural binding, real-model adoption, and behavioral action choice are all **untested**, not failed or confirmed.
- The content-blind export audit passed: no task identifier, answer, hint, validator, raw message, SQL/tool argument/result, trace, or credential was exported. Raw execution context remains only in the isolated remote run tree.
- Deterministic Evidence and Graph-closure drafts were independently reviewed. Review SHA-256: `50362d00554887ee9c43ea0c44627b3686cc193c641d1d6911412a031b759764`; terminal receipt SHA-256: `86ac90a7b925daf58a7f9453619cad258b0df54c4ba4f1ffb3d064a6821a8fb1`.
- The review corrected one documentation error: 1,381 is `recorded_llm_call_count`, while the five specialized-Evidence cohorts sum to 0 `guidance_suppressed_no_state_count`. It also records that `formal_run_performed=false` and `evaluation_run=false` in the specialized extractor are mechanism-only/no-claim fields; the receipt and Evidence draft jointly establish formal completion.
- G12 Evidence SHA-256 is `5030d3901b764624053f0d5147257b2bb5ea24386e5231f4029e7fc547801bdd`; four-node Graph SHA-256 is `790282ece9c81abad1b239c629cd622681162fcf94523b45c81df9de0fae9076`; `research_graph_memory_v12.json` SHA-256 is `80eda89e3664128d092d7374cbb2a0f74e040c3d37bbbd77a531f31b158de544`.

Status now: **formally evaluated once; deterministic Evidence independently validated; G12 four-node Graph closed and appended to the two-layer memory; mechanism untested**.

## G13 Research Meta boundary

The one authorized formal run and its Graph closure are complete. Its score is descriptive and does not establish causal benefit; the mechanism remained untested because no model-authored record or directive occurred. Strict timing equivalence remains unclaimed.

A hash-bound G0-G12 plus incubation packet was created at `experiments/research_graph_baseline_20261016/research_graph_solution_loop_meta_packet_g013_v1.json`, SHA-256 `f87082ddac735ccdba4701c2d81464097620c300b75c9daaf36e91dbcc259f81`. It contains 26 symmetric formal facts, all 20 incubation nodes, the G12 promotion edge, and 13 Graph-bound code-parent records. The solution-loop contract tests passed 7/7.

Three real DeepSeek Research Meta attempts are preserved in `g013_research_meta_solution_loop_001` through `_003`, but none passed `validate_solution_loop_result(...)`: attempt 001 serialized observations/counterexamples/unknowns as strings; attempt 002 repaired those rows but omitted `minimum_no_task_check` and `interface_status` from all five mechanism candidates; attempt 003 added those fields but omitted the top-level `unknowns` section. Their raw output hashes are respectively `0b462e8f64138be9d4a8779e2b6bbb059f63c6a8fd20fc7c3acc9a54c1e86975`, `6f08ea6a2bac7152cc235d889281ec720595dc58132572c097b2e0abdda14b9c`, and `57fae282f550fe4cd479f227232912262ad14c9aa12306aaa982ff10cf09a8cc`.

An independent contract audit found that the revision prompts had not repeated the complete unchanged validator schema. It authorized one mechanism-neutral, schema-complete retry. Attempt `_004` used the same packet and immutable `_003` output as data, returned provider-complete JSON, and passed the original `validate_solution_loop_result(...)` without code-side repair. Raw Research Meta output SHA-256: `6609b286be192258ab0cb3ccace712139896cd80534be74d9bc71a1576bed071`.

The valid Research Meta target is `mech_requirement_observation_coverage`, primary lens `task_representation_decomposition`, related lenses `evidence_acquisition_grounding`, `state_memory_belief_update`, and `action_tool_policy_recovery`, state `interface_investigation`. The proposal is to investigate a model-authored requirement-to-observation coverage matrix whose structural unresolved states may guide a bounded next evidence action. This is a research target only: its runtime carrier, row schema, freshness/update rules, distinction between instrumentation loss and genuine evidence absence, model-facing action view, no-leak boundary, real-model authorship, and behavioral compliance are unverified. No code parent, Experiment, implementation, benchmark, launch, or evaluation is frozen.

The first bounded interface investigation is now complete in `g013_interface_investigation_001`. Its strict opaque carrier, coverage/freshness/fault transitions, instrumentation-loss separation, structural next-action view, one-action cap, deadline guard, disabled-mode inertness, and aggregate-only export passed 49 no-task tests and an independent replay. No provider was called: real-model authorship, opaque-reference copying, provider/production-boundary acceptance, and action compliance remain unknown. Manifest SHA-256: `f5fd8fa52df71196f101686c33f2569f22e28a354ab08b97e44eeeb6f3391db7`; verification SHA-256: `8f95b4cfc9c8a29f1e2419e45382a766446c3dce3ccc1449ed5e1b6468003f6b`; `research_graph_memory_v13.json` SHA-256: `e44ab7a0fbefa3e8689f37663d33c231dfb7318c0fcc82f17fa733c269170f94`.

Post-interface Research Meta then consumed a new G0-G12 plus 23-node packet, SHA-256 `69f6ed15d6d536987d17ac647af22409e4385273281d64f7e60a88de618f1fdd`. Attempt `_001` is preserved as mechanically invalid because it serialized `next_interface_investigation.source_scope` as a string rather than an array; raw SHA-256 `602799cf51954315229758f5a7d7097e3d5accd5bf77dabe09b3ae0770afcdd9`. A bounded full-object serialization revision `_002` preserved the same decision and passed the unchanged validator; raw SHA-256 `10ea715d6c05a7c0c5fd1b489ec5933e4a274c6765e473c1a36bce21fc783f39`.

The valid decision keeps `mech_requirement_observation_coverage` in `interface_investigation`. It requests one smallest new synthetic provider/production-response-boundary investigation for carrier acceptance, exact opaque-token preservation, fail-closed unknown handling, no-leak export, and enabled/disabled inertness. It explicitly leaves real-model authorship and action compliance as future formal endpoints only if that boundary passes. No code parent, Experiment, implementation, benchmark, or launch is frozen. The revised target is appended as `research_target:g013:002` in `research_graph_memory_v14.json`, SHA-256 `ecdec2bbe36dc83ecb6cd5242cd5344829a03febe5f4570b1e48e480766eed22`.

The second investigation is complete. Attempt `_001` preserved a provider request rejected because DeepSeek thinking mode does not support forced function `tool_choice`; it produced no model response. Attempt `_002` used the production-compatible automatic tool-selection path and completed one accepted synthetic round trip through the source-generated `record_self_observation` schema and actual `choices[0].message.tool_calls` boundary. Both opaque tokens were copied exactly. Missing, malformed, truncated, and provider-rejected fixtures remained explicit unknown. Enabled/disabled controls preserved zero tool dispatch, forced answer, scoring mutation, and wall-timeout extension. Cumulative provider requests were 2, with 1 accepted round trip; `12 passed` independently. Findings SHA-256: `2e6ada16d49a46a12b605a35b2931f61527c3966a7a1e85532e494a6b243f89b`; verification SHA-256: `3f1b9512085b9475f7feff6da14124683ce528be9f9904356c27b0bf8135bcdb`; `research_graph_memory_v15.json` SHA-256: `4206f1706eafbcd12bf318fed01acb0bac6f2a17843f216b310f1af9ad35429b`.

Status: **G13's second bounded interface investigation is independently verified and appended; G13 formal generation has not started.** Formal model-authorship rate, action compliance, semantic coverage, task-bearing behavior, code parent, Experiment, implementation, benchmark, and launch remain untested or unfrozen. Return the finding to real Research Meta; do not enter Implementation Meta directly.

Post-finding Research Meta has now consumed a new G0-G12 plus 26-node packet, SHA-256 `40c6b556a561e54c1beb71484783c8f873c4ab8d86eac24bca3aa325640cc393`. Attempt `_001` selected `experiment_ready` and G7 as the code parent but was mechanically invalid: it used aliases for the frozen protocol and structural-binding endpoint. Its raw SHA-256 is `17dcbde71f9b6c3adbb0d4f76d207fb02bac90230da30bb027f468f8961d8695`. A bounded full-object revision `_002` made only the audited serialization changes, was byte-for-byte equal to an in-memory normalization of `_001`, and passed the frozen validator. Its raw SHA-256 is `0e01fa9290e8ecf722a3e3092e60b74c335b15f439811774cb0c4bb4210bf3b1`.

The valid decision promotes `mech_requirement_observation_coverage` to `experiment_ready` and selects verified G7 tree `572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac` because it is the last mechanism-neutral structural-instrumentation parent before the G8-G12 audit/checklist/ledger/uncertainty lines. The frozen research contract is `g013_formal_research_contract.json`, SHA-256 `5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c`. It preserves separate structural binding, real-model authorship, coverage-state, behavioral-action, and strict-outcome endpoints; exact 56/base-no-hint/1200/strict-over-56/one-arm protocol; fail-closed unknown; inertness/privacy/fault gates; and no causal claim.

`research_graph_memory_v16.json`, SHA-256 `fc206dac718781d9e3d9eb0dc79e2f6593e98d5e25cb9be3448124c8e15fe54e`, appends `research_target:g013:003` as an experiment-ready incubation node. No implementation, admission, benchmark, launch, or formal G13 Experiment exists yet.

Status before implementation: **G13 research contract frozen and experiment-ready; code parent G7 frozen.**

Formal Implementation Meta then created the isolated `g013_formal_implementation_002` candidate from the exact G7 parent. Its initial manifest passed local tests but failed independent source review because raw G13 carrier/token values could persist through inherited self-observation, LLM-log, message, and final-state producers. That failed review is preserved as `source_review_001.json`; the candidate was not admitted in that state.

A bounded Implementation Meta revision added content-blind producer-boundary handling and an end-to-end synthetic persistence test. Revised manifest SHA-256: `96e8874152ed3f8be070c37731bf906b556bdc27ca10fe5eaa4bef8b371c88ce`; child tree SHA-256: `998efc2abc946276df6aa58a7b8a6e04d8aa6f2c719608d21702d3523a1a7da3`. Independent replay recorded 82 focused G13+G7 passes. The complete candidate suite recorded 200 passes and the exact same five inherited `test_tool_failure_recovery.py` failures as the 153-pass G7 parent control, for zero new failures. The synthetic provider-shaped path preserved one accepted record and exact opaque binding while all materialized logs, final state, normalized artifacts, analyzer output, and evidence exports had zero token-sentinel hits.

Status after source review: **G13 locally implemented; initial privacy review failed and was repaired; revised source/contract review passed.**

Bounded runtime admission attempts `_001` and `_002` stopped before provider calls on local upstream/dependency preflight gaps. Attempt `_003` reached the real DeepSeek production path in three automatic-tool calls. It verified one model-authored accepted carrier, one exact visible opaque-token binding, one delivered structural view, zero prohibited actions, and zero persisted sensitive-token hits. It did **not** pass admission: the content-blind assistant-history proxy changes the record call used as the DeepSeek adapter's reasoning key and omits `reasoning_content`, so the post-view request is rejected locally as unbound historical reasoning. Behavioral action consistency remains `unknown`.

The `_003` probe's missing fixture, enabled/disabled early-stop comparison, and temporary-directory layout were also defective, but are not the critical candidate failure. A clean replay still yields candidate `200 passed, 5 failed` versus parent `153 passed, 5 failed`, with the same five inherited failures and zero new test failures. Independent diagnosis is in `g013_admission_003/independent_failure_review.json`.

Status after attempt 003: **G13 runtime admission rejected pending a bounded Implementation Meta repair; no formal evaluation, launch, or Graph closure occurred.**

The bounded repair is now complete in the new immutable `g013_formal_implementation_003` workspace. Implementation Meta added a process-local, non-serialized native-message binding: the raw provider record call and authentic `reasoning_content` are captured before sanitization, persistent history remains marker-only, and only a deep-copied provider request is hydrated immediately before the next call. The unchanged DeepSeek adapter retains its no-fabrication guard. Missing, mismatched, duplicate/ambiguous, conflicting, or persistently reasoned histories fail closed.

- Child tree SHA-256: `b0acbc351292ba5653032eeda9dbf9191b855144211c2cf4813478e0f12aa351`.
- Manifest revision 3 SHA-256: `2f9bb26d6cbe60a8d6440e68d69361b215a277bb6517afa4f2ff29dc0c223fa4`.
- Independent source review SHA-256: `2574020cf1faa6ff69e80e9c5a3399d0278417965e6f8e6d5ba25b28eb34a741`.
- Independent tests: 86 focused G13+G7 passed; candidate full `204 passed, 5 failed`; parent G7 full `153 passed, 5 failed`; the same five inherited nodeids failed, so new failure count is zero.
- Generated privacy scan: 309 files with zero requirement, observation, reasoning-sentinel, or `reasoning_content` persistence hits.
- The corrected attempt-004 probe fixes the invalid missing-carrier fixture, asymmetric control early stop, and TMP/basetemp collision; it also checks persisted `reasoning_content` field counts. Local control execution remains environment-blocked by absent optional upstream dependencies, so this is not runtime admission evidence.

Attempt `g013_admission_004` then crossed the real DeepSeek boundary in two automatic-tool requests. It observed one accepted real-model carrier, one exact visible opaque-token copy, one delivered directive, selected structural action `acquire_evidence`, zero prohibited mutations/actions, and a passing content-blind persistence audit. The admission nevertheless remained blocked:

- the real provider record call included an `index` field, while the persistent content-blind proxy dropped it; exact native-binding comparison therefore failed closed with `G13 native reasoning binding conflicting tool calls` before the post-view provider request, leaving action consistency `unknown`;
- the empty-object missing-carrier fixture was fail-closed but classified as `malformed`, leaving the contract's explicit `missing` count at zero;
- the driver used an in-repository temporary layout and recorded `198 passed, 11 failed`, but retained only an output hash. A clean replay outside the candidate tree restored candidate `204 passed, 5 failed` versus parent `153 passed, 5 failed`, with the same five inherited failures and zero new failures. The extra six failures' exact cause is unknown, so the driver result is invalid for comparison.

Independent failure review SHA-256: `2be712a20c4a3a84cdc326fb16b1b0671509a68269b0f7a5424794b427310ff3`.

Status now: **G13 implementation revision 3 remains source-admitted but runtime admission attempt 004 is blocked; formal G13 evaluation, launch, and Graph closure have not occurred.**

The first two post-crash revision attempts did not form valid candidates. `g013_formal_implementation_004` / `g013_formal_implementation_meta_005` ended before implementation; `g013_formal_implementation_005` / `g013_formal_implementation_meta_006` wrote a partial revision but had no terminal Meta completion. All four directories are preserved and excluded from candidate selection.

A clean restart from the exact revision-3 source completed in `g013_formal_implementation_006` through terminal Implementation Meta attempt `g013_formal_implementation_meta_007`:

- Revision-4 child tree SHA-256: `e966e07211bae0d8ddea96af8d88143b47af40db40567161d2d8391abfc7591c`.
- Manifest SHA-256: `0c939b2afd6c51163e9b1702052f882fd9e5f0651234ab20e2cf0c9b9d0e9ff2`.
- Independent source/privacy review SHA-256: `235b54b132fb8eb44020a0f5f5fa47834712b0cd37101a4d616f0cb94177d4a0`.
- The content-blind proxy now preserves native `id`, `type`, optional `index`, and `function.name`; raw arguments and reasoning remain process-local only. Missing or mismatched index, ambiguous identity, persistent reasoning, and absent binding still fail closed.
- Absent arguments/null carrier are explicitly `missing`; `{}` remains `malformed`.
- All test roots were external to the candidate. Independent replay: G13+G7 focused `98 passed`; candidate full `216 passed, 5 failed`; frozen G7 parent full `153 passed, 5 failed`; the five nodeids are identical inherited failures, so new failures are zero.
- An independent scan of 768 materialized test files found zero exact carrier/requirement/observation/reasoning sentinel or persisted `reasoning_content` hits. The DeepSeek adapter remains byte-identical to G7.
- Attempt 005 ran once against the bound revision-4 child. Three automatic DeepSeek calls produced one accepted real-model carrier, one exact visible opaque-token copy, one directive, and a structurally consistent `acquire_evidence` action. Fault fixtures, enabled/disabled inertness, frozen-source checks, and external candidate/parent test comparison passed; candidate and parent retained the same five inherited failures with zero new failures.
- Admission 005 is nevertheless blocked. One accepted opaque requirement token was copied into the optional `self_observation` sidecar on the post-view `query_db` call and persisted in `agent_self_observations.jsonl` at `payload.what_i_know[0]`. The generic `tool_action_sidecar` writer did not apply the G13 content-blind sanitizer. No raw token was copied to the research artifact; the isolated raw surface recorded one hit and every other scanned persistence surface recorded zero.
- Admission result SHA-256: `b9e23a8adc7b1839b80305ff374a98eb454624032362a4b99f67b2f8b018ebc7`; independent failure review SHA-256: `45092cf1790edb234cfce2a208718857a6d8137f4103f05b462bf7a45d2dacec`.

Status now: **G13 implementation revision 4 remains source-admitted, but runtime admission attempt 005 is blocked by a confirmed persistence-boundary privacy failure. Formal evaluation, launch, and Graph closure remain prohibited.**

## Other campaign states

- `dataset17_half56_deepseek_v1_20261011`: `ready_for_intent`, `next_generation=20`, last completed node Gen19. Historical only unless the user explicitly resumes it.
- `domain17_glm53_unbounded_v1_20260930`: `intent_sealed`, `next_generation=12`, `execution_status=paused_by_user`, `automatic_resume_authorized=false`.

Status: **verified from current `campaign_state.json` files**.

## Immediate safe work

G12 is closed. G13 runtime admission attempt 007 passed its bounded synthetic gate and an independent runtime review. The next safe task is an independent formal-launch readiness review over the frozen contract, revision-6 child, admission artifact, live process/disk boundary, exact 56-task manifest, and one-launch claim protocol. Admission is not itself launch authorization or formal Evidence.

## Version-inclusion milestone (2026-10-20)

- User-selected categories 1-3 were reviewed for safe Git inclusion; only explicit research source, tests, prompts, memory/protocol Markdown, and compact manifest/evidence summaries are being staged.
- Candidate repositories, raw traces/JSONL, provider probe payloads, runtime/benchmark trees, archives, and ambiguous one-off scripts remain in place and are not staged.
- The user selected categories 1-3 for one checkpoint commit: research source/tests/prompts and small tools; research memory/protocol documents; and compact manifest/evidence/Graph/verification metadata.
- Before the checkpoint, the index is being narrowed to those categories only. Candidate repositories, raw traces/JSONL, provider transcripts, runtime/benchmark copies, archives, symlink/mode-only noise, and Zone metadata remain outside the commit and are not cleaned from the worktree.

## G13 revision-5 source admission recovery (2026-10-21)

The first sidecar-privacy repair attempt, `g013_formal_implementation_007` / `g013_formal_implementation_meta_008`, was interrupted after partial edits and tests. It has no terminal Meta completion, `final_raw.txt`, final child binding, or independent review and is excluded from candidate selection.

A clean restart from the last valid revision-4 child completed in `g013_formal_implementation_008` through terminal Meta attempt `g013_formal_implementation_meta_009`:

- Revision-5 child tree SHA-256: `64004f8ef66cb3b8071f8eef1f0bd48b3b0bdf931b64e95467c7412a591ef218`.
- Manifest SHA-256: `98424bc0d4d257c82997d348f45bea0d5924e94d9aac323eb1506725ad68a2cd`.
- Independent source/privacy review SHA-256: `2e320a6a2a40cc6b6da8c7d71c114145cd434c09aa9c4742ad833776a176887b`.
- All G13-sensitive persisted open self-observation producers, including `tool_action_sidecar`, now use one content-blind projection while retaining schema, shape, counts, status/reason metadata, and normal non-G13 behavior. Actual tool dispatch and process-local authentic reasoning are unchanged; native binding remains fail-closed.
- Independent replay: G13+G7 focused `100 passed`; candidate full `218 passed, 5 failed`; frozen G7 parent full `153 passed, 5 failed`; the same five inherited nodeids fail in both, so new failures are zero.
- Independent full materialization scan: 768 files, zero exact carrier/requirement/observation/reasoning sentinel hits and zero persisted `reasoning_content` fields. Candidate generated cache/test state is zero.

Status now: **G13 revision 5 passed independent source/privacy review but has not run runtime admission.** Admission attempt 006 is prepared only. No provider, benchmark, database, formal evaluator, launch, or Graph mutation occurred in the revision/review task.

## G13 runtime admission 006 (2026-10-21)

The bound no-benchmark attempt ran once in the fresh remote synthetic scratch and is **blocked**. It made three automatic DeepSeek calls and again observed one accepted model-authored carrier, one exact visible opaque-token copy, one delivered directive, and a structurally consistent `acquire_evidence` action. Fault fixtures, enabled/disabled inertness, native reasoning continuity, frozen-source checks, and focused tests passed. No benchmark, database, formal evaluator, launch claim, or Graph mutation occurred.

Independent review found a distinct persistence failure. The upstream `BaseTool.exec` row for `record_self_observation` persisted the complete carrier twice in remote-isolated `provider/tool_calls.jsonl`: three unique sensitive tokens appeared once each under `args.freeform` and once each under `val_args.freeform`, for six exact hits. No raw values were copied into the research artifact, and persisted `reasoning_content` hits remained zero. The source-level path proxy did not protect this real boundary because it implements `Path.open()`, while upstream `BaseTool` writes with built-in `open(path)`, which resolves `__fspath__` and bypasses the proxy's write-stream sanitizer.

The driver also reported `inherited_failure_match=false` only because its predicate hard-coded the previous candidate count `216 passed`. The candidate and parent failed-nodeid arrays are exactly equal at the same five inherited failures; revision 5 now has `218 passed` because it adds tests. This is an admission-driver defect, not a candidate regression, but it must be corrected before another attempt.

- Admission result SHA-256: `bed421c07aff99debbc948ff31877069c71ca25f3de26ce3e7aba5294bb57f54`.
- Privacy scan SHA-256: `4e929311b420f041fed9293157cce03cb62d70c8c89ccfd4edcee388d877a06d`.
- Independent failure review SHA-256: `4227f8bfb97d5e59cdd727ee0d65fc7d28e25abf2ffbbe6aed7dc8105f1e3b39`.

Status now: **G13 runtime admission 006 is blocked by raw record-tool log persistence. Formal evaluation, launch, and Graph closure remain prohibited.** The next safe task is a bounded Implementation Meta revision that sanitizes the actual built-in-open `BaseTool` persistence boundary while keeping transient dispatch, non-G13 behavior, authentic process-local reasoning, and fail-closed binding unchanged. It must also make the candidate/parent inherited-failure predicate depend on exact nodeid equality rather than a hard-coded pass count, then receive independent source/privacy review before a new admission attempt.

## G13 revision-6 source admission (2026-10-21)

The bounded producer-boundary revision completed in `g013_formal_implementation_009` through terminal Implementation Meta attempt `g013_formal_implementation_meta_010`.

- Child tree SHA-256: `31277b0514798b52b7547bb5cc12900c63d556fca0fc4919bff0b8be4902322c`.
- Manifest SHA-256: `d8bd9714718343c51b30290e4ab1b8c8db5a077543a128f163cd48c34e36b5e1`.
- Independent source/privacy review SHA-256: `095d36fa7b32a4f0b4b9f6bb048dffacacb9274574b8d993ac4566dee4629880`.
- The G13-active `record_self_observation` adapter now gives inherited `BaseTool.exec` content-blind `args` and `val_args` for its real built-in-open log row while strict validation and `_exec` consume the exact process-local carrier. No global builtins patch or upstream adapter edit was introduced. Disabled, non-G13, and no-sensitive-carrier logging retains inherited behavior.
- Independent replay: G13+G7 focused `102 passed`; candidate full `220 passed, 5 failed`; G7 parent full `153 passed, 5 failed`; failed-nodeid sets are identical, so new failures are zero.
- Independent materialization scan: 773 files, zero exact sensitive-token hits and zero persisted `reasoning_content` fields. Candidate generated state is zero.
- Admission 007 probe SHA-256: `a33412dcdc40585563fd3e3f098134d63b785f366f358356429bce499fbb731a`; driver SHA-256: `3ab956b401c2aecf3f9c5577ffacfd6f7c67eaf12481ea0acdf6acf651031934`; preflight SHA-256: `b47e3444a21f87e81ba734d5899f1826628cb5e108818218b887a84a7cdce439`.

Status now: **revision 6 passed independent source/privacy review; runtime admission 007 passed and was independently reviewed.** Formal evaluation, launch, and Graph closure have not occurred; an independent formal-launch readiness review is the next gate.

## G13 runtime admission 007 (2026-10-21)

The bound no-benchmark attempt ran once in a fresh remote synthetic scratch and passed. It used three automatic DeepSeek calls, accepted one real model-authored carrier, copied one visible opaque token exactly, delivered one directive, and observed one structurally consistent `acquire_evidence` action. Missing, malformed, truncated, and provider-rejected fixtures failed closed. Enabled/disabled controls matched outside the directive channel, with zero mechanism-initiated tool calls, forced tools or answers, scoring mutation, or timeout extension.

The privacy gate passed across the remote-isolated `llm_calls.jsonl`, `tool_calls.jsonl`, `agent_self_observations.jsonl`, coverage sidecar, and final state: zero exact sensitive-token hits and zero persisted `reasoning_content` fields. Remote surface hashes independently matched the provider receipt; raw synthetic context was not copied into the research artifact or read by the research export.

Independent replay recorded focused `102 passed`; candidate `220 passed, 5 failed`; G7 parent `153 passed, 5 failed`; the failed-nodeid sets are exactly equal and new failures are zero. Frozen child, parent, contract, manifest, source-review, probe, and driver hashes remained unchanged, and no matching remote process remained.

- Admission result SHA-256: `2f1759d93ef77337e88a501b7b286b381fb4860ef421dfe94f32ef84741bae5e`.
- Privacy scan SHA-256: `a3f51902ed2d7020aaf9bf8fd85bd0b7d0091f32a3cfe8c29bb430ccbec61445`.
- Independent admission review SHA-256: `8d499cd636b651dc30faf7b83b8bc0180a2d599f2650f6246898025233926341`.

Status now: **bounded no-benchmark runtime admission passed and was independently reviewed.** This establishes runtime admissibility only. It does not establish task-bearing authorship, semantic coverage, action benefit, benchmark score, causal improvement, or strict timing equivalence. Formal launch still requires a separate readiness review and an atomic unique launch claim.

## G13 formal launch in progress (2026-10-21)

The independent readiness gate completed and one atomic formal launch was created at remote attempt `/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g013_formal_001`, run ID `g013_requirement_coverage_nohint_56_v1`. The launch is bound to claim SHA-256 `b3ec584af47e8f680b1ed085ebc7a01d2aedd84e1d0bf716b3cbb7a772e2facb`, launch-manifest SHA-256 `7d9a854b4eb3c3bedf4918a1041701b4d78a9156659291c2c5b2805ec19b85a7`, and finalizer-binding SHA-256 `4e59acae484ac070c39f85b57a516eb4a06f82bf1a1fd996313e9964b56a4dcc`. Prepare-only evidence SHA-256 `e3873e96c3fa536e2fcff351d1e789e6897e9df6dd5b44327677791cb42d1572` records 56/56 tasks prepared under `base_no_hint`, one arm, 1200 seconds per task, four workers, and same-family serialization. Launch free space was `16,694,403,072` bytes.

The active process is PID `709990`. A content-blind monitor receipt at `2026-10-21T04:26:23Z` recorded `8/56 completed`, runner active, no summary yet, `16,491,847,680` bytes free, and exactly one G13 launch claim. No failed or timeout status had been observed at that checkpoint; this does not predict the remaining tasks or classify any future failure.

The bundled local Python executable changed from the frozen expected SHA-256 `b07b03b9ba866a341a3c13ee69710fbc8d43d4ce2523dee13f6df5c25378d15b` to observed `7c4ee3011932a75b30db176f35fb91b28f0b299e608eaf643fb1bf36ed5ace99`. Codex and PowerShell runtime bindings remained unchanged. Formal evaluation does not invoke Research Meta or Codex, so launch used the bounded formal-provider-only review in `g013_formal_001/formal_provider_route_review.json`; this exception must not be reused to silently update the Meta runtime binding.

Status now: **G13 formal execution is launched and still running; no formal outcome, score, Evidence, promotion edge, or Graph closure exists.** Continue only content-blind monitoring. Do not restart or duplicate the run. After PID `709990` exits naturally, require exactly 56 terminal progress and summary rows, then invoke the hash-bound finalizer exactly once. If finalization rejects, preserve the run and diagnose without rerunning the formal evaluation.

## G13 formal terminal and rejected first finalization (2026-10-21)

The sole formal runner exited naturally at `2026-10-21T06:08:12Z`. Content-blind monitoring verified exactly 56 terminal rows: 52 `completed` and 4 task `timeout`, with no duplicate launch. The terminal progress SHA-256 is `c6750f0d2d127d817dbfa76e4f79e1b1609527baa0f77826918b79296d5202f2`; the summary SHA-256 is `1e05433f487322b642316548b93d168c6a7ad6c405e796da88cf8cc426b3478c`.

The bound finalizer SHA-256 `3ef3d9c2e8c1886683daf410aa57863b2d4069a967adaf6b90d902f3a00be428` was then invoked exactly once and exited 1 before any binding, terminal-row, privacy, or Evidence extraction gate ran. Its dynamic loader opened the frozen extractor, but `ATTEMPT/source` was absent from `sys.path`; the extractor's absolute import `from experiments.g013_requirement_coverage ...` therefore raised `ModuleNotFoundError: No module named 'experiments'`. Remote resolution checks confirmed that the module is absent without that path and resolves to the frozen source when the exact source root is supplied.

No `postrun/` directory, Evidence draft, privacy audit, outcome partition, terminal receipt, or closure draft was created. Consequently the strict score and all formal mechanism endpoints remain **unknown**, not failed or untested. G13's Graph remains open, and G14 is prohibited.

The minimum safe recovery is not a direct retry and must not change the frozen source, extractor, or finalizer. It requires an immutable content-blind failure receipt plus a separate atomic recovery claim/binding that fixes the exact `PYTHONPATH` to the deployed source root, binds the Python 3.12.12 interpreter SHA-256 `3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66`, and rebinds the finalizer, launch, progress, summary, source, extractor, and task-manifest hashes. Only explicit independent authorization may execute that recovery once; its outputs still require independent review.

Status now: **the G13 formal run is terminal, but finalization is rejected before gates and remains unrecovered.** Do not rerun the formal evaluation, directly rerun the finalizer, close the Graph, or start G14.

## G13 recovered finalization pending independent review (2026-10-21)

After read-only diagnosis established a pure import-path deployment defect, the research controller authorized one non-overwriting recovery invocation. The unchanged frozen finalizer was executed once with only `PYTHONPATH=/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g013_formal_001/source` added. Formal evaluation was not rerun, and the source, extractor, finalizer, summary, and progress files were not modified.

The recovered finalizer produced six content-blind `postrun/` artifacts and reported `complete_pending_independent_review`. The draft outcome is 31/56 strict: 31 strict pass, 18 known strict fail, 3 completed strict-verdict unknown, and 4 task timeout; other terminal failures are zero. The specialized aggregate contains zero records, accepted records, directives, consistent actions, or contradictory actions, so all four G13 mechanism endpoints remain `untested`. The finalizer's privacy draft reports `passed`, but neither outcome nor privacy is independently validated yet.

Key draft hashes: terminal receipt `a9f7ad3152116cd8b117f7705980b289f785f26fe0146258669f54c19e141b62`; Evidence draft `cca47010fe711b2de4aa4f190fcd4d415d47baa59d7016c396ad1c6c5a3797f5`; specialized Evidence `5961a68f3641380b717f07c09792c2d904ccf2827b7e56492e6ca60f12576afb`; outcome partition `c4bdcb7f23682d286b15e5003ff6ba9dc74413564220e04157954c1cab5f29f3`; privacy audit `0e18d16a35ee581e7cab5ed4b17185fe1bfde9c852846eb7f6000d1cf067f1b3`; closure-input draft `b146f7aeb62159b144aa2b1e1b26ccc631ae27eec349de3b1d640d81cffe4b69`.

Two recovery-procedure facts require explicit independent review. First, the enclosing PowerShell/SSH capture wrapper returned exit 1 after the original finalizer had already emitted a complete stdout result and created all six artifacts; shell interpolation corrupted the numeric exit-code capture. The preserved finalizer stderr is empty, and no retry occurred. Second, the pre-execution recovery binding named the exact interpreter path but omitted its SHA-256 field. A post-execution attestation observed the expected Python 3.12.12 SHA-256 `3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66`; this does not retroactively turn it into a pre-bound field.

Status now: **formal run complete; recovered deterministic drafts exist; G13 remains pending independent review and its Graph remains open.** Do not close G13 or start G14 until an independent reviewer accepts the original bindings, the environment-only recovery, both procedural anomalies, all postrun hashes, the 31/56 partition, mechanism endpoints, and privacy boundary.

## G13 independently validated closure (2026-10-21)

Independent review accepted the unique formal run and the one environment-only recovery. The formal run ended 56/56 with 52 completed, 4 wall timeouts, and no other detected provider or infrastructure terminal failure. The fixed-denominator outcome is 31/56 strict: 31 strict pass, 18 known strict fail, and 3 completed strict-verdict unknown. This is an unpaired descriptive result, not a causal or benefit claim.

No model-authored record, accepted record, directive, model-facing view, or post-directive action was observed. Structural binding, real-model authorship, coverage-state behavior, behavioral action choice, and the overall mechanism therefore remain **untested**. The privacy/export audit passed.

The review retained both recovery caveats. The first finalizer failed before postrun creation because the frozen source root was absent from `sys.path`; the only recovery added that exact root through `PYTHONPATH` without changing source or extractor semantics. The wrapper's exit 1 was a transport status-capture error after the finalizer had completed. The executed interpreter identity was verified at SHA-256 `3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66`, while the fact that this SHA was not pre-bound remains an explicit procedural limitation.

The immutable safe snapshot is `g013_safe_snapshot/`. Evidence SHA-256 is `8dfdcaa180e2641475e5c481f98f612f788eea6f8bd82070f87bd85b4f83bcb7`; Graph SHA-256 is `a231eff12aad1d850b79b89e791bd1c8bd8d43d4941ff28c684cc8a4ff2b32b6`; independent review SHA-256 is `3e6249178e8a5aedcd88023468e8da8c361402d40d9207284cdd0202d4fb72c7`; closure receipt SHA-256 is `d77aa4e00511992ef78bc0b884faec047073dba5d4118807f6839c5f1a27a480`. `research_graph_memory_v17.json` SHA-256 is `176d91bca69138088353be80735c9ce8c93d36bf8b661ca57d10cd3bf88cd648`; it covers formal G0-G13, preserves all 27 incubation nodes and prior edges, and appends only `research_target:g013:003 -> experiment:g013` as the new promotion edge.

Status now: **G13 formally evaluated once; Evidence independently validated; four-node Graph closed; mechanism untested.** No G14 Research Meta, candidate, admission, or formal run has started. The next workflow action is to build an answer-blind, hash-bound G14 solution-loop packet from closed G0-G13 plus the unchanged incubation layer and invoke real Research Meta without preselecting a mechanism.

## G14 Research Meta target (2026-10-21)

The answer-blind layered G14 packet covers formal G0-G13, 28 symmetric formal facts, all 27 prior incubation nodes, and 14 verified code-parent records. Packet SHA-256 is `0e4525b5f8378f536eb68fa36125d076f319b08ecd6dc60a80625a4824711b04`.

Attempt 001 stopped before provider invocation because the bundled Python executable no longer matched the frozen Meta runtime binding. A bounded, recorded runtime-identity rebind changed only `tools.python.sha256` from `b07b03b9ba866a341a3c13ee69710fbc8d43d4ce2523dee13f6df5c25378d15b` to `7c4ee3011932a75b30db176f35fb91b28f0b299e608eaf643fb1bf36ed5ace99`; Codex, PowerShell, provider route, model catalog, profile, and policy remained unchanged. Attempt 002 returned provider-complete JSON but was mechanically invalid because `minimum_de_risking` was a string instead of an array. Attempt 003 made one complete-object, mechanism-neutral schema revision and passed the unchanged validator. Valid Research Meta output SHA-256 is `5a5d53429db99b5437bb4ac5aff3a34c4f34386cc3fc67872daf0609e8f0c7ad`.

Research Meta selected `mech_progressive_query_probing`, primary lens `action_tool_policy_recovery`, related lenses `evidence_acquisition_grounding`, `state_memory_belief_update`, and `hypothesis_search`, state `interface_investigation`. The target asks whether a bounded pre-dispatch discriminating probe and structural progress checkpoint can change action selection or preserve unknown before an expensive data-acquisition path, without treating timeout localization as causal proof. No code parent, Experiment, implementation, benchmark, database run, or launch is frozen.

`research_graph_memory_v18.json` SHA-256 is `51c2283f77db70185790b6d660e6b00d3c55a83ed2523d3a27746554cac3fe8b`. It retains formal G0-G13 and all 27 prior incubation nodes, then appends only `research_target:g014:001` plus its evidence/incubation references.

Status now: **G14 has one validator-approved Research Meta target in interface investigation; no formal generation exists yet.** The next workflow action is the single bounded synthetic no-task interface investigation specified by the target.

## G14 rejected interface finding recorded (2026-10-21)

Three bounded no-task interface revisions passed scoped suites of 40, 64, and 100 tests but failed independent admission in sequence: boolean/integer aliases plus caller-controlled cap/deadline bounds, direct public dataclass construction, and numeric-subclass comparison behavior bypassed the claimed fail-closed boundary. Independent review status is `rejected_bounded_stop_return_to_research_control`, SHA-256 `c4c8c947b0a2b04ad0b822b50693c44f0f5206014e20fcd8a1b9118993766a51`.

The first direct finalizer invocation failed before mutation because script execution did not put the repository root on `sys.path`. After source review and exact verification of v18, all three manifests, and the independent review hashes, the unchanged finalizer was invoked once as a module. It appended only `interface_investigation:g014:001`, `interface_finding:g014:001`, and two incubation-layer edges. The formal layer and cross-layer edges are byte-structure identical to v18.

`research_graph_memory_v19.json` contains 14 formal generation references, 30 incubation nodes, and 48 incubation edges. It passed `validate_research_memory(...)`; SHA-256 is `6415bd199798b4c54100afdb81874bd2eca5049a8e24a8aca4ed6694f3f74504`.

Status now: **the rejected G14 interface finding is durably recorded; research control has not selected a successor direction.** The next safe action is to build an answer-blind post-interface packet from v19, report its bounded provider-call budget, and obtain explicit confirmation before one Research Meta dispatch. Do not perform a fourth hand-selected repair or enter Implementation Meta directly.

## G14 post-interface Research Meta decision (2026-10-21)

One authorized Research Meta call used the v19 post-interface packet (SHA-256 `d492489c4fdea1a96dde961aaf056e46082c3ac2023200d333ac7f141eeea19b`). It selected `mech_discriminating_observation_portfolio`, primary lens `hypothesis_search`, state `interface_investigation`. The mechanism keeps a small set of competing interpretations, chooses a bounded low-cost observation that discriminates among them, and updates explicit unresolved state without treating structural evidence as correctness.

The call used 113,131 input tokens, 4,736 cached input tokens, and 20,339 output tokens, including 12,146 reasoning tokens. Raw SHA-256 is `9bc2052b7086ba9339d6b89868ba7531c4ffbdb349e1cdccace43199a494d85c`. The raw result had one lossless schema mismatch: `minimum_de_risking` was a string rather than an array. Wrapping it in a one-item array made the unchanged full validator pass; normalized SHA-256 is `087017c5d3cea41538d0715fbb3f672b239bdc6b1cd750b13a67108b4cb59226`, with the transformation recorded in `validation.json`.

Status now: **a validator-approved successor direction exists, but remains interface investigation only.** No model retry, implementation, benchmark, database, server, candidate, admission, or formal evaluation action occurred.

## Non-formal G13.2 exploration closed (2026-10-22)

The candidate-only G13.2 Civic exploration is closed and preserved without promotion. One bounded read-only remote verification found `/srv/text2sql/evolution_runtime/g0132_budget_eval_20261022` present, PID `767770` absent, and `g0132_civic_q1_v1` summary status `completed`; no SIGTERM, SIGKILL, retry, or new run occurred. The bounded aggregate scan did not expose model-call, tool-call, token, cost, exit-code, or strict-result fields, so those remain unknown.

The closure manifest is `experiments/g0132_budget_eval_20261022/closure/closure_manifest.json`, SHA-256 `497c137b3c390023021a203bcf4063d9375c45b5cf2c3675cd954d1e911dff61`. This result is non-formal exploratory evidence only: it did not pass admission, is not a formal evaluation, and provides no causal-benefit claim.

Status now: **G13.2 is closed; the authorized next direction is a bounded synthesis of G11-G13 mechanisms and trace-derived failures before any implementation or evaluation.**

## Controller-authored G11-G13 synthesis (2026-10-22)

An answer-blind synthesis of immutable G11, G12, and G13 artifacts produced one proposed loop: G11 owns revision/supersession and active work-state lifecycle; G13 binds active requirement rows to genuinely visible opaque observations and updates structural coverage; G12 classifies uncertainty, freshness, and faults and selects at most one bounded structural next-action view. The design requires one carrier, one parser, one state store, one controller, and one view path, with fail-closed base behavior for absent or invalid state.

Artifacts are under `experiments/g011_g013_synthesis_20261022/`. Evidence manifest SHA-256 is `2734f865f1516bb34d7d0e2e6a472337f54a0097d2586e21379eb3e9394de8ed`; Meta-compatible intent draft SHA-256 is `434da42dd62e7d7d2254eabb09e8c289ff239fd62ccfde123b9b6fafd7e81144`; implementation contract SHA-256 is `a346f79c0035c6d7a591918cca37d2044fbb7a95e693bafcda01054e790312f8`.

This is controller-authored and is not Research Meta output, a Graph target, admission, or evaluation evidence. The formal G11-G13 endpoints were all untested because activation was zero; adoption, action sensitivity, timeout effects, score gain, and causal benefit remain unknown. Status now: **contract accepted for isolated implementation and provider-free local verification only.**

## Integrated G11-G13 candidate implementation (2026-10-22)

The isolated candidate implements one carrier/parser/store/controller/view path plus minimal runner, analyzer, and evidence-pack telemetry wiring. Focused provider-free contracts passed 25/25; focused plus current G13, G13.1, G13.2, and batch-runner regressions passed 45/45. The implementation manifest SHA-256 is `993d3fe1f62948291554959eb16ac7b329050a4ca53afd48335d1290542f0223`; validation manifest SHA-256 is `20d6606eb8dcdebb2c2f36439805d986ef5fe9b89a9911f1306b235d58034865`.

Two attempts to collect archived snapshot tests stopped before candidate execution because the copied archival contexts omit required package roots and generated fixtures; they were not retried and are not evidence of a candidate regression. No network, provider, database, benchmark, Meta, or Graph action occurred.

Status now: **local implementation contracts pass; independent source/privacy/contract review is required before any small-scale staging.** Real-model adoption and all behavioral/score endpoints remain unknown.

## Integrated candidate independent review rejection (2026-10-22)

Independent source review rejected the first implementation before test execution under its mandatory stop rule. It found three P1 defects: exact provenance matching did not require an observation to be model-visible; telemetry export accepted arbitrary schema/content under nominally safe field names; and repeated installation could nest global wrappers/controllers. It also found activation-miss telemetry was defined but not invoked at runtime.

Review JSON SHA-256 is `c753a9983ff7084908d95eb8b631b29558be855b88e5785113cc600db21280a4`; review Markdown SHA-256 is `10961f0e2f458b4e21421c90788d2b3ccc7052bed0b21ae62de4e2ec217fbb29`. The prior local 25/45 pass claims remain implementation-side evidence only, not independent acceptance.

Status now: **candidate rejected; repair only the four named defects and add negative tests before a fresh independent review.**

## Integrated candidate repair revision 001 (2026-10-22)

Revision 001 fixes only the four review findings: visible provenance is mandatory; telemetry export uses a recursively closed schema/type/content validator; repeated installation is idempotent and conflicting installation fails closed; and enabled carrier-miss events are recorded exactly once without changing base behavior. Focused tests pass 38/38 and selected current-mainline regressions pass 58/58, with complete outputs and exit codes preserved under `experiments/g011_g013_integrated_implementation_20261022/repair_001/`.

Repaired source SHA-256 is `c16b09d13f30acb8aa6539d7993d1c9cf30f94f75f0b430371d1449fd60f79a7`; exact patch SHA-256 is `d6659b951f4785e5902655b341a2f47bfe536f6950832a3c35762350c81a6ffe`; repair manifest SHA-256 is `7e919fc80c8bbdcbd93653cf8d80026bab42929b7e91e01f215cde46ccafe5c4`.

Independent review 002 accepted repair revision 001 after rechecking F01-F04, the runner/analyzer/evidence-pack wiring, disabled inertness, no-forced-action behavior, and the aggregate-only privacy boundary. The reviewer reran each prescribed provider-free suite exactly once: 38/38 focused and 58/58 selected current-mainline regressions passed. Review SHA-256 is `ff901bc92c30702f59f0e76c533500be3f4a30bb663097e0abed3bef647a657d`; validation SHA-256 is `36a26e2a45bfc0c06e02bb54c0e89a75804b97e5d1bf719ad8c564c77407e527`.

Status now: **repair independently accepted as a local engineering gate; next freeze the six-question small-panel manifest and protocol without executing it. External evaluation remains unauthorized.**

## Integrated candidate six-question panel freeze (2026-10-22)

The answer-blind selection and protocol are frozen under `experiments/g011_g013_integrated_small_panel_20261022/`. A read-only, content-minimized check of the hash-bound G13 formal summary recovered only anonymous manifest-index/cohort mappings and verified the expected `31/18/3/4` partition. SHA-256 ranking selected zero-based indices `18,21,27,37,38,41`, meeting the predeclared `3 known_strict_fail + 1 strict-verdict unknown + 1 timeout + 1 strict-pass guardrail` quota without using task text or answers.

Freeze manifest SHA-256 is `c09f2577f587e654f9aabe5aa3dcc1c28a202962432f87336045c31ae3eff0c1`; validation SHA-256 is `3e8966f483a70beb9c381d41e00811872eda938114f4376a060e53fd68f25b37`. No prepare-only or panel execution occurred.

Status now: **selection and protocol frozen, but not launch-ready.** The generic multi-query runner directly invokes `experiments/run_dab_tool_agent.py` and has no integrated-mode pass-through, so using it unchanged would evaluate the wrong agent. Next create and independently review an isolated batch launch path, then perform provider-free prepare-only verification.
