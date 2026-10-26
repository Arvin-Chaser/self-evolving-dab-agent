# Codex Project Recovery Handoff

> Cold one-time recovery record. It is preserved for provenance and is not part of default session startup. Use `docs/agent_memory/CURRENT_STATE_BRIEF.md` first.

Recovered on 2026-10-21 (Asia/Shanghai). This document is a recovery snapshot, not authorization to run an experiment, contact a provider, modify the remote host, commit, or push.

## Evidence labels

- **Verified**: checked against the current worktree, Git metadata, immutable artifacts, hashes, or current Codex thread metadata.
- **Historical**: reported by a prior session or an older document but not re-executed in this recovery.
- **Inference**: a proposed interpretation or next step, clearly separated from observed facts.
- **Unknown**: unavailable, stale, or not safely rechecked.

## Recovered objective and interruption point

**Verified:** The active project is the DAB / DataAgentBench multi-turn tool-agent Research Graph line under `experiments/research_graph_baseline_20261016/`. G0-G13 have closed four-node Graphs. The active generation is G14.

**Verified:** G14 Research Meta selected `mech_progressive_query_probing`, primary lens `action_tool_policy_recovery`, in state `interface_investigation`. No code parent, formal Experiment, formal candidate, benchmark run, or launch is frozen for G14.

**Verified:** Three bounded synthetic, no-task G14 interface revisions exist. Their scoped suites recorded 40, 64, and 100 passing tests, but independent review rejected each revision:

1. revision 001 allowed bool/integer aliases and caller-controlled cap/deadline bypasses;
2. revision 002 allowed direct public dataclass construction to bypass validation;
3. revision 003 still allowed numeric subclasses with custom comparison behavior to bypass the one-action cap and deadline guard.

The terminal review status is `rejected_bounded_stop_return_to_research_control`, SHA-256 `c4c8c947b0a2b04ad0b822b50693c44f0f5206014e20fcd8a1b9118993766a51`. It prohibits promotion or entry into Implementation Meta from these revisions. No provider, benchmark, database, formal evaluation, or formal candidate was involved in the investigation.

**Verified:** The most recent prior Codex task is `01a15895-c0e3-7991-90d2-c4691aff2cbf`, title `检查 DAB 研究进度`. Its last substantive turn failed with HTTP 402: `已达到每日费用限制 ($200)`. The delegated recovery task failed for the same reason.

**Verified:** Immediately before the quota failure, that task created the untracked script `experiments/finalize_research_graph_g014_rejected_finding.py`, SHA-256 `f959f3e39e43ae236cbdf7563f700b2f41970e502f5f15d81225f522c930d86c`. Its intended purpose is to append the rejected G14 investigation and finding to Research Graph memory v19. A direct invocation failed with `ModuleNotFoundError: No module named 'experiments'` before producing the output. `research_graph_memory_v19.json` does not exist.

**Verified:** No local process other than the recovery check itself matched G14 or the Research Graph runtime at the end of this investigation.

Therefore the exact interrupted development goal was: append the rejected G14 finding to the incubation layer, validate the new memory, then return the finding to real post-interface Research Meta. It was not to perform a fourth implementation repair or start a formal evaluation.

## Current Git and worktree state

