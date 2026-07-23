# Component Map

This document maps the DAB meta-agent project to a HyperAgent-style software
engineering architecture.

## HyperAgent-Style Roles

### Planner

Local responsibility:

- Decide the iteration flow.
- Track parent/child comparison.
- Decide whether the loop is ready for the next iteration.

Local components:

- future `experiments/run_meta_agent_loop.py`;
- `meta_agent/loop_design.md`;
- candidate and report files.

### Navigator

Local responsibility:

- Gather evidence for the coding/meta-agent.
- Select trajectory files, script run reports, analyzer output, and source refs.

Local components:

- future `experiments/build_evolution_task.py`;
- `trajectories/dab/`;
- `logs/dab_agent/`;
- `meta_agent/`;
- `adapters/runtime_observer.py`;
- `adapters/feedback/`.

### Code Editor

Local responsibility:

- Read the task package and source refs.
- Modify the data-agent project.
- Produce a patch and change summary.

Local components:

- Codex/Claude Code/human-in-the-loop meta-agent;
- `prompts/dab/meta_agent/project_evolve_prompt.txt`;
- `candidates/dab/`.

### Executor

Local responsibility:

- Run object-level data agents.
- Run analyzers.
- Validate parent/child behavior.

Local components:

- `experiments/run_dab_agent.py`;
- `experiments/analyze_agent_error.py`;
- feedback adapters;
- future comparison/reporting in `run_meta_agent_loop.py`.

## Evolution Targets

Primary targets:

- object-level prompts;
- meta-agent prompts;
- runner context construction;
- analyzer and problem-candidate logic;
- runtime observer logic;
- feedback adapters;
- task package construction;
- loop orchestration.

Protected targets:

- validators and ground truth;
- old logs/evidence;
- `legacy/`;
- low-level LLM client, unless explicitly approved.

## 中文说明

本文档把 DAB meta-agent 项目映射到 HyperAgent 风格的软件工程架构。

## HyperAgent 风格角色

### Planner

本地职责：

- 决定 iteration flow。
- 跟踪 parent/child comparison。
- 判断 loop 是否可以进入下一轮。

本地组件：

- 未来的 `experiments/run_meta_agent_loop.py`；
- `meta_agent/loop_design.md`；
- candidate 和 report 文件。

### Navigator

本地职责：

- 为 coding/meta-agent 收集证据。
- 选择 trajectory files、script run reports、analyzer output 和 source refs。

本地组件：

- 未来的 `experiments/build_evolution_task.py`；
- `trajectories/dab/`；
- `logs/dab_agent/`；
- `meta_agent/`；
- `adapters/runtime_observer.py`；
- `adapters/feedback/`。

### Code Editor

本地职责：

- 阅读 task package 和 source refs。
- 修改 data-agent 项目。
- 生成 patch 和 change summary。

本地组件：

- Codex / Claude Code / human-in-the-loop meta-agent；
- `prompts/dab/meta_agent/project_evolve_prompt.txt`；
- `candidates/dab/`。

### Executor

本地职责：

- 运行 object-level data agents。
- 运行 analyzers。
- 验证 parent/child 行为。

本地组件：

- `experiments/run_dab_agent.py`；
- `experiments/analyze_agent_error.py`；
- feedback adapters；
- 未来 `run_meta_agent_loop.py` 中的 comparison/reporting。
