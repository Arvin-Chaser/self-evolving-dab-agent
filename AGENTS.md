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
