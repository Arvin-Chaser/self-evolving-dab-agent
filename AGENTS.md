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

Use the tiered memory under `docs/agent_memory/`. Do not preload the whole memory set.

At the start of a non-trivial DAB task:

1. Read only `docs/agent_memory/CURRENT_STATE_BRIEF.md`.
2. Consult `docs/agent_memory/MEMORY_INDEX.json` to select any additional source needed for the specific task.
3. Read targeted sections or search hits from cold records; do not read an entire cold record unless the task genuinely requires it.

The following are cold records and are not part of default startup: `CURRENT_STATE.md`, `HANDOFF.md`, `PROJECT_OVERVIEW.md`, `DECISIONS.md`, `EXPERIMENTS.md`, `ENVIRONMENT.md`, `HISTORY_INDEX.md`, `docs/CODEX_HANDOFF.md`, historical session JSONL, raw logs, and full Research Graph memory JSON. Use `rg` and stable experiment, decision, node, or artifact IDs to retrieve the smallest relevant slice.

Treat evidence in this order: current immutable experiment artifacts and manifests, current code/tests, Git metadata, then the redacted historical session index. A historical plan or assistant statement is not implementation evidence. Keep these states distinct: proposed, implemented, local tests passed, admitted, formally evaluated, and independently verified.

Update the memory after a material milestone:

- replace the concise facts in `CURRENT_STATE_BRIEF.md` without turning it into an append-only log;
- update detailed `CURRENT_STATE.md` and `HANDOFF.md` only when the active boundary or next safe action materially changes;
- append decisions and corrected beliefs to `DECISIONS.md`;
- append completed, invalid, interrupted, or superseded runs to `EXPERIMENTS.md` without erasing failures;
- update `ENVIRONMENT.md` only from a bounded verification, never with credential values;
- update `HISTORY_INDEX.md` when a new source archive or extraction pass is added.

Follow `docs/agent_memory/MEMORY_POLICY.md` when changing the memory structure or orchestration rules. Do not duplicate facts already owned by another canonical file, paste routine command output into memory, or automatically rewrite memory after every turn.

Memory documents are not execution authorization. Re-check the dirty worktree, artifact hashes, live process state, disk space, provider boundary, and the user's current authorization before any formal run or destructive cleanup.

## Context and Agent Cost Guardrails

- Default to one Agent. Do not create subagents unless the user explicitly requests delegation or parallel Agent work.
- If delegation is authorized, use at most one subagent at a time, start it without inherited conversation history, give it a task packet no larger than 8 KB, and prohibit nested delegation.
- Do not poll Agents or processes in a tight loop. Use one bounded wait, then do independent work or return control; stop after two unchanged waits.
- Keep command and tool output bounded. Prefer hashes, counts, targeted line ranges, and artifact paths over full logs or recursive listings.
- Do not inject full historical sessions or long migration summaries. A cross-session handoff should be at most 4 KB and should point to canonical evidence.
- Do not use a fixed model/tool-cycle count or compaction count as a mandatory context-rotation boundary. The user normally decides when to start a fresh conversation, for example once per day or at a natural work-stage boundary.
- If retained context is approaching a platform limit, repeated compaction or degraded recall is making the work materially less reliable, or the Agent otherwise judges that continuation carries a substantial context-loss or cost risk, briefly recommend a fresh conversation. Do not stop the current task or create, fork, hand off to, or continue a replacement thread unless the user explicitly asks.
- If a platform hard limit makes reliable continuation impossible, perform only the minimum deterministic state capture needed for recovery, prepare a handoff no larger than 4 KB that points to canonical artifacts, and ask the user to start or authorize a replacement conversation. A user-authorized replacement must reuse the same project checkout, re-read `AGENTS.md`, `CURRENT_STATE_BRIEF.md`, and `MEMORY_INDEX.json`, and must not receive inherited conversation history, full logs, raw sessions, or full Research Graph memory. Existing provider, benchmark, database, server, formal-run, commit, and push authorization does not expand during rotation; restate the current authorization boundary in the handoff.
- Validation of Git state, hashes, manifests, schemas, and memory budgets must be deterministic when possible. Do not use an LLM merely to re-summarize or synchronize unchanged state.
- Provider, benchmark, database, server, formal-run, commit, and push operations still require the user's current authorization.