- **Verified repository:** `C:\Users\34934\source\text2sql`.
- **Verified branch:** `repair/patents-feedback-analyzer-v4`.
- **Verified HEAD:** `2ec626da9bdfb9982bc2f1358b7047f1041a8373`, dated 2026-10-21 00:31:19 +08:00, subject `checkpoint DAB research graph through G12 admission`.
- **Verified configured upstream:** `origin/repair/patents-feedback-analyzer-v4`.
- **Verified local comparison:** ahead/behind is `0/0` against the current local remote-tracking ref. No fetch was performed, so the live remote repository state is unknown.
- **Verified remote URL:** `git@github.com:Arvin-Chaser/self-evolving-dab-agent.git`.
- **Verified index:** no staged changes.
- **Verified working tree before adding this handoff:** 882 default status entries: 22 tracked unstaged entries and 860 untracked entries. `git ls-files --others --exclude-standard` enumerated 61,858 untracked files.
- **Verified tracked state:** 19 modified paths and three deleted `Zone.Identifier` alternate-stream paths. Four research-memory Markdown files are modified, along with active experiment entry points and several legacy/script files. Many apparent zero-line modifications are mode/metadata differences.
- **Verified diff limitation:** an unfiltered `git diff --stat` fails when Git tries to hash the three missing tracked `Zone.Identifier` paths. Excluding those paths yields 19 changed paths, 838 insertions and 19 deletions.
- **Verified benchmark dependency anomaly:** Git expects `benchmarks/DataAgentBench` as gitlink `5b2afd5f0088e6bda9c8e7de68de346f054666bb`, but the worktree path is currently a zero-byte ordinary file, not a usable checkout. This must be repaired or re-materialized deliberately before any benchmark work; do not overwrite it during recovery.
- **Verified unpushed work:** there are no local commits ahead of the current local upstream ref, but all G13/G14 work and much of the September/October research state remain uncommitted or untracked. The branch being `0/0` does not mean the research work is safely pushed.

Do not reset, clean, checkout, switch branches, stage, commit, or push without a separately reviewed preservation plan.

## Current research boundary

### G13: formally closed

**Verified from current artifacts:** G13 completed one fixed 56-task, base/no-hint formal run with four workers and same-dataset-family serialization:

- 56 ended;
- 52 completed;
- 4 wall-timeout failures;
- 0 other/provider/infrastructure terminal failures;
- 31 strict pass;
- 18 known strict fail;
- 3 completed strict-verdict unknown;
- primary result: **31/56 strict**.

No model-authored record, accepted record, directive, view, or post-directive action was observed. Structural binding, real-model authorship, coverage-state behavior, behavioral action choice, and the overall mechanism are all `untested`. The result is descriptive and unpaired, not a causal benefit claim.

Verified G13 hashes:

- Evidence: `8dfdcaa180e2641475e5c481f98f612f788eea6f8bd82070f87bd85b4f83bcb7`;
- Graph: `a231eff12aad1d850b79b89e791bd1c8bd8d43d4941ff28c684cc8a4ff2b32b6`;
- independent review: `3e6249178e8a5aedcd88023468e8da8c361402d40d9207284cdd0202d4fb72c7`;
- closure receipt: `d77aa4e00511992ef78bc0b884faec047073dba5d4118807f6839c5f1a27a480`;
- Research Graph memory v17: `176d91bca69138088353be80735c9ce8c93d36bf8b661ca57d10cd3bf88cd648`.

The first finalizer invocation failed before gates because the frozen source root was absent from `sys.path`. One separately reviewed environment-only recovery added the exact source root through `PYTHONPATH`; independent review accepted the output while retaining the missing pre-bound interpreter hash as a procedural limitation.

### G14: research target selected, interface investigation rejected

**Verified:** The G14 answer-blind packet covers closed G0-G13, 28 symmetric formal facts, 27 incubation nodes, and 14 verified code parents. Packet SHA-256 is `0e4525b5f8378f536eb68fa36125d076f319b08ecd6dc60a80625a4824711b04`.

Research Meta attempt 001 stopped before provider invocation because the bundled Python hash drifted. A recorded rebind changed only that runtime hash. Attempt 002 was provider-complete but schema-invalid because `minimum_de_risking` was a string. Attempt 003 passed the unchanged validator; its raw output SHA-256 is `5a5d53429db99b5437bb4ac5aff3a34c4f34386cc3fc67872daf0609e8f0c7ad`.

Research Graph memory v18 SHA-256 is `51c2283f77db70185790b6d660e6b00d3c55a83ed2523d3a27746554cac3fe8b`. It contains `research_target:g014:001`, but does not yet contain the three-revision rejected interface finding.

Verified G14 interface manifest hashes:

