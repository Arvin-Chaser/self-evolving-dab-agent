# CT104 DAB baseline runs

This host has the official 104-query DataAgentBench checkout at
`/srv/text2sql/external/DataAgentBench_official`, the project virtual environment
at `/srv/text2sql/.venv`, and local-only PostgreSQL and MongoDB containers.
The project registry was regenerated on CT104 from the official checkout.

The helper script loads the API key from `/root/.config/dab/school_api.env` without
printing it, uses the direct school API endpoint, passes each domain’s full
`db_description.txt`, and produces per-query run traces and deterministic
post-run validator feedback. It does not run the LLM observer or meta-agent.

Run a bounded five-query batch:

```bash
cd /srv/text2sql
tools/run_ct104_dab_batch.sh \
  --batch dab_corpus/batches/multi_query_arch_smoke_001.json \
  --run-id dab_five_001
```

Run the complete 104-query baseline only when the expected API cost and runtime
are acceptable:

```bash
cd /srv/text2sql
tools/run_ct104_dab_batch.sh --all-queries --run-id dab_full_001
```

If interrupted, repeat the **same selection and run ID** with `--resume`.
Use a new run ID for a real run after `--prepare-only`; prepared runs are not
resumed as real runs. Completed per-query runs are skipped on resume. An
incomplete or differently configured per-query run stops rather than silently
overwriting its trace.

Results appear under `/srv/text2sql/logs/multi_query_baseline/<run-id>/`.
`multi_query_progress.json` updates after each query; `multi_query_summary.json`
contains `strict_pass_count`. Each query has its own normalized full execution
trace under the `runs/` subdirectory. An agent process exiting successfully
does **not** necessarily mean it answered correctly: check
`strict_match_passed` and `final_answer_nonempty`.

This setup supports baseline DAB evaluation. Historical candidate archives,
query workspaces, and Codex-driven meta-agent repair have not been validated
for continuation on CT104.
