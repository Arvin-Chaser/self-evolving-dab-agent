# Research Decisions and Corrected Beliefs

Each entry separates the decision from its evidence and current status.

## D1. Use Research Graph as research memory, not a candidate leaderboard

- Decision: represent `Problem / Hypothesis / Experiment / Evidence` separately; candidate code is an Experiment artifact, not the Hypothesis itself. Separate research parents from the single code parent.
- Reason: earlier compact candidate summaries encouraged narrow repair loops and confused code lineage with research explanation.
- Evidence: session `S:20125`; implemented G0-G11 Graph files and `DAB_RESEARCH_GRAPH_BASELINE_WORKFLOW_V1.md`.
- Version: current local Research Graph line, not represented by a later Git commit than HEAD `9e0c752`.
- Status: **verified and active**.

## D2. Replace fixed ten-axis ontology with extensible evidence structure

- Decision: keep core causal fields and allow named facets rather than requiring ten fixed axes as Graph ontology.
- Reason: the ten axes were an audit checklist; forcing all of them recreated an overcompressed template.
- Evidence: session `S:20125`; corresponding route/workflow tests were reported passing historically.
- Status: **implemented historically; current Graph schema supersedes the original route implementation**.

## D3. Measure opportunity and reachability before implementing a repair

- Decision: when opportunity denominator, live interface reachability, or predicted observable is unknown, create a diagnostic/interface investigation instead of a production candidate.
- Evidence: Gen4-Gen11 repeatedly integrated mechanisms that did not activate; G11 had zero authored records/bindings. G12 explicitly passed through two interface investigations before `experiment_ready`.
- Code/artifacts: `research_graph_memory_v11.json`; G12 independent verifications.
- Status: **verified and active**.

## D4. Keep strict/56 as the new-line primary score

- Decision: score strict passes over all frozen 56 tasks; timeouts remain failures and missing verdicts remain unknown.
- Correction: the older campaign often reported strict/non-timeout-completed. That denominator is not comparable to the Research Graph baseline line.
- Evidence: G0 Evidence explicitly records `completed_and_strict_true_over_all_56;timeout_is_failure`; session `S:67525`.
- Status: **verified and active**.

## D5. Do not treat score differences as causal without matched design

- Decision: report unpaired generation differences descriptively. Mechanism status and score movement are separate endpoints.
- Evidence: all G0-G11 Evidence limitations; G10's repaired two-run view is explicitly supplementary; G6's 37/56 is not a causal gain claim.
- Status: **verified and active**.

## D6. Preserve failed, interrupted, superseded, and invalid runs

- Decision: never overwrite a failed candidate, incident, or interrupted attempt with a later revision. Store revisions and explain why they were rejected.
- Evidence: Gen8 candidate revisions, Gen15 repair branches, G3 DNS incident, G10 infrastructure incident/reconciliation, G11 preflight incident. Session `S:21197`, `S:52505`, `S:72800`, `S:83708`, `S:87981`.
- Status: **verified policy; artifacts present**.

## D7. Separate formal Evidence from incubation/interface research

- Decision: formal completed generations remain exactly four nodes; interface findings, blocked directions, and candidate feasibility live in an incubation layer. Promotion requires `experiment_ready` plus engineering admission.
- Evidence: `research_graph_memory_v11.json`; session `S:86667`, `S:88815`, `S:90137`.
- Status: **verified and active**.

## D8. Meta selects research direction; deterministic engineering owns admission

- Decision: Research Meta may select a target but does not authorize a run or certify source/interface feasibility. Implementation Meta writes the candidate; deterministic checks own hashes, tests, privacy, provider boundary, and launch claims.
- Corrected belief: `implementation_ready=true` from a Meta response was renamed/reframed because it had been mistaken for source feasibility and run readiness.
- Evidence: session `S:69401`; current workflow and G12 manifest.
- Status: **verified and active**.

## D9. Do not expose answers, hints, validator targets, held-out tasks, or raw answer-bearing logs to Meta

- Decision: Meta receives bounded, hash-bound, answer-blind research packets. Official hints were evaluated only as a separate historical ablation and must not contaminate no-hint Graph evidence.
- Evidence: workflow documents; G0-G11 evidence manifests; session `S:39795`, `S:40908`.
- Status: **verified policy**.

## D10. Provider or infrastructure failure is not a mechanism result

- Decision: classify DNS, provider 503, database-load, protocol, and disk failures separately. Do not merge them into a valid formal score or infer the hypothesis failed.
- Evidence: Gen15 503 interruption (`S:52505`), G3 DNS incident (`S:72800`), G10 PostgreSQL load incident and user-authorized reconciliation (`S:82626`, `S:83708`).
- Status: **verified and active**.

