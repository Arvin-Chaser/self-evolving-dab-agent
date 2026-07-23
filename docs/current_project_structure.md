# Current project structure

This repository now treats the DAB / DataAgentBench multi-turn tool-agent evolution pipeline as the active research mainline. The old one-shot `generated_solve.py` path and Codex-Qwen proxy experiments have been archived under `legacy/cleanup_20260724_observer_trace_realign/`.

## Active mainline

- `experiments/run_dab_tool_agent.py`
  Runs one DAB tool-agent workflow. It records LLM calls, tool calls, workflow state, final answers, and the normalized `full_execution_trace.jsonl` artifact.

- `experiments/analyze_dab_tool_agent_trace.py`
  Performs deterministic analysis over a DAB tool-agent run: answer quality, selected stage/signal, helper usage, and trace-level observations.

- `experiments/build_dab_tool_agent_evidence_pack.py`
  Builds compact evidence artifacts for meta-agent repair from the current tool-agent run format.

- `experiments/run_fine_grained_observer_agent.py`
  LLM observer that reads the raw run behavior, especially `full_execution_trace.jsonl`, and generates flexible fine-grained feedback without relying on the old fixed failure taxonomy.

- `experiments/run_direct_failure_observer_agent.py`
  Parent/child comparison observer. It now prioritizes `full_execution_trace.jsonl` when collecting run artifacts.

- `experiments/run_meta_agent_evolution_loop.py`
  Orchestrates parent selection, parent run/reuse, deterministic analysis, observer feedback injection, Codex-native repair, isolated child eval, and archive update.

- `experiments/run_codex_native_repair_launcher.py`
  Generates and validates Codex-native repair candidates. This is the active candidate launcher; the old Codex-Qwen proxy launchers are legacy.

- `experiments/meta_agent_cycle.py`
  Postprocesses candidates, scores child evals, applies parent-eligibility gates, and updates archive-facing candidate state.

- `experiments/archive_selector.py` and `experiments/archive_observation.py`
  Select parent/evidence candidates from archive and preserve observations for future evolution.

## Active data-agent policy and skills

- `prompts/dab/dab_tool_agent_policy_zero_start.txt`
  Current zero-start DAB tool-agent policy baseline.

- `skills/dab-meta-agent-project-memory/`, `skills/dab-tool-agent-zero-start-memory/`, `skills/dab-tool-agent-zero-start-repair/`
  Current project memory/repair guidance for meta-agent runs.

## Active adapters

- `adapters/feedback/`
  Feedback/error-analysis infrastructure shared by trace analyzers.

- `adapters/patents/`
  Domain helper modules generated or used during PATENTS evolution experiments.

## Evolution records

- `archive/`
  Long-lived agent/candidate indexes, cards, selection metadata, and parent/evidence records.

- `candidates/dab/`
  Candidate patch bundles produced by meta-agent repair runs.

- `trajectories/meta_agent_loops/`
  Loop-level parent/candidate/child-eval run records.

- `logs/dab_tool_agent/`
  DAB tool-agent execution logs, including full execution traces.

## Legacy / historical material

- `legacy/text2sql_demo/`
  Early Text-to-SQL demo code.

- `legacy/generated_solve_dab/` and `legacy/cleanup_20260724_observer_trace_realign/`
  Archived one-shot `generated_solve.py` DAB runner/analyzer, Codex-Qwen proxy launchers, old prompt-repair skills, and historical tests.

These legacy paths are reference material only. Active evolution should not import or repair them unless the user explicitly asks for legacy maintenance.
