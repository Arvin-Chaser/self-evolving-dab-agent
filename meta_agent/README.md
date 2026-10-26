# DAB Meta-Agent Workspace

This directory documents the project-level evolution workspace for the DAB data
agent.

The goal is to evolve the data agent as a software project. The agent is not
only a prompt: it includes prompts, runners, runtime observer code, generated
scripts, runtime logs, analyzers, feedback adapters, task packaging, candidate
patches, and evaluation workflow.

The architecture follows a lightweight HyperAgent-style split:

- Planner: loop coordination and parent/child comparison.
- Navigator: evidence packaging and source-reference selection.
- Code Editor: coding/meta-agent that edits the project.
- Executor: data-agent execution, analysis, and validation.

## Core Method

Agent-generated runtime instrumentation is the fine-grained feedback mechanism.
The runner injects a local `runtime_observer.py` into each run directory, and
the LLM-generated `solve.py` should use it to emit runtime logs during actual
local execution. Function decomposition is allowed, but the feedback signal is
the runtime event stream: checks, anomalies, fallbacks, exceptions, counts,
warnings, and answer-contract evidence.

The meta-agent then uses these signals, plus script-level reports from project
scripts, to decide which project component to evolve.

## Mainline Scripts

- `experiments/run_dab_agent.py`: run the object-level data agent.
- `experiments/analyze_agent_error.py`: produce observations/problem candidates.
- `experiments/build_evolution_task.py`: package evidence for the meta-agent.
- `experiments/run_meta_agent_loop.py`: coordinate parent/child project-level
  evolution.

The last two scripts are planned mainline pieces and should be added next.

## Mainline Loop

1. Run a parent data agent on selected DAB cases.
2. Save raw run artifacts and runtime logs.
3. Analyze run artifacts into problem candidates.
4. Package artifacts, script reports, source refs, and scope docs into a
   meta-agent task.
5. Let a coding/meta-agent produce a bounded project patch.
6. Save child candidate metadata and patch.
7. Re-run and analyze the child data agent.
8. Compare parent and child behavior.

## Important Directories

- `experiments/`: executable experiment entry points and orchestrators.
- `prompts/dab/`: object-level data-agent prompts.
- `prompts/dab/meta_agent/`: coding/meta-agent prompts.
- `adapters/feedback/`: reusable feedback adapters.
- `trajectories/dab/`: normalized evidence packages when needed.
- `candidates/dab/`: parent/child candidate metadata, patches, and summaries.
- `logs/dab_agent/`: raw DAB data-agent execution logs.
- `logs/meta_agent/`: raw meta-agent execution logs.
- `reports/meta_agent/`: comparison summaries and experiment notes.

## Baseline Scripts

These scripts remain useful as historical baselines, but they should not drive
the new project-level loop:

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

## 中文说明

这个目录说明 DAB data agent 的项目级演进工作区。

我们的目标是演进一个完整 data-agent 项目，而不是只优化一段 prompt。这里的 agent
包括 prompts、runner、runtime observer code、generated scripts、runtime logs、
analyzer、feedback adapters、task packaging、candidate patches 和 evaluation workflow。

架构借鉴轻量 HyperAgent 分工：

- Planner：loop 编排和 parent/child 对比。
- Navigator：证据打包和 source refs 选择。
- Code Editor：真正修改项目的 coding/meta-agent。
- Executor：data-agent 执行、分析和验证。

## 核心方法

agent-generated runtime instrumentation 是细粒度反馈信号的生成机制。runner 会把本地
`runtime_observer.py` 注入每个 run 目录，LLM 生成的 `solve.py` 应该使用它在真实本地执行
过程中输出 runtime logs。函数拆分可以作为代码组织方式，但反馈信号是 runtime event
stream：checks、anomalies、fallbacks、exceptions、counts、warnings 和 answer-contract evidence。

meta-agent 再根据这些信号，以及项目脚本自己的 script-level reports，决定演进哪个项目组件。

## 主线脚本

- `experiments/run_dab_agent.py`：运行 object-level data agent。
- `experiments/analyze_agent_error.py`：生成 observations / problem candidates。
- `experiments/build_evolution_task.py`：给 meta-agent 打包证据。
- `experiments/run_meta_agent_loop.py`：编排 parent/child project-level evolution。

后两个是下一步要补的主线脚本。

## 主线循环

1. 用 parent data agent 跑选定 DAB cases。
2. 保存 raw run artifacts 和 runtime logs。
3. 把 run artifacts 分析成 problem candidates。
4. 把 artifacts、script reports、source refs 和 scope docs 打包成 meta-agent task。
5. 让 coding/meta-agent 生成有边界的 project patch。
6. 保存 child candidate metadata 和 patch。
7. 重新运行并分析 child data agent。
8. 比较 parent 和 child 行为。
