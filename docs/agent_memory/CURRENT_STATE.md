# Current Research State

Verified on 2026-10-20. This file is a state snapshot, not permission to run an experiment.

## Repository

- Branch: `repair/patents-feedback-analyzer-v4`.
- HEAD: `9e0c752827cb306b31080e1004021940842c75bc` (`add DAB meta harness evolution updates`).
- Worktree before this documentation phase: 823 status entries: 20 tracked changes and 803 untracked paths.
- Most September/October research artifacts are untracked; Git history alone is not the research record.
- Do not reset, clean, checkout, commit, or push as part of memory restoration.

Status: **verified** from Git. Conflict note: root `CURRENT_STATE.md` and `PROJECT_HANDOFF.md` describe the older 17-task campaign as current; they were accurate on 2026-10-10 but are now stale relative to `experiments/research_graph_baseline_20261016/`.

## Authoritative research boundary

G0-G11 in `experiments/research_graph_baseline_20261016/` have completed four-node Graphs. The fixed metric is strict pass over all 56 frozen tasks; 1200-second timeouts are failures and do not shrink the denominator. Missing completed-task strict verdicts remain unknown.

The best observed score in this line is G6: 37/56 strict. It is an unpaired observation, not a proven causal improvement. G8, G9, and G11 each recorded 35/56. G11's mechanism was **untested** because all 53 completed tasks had zero model-authored records and zero guidance binding.

Evidence: G0-G11 evidence JSON files; especially `g006_safe_snapshot/g006_evidence.json` and `g011_solution_loop_safe_snapshot/g011_solution_loop_evidence.json`. Status: **formally evaluated and artifact-verified**.

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

Status: **bounded no-task runtime admission passed; still not formally evaluated and not promoted to a G12 Graph**. Evidence: `experiments/research_graph_baseline_20261016/g012_admission_005/`.

## G12 remaining boundary

The bounded gate requested on 2026-10-20 passed, but it is not benchmark Evidence and does not authorize a formal run. Strict timing equivalence remains unclaimed: the admitted control reports measured synthetic enabled/disabled timings only. Separate authorization for one formal 56-task run is still absent.

Independent research control has accepted `g012_admission_005` as a passed bounded no-benchmark admission. Do not create a launch claim, deploy, run the benchmark, promote G12 to the formal Graph, or state a score/benefit claim without separate authorization for the formal run.

## Other campaign states

- `dataset17_half56_deepseek_v1_20261011`: `ready_for_intent`, `next_generation=20`, last completed node Gen19. Historical only unless the user explicitly resumes it.
- `domain17_glm53_unbounded_v1_20260930`: `intent_sealed`, `next_generation=12`, `execution_status=paused_by_user`, `automatic_resume_authorized=false`.

Status: **verified from current `campaign_state.json` files**.

## Immediate safe work

Research-control read-only verification of `g012_admission_005` is complete and accepted as PASSED, including the preserved failed attempts and measurement-only timing limitation. Stop at this boundary. A formal 56-task run still requires separate explicit authorization; no benchmark execution is authorized by this admission result, and G13 has not been implemented.

## Version-inclusion milestone (2026-10-20)

- User-selected categories 1-3 were reviewed for safe Git inclusion; only explicit research source, tests, prompts, memory/protocol Markdown, and compact manifest/evidence summaries are being staged.
- Candidate repositories, raw traces/JSONL, provider probe payloads, runtime/benchmark trees, archives, and ambiguous one-off scripts remain in place and are not staged.
- The user selected categories 1-3 for one checkpoint commit: research source/tests/prompts and small tools; research memory/protocol documents; and compact manifest/evidence/Graph/verification metadata.
- Before the checkpoint, the index is being narrowed to those categories only. Candidate repositories, raw traces/JSONL, provider transcripts, runtime/benchmark copies, archives, symlink/mode-only noise, and Zone metadata remain outside the commit and are not cleaned from the worktree.
