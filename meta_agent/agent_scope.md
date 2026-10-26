# Meta-Agent Scope

This file defines the default edit boundary for a coding/meta-agent that
improves the DAB data-agent project.

## Primary Editable Areas

- `prompts/dab/`
- `prompts/dab/meta_agent/`
- `adapters/runtime_observer.py`
- `experiments/analyze_agent_error.py`
- `experiments/build_evolution_task.py`
- `experiments/run_meta_agent_loop.py`
- `adapters/feedback/`
- `meta_agent/`

## Conditional Editable Areas

- `experiments/run_dab_agent.py`: editable when evidence points to runner,
  context-loading, execution, or artifact-writing issues.
- `trajectories/dab/`: new evidence packages may be created, but historical
  evidence must not be rewritten.
- `candidates/dab/`: candidate manifests, patches, change summaries, and scores
  may be written.
- `reports/meta_agent/`: comparison reports and experiment notes may be written.
- `logs/meta_agent/`: raw meta-agent process logs may be written.

## Baseline / Reference Areas

These scripts can be read but should not drive the new mainline:

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

## Protected Areas

- `legacy/text2sql_demo/`
- benchmark validators, ground truth, and expected answers
- old run logs and historical evidence
- `.git/`, `.env`, virtual environments, and external benchmark source trees
- `llm_client.py`, unless explicitly approved
- `adapters/dab_validator.py`, except for read-only inspection

## Preferred Change Style

- Prefer small, reviewable patches.
- Make one conceptual change per candidate when possible.
- Ground every change in runtime-log, analyzer, comparison, or script-level evidence.
- Record every candidate change as a patch and a short rationale.
- Do not make fixed repair decisions in helper scripts when the meta-agent
  should decide them from evidence.

## 中文说明

这个文件定义 coding/meta-agent 改进 DAB data-agent 项目时的默认编辑边界。

## 主要可修改区域

- `prompts/dab/`
- `prompts/dab/meta_agent/`
- `adapters/runtime_observer.py`
- `experiments/analyze_agent_error.py`
- `experiments/build_evolution_task.py`
- `experiments/run_meta_agent_loop.py`
- `adapters/feedback/`
- `meta_agent/`

## 有条件可修改区域

- `experiments/run_dab_agent.py`：当证据指向 runner、context loading、execution 或
  artifact writing 问题时可以改。
- `trajectories/dab/`：可以创建新证据包，但不能改写历史证据。
- `candidates/dab/`：可以写 candidate manifests、patches、change summaries 和 scores。
- `reports/meta_agent/`：可以写比较报告和实验记录。
- `logs/meta_agent/`：可以写 meta-agent 过程日志。

## Baseline / Reference 区域

这些脚本可以读，但不应该驱动新主线：

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

## 保护区域

- `legacy/text2sql_demo/`
- benchmark validators、ground truth 和 expected answers
- old run logs 和历史证据
- `.git/`、`.env`、虚拟环境和外部 benchmark 源码树
- `llm_client.py`，除非明确批准
- `adapters/dab_validator.py`，除非只读检查

## 推荐修改风格

- 优先做小而可 review 的 patch。
- 尽量每个 candidate 只做一个概念改动。
- 每个改动都要基于 runtime log、analyzer、comparison 或 script-level evidence。
- 每个 candidate 都要记录 patch 和简短理由。
- 不要在辅助脚本里写死修复决策；这些决策应该由 meta-agent 基于证据决定。