## D11. Mixed F1 was removed from Meta and promotion decisions

- Decision: do not use heterogeneous task F1 as an evolution signal in this line; preserve it only as historical evaluation data where applicable.
- Reason: mixed task types made the aggregate misleading.
- Evidence: historical session lines before `S:20125`; Baseline/Gen records in the older campaign.
- Status: **historical decision, still respected**.

## D12. The old “mechanism present in code” inference was overturned

- Rejected conclusion: a mechanism is active because code, counters, or a synthetic reachability test exists.
- Corrected conclusion: require live opportunity, binding/delivery, and target-effect observations. Zero observations may mean untested, not ineffective.
- Evidence: Gen2 replay=0; Gen8 repair=0; Gen9 checks almost never triggered; G11 authored record=0 and guidance binding=0. Session `S:21792`, `S:30590`, `S:88815`.
- Status: **overturned; replacement verified**.

## D13. “17 datasets” is not “official 17 domains”

- Correction: the half-56 campaign was constructed from 17 local dataset directories and 104 queries, selecting the first `ceil(n/2)` for 56 and holding out 48. This is not the same as an official 17-domain benchmark claim.
- Evidence: early session history summarized in `HISTORY_INDEX.md`; current campaign artifacts.
- Status: **corrected historical terminology**.

## D14. Mechanism-only extractor flags do not determine formal-run completion

- Decision: establish formal-run completion from the hash-bound terminal receipt and general Evidence together; interpret a specialized extractor's `formal_run_performed` or `evaluation_run` fields only within that extractor's declared no-claim scope.
- Corrected belief: G12's 1,381 count is `recorded_llm_call_count`, not `guidance_suppressed_no_state_count`; the latter sums to 0 across the five cohorts.
- Evidence: `g012_formal_001/postrun/terminal_receipt.json`, `evidence_draft.json`, `g012_specialized_evidence.json`, and `g012_safe_snapshot/g012_independent_review.json`.
- Status: **independently verified and applied to G12 closure**.

## D15. Repeated content in invalid Meta output is not a research selection

- Decision: a Research Meta mechanism or target becomes workflow input only after the complete output passes the frozen mechanical validator. Repetition across schema-invalid attempts cannot be promoted, manually repaired, or used to authorize interface research or implementation.
- Evidence: G13 attempts `_001` through `_003` each repeated `mech_requirement_observation_coverage` but failed different required schema gates; all attempts and hashes are preserved in `EXPERIMENTS.md`.
- Status: **verified policy applied to attempts `_001` through `_003`; none was promoted**.

## D16. Schema repair must regenerate a complete Meta output under the unchanged validator

- Decision: when a provider-complete Research Meta result fails only the frozen structural contract, do not patch research fields in code and do not relax the validator. A bounded retry may restate the complete, mechanism-neutral schema and require the Meta model to regenerate the entire output from the same hash-bound packet.
- Evidence: an independent audit of G13 attempts `_001` through `_003` found revision-prompt/validator drift and hidden fail-fast omissions. Attempt `_004` used the complete contract, passed the unchanged validator, and produced raw output SHA-256 `6609b286be192258ab0cb3ccace712139896cd80534be74d9bc71a1576bed071`.
- Boundary: the validated `_004` output authorizes only its `interface_investigation` research target. It does not freeze a code parent, Experiment, implementation, benchmark, launch, or benefit claim.
- Status: **validated and applied to G13 Research Meta selection**.

## D17. Programmed structural sensitivity is not real-model adoption evidence

- Decision: a no-task prototype may establish carrier shape, deterministic state transitions, fault separation, an information-bearing action view, and inertness. It may not establish provider acceptance, model authorship, visible-reference copying, or model compliance unless those endpoints are separately observed at the real provider/runtime boundary.
- Evidence: `g013_interface_investigation_001` passed 49 structural tests without a provider call; its manifest and independent verification preserve real-model endpoints as unknown.
- Status: **verified boundary; applied to G13 interface finding 001**.

## D18. A production/provider boundary is an admission premise, not a guessed implementation detail

- Decision: when a selected mechanism's structural prototype is verified but its carrier has not crossed the actual provider and production response boundary, Research Meta may request one bounded synthetic provider investigation before freezing an Experiment. The check must be discriminating and must not repeat already-established state-transition fixtures.
- Boundary: provider acceptance, exact opaque-token preservation, fail-closed instrumentation handling, privacy, and inertness may be interface findings. Real-model authorship, action compliance, semantic coverage, and benchmark benefit remain separate formal endpoints or unknowns.
- Evidence: G13 post-interface Research Meta `_002`, raw SHA-256 `10ea715d6c05a7c0c5fd1b489ec5933e4a274c6765e473c1a36bce21fc783f39`; `research_graph_memory_v14.json`.
- Status: **validated Research Meta decision; second G13 investigation pending**.

