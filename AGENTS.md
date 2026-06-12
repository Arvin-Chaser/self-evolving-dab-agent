# Repository Guidance

## Mainline

The current research mainline is the DAB / DataAgentBench code-agent evolution pipeline.

Primary implementation targets:
- `experiments/`
- `adapters/`
- `prompts/dab/`
- DAB-related logs under `logs/dab/` and `logs/dab_agent/`

The main research loop is:
case execution -> generated code -> stage trace and structured logs -> stage-level failure observations -> primary signal selection -> targeted prompt evolution -> re-evaluation.

## Legacy Code

`legacy/text2sql_demo/` is archived legacy code from an early Text-to-SQL demo loop.

Codex should not treat the legacy Text-to-SQL demo as the primary implementation target. It may be used only as historical reference or a smoke-test example when explicitly requested.

Do not refactor or repair archived legacy code unless the user explicitly asks for legacy maintenance.

## Current Entry Points

Use these files for the active DAB / code-agent line:
- `experiments/run_dab_agent.py`
- `experiments/analyze_agent_error.py`
- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

`llm_client.py` remains in the repository root because the DAB / code-agent pipeline imports `call_llm()` from it.
