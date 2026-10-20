# Environment and Operations Memory

No credential value is stored here. Paths and commands are operational references, not authorization.

## Local environment

- Repository: `C:\Users\34934\source\text2sql`.
- Shell: PowerShell 7.6.5.
- Python observed on PATH: 3.12.4.
- Git: 2.55.0.windows.2.
- ripgrep: 15.2.0.
- `CODEX_HOME`: unset during migration. The old session was found under `C:\Users\34934\.codex\sessions`.
- Current API route config: `configs/dab_active_api_route.json` selects `deepseek_official`, model `deepseek-flash`, base URL `https://api.deepseek.com/v1`, Meta profile `deepseek-standalone-dab`, and disables automatic resume of old runs.

Status: **verified locally on 2026-10-20**. Provider availability and credentials were not tested.

## Remote formal-evaluation host

Historical and current artifacts identify:

- host: `root@100.83.10.33`;
- SSH identity path: `C:/Users/34934/.ssh/codex_ct104`;
- required options: `IdentitiesOnly=yes`, `BatchMode=yes`;
- project root: `/srv/text2sql`;
- Python: `/srv/text2sql/.venv/bin/python`;
- Research Graph runtime root: `/srv/text2sql/evolution_runtime/research_graph_baseline_20261016`.

Before any remote action, the historical workflow requires the first remote command to be `df -hT /srv/text2sql`. Then verify no matching active process, exact runtime paths, and available disk. Do not assume the latest historical disk snapshot is current.

Read-only connection template:

```powershell
ssh -i C:/Users/34934/.ssh/codex_ct104 `
  -o IdentitiesOnly=yes -o BatchMode=yes `
  root@100.83.10.33 "df -hT /srv/text2sql"
```

Status: **historically verified route; not contacted during this migration**. Evidence: session `S:20742`, `S:64125`, `S:87981`.

## Fixed formal protocol used by G0-G11

- exactly 56 frozen tasks;
- full base database description, no hints;
- `deepseek-flash`;
- `max_iterations=0`;
- model request timeout 600 seconds, two attempts, 20-second delay, SDK retries disabled;
- per-task runner wall limit 1200 seconds;
- PostgreSQL statement timeout 1,080,000 ms;
- four workers, same-dataset serialization and cross-dataset concurrency;
- observer skipped during the batch; evidence extraction occurs after execution;
- primary score strict/56; timeout is failure.

Status: **verified from Graph experiment nodes and historical launch records**. Re-read the actual candidate and launcher before any future run; do not reconstruct a launch command from this summary alone.

## Provider and Meta boundary

Meta calls historically use `experiments.dab_meta_runtime.meta_environment('deepseek-standalone-dab')` with `run_logged_command`. Do not invoke the desktop/default route directly: an earlier attempt reached the wrong CRS route and returned 403. Provider 503 and DNS incidents must be recorded as infrastructure failures.

Never print or copy:

- API key file contents;
- tokens, cookies, Authorization headers, environment dumps, or private keys;
- official answers, validator targets, held-out tasks, or answer-bearing raw traces into Meta packets.

The redacted old-session index replaced 182 credential-like matches. A post-generation residual scan found zero common private-key, Bearer, OpenAI-style, AWS, GitHub, or Slack credential patterns.

## Disk and cleanup boundary

Historical runs produced very large stderr files and database copies. Some explicitly authorized old logs/copies were removed or losslessly compressed, but that authorization does not generalize.

Before cleanup:

1. resolve the exact path and owning run;
2. prove the run is inactive;
3. preserve Graphs, results, traces, manifests, sources, incidents, and hash journals;
4. never delete original databases or broad roots;
5. obtain current user authorization for the exact target.

Status: **active safety rule**, based on session `S:20742`, `S:57753`, `S:81736`.

## Session extraction tools

The historical session index can be regenerated without modifying the source:

```powershell
python tools/extract_codex_session_memory.py --help
python tools/query_codex_session_index.py `
  docs/agent_memory/source_index/session_01a124ff-f402-7763-8200-0fba53b96381 `
  --start-line 1 --end-line 10000 --compactions-only
```

Read `HISTORY_INDEX.md` before regenerating. The existing index already covers the complete source and should not be overwritten casually.