## D19. Provider-request compatibility failures are preserved separately from carrier acceptance

- Decision: a provider rejection caused by an unsupported request-control option is an interface-attempt failure, not evidence for or against the research mechanism. Preserve it, remove only the unsupported option in a new pre-registered attempt, and count both provider requests.
- Corrected interface fact: DeepSeek thinking mode rejected forced function `tool_choice`; the source-compatible automatic tool-selection request accepted the production schema and produced one exact opaque-token carrier.
- Boundary: the successful synthetic round trip establishes provider/schema/response-boundary feasibility only. Formal model-authorship rate, action compliance, semantic coverage, task-bearing privacy, benchmark benefit, and causal effect remain untested.
- Evidence: `g013_provider_boundary_investigation_001/failure_receipt.json`, `g013_provider_boundary_investigation_002/provider_boundary_receipt.json`, and independent verification SHA-256 `3f1b9512085b9475f7feff6da14124683ce528be9f9904356c27b0bf8135bcdb`.
- Status: **independently verified and appended to research memory v15**.

## D20. A validated post-finding contract may promote interface unknowns into formal endpoints

- Decision: once carrier/state/fault behavior and the real provider/production boundary have passed bounded interface checks, Research Meta may freeze an Experiment while leaving model authorship, coverage-state activation, and action compliance unproven. Those become separate formal endpoints with explicit supported/refuted/untested rules; they are not prerequisites that must be pre-proved by more interface work.
- Parent rule: code-parent selection remains a Research Meta evidence decision from the packet's verified trees. For G13, Meta selected G7 tree `572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac` as the last mechanism-neutral structural-instrumentation base, not because it was easiest to edit.
- Boundary: `experiment_ready` freezes a research contract but does not itself create source, pass admission, authorize a launch, prove task-bearing privacy, or establish benchmark benefit. Implementation, independent review, bounded admission, and the one fixed formal run remain distinct gates.
- Evidence: G13 post-finding Research Meta `_002`, raw SHA-256 `0e01fa9290e8ecf722a3e3092e60b74c335b15f439811774cb0c4bb4210bf3b1`; frozen contract SHA-256 `5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c`; memory v16 SHA-256 `fc206dac718781d9e3d9eb0dc79e2f6593e98d5e25cb9be3448124c8e15fe54e`.
- Status: **validated and active for G13 implementation handoff**.

## D21. Aggregate-only output tests do not prove producer-boundary privacy

- Decision: source admission for a content-blind mechanism must trace the raw carrier through every producer and persistence boundary, including provider-response logging, inherited tool dispatch, self-observation logs, persistent messages, final agent state, normalization, analyzer output, and evidence export. Scanning only the new sidecar, aggregate, and model-facing view is insufficient.
- Corrected implementation fact: G13's first manifest claimed privacy after scanning only derived surfaces, while the inherited record tool and LLM logger could persist the strict carrier. Independent review rejected that candidate state and preserved the failure. A bounded Implementation Meta revision inserted content-blind handling before persistence and added a provider-shaped end-to-end materialization test.
- Evidence: `g013_formal_implementation_002/source_review_001.json`, revised manifest SHA-256 `96e8874152ed3f8be070c37731bf906b556bdc27ca10fe5eaa4bef8b371c88ce`, and `source_review_002.json`.
- Boundary: this decision establishes local source/privacy admission only. Real-provider runtime behavior and task-bearing formal privacy remain gated by no-benchmark runtime admission and the frozen formal protocol.
- Status: **initial implementation review failed; revision independently passed source review**.

## D22. Content-blind assistant history must preserve native provider reasoning identity

- Decision: privacy sanitization at a provider tool-call boundary may change persisted arguments, but it must not silently destroy the provider adapter's authenticated multi-turn reasoning binding. A safe implementation must retain a content-blind lookup from sanitized history to the exact native reasoning already returned by the provider; it may neither persist the raw carrier nor fabricate reasoning text.
- Corrected implementation fact: G13 source review proved raw-token removal locally, but the first real multi-turn runtime probe showed that sanitizing `tool_calls` changed the DeepSeek adapter key while the proxy omitted `reasoning_content`. The next call was rejected locally before reaching the provider.
- Boundary: the same probe did verify one real model-authored carrier, one exact visible-token binding, one delivered view, and zero persisted token hits. Those facts do not override the failed admission or establish behavioral compliance.
- Evidence: `g013_admission_003/provider_probe_result.json` and `g013_admission_003/independent_failure_review.json`.
- Status: **runtime admission rejected; bounded Implementation Meta revision required before retry or formal launch**.

