# Legacy generated-solve DAB chain

This directory documents the retired one-shot generated-solve DAB pipeline.

The historical implementation files remain in `experiments/` for explicit legacy-run compatibility, but they are no longer the active research mainline:

- `experiments/run_dab_agent.py`
- `experiments/analyze_agent_error.py`
- `experiments/extract_primary_signal.py`
- `experiments/build_meta_agent_evidence_pack.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

The active mainline is now the multi-turn DAB tool-agent workflow:

- `experiments/run_dab_tool_agent.py`
- `experiments/analyze_dab_tool_agent_trace.py`
- `experiments/build_dab_tool_agent_evidence_pack.py`
- `experiments/run_meta_agent_evolution_loop.py`
- `experiments/run_codex_native_repair_launcher.py`

Do not route new parent evidence or child eval through the generated-solve chain unless an explicitly supplied legacy run directory requires it.
