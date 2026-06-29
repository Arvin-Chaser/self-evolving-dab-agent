# Repository Cleanup Plan

This plan is intentionally non-destructive. Do not delete or move existing artifacts until the active meta-agent loop is stable and the user has approved the cleanup batch.

## Current diagnosis

The repository is dirty for two different reasons:

- Some active DAB/meta-agent infrastructure is still untracked or mixed with experimental files.
- Older generated artifacts were tracked before ignore rules were strict enough.

Current tracked artifact counts observed on 2026-06-26:

- `logs/`: 72 tracked files
- `archive/`: 26 tracked files
- `candidates/`: 21 tracked files
- `trajectories/`: 0 tracked files
- `reports/`: 0 tracked files

Current dirty top-level distribution was dominated by:

- `candidates/`: local candidate bundles
- `logs/`: tracked deleted historical run logs
- `experiments/`: active infrastructure plus local scripts
- `prompts/`: historical prompt deletions and current prompt edits
- `archive/`: local index updates used by selector experiments

## Keep in active mainline

Keep these as normal source-controlled project code after review:

- `experiments/run_dab_agent.py`
- `experiments/analyze_agent_error.py`
- `experiments/extract_primary_signal.py`
- `experiments/meta_agent_cycle.py`
- `experiments/run_meta_agent_evolution_loop.py`
- `experiments/run_codex_qwen_repair_launcher.py`
- `experiments/build_meta_agent_evidence_pack.py`
- `adapters/runtime_observer.py`
- `adapters/feedback/`
- `skills/dab-meta-agent-project-memory/`
- `skills/dab-patents-project-repair/`
- `tools/codex_qwen_bounded_proxy.py`
- active prompt(s) under `prompts/dab/`

## Keep as local artifacts, not git mainline

These should normally stay on disk for research continuity but should not be committed as ordinary source:

- `logs/`
- `candidates/`
- `trajectories/`
- `reports/`
- local `.codex/`
- transient `archive/indexes/*` updates from experimental selector runs

If a run is important, promote a small summary card or review report instead of committing the full run directory.

## Move to legacy only when it is old source, not generated output

`legacy/` should hold retired code or prompt architectures, not large run artifacts. Good candidates after review:

- early DAB prompt families no longer usable as parent agents;
- old one-off meta-agent scripts replaced by the current launcher/loop;
- retired Text2SQL demo code, already under `legacy/text2sql_demo/`.

Suggested future location:

```text
legacy/dab_early_prompts_202606/
legacy/dab_one_off_launchers_202606/
```

## Recommended cleanup sequence

1. Commit or stash active source-code changes that belong to the current DAB meta-agent infrastructure.
2. Add/confirm ignore rules for generated artifacts.
3. Stop tracking historical generated artifacts with `git rm --cached`, not by deleting the user's local files.
4. Move only reviewed old source/prompt families to `legacy/`.
5. Keep the archive as a local experiment database; export lightweight summary snapshots only when needed for reproducibility.

## Candidate commands for a later approved cleanup batch

Do not run these without explicit approval:

```bash
git rm --cached -r logs
git rm --cached -r candidates
git rm --cached -r archive
```

If archive selector state needs to remain versioned, replace the broad archive removal with a narrow policy that tracks schemas or curated snapshots only.