## D23. Native reasoning continuity may use volatile hydration, never persistent replay

- Decision: when privacy requires a sanitized persistent assistant tool call, authentic provider reasoning may be retained only in process-local, non-serialized state and restored only into a deep-copied provider request after exact structural-identity checks. The persistent message remains content-blind. Missing, ambiguous, mismatched, or conflicting bindings fail closed; reasoning is never reconstructed, summarized, or fabricated.
- Evidence: `g013_formal_implementation_003` manifest revision 3, child tree SHA-256 `b0acbc351292ba5653032eeda9dbf9191b855144211c2cf4813478e0f12aa351`, and independent source review SHA-256 `2574020cf1faa6ff69e80e9c5a3399d0278417965e6f8e6d5ba25b28eb34a741`.
- Boundary: synthetic adapter replay and source/privacy review do not prove real-provider runtime admission. The corrected attempt-004 probe must still cross the live production boundary before any formal launch.
- Status: **implemented and independently source-reviewed; runtime readmission pending**.

## D24. Content-blind native binding must preserve provider structural shape

- Decision: a privacy proxy may redact carrier arguments and omit reasoning content, but fields used to establish the provider's native tool-call identity must be preserved exactly, including optional provider fields such as `index`. Equality against a locally simplified proxy is not sufficient; a structural mismatch must continue to fail closed until a bounded implementation revision is independently reviewed.
- Corrected implementation fact: G13 attempt 004 received a real DeepSeek record call with keys `function/id/index/type`, while the persisted content-blind proxy emitted only `function/id/type`. The resulting native-binding conflict prevented the post-view request even though carrier authorship, token copying, directive delivery, privacy, and inertness had already been observed.
- Probe rule: missing, malformed, truncated, and provider-rejected fixtures must each be both fail-closed and explicitly classified. Test temporary roots must remain outside the frozen candidate source tree so generated artifacts cannot invalidate the candidate/parent comparison.
- Evidence: `g013_admission_004/admission_result.json` and independent failure review SHA-256 `2be712a20c4a3a84cdc326fb16b1b0671509a68269b0f7a5424794b427310ff3`.
- Status: **runtime admission blocked; bounded revision required before any fresh admission or formal launch**.

## D25. Interrupted Meta output is not a candidate without terminal completion

- Decision: a partially modified candidate directory is not an implementation result unless the frozen Implementation Meta reaches terminal completion and emits a final manifest that passes independent source/privacy review. After a process or desktop crash, preserve the directory, mark it interrupted, and restart from the last valid child in a new immutable attempt; do not resume or promote partial edits.
- Evidence: `g013_formal_implementation_004` / `g013_formal_implementation_meta_005` and `g013_formal_implementation_005` / `g013_formal_implementation_meta_006` ended without a complete candidate/review chain. The clean `g013_formal_implementation_006` / `g013_formal_implementation_meta_007` restart reached terminal completion and independent review.
- Boundary: this rule prevents crash artifacts from entering admission. It does not require discarding their audit logs or repeating a completed, independently reviewed candidate.
- Status: **applied; both interrupted attempts preserved and excluded**.

## D26. Content-blind privacy includes optional open self-observation sidecars

- Decision: when a mechanism declares opaque carrier fields non-persistent, sanitization must cover every producer that can copy those fields, not only the mechanism tool call, provider log, persistent messages, sidecar, and final state. Optional model-authored `self_observation` objects attached to ordinary action tools are persistence boundaries too.
- Corrected implementation fact: G13 admission 005 passed real-provider carrier, directive, action, fault, inertness, source-binding, and test subgates, but the post-view model copied one accepted requirement token into a `query_db.self_observation.what_i_know` item. The generic `tool_action_sidecar` writer persisted it in `agent_self_observations.jsonl`, so the privacy gate correctly blocked admission.
- Boundary: the repair must be G13-aware and content-blind without disabling or globally erasing ordinary non-G13 research observations. It must preserve authentic reasoning only in process-local state and retain all fail-closed native-binding checks. Passing behavioral subgates cannot compensate for a privacy failure.
- Evidence: `g013_admission_005/privacy_scan.json`, admission result SHA-256 `b9e23a8adc7b1839b80305ff374a98eb454624032362a4b99f67b2f8b018ebc7`, and independent failure review SHA-256 `45092cf1790edb234cfce2a208718857a6d8137f4103f05b462bf7a45d2dacec`.
- Status: **runtime admission blocked; bounded Implementation Meta persistence-boundary revision required before any fresh admission or formal launch**.

## D27. One content-blind projection must guard every G13 persistence producer

