# Script Contracts

This document describes the scripts that belong to the new DAB project-level
meta-agent mainline.

Each mainline script should eventually emit a `script_run_report.json` so the
meta-agent can inspect how the script behaved and decide whether that script
itself should be evolved.

## Mainline Scripts

### `experiments/run_dab_agent.py`

Role: object-level data-agent executor.

Responsibilities:

- Build the object-level prompt from a DAB case.
- Call the LLM to generate `solve.py`.
- Inject `runtime_observer.py` into the run directory.
- Save `prompt.txt`, `raw_llm_output.txt`, and `generated_solve.py`.
- Execute the generated script.
- Validate `final_answer.txt`.
- Save run artifacts under `logs/dab_agent/`.

Expected feedback:

- prompt build status;
- LLM call status and latency;
- generated code extraction status;
- runtime observer injection status;
- generated script execution status;
- missing artifacts;
- validation result;
- paths to all generated artifacts.

Evolution space:

- prompt context construction;
- case/schema/sample loading;
- runtime observer injection;
- generated-code execution wrapper;
- artifact and report writing.

### `experiments/analyze_agent_error.py`

Role: feedback analyzer.

Responsibilities:

- Read run artifacts from `run_dab_agent.py`.
- Parse runtime logs from the generated script.
- Call feedback adapters.
- Produce structured observations and problem candidates.
- Avoid choosing a single primary signal or deciding the repair.

Expected feedback:

- loaded/missing artifact counts;
- runtime log quality;
- runtime event count;
- adapter results;
- problem candidate count;
- diagnosis confidence and uncertainty.

Evolution space:

- observation extraction;
- problem candidate schema;
- feedback adapter selection;
- analyzer self-feedback.

### `experiments/build_evolution_task.py`

Role: Navigator/task packager.

Responsibilities:

- Gather run artifacts, analyzer output, script run reports, and source refs.
- Build `task.md` for the coding/meta-agent.
- Build `context_manifest.json`.
- Record what evidence was included or omitted.

Expected feedback:

- evidence inclusion/exclusion report;
- missing context;
- source refs selected;
- token/readability budget;
- meta-agent readiness score.

Evolution space:

- evidence selection;
- source-reference selection;
- task prompt structure;
- context manifest schema.

### `experiments/run_meta_agent_loop.py`

Role: Planner/Executor coordinator.

Responsibilities:

- Run the parent candidate.
- Analyze parent artifacts.
- Build a meta-agent task package.
- Wait for or call a coding/meta-agent to produce a patch.
- Save child candidate metadata.
- Re-run and analyze the child candidate.
- Compare parent and child behavior.

Expected feedback:

- parent/child scores;
- patch application status;
- changed files;
- improved/regressed cases;
- loop failures;
- validation plan status.

Evolution space:

- orchestration policy;
- human-in-the-loop vs automatic mode;
- candidate management;
- comparison/reporting policy.

## Baseline / Reference Scripts

These existing scripts are not part of the new mainline:

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

They can be kept as historical baselines, but the new meta-agent should decide
problem priority, repair target, and patch content itself.

## 中文说明

本文档描述新的 DAB project-level meta-agent 主线脚本。

每个主线脚本后续都应该输出 `script_run_report.json`，让 meta-agent 不仅能看
data agent 的运行结果，也能看每个项目脚本自己的执行过程，从而决定这些脚本是否需要被演进。

## 主线脚本

### `experiments/run_dab_agent.py`

角色：object-level data-agent executor。

职责：

- 根据 DAB case 构造 object-level prompt。
- 调用 LLM 生成 `solve.py`。
- 把 `runtime_observer.py` 注入 run 目录。
- 保存 `prompt.txt`、`raw_llm_output.txt` 和 `generated_solve.py`。
- 执行生成脚本。
- 验证 `final_answer.txt`。
- 把 run artifacts 保存到 `logs/dab_agent/`。

反馈信号：

- prompt build status；
- LLM call status 和 latency；
- generated code extraction status；
- runtime observer injection status；
- generated script execution status；
- missing artifacts；
- validation result；
- 所有生成 artifacts 的路径。

可演进空间：

- prompt context construction；
- case/schema/sample loading；
- runtime observer injection；
- generated-code execution wrapper；
- artifact/report writing。

### `experiments/analyze_agent_error.py`

角色：feedback analyzer。

职责：

- 读取 `run_dab_agent.py` 产生的 run artifacts。
- 解析 generated script 产生的 runtime logs。
- 调用 feedback adapters。
- 生成 structured observations 和 problem candidates。
- 不选择唯一 primary signal，也不决定修复方式。

反馈信号：

- loaded/missing artifact counts；
- runtime log quality；
- runtime event count；
- adapter results；
- problem candidate count；
- diagnosis confidence 和 uncertainty。

可演进空间：

- observation extraction；
- problem candidate schema；
- feedback adapter selection；
- analyzer self-feedback。

### `experiments/build_evolution_task.py`

角色：Navigator / task packager。

职责：

- 收集 run artifacts、analyzer output、script run reports 和 source refs。
- 生成给 coding/meta-agent 的 `task.md`。
- 生成 `context_manifest.json`。
- 记录哪些 evidence 被包含或省略。

反馈信号：

- evidence inclusion/exclusion report；
- missing context；
- selected source refs；
- token/readability budget；
- meta-agent readiness score。

可演进空间：

- evidence selection；
- source-reference selection；
- task prompt structure；
- context manifest schema。

### `experiments/run_meta_agent_loop.py`

角色：Planner / Executor coordinator。

职责：

- 运行 parent candidate。
- 分析 parent artifacts。
- 构造 meta-agent task package。
- 等待或调用 coding/meta-agent 生成 patch。
- 保存 child candidate metadata。
- 重新运行并分析 child candidate。
- 比较 parent 和 child 行为。

反馈信号：

- parent/child scores；
- patch application status；
- changed files；
- improved/regressed cases；
- loop failures；
- validation plan status。

可演进空间：

- orchestration policy；
- human-in-the-loop vs automatic mode；
- candidate management；
- comparison/reporting policy。

## Baseline / Reference Scripts

以下已有脚本不属于新主线：

- `experiments/extract_primary_signal.py`
- `experiments/evolve_dab_prompt.py`
- `experiments/evolve_code_agent_prompt.py`
- `experiments/run_self_evolve_loop.py`

它们可以保留为历史 baseline，但新 meta-agent 应该自己决定问题优先级、修复目标和 patch 内容。
