# Evolution Targets

This document lists what the project-level meta-agent may evolve.

## Phase 1 Targets

These are suitable for the first minimal project-level loop:

- `prompts/dab/`: object-level prompt and runtime observer usage contract.
- `prompts/dab/meta_agent/`: coding/meta-agent prompt.
- `adapters/runtime_observer.py`: injected runtime observer used by generated
  `solve.py` to emit local execution logs.
- `experiments/analyze_agent_error.py`: analyzer wrapper and problem candidate
  output.
- `adapters/feedback/`: common and domain-specific feedback adapters.
- `experiments/run_dab_agent.py`: narrow runner instrumentation and
  pre-execution guards when evidence shows generated code is regressing before
  meaningful runtime feedback can be collected.
- `experiments/build_evolution_task.py`: evidence packaging and task
  construction.
- `experiments/run_meta_agent_loop.py`: loop orchestration and reporting.

## Phase 2 Targets

These should wait until the minimal loop is stable:

- broad `experiments/run_dab_agent.py` rewrites or generalized DAB context
  loading changes.
- richer script-level `script_run_report.json` generation for all mainline
  scripts.
- data-completeness and data-validity feedback.
- held-out evaluation selection.

## Baseline / Not Mainline

These scripts can remain as references, but should not decide the new
project-level evolution process:

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

## Avoid as Targets

- benchmark validators or ground truth;
- old logs, old trajectories, and historical evidence;
- `legacy/text2sql_demo/`;
- broad project rewrites;
- changes requiring external network access;
- `llm_client.py`, unless explicitly approved.

## Method Principle

Agent-generated runtime instrumentation is a research method, not just prompt
style. The LLM-generated `solve.py` should use the local `runtime_observer.py`
to emit logs during actual execution. Function decomposition is allowed, but the
main feedback signal is the runtime event stream triggered by local checks,
anomalies, fallbacks, exceptions, and answer-contract checks. The meta-agent can
then evolve prompts, the runtime observer, runner injection, analyzer logic,
feedback adapters, and task packaging based on those fine-grained signals.

## 中文说明

本文档列出 project-level meta-agent 可以演进的对象。

## 第一阶段目标

这些目标适合最小 project-level loop：

- `prompts/dab/`：object-level prompt 和 runtime observer 使用约束。
- `prompts/dab/meta_agent/`：coding/meta-agent prompt。
- `adapters/runtime_observer.py`：注入到 run 目录、供 generated `solve.py`
  输出本地执行日志的 runtime observer。
- `experiments/analyze_agent_error.py`：analyzer wrapper 和 problem candidate output。
- `adapters/feedback/`：通用和领域特定 feedback adapters。
- `experiments/run_dab_agent.py`：当证据显示 generated code 在产生有效 runtime
  feedback 之前就回归时，可以做窄范围 runner instrumentation 和 pre-execution guards。
- `experiments/build_evolution_task.py`：证据打包和 task construction。
- `experiments/run_meta_agent_loop.py`：loop orchestration 和 reporting。

## 第二阶段目标

这些目标应该等最小 loop 稳定后再做：

- 大范围 `experiments/run_dab_agent.py` 重写，或更通用的 DAB context loading 改造。
- 所有主线脚本的 `script_run_report.json`。
- data-completeness 和 data-validity feedback。
- held-out evaluation selection。

## Baseline / 非主线

这些脚本可以保留为参考，但不应该决定新的 project-level evolution 流程：

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

## 避免作为演进目标

- benchmark validators 或 ground truth；
- old logs、old trajectories 和历史证据；
- `legacy/text2sql_demo/`；
- 大范围项目重写；
- 需要外部网络访问的修改；
- `llm_client.py`，除非明确批准。

## 方法原则

agent-generated runtime instrumentation 是研究方法，不只是 prompt 风格。LLM 生成的
`solve.py` 应该使用本地 `runtime_observer.py`，在真实本地执行过程中输出日志。函数拆分
可以作为代码组织方式，但主要反馈信号是由 runtime checks、anomalies、fallbacks、
exceptions 和 answer-contract checks 触发的 runtime event stream。meta-agent 再根据这些
细粒度信号演进 prompts、runtime observer、runner injection、analyzer、feedback adapters
和 task packaging。