- Decision: once G13-sensitive carrier state is active, every persisted open self-observation producer must apply the same content-blind projection before bytes are written. This includes record-tool rows, optional action-tool sidecars, automatic observations, tool/LLM logs, persistent messages and final state, normalization, analyzer output, evidence packs, and aggregate sidecars.
- Preservation rule: the projection retains field names, container shape, counts, source/status metadata, reason codes, and aggregate counters. Actual tool dispatch remains transient and unmodified; disabled/non-G13/no-sensitive-state observations retain inherited content; authentic provider reasoning remains process-local and exact.
- Evidence: revision-5 child `64004f8ef66cb3b8071f8eef1f0bd48b3b0bdf931b64e95467c7412a591ef218`, manifest `98424bc0d4d257c82997d348f45bea0d5924e94d9aac323eb1506725ad68a2cd`, and independent review `2e320a6a2a40cc6b6da8c7d71c114145cd434c09aa9c4742ad833776a176887b`.
- Boundary: local source/privacy admission does not prove real-provider persistence behavior. A new bounded runtime admission and independent review remain mandatory before formal launch.
- Status: **implemented and independently source/privacy reviewed; runtime admission pending**.

## D28. A path-like sanitizer does not protect built-in `open(path)` persistence

- Decision: privacy review must verify the exact write API used by each upstream producer. A wrapper that sanitizes `Path.open()` is ineffective when the producer calls built-in `open(path)`, because Python resolves the wrapper through `__fspath__` and writes directly to the underlying file. Admission requires the bytes at the real producer boundary to be content-blind, not merely a sanitizer object attached to a path attribute.
- Corrected implementation fact: G13 admission 006 passed carrier, directive, action, fault, inertness, reasoning-continuity, and test subgates, but the live `record_self_observation` `BaseTool.exec` row persisted the three carrier tokens twice in `args.freeform` and `val_args.freeform`. The raw tool log remained remote-isolated and was not exported, but isolation does not satisfy the frozen zero-persistence gate.
- Test rule: inherited failure comparison must use the exact failed-nodeid sets and expected inherited count, not a hard-coded candidate pass total that changes when new passing tests are added.
- Evidence: `g013_admission_006/privacy_scan.json`, admission result SHA-256 `bed421c07aff99debbc948ff31877069c71ca25f3de26ce3e7aba5294bb57f54`, and independent failure review SHA-256 `4227f8bfb97d5e59cdd727ee0d65fc7d28e25abf2ffbbe6aed7dc8105f1e3b39`.
- Status: **runtime admission blocked; a bounded producer-boundary revision and fresh admission are required before formal launch**.

## D29. Protect the producer's argument object, not the global file API

- Decision: when inherited `BaseTool.exec` logs both `args` and validated `val_args` through built-in `open`, the bounded G13 repair supplies a content-blind argument copy only to that inherited persistence call and retains the exact carrier in a one-call process-local binding for strict validation and execution. The validated object is projected before serialization. Do not globally patch `builtins.open` or modify generic upstream logging.
- Preservation rule: disabled, non-G13, and no-sensitive-carrier logging remains inherited; actual dispatch and authentic reasoning stay transient; native identity checks and no-fabrication remain fail-closed.
- Regression rule: candidate/parent comparison is exact failed-nodeid set equality. Pass totals are descriptive and must never be hard-coded because adding passing focused tests legitimately changes them.
- Evidence: revision-6 child `31277b0514798b52b7547bb5cc12900c63d556fca0fc4919bff0b8be4902322c`, manifest `d8bd9714718343c51b30290e4ab1b8c8db5a077543a128f163cd48c34e36b5e1`, and independent review `095d36fa7b32a4f0b4b9f6bb048dffacacb9274574b8d993ac4566dee4629880`.
- Status: **implemented and independently source/privacy reviewed; runtime admission 007 pending**.

## D30. Runtime admission requires byte-level privacy at every real producer boundary

- Decision: a content-blind mechanism is runtime-admissible only when the real provider path crosses authorship, binding, directive, and action boundaries while every materialized producer remains free of exact carrier tokens and persisted reasoning fields. Local source scans or partial producer coverage cannot substitute for this live persistence check.
- Corrected implementation fact: after failures at assistant-history identity, optional provider `index`, action self-observation sidecars, and inherited built-in-open tool logging, revision 6 preserved exact transient carrier execution while projecting both raw and validated record-tool arguments before the actual inherited persistence call. Admission 007 then passed with one accepted carrier, exact token binding, one directive, one consistent `acquire_evidence` action, and zero persistence hits.
- Regression rule: candidate/parent comparison uses exact failed-nodeid equality; pass totals remain descriptive. Raw synthetic surfaces remain remote-isolated and hash-audited, not copied into research artifacts.
- Boundary: this decision establishes bounded no-benchmark runtime admissibility only. Formal task-bearing endpoints, score, causal benefit, and strict timing equivalence remain untested until the frozen formal Experiment completes and receives independent Evidence review.
- Evidence: admission result SHA-256 `2f1759d93ef77337e88a501b7b286b381fb4860ef421dfe94f32ef84741bae5e`; independent review SHA-256 `8d499cd636b651dc30faf7b83b8bc0180a2d599f2650f6246898025233926341`.
- Status: **validated for G13 formal-launch readiness review; not launch or outcome evidence**.

