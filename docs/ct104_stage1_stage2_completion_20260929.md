# CT104 DAB stage 1–2 completion record

Date: 2026-09-29

## Stage 1: environment and deployment audit

- Host: `CT104` (`100.83.10.33` over Tailscale).
- Deployment root: `/srv/text2sql`.
- The deployment root is a copied source tree, not a Git checkout. Future
  updates must therefore use explicit file manifests, hashes, and backups.
- Official DataAgentBench materialization: 104/104 tasks discovered.
- Storage: 125 GB total, 91 GB available at audit time.
- Memory: 16 GiB total, approximately 15 GiB available at audit time.
- Python: 3.12.12 in `/srv/text2sql/.venv`.
- `dab-postgres`: healthy and accepting connections on loopback port 5432.
- `dab-mongo`: healthy (`ping=1`) on loopback port 27017.
- No DAB/meta-agent runner process was active during the audit.
- The server credential file is mode `600`, owned by `root:root`; its contents
  were not printed.
- All previously deployed active DAB files checked during the audit matched the
  local SHA-256 values. `intent_candidate_workspace.py` and the roadmap
  protocol were new deployments.
- Pre-deployment files were preserved under
  `/srv/text2sql/audit_tmp/stage2_backup_20260929_1212`.

### Network finding

The school API endpoint was reachable from the Windows host (`HTTP 401` without
credentials, which proves service reachability) but CT104 could not establish a
TCP connection to `10.29.1.10:3001`. CT104 routed that address through
`10.10.10.11` using source `10.10.10.227`. This is a network-path problem, not
an API-key validation result. It must be resolved, or replaced with a narrowly
scoped reverse tunnel, before live DAB runs.

## Stage 2: roadmap protocol

Implemented:

- `experiments/dab_roadmap_protocol.py`
  - append-only roadmap with a verified hash chain;
  - separate code parent and information-parent snapshot;
  - sealed mechanism intent;
  - immutable candidate, result, and detailed-review artifacts;
  - compact roadmap nodes with second-level evidence links;
  - explicit review outcomes for implementation, integration, activation,
    behavioral effect, and task effect;
  - review-controlled `promote_candidate` versus `retain_parent` transition;
  - Codex intent/review calls with no subprocess wall-clock deadline;
  - candidate coding/repair with explicit `timeout=0`.
- `experiments/intent_candidate_workspace.py`
  - canonical bounded source-tree parent hash for multi-file harness evolution;
  - backward-compatible historical single-file parent binding;
  - source admission with changed-file scope, compilation, exact DAB entrypoint,
    and claim-to-source checks;
  - no candidate-generation wall-clock deadline by default.
- `experiments/run_multi_query_baseline.py`
  - explicit Python executable for isolated candidate source snapshots;
  - deployed query-path resolution against the official DAB root;
  - runner/source/interpreter provenance in the batch summary.
- `docs/dab_roadmap_evolution_protocol.md`
  - operating sequence, boundaries, evaluation command, and admission gates.

## Verification

- Six local synthetic tests passed.
- Three focused server lifecycle tests passed.
- Server source compilation passed.
- Server roadmap verification passed.
- A one-query server `prepare-only` batch passed without calling a model.
- A real `glm-5.3-flash` Codex meta-agent call successfully produced and sealed
  generation-1 intent `schema_anchored_execution_memory`; the invocation record
  states `started_without_wall_clock_deadline: true`.
- `deepseek-v4-flash` returned HTTP 403: the current token is not authorized for
  that model. This is distinct from timeout, high load, or candidate import
  failure.

## Gate before stage 3

Do not start live DAB evolution until:

1. CT104 can reach the data-agent API, directly or through an explicitly
   authorized restricted tunnel;
2. the non-full evolution batch is frozen;
3. the baseline parent is run on exactly that batch; and
4. the formal campaign directory is initialized from the final deployed source
   hash.