- revision 001: `8f8c42f0997f78f637d549f37abae9d165200bc0eae5697b1002814433d38ee4`;
- revision 002: `d4c9b6ed8cc4f73b90455b29145172b644d8ff53cfb718b5aa3d9f9d83f0b5ad`;
- revision 003: `22d1e78f44c54fd2143b758c473d3eb677f8c087b208009618d71233d9c4a04b`.

The passing scoped suites establish only the tested ordinary paths. The independent counterexamples override the manifests' pending verification status and block promotion.

## Experiment summary

All Research Graph formal generations use a fixed 56-task, base-description, no-hint protocol with a 1200-second per-task wall limit unless explicitly recorded otherwise. Timeouts remain failures in the denominator.

| Generation | Strict/56 | Important status |
| --- | ---: | --- |
| G0 | 33 | baseline root |
| G1 | 30 | reserve reached 5/56 |
| G2 | 30 | lifecycle localization partly untested |
| G3 | 35 | structural concordance supported; prior DNS incident preserved |
| G4 | 34 | alignment prediction contradicted |
| G5 | 30 | diagnostics supported; reason-code subclaim untested |
| G6 | 37 | highest observed score; unpaired, not causal |
| G7 | 32 | last-pre-exec elapsed localization supported |
| G8 | 35 | preterminal audit structure supported |
| G9 | 35 | later-turn gate structure supported |
| G10 | 27 original / 32 repaired view | repaired view is supplementary, not one uninterrupted run |
| G11 | 35 | mechanism untested: zero authored records/bindings |
| G12 | 30 | mechanism untested: zero formal activation |
| G13 | 31 | mechanism untested: zero formal activation; independently closed |

The best observed result is G6 at 37/56. It must not be described as a proven causal improvement.

Recent important failures remain part of the record: G13 admission attempts 003-006 exposed reasoning-identity, provider-native shape, self-observation sidecar, and built-in `open()` persistence defects before admission 007 passed; G13's first finalizer invocation failed before gates; G14 interface revisions 001-003 all failed independent adversarial review despite passing their own scoped suites.

## Environment and data locations

### Local

- Repository: `C:\Users\34934\source\text2sql`.
- PowerShell: 7.6.5.
- Python on PATH: 3.12.4.
- Git: 2.55.0.windows.2.
- ripgrep: 15.2.0.
- Local C: free space observed during recovery: 87,590,887,424 bytes.
- Codex session root exists at `C:\Users\34934\.codex\sessions`.
- Current route config selects provider `deepseek_official`, model `deepseek-flash`, base URL `https://api.deepseek.com/v1`, Meta profile `deepseek-standalone-dab`, and `automatic_resume_old_runs=false`.

No credential value was read or written.

### Remote and formal-run locations

The following are **historically/artifact verified locations**, not a current connectivity or health check:

- host: `root@100.83.10.33`;
- SSH identity path: `C:/Users/34934/.ssh/codex_ct104` (file existence verified; contents not read);
- project root: `/srv/text2sql`;
- Python: `/srv/text2sql/.venv/bin/python`;
- current Research Graph runtime root: `/srv/text2sql/evolution_runtime/research_graph_baseline_20261016`.

The remote host was not contacted during this recovery. Current remote disk, processes, databases, provider availability, quota, and credential validity are unknown. Before a future authorized remote action, the repository policy requires a fresh bounded disk/process/path/provider check; historical snapshots are not sufficient.

### Local research data

- Active Research Graph artifacts: `experiments/research_graph_baseline_20261016/`.
- Older 56-task campaign: `experiments/dab_evolution_campaigns/dataset17_half56_deepseek_v1_20261011/` (historical; state previously recorded as `ready_for_intent`, next generation 20).
- Older 17-task campaign: `experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930/` (historical and paused by user).
- DAB task/runtime material also exists under `dab_corpus/`, `query_workspaces/`, and `external/`; much of it is untracked.

Do not resume either older campaign by inference.

## Documentation and history reconciliation