## D31. An admitted generation receives one atomic formal launch and one bound finalization

- Decision: after independent readiness review, a formal generation may create exactly one atomic launch claim. Monitoring is content-blind and cannot authorize a duplicate launch or restart. Natural runner exit plus exactly 56 terminal progress and summary rows is required before the hash-bound finalizer is invoked exactly once. A finalizer rejection preserves a diagnostic run; it does not authorize a fresh evaluation.
- G13 application: the sole remote attempt is `/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g013_formal_001`, run ID `g013_requirement_coverage_nohint_56_v1`, PID `709990`, claim SHA-256 `b3ec584af47e8f680b1ed085ebc7a01d2aedd84e1d0bf716b3cbb7a772e2facb`, launch-manifest SHA-256 `7d9a854b4eb3c3bedf4918a1041701b4d78a9156659291c2c5b2805ec19b85a7`, and finalizer-binding SHA-256 `4e59acae484ac070c39f85b57a516eb4a06f82bf1a1fd996313e9964b56a4dcc`.
- Runtime-binding exception: the bundled Python executable hash changed from expected `b07b03b9ba866a341a3c13ee69710fbc8d43d4ce2523dee13f6df5c25378d15b` to observed `7c4ee3011932a75b30db176f35fb91b28f0b299e608eaf643fb1bf36ed5ace99`. A bounded provider-only route review is valid for this formal evaluator because it invokes neither Meta nor Codex. It must not silently update, waive, or generalize the frozen Meta runtime binding.
- Evidence: prepare-only SHA-256 `e3873e96c3fa536e2fcff351d1e789e6897e9df6dd5b44327677791cb42d1572`; 56/56 prepared under `base_no_hint`, 1200 seconds per task, four workers, same-family serialization; content-blind checkpoint `2026-10-21T04:26:23Z` recorded 8/56 completed, runner active, no summary, and one claim.
- Boundary: launch and progress are execution facts, not outcome Evidence. Score, mechanism endpoints, benchmark benefit, causal interpretation, promotion, and Graph closure remain unknown until terminal finalization and independent review.
- Status: **applied; G13 formal run active and not yet finalized**.

## D32. A pre-gate finalizer import failure requires a separately bound recovery, not an implicit retry

- Decision: if a hash-bound finalizer exits before any evidence gate because its launch environment cannot resolve a frozen source dependency, preserve that invocation as a failed finalization attempt. Do not reinterpret terminal task statuses as Evidence, directly rerun the script, or rerun the formal evaluation.
- Corrected fact: G13 ended naturally with exactly 56 terminal rows, 52 completed and 4 task timeouts, but the first and only finalizer invocation exited 1 before gates. Its dynamic loader did not add `ATTEMPT/source` to `sys.path`, so the frozen extractor's absolute `experiments.g013_requirement_coverage` import raised `ModuleNotFoundError`. No `postrun/` or derived result exists; strict score and mechanism endpoints remain unknown.
- Recovery rule: preserve an immutable content-blind failure receipt, then create a unique recovery claim/binding over the unchanged finalizer, source, extractor, launch, terminal files, task manifest, exact source-root `PYTHONPATH`, and interpreter. Recovery execution requires separate independent authorization and remains subject to independent result review.
- Prohibition: do not patch the extractor, add package files, or otherwise change the frozen candidate tree after the run. Do not treat a working-directory change alone as a complete binding, and do not start G14 before G13 Evidence and Graph closure are independently validated.
- Evidence: progress SHA-256 `c6750f0d2d127d817dbfa76e4f79e1b1609527baa0f77826918b79296d5202f2`; summary SHA-256 `1e05433f487322b642316548b93d168c6a7ad6c405e796da88cf8cc426b3478c`; finalizer SHA-256 `3ef3d9c2e8c1886683daf410aa57863b2d4069a967adaf6b90d902f3a00be428`; Python 3.12.12 interpreter SHA-256 `3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66`.
- Status: **applied; G13 finalization blocked pending an independently authorized recovery binding**.

## D33. Environment-only recovery output remains a draft until procedural anomalies are reviewed

