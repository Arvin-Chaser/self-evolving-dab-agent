# Meta-Agent Loop Design

This document defines the minimal project-level loop for evolving the DAB data
agent.

## Goal

The loop should mimic a lightweight HyperAgent-style software engineering
workflow:

- Planner: decide the iteration goal and compare parent/child behavior.
- Navigator: gather trajectory, script reports, feedback, and source references.
- Code Editor: modify the data-agent project and produce a patch.
- Executor: run the parent/child agents and verify the patch.

The meta-agent should evolve the project itself: prompts, runner logic,
runtime observer logic, analyzer logic, feedback adapters, task packaging, and
evaluation workflow.

## Mainline Scripts

The new mainline has four scripts:

1. `experiments/run_dab_agent.py`
   - Runs the object-level data agent.
   - Produces raw run artifacts.

2. `experiments/analyze_agent_error.py`
   - Reads raw run artifacts.
   - Produces structured observations/problem candidates.
   - Does not choose a single primary signal and does not decide how to repair.

3. `experiments/build_evolution_task.py`
   - Packages run artifacts, analyzer output, script run reports, and source
     references.
   - Produces the meta-agent task package.

4. `experiments/run_meta_agent_loop.py`
   - Coordinates parent run, analysis, task building, meta-agent patching, child
     rerun, and comparison.

## Minimal Loop

1. Select search cases.
2. Run the parent data agent with `run_dab_agent.py`.
3. Analyze parent run artifacts with `analyze_agent_error.py`.
4. Build a meta-agent task package with `build_evolution_task.py`.
5. Let the coding/meta-agent inspect evidence and project files.
6. Let the coding/meta-agent produce a bounded project patch.
7. Save child candidate metadata, patch, and change summary.
8. Re-run the child data agent.
9. Analyze child run artifacts.
10. Compare parent and child behavior.

## Feedback Signals

The loop should use these signals:

- object-level trajectory from generated `solve.py`;
- adaptive runtime events produced by generated `solve.py` through the injected
  local `runtime_observer.py`;
- script-level `script_run_report.json` from project scripts;
- analyzer-produced problem candidates;
- parent/child pass-fail and behavior comparison;
- patch/change summary from the meta-agent.

## Baseline / Non-Mainline Scripts

These existing scripts are useful references but should not drive the new
project-level loop:

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

They make fixed prompt-level decisions that should now be left to the
project-level meta-agent.

## Deferred Work

- Held-out evaluation.
- Full automation of the coding/meta-agent call.
- runtime LLM observer/probe planning beyond the initial local runtime observer.
- Large benchmark sweeps.

## 中文说明

本文档定义 DAB data agent 的最小项目级演进循环。

## 目标

这个 loop 借鉴轻量 HyperAgent 风格的软件工程流程：

- Planner：决定本轮目标，并比较 parent/child 行为。
- Navigator：收集 trajectory、script reports、feedback 和 source references。
- Code Editor：修改 data-agent 项目并生成 patch。
- Executor：运行 parent/child agent 并验证 patch。

meta-agent 要演进的是项目本身，包括 prompts、runner、runtime observer、analyzer、
feedback adapters、task packaging 和 evaluation workflow。

## 主线脚本

新主线包含四个脚本：

1. `experiments/run_dab_agent.py`
   - 运行 object-level data agent。
   - 生成 raw run artifacts。

2. `experiments/analyze_agent_error.py`
   - 读取 raw run artifacts。
   - 生成 structured observations / problem candidates。
   - 不选择唯一 primary signal，也不决定怎么修。

3. `experiments/build_evolution_task.py`
   - 打包 run artifacts、analyzer output、script run reports 和 source refs。
   - 生成 meta-agent task package。

4. `experiments/run_meta_agent_loop.py`
   - 编排 parent run、analysis、task building、meta-agent patch、child rerun 和 comparison。

## 最小循环

1. 选择 search cases。
2. 用 `run_dab_agent.py` 运行 parent data agent。
3. 用 `analyze_agent_error.py` 分析 parent run artifacts。
4. 用 `build_evolution_task.py` 构造 meta-agent task package。
5. 让 coding/meta-agent 阅读 evidence 和项目文件。
6. 让 coding/meta-agent 生成有边界的 project patch。
7. 保存 child candidate metadata、patch 和 change summary。
8. 重新运行 child data agent。
9. 分析 child run artifacts。
10. 比较 parent 和 child 行为。

## 反馈信号

loop 应该使用这些信号：

- generated `solve.py` 通过注入的本地 `runtime_observer.py` 产生的 adaptive runtime events；
- 项目脚本产生的 `script_run_report.json`；
- analyzer 产生的 problem candidates；
- parent/child pass-fail 和行为对比；
- meta-agent 产生的 patch/change summary。

## Baseline / 非主线脚本

以下已有脚本可作为参考，但不应该驱动新的 project-level loop：

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

它们会提前做固定的 prompt-level 决策；这些决策现在应该交给 project-level
meta-agent。