- There is no root `README.md` in the current worktree.
- `AGENTS.md` and `docs/agent_memory/` are the current guidance sources.
- Root `CURRENT_STATE.md` and `PROJECT_HANDOFF.md` are dated 2026-10-10 and describe the older 17-task Gen12 campaign; they are stale for the current Research Graph line.
- `meta_agent/README.md` still names old one-shot entry points that `AGENTS.md` now classifies as legacy. Treat that README as historical architecture context, not the current execution plan.
- `docs/agent_memory/CURRENT_STATE.md`, `HANDOFF.md`, `DECISIONS.md`, and `EXPERIMENTS.md` are current through G14 target selection, but they do not yet record the three rejected G14 interface revisions or the quota interruption.
- The redacted historical index in `docs/agent_memory/source_index/session_01a124ff-f402-7763-8200-0fba53b96381/` was complete for the indexed source snapshot. The underlying JSONL has since grown from 345,029,482 bytes / SHA-256 `ad7974...` to 345,042,753 bytes / SHA-256 `dac52597de93c6e9bd2948476e13c628c5ed9c92d85f2cb857f77032911211af`; therefore the existing index is no longer complete for later appends.
- The newer project session is stored at `C:\Users\34934\.codex\sessions\2026\10\20\rollout-2026-10-20T17-12-51-01a15895-c0e3-7991-90d2-c4691aff2cbf.jsonl` and was inspected through the Codex thread API. Its file was active/locked during recovery, so no whole-file hash was obtained.

## Unfinished tasks

1. **Preserve and independently review** `experiments/finalize_research_graph_g014_rejected_finding.py`. Its content is present, but it has not executed successfully and has no validated output.
2. **After explicit continuation authorization**, execute the append operation in an import context that resolves the repository package (for example a reviewed module invocation or explicit repository-root import binding). Do not modify the three rejected investigation artifacts. Verify all bound input hashes, validate the resulting memory, and record the new memory SHA-256. Do not infer that the failed direct invocation authorizes an unreviewed retry.
3. Build a new answer-blind, hash-bound post-interface Research Meta packet from the validated memory containing the rejected finding.
4. Call real Research Meta once under the bound Meta route. It must decide whether to revise the target, request a genuinely different bounded investigation, select another mechanism, or select none. The orchestrator must not choose the mechanism or perform a fourth repair automatically.
5. Only if a later validator-approved Research Meta result reaches `experiment_ready` should Implementation Meta, admission, or a formal run be considered.
6. After the next material milestone, update `docs/agent_memory/CURRENT_STATE.md`, `HANDOFF.md`, `DECISIONS.md`, and `EXPERIMENTS.md` append-only, preserving all rejected attempts and the quota interruption.
7. Separately plan preservation/versioning of the large dirty worktree. Do not combine that cleanup/versioning task with G14 research execution without explicit scope review.

## Unknowns and blockers

- **Unknown:** live remote host, disk, process, database, and provider state; no SSH check was performed.
- **Unknown:** current provider and CRS daily quota/reset state. The prior Codex task failed on a `$200` daily limit; this recovery did not test or change it.
- **Unknown:** whether the live Git remote has changed since the local remote-tracking ref was last updated; no fetch was performed.
- **Blocked for benchmark work:** `benchmarks/DataAgentBench` is not materialized as a usable gitlink checkout.
- **Blocked for G14 continuation until confirmation:** the user explicitly requested investigation and handoff first, with no experiment, provider call, server mutation, commit, or push.
- **Not a blocker but a preservation risk:** most G13/G14 artifacts are untracked; accidental cleanup would destroy the current research record.

## Actions taken in this recovery

- Performed read-only Git, filesystem, documentation, artifact-hash, local environment, process, and Codex-thread checks.
- Did not run tests, experiments, providers, databases, benchmark code, finalizers, launchers, or SSH commands.
- Did not modify research code, experiment artifacts, existing memory documents, Git index, branches, commits, remotes, or server state.
- Added only this handoff document.