- Decision: a finalizer that failed before gates may be recovered once without rerunning the formal evaluation only when the frozen finalizer and all formal inputs remain unchanged and the repair is limited to the diagnosed invocation environment. The recovered files remain drafts; successful artifact creation does not waive independent review.
- G13 application: attempt 002 added only the exact frozen source root to `PYTHONPATH`. The original finalizer then produced a 31/56 draft outcome, content-blind privacy draft, Evidence draft, and terminal receipt. The mechanism did not activate, so all four mechanism endpoints remain untested.
- Procedural boundary: the enclosing shell wrapper corrupted the numeric exit-code capture after the finalizer completed, and the pre-execution recovery binding omitted the interpreter SHA field. Empty finalizer stderr, complete stdout, postrun hash consistency, and a post-execution matching interpreter attestation are evidence for review, not substitutes for the missing pre-bound field.
- Prohibition: do not retry finalization again, reinterpret the draft as independently validated Evidence, close the Graph, or start G14 until an independent reviewer adjudicates both anomalies and all postrun artifacts.
- Evidence: terminal receipt SHA-256 `a9f7ad3152116cd8b117f7705980b289f785f26fe0146258669f54c19e141b62`; recovery execution receipt under `g013_formal_001/finalizer_recovery_attempt_002/`.
- Status: **recovered finalization complete pending independent review**.

## D34. A verified environment-only finalizer recovery may close the same formal generation

- Decision: when a frozen finalizer's first invocation fails before reading aggregate sidecars or creating postrun output, one separately bound recovery may remain part of the same formal generation if it changes only the diagnosed invocation environment, leaves all frozen source and terminal inputs unchanged, and receives independent review before Graph closure.
- G13 application: the sole recovery added the exact frozen source root to `PYTHONPATH`. Independent review verified one formal run, one recovery, no third attempt, matching remote/local postrun hashes, and no partial output from the first failure. The outer exit 1 was caused by wrapper status interpolation after finalizer completion, not by the frozen Python finalizer.
- Limitation: the interpreter path and stable binary identity were independently verified at SHA-256 `3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66`, but the SHA was not pre-bound. This is retained as a procedural limitation and is not generalized as permission to omit interpreter bindings later.
- Result: G13 Evidence is independently validated at 31/56; the mechanism remains untested because all formal mechanism activation counts are zero. The four-node Graph and memory promotion may close without rerunning evaluation or finalization.
- Status: **applied to G13 closure only; future finalizers must bind their import root and interpreter hash before launch**.

## D35. Runtime identity drift must be recorded and narrowly rebound before Research Meta dispatch

- Decision: when an exact Meta runtime executable hash changes, fail before credential read or provider dispatch. A resumed Meta call may proceed only after recording the failed pre-provider attempt, verifying the new executable identity and unchanged Codex, PowerShell, provider route, model catalog, profile, and permission policy, and updating only the changed runtime hash.
- G14 application: attempt 001 stopped before provider dispatch. The bounded rebind changed only `tools.python.sha256` from `b07b03b9...d15b` to `7c4ee301...ace99` after verifying Python 3.12.14 x64 and the unchanged surrounding bindings. Attempt 002 explicitly used the independently bound Codex executable rather than resolving the desktop executable.
- Boundary: a formal-provider-only exception does not authorize Meta. Conversely, a recorded Meta rebind does not change model, endpoint, credentials, sandbox policy, research packet, or research selection.
- Status: **applied to G14 Research Meta runtime recovery**.

## D36. A Research Meta schema revision may repair serialization but cannot select the mechanism

- Decision: when provider-complete Research Meta output fails only a mechanical field-type contract, preserve the invalid attempt and permit one complete-object revision that restates the full unchanged schema and explicitly treats the prior output as data. Code may not patch research fields or treat the repair request as support for a candidate.
- G14 application: attempt 002 serialized `minimum_de_risking` as a string. An in-memory placeholder check established that this was the only observed schema failure without validating content. Attempt 003 returned a complete object and passed the original validator, selecting `mech_progressive_query_probing` for interface investigation.
- Boundary: validator success admits a research target to the incubation layer only. It does not freeze a parent or Experiment and does not authorize implementation, benchmark, or launch.
- Status: **applied to G14 target selection**.

## D37. A rejected interface investigation returns control to Research Meta

- Decision: when bounded interface revisions expose successive bypass classes, record the complete rejected investigation and independently reviewed finding in the incubation layer before selecting any successor direction.
- G14 application: three revisions passed progressively larger scoped suites but failed independent admission on distinct boundary bypasses. The result is a research finding, not authorization for a fourth hand-selected repair.
- Boundary: the deterministic memory append may preserve the finding, but only a new answer-blind Research Meta decision may revise the target, choose another investigation, change mechanism, or stop. Validator success on memory structure is not `experiment_ready` status.
- Status: **applied; G14 returned to research control**.

