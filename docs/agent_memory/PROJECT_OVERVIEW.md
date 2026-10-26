# DAB / Self-Evolving Agent Project Overview

Last reconciled: 2026-10-20 (Asia/Singapore).

## Research objective

The active project is a DataAgentBench multi-turn tool-agent evolution system. The goal is not merely to generate SQL, but to improve an agent that plans, calls database/Python tools, evaluates evidence, and returns an answer under a fixed evaluation protocol. The research loop preserves failures and mechanism evidence so that later Meta agents can choose a research target without depending on chat history.

Status: **verified current architecture**. Evidence: root `AGENTS.md`; `experiments/DAB_RESEARCH_GRAPH_BASELINE_WORKFLOW_V1.md`; current entry points under `experiments/`; Git HEAD `9e0c752`. Historical corroboration: session lines `S:20125`, `S:64125`, `S:86667`.

## Current architecture

```text
frozen DAB task set
  -> tool-agent execution and deterministic artifacts
  -> answer-blind observer / specialized extractor
  -> Evidence node and immutable four-node generation Graph
  -> layered Research Graph memory and Research Meta selection
  -> interface investigation when reachability is unknown
  -> Implementation Meta in an isolated child tree
  -> deterministic admission and unified preflight
  -> one isolated formal evaluation
  -> Evidence/Graph closure and memory append
```

Each completed formal generation contains exactly four typed nodes:

- `Problem`: an unresolved, evidence-backed research problem.
- `Hypothesis`: a falsifiable explanation or mechanism.
- `Experiment`: the intervention or diagnostic, its code parent, fixed protocol, measurement plan, and safety boundary.
- `Evidence`: immutable results, limitations, artifact hashes, and supported/contradicted/untested state.

The newer memory is two-layered. The formal layer contains completed benchmark generations. The incubation layer holds research targets, interface findings, blocked directions, and implementation findings that are not benchmark Evidence. Promotion occurs only after a target is `experiment_ready` and engineering admission succeeds. Evidence: `experiments/research_graph_baseline_20261016/research_graph_memory_v11.json`. Status: **verified**.

## Roles and trust boundaries

- Research Meta compares evidence, explores competing mechanisms, and selects at most one research target. It must not receive official answers, hints, validator targets, held-out tasks, credentials, or answer-bearing raw logs.
- Implementation Meta implements a frozen research contract in an isolated source tree. Its output is not admitted merely because code exists or tests pass.
- Deterministic code owns source-tree hashes, manifests, task/protocol binding, privacy checks, preflight, result extraction, and Graph closure.
- The benchmark run is evidence, not an optimization loop. Unpaired score differences are descriptive unless a matched causal design exists.
- The current user authorization always overrides historical automation or continuation instructions.

Status: **verified policy**, but enforcement varies by generation and must be checked in the relevant manifest. Evidence: `experiments/DAB_RESEARCH_GRAPH_BASELINE_WORKFLOW_V1.md`, G0-G11 Graphs, G12 implementation manifest, session `S:69401`, `S:71969`, `S:88815`.

## Active and historical lines

### Active research line

`experiments/research_graph_baseline_20261016/` is the current main research line. G0-G11 are closed four-node generations. G12 has an `experiment_ready` research target and a locally implemented candidate, but is not admitted or formally evaluated. See `CURRENT_STATE.md`.

### Older 56-task campaign

`experiments/dab_evolution_campaigns/dataset17_half56_deepseek_v1_20261011/` contains Gen1-Gen19 and later Gen15 repair branches. It is valuable historical evidence, especially for activation failures, but it is no longer the authoritative current workflow. Its `campaign_state.json` says `ready_for_intent`, `next_generation=20`; do not resume it by inference.

### Paused 17-task campaign

`experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930/` remains `paused_by_user`, `next_generation=12`, `stage=intent_sealed`. It is not the current research mainline and must not be resumed automatically.

### Legacy

`legacy/text2sql_demo/` and `legacy/cleanup_20260724_observer_trace_realign/` are historical only. Do not import archived one-shot generated-solve code into the current workflow.

## Evidence vocabulary

- **Verified**: directly checked against current artifacts, hashes, Git metadata, or deterministic records.
- **Locally verified**: implementation/tests/manifests passed without provider, benchmark, or formal evaluation.
- **Formally evaluated**: a bound task run naturally completed and its result artifacts were audited.
- **Supported / contradicted / untested**: the preregistered mechanism-evidence state, not a general quality judgment.
- **Historical**: supported by the redacted old session and possibly artifacts, but not re-executed now.
- **Pending confirmation**: incomplete, conflicting, or irrecoverable evidence.

Never collapse “planned”, “implemented”, “tests passed”, “admitted”, “formally run”, and “validated benefit” into one status.
