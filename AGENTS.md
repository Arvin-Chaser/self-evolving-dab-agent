# Repository Guidance

## Mainline

The current research mainline is the DAB / DataAgentBench multi-turn tool-agent evolution pipeline.

Primary implementation targets:
- `experiments/`
- `adapters/`
- `prompts/dab/`
- DAB-related logs under `logs/dab_tool_agent/` and `logs/dab_agent/`

The main research loop is:
DAB tool-agent workflow execution -> deterministic full execution trace -> observer-agent fine-grained feedback -> archive-aware parent/evidence selection -> Codex/meta-agent candidate repair -> isolated child eval -> archive update.

## Legacy Code

`legacy/text2sql_demo/` is archived legacy code from an early Text-to-SQL demo loop.

The old one-shot generated-solve DAB chain (`experiments/run_dab_agent.py`, `experiments/analyze_agent_error.py`, `experiments/extract_primary_signal.py`, and `experiments/build_meta_agent_evidence_pack.py`) is also legacy for the current research mainline and has been moved under `legacy/cleanup_20260724_observer_trace_realign/`. Do not import it from active mainline code.

Codex should not treat legacy Text-to-SQL or one-shot generated-solve code as the primary implementation target. It may be used only as historical reference or a smoke-test example when explicitly requested.

Do not refactor or repair archived legacy code unless the user explicitly asks for legacy maintenance.

## Current Entry Points

Use these files for the active DAB / tool-agent line:
- `experiments/run_dab_tool_agent.py`
- `experiments/analyze_dab_tool_agent_trace.py`
- `experiments/build_dab_tool_agent_evidence_pack.py`
- `experiments/run_fine_grained_observer_agent.py`
- `experiments/run_direct_failure_observer_agent.py`
- `experiments/run_meta_agent_evolution_loop.py`
- `experiments/run_codex_native_repair_launcher.py`
- `experiments/archive_selector.py`
- `prompts/dab/dab_tool_agent_policy_zero_start.txt`

`llm_client.py` remains in the repository root for shared LLM-call compatibility, but new DAB tool-agent runs primarily go through `experiments/run_dab_tool_agent.py` and observer feedback goes through `experiments/run_fine_grained_observer_agent.py`.

## Cross-Session Research Memory

For non-trivial DAB research work, restore context from `docs/agent_memory/` before acting. Read in this order:

1. `CURRENT_STATE.md` for the verified present boundary and blockers.
2. `HANDOFF.md` for the next safe actions and prohibitions.
3. `PROJECT_OVERVIEW.md` for architecture and terminology.
4. `DECISIONS.md` and `EXPERIMENTS.md` when changing research direction, interpreting results, or selecting evidence.
5. `ENVIRONMENT.md` before any provider, server, database, or formal-run work.
6. `HISTORY_INDEX.md` only when historical provenance or the old Codex session must be traced.

Treat evidence in this order: current immutable experiment artifacts and manifests, current code/tests, Git metadata, then the redacted historical session index. A historical plan or assistant statement is not implementation evidence. Keep these states distinct: proposed, implemented, local tests passed, admitted, formally evaluated, and independently verified.

Update the memory after a material milestone:

- update `CURRENT_STATE.md` and `HANDOFF.md` when the active boundary or next action changes;
- append decisions and corrected beliefs to `DECISIONS.md`;
- append completed, invalid, interrupted, or superseded runs to `EXPERIMENTS.md` without erasing failures;
- update `ENVIRONMENT.md` only from a bounded verification, never with credential values;
- update `HISTORY_INDEX.md` when a new source archive or extraction pass is added.

Memory documents are not execution authorization. Re-check the dirty worktree, artifact hashes, live process state, disk space, provider boundary, and the user's current authorization before any formal run or destructive cleanup.