## D38. Lossless shape normalization may preserve a Research Meta result

- Decision: a provider-complete result may be normalized locally only when the change is transparent, lossless, independently recorded, and leaves all research statements unchanged; the original output must remain immutable and the full unchanged validator must pass afterward.
- G14 application: Research Meta emitted `minimum_de_risking` as one string where the validator requires a list. Wrapping that exact string in a one-item array was the sole normalization, after which validation passed.
- Boundary: this does not authorize semantic editing, a provider retry, Implementation Meta, or promotion. The selected target remains `interface_investigation`.
- Status: **applied to the G14 post-interface Research Meta result only**.

## D39. Do not scale the current G13 intent-first policy to 56 tasks

- Decision: the three-task paired panel is sufficient to reject a 56-task run of the current policy. Baseline and intent-first tied at 1/3 strict and equal aggregate model/tool calls, while intent-first used 21.19% more total tokens and finalized fewer tasks.
- Interpretation: requirement-driven evidence acquisition is viable without Graph-facing interfaces, but it is not a complete solver policy. On hard tasks it can become unresolved-coverage chasing or repeated Python synthesis.
- Next design boundary: retain requirement decomposition, but add sufficiency conditions, bounded attempts, synthesis-budget reservation, evidence compression, and an irreversible finalize phase. Validate that revision on another small paired panel before any 56-task run.
- Status: **current intent-first policy rejected for full evaluation**.

## D40. Treat convergence as a runtime control, not only a prompt instruction

- Decision: do not scale G13.1 to 56 tasks and do not spend a fresh paired control budget yet. Its prompt-level controls reduce aggregate cost but do not reliably force synthesis or finalization.
- Evidence: G13.1 matched the prior 1/3 strict result while reducing total tokens to 663,391 and model calls to 39. On Civic it still exhausted 20 turns, returned no answer, and made 15 Python calls despite guidance that normally capped Python at three.
- Next design boundary: enforce action counts, diminishing-return redirects, synthesis reserve, and final-answer fallback in the runtime. Test candidate-only on Civic and PATENTS before any fresh paired panel.
- Status: **G13.1 rejected for full evaluation; runtime-controller revision is the next bounded step**.

## D41. Independent local acceptance gates panel freezing, not panel execution

- Decision: an integrated candidate may advance from repair to small-panel protocol freezing only after a fresh source/privacy/contract review independently closes all blocking findings and reruns the declared provider-free suites. Acceptance at this gate does not authorize provider, database, benchmark, Meta, or Graph execution.
- G11-G13 application: review 002 verified F01-F04 closed, found no new P0/P1 or privacy/protocol/invariant issue, and observed 38/38 focused plus 58/58 selected-regression passes.
- Evidence: review SHA-256 `ff901bc92c30702f59f0e76c533500be3f4a30bb663097e0abed3bef647a657d`; validation SHA-256 `36a26e2a45bfc0c06e02bb54c0e89a75804b97e5d1bf719ad8c564c77407e527`.
- Status: **applied; next action is freeze-only for the six-question small panel, with execution still requiring explicit authorization**.

## D42. A frozen task panel is invalid if its batch path silently evaluates the base agent

- Decision: small-panel selection and protocol may be frozen independently of launch readiness, but execution is prohibited until every child is proven to enter the independently reviewed integrated candidate path. A generic batch runner that invokes the base entry point without the integrated flag would produce a mislabeled control run, not candidate evidence.
- Application: the six-task selection is frozen at zero-based parent-manifest indices `18,21,27,37,38,41`. The existing generic multi-query runner invokes `experiments/run_dab_tool_agent.py` directly and has no integrated-mode pass-through.
- Required next gate: create an isolated launcher without changing reviewed candidate behavior, independently source-review its exact activation path, then run provider-free prepare-only verification before any panel execution.
- Status: **panel selection/protocol frozen; launch not ready and no panel task executed**.

## D43. PostgreSQL statement limits must bind the tool connection, not only the child environment

- Decision: the DAB child runner must append the configured statement limit to upstream PostgreSQL query/list connection URLs. Environment-level `PGOPTIONS` is insufficient where upstream passes an explicit `options` URL parameter.
- Evidence: panel `006` completed two rows but its third child reached the 1200-second wall limit after a successful preload. A read-only probe of the exact upstream URL with `PGOPTIONS` set reported `statement_timeout=0`; the repaired tool path reported the configured 300-second limit. The focused suite passed 20/20.
- Boundary: this is an infrastructure containment repair only. It does not establish candidate quality, recover the invalid panels, or authorize 56-task expansion.
