# Feedback Schema

This file describes the feedback signals consumed by the project-level
meta-agent.

## Object-Level Signals

Generated `solve.py` should import the injected local `runtime_observer.py` and
write adaptive runtime logs to `STAGE_TRACE_PATH`. The filename remains
`stage_trace.json` for compatibility, but the content should be a list of
runtime events produced by executed code rather than a fixed reasoning-stage
protocol.

The runtime observer is a project code component, not only a prompt instruction.
It may be evolved by the meta-agent together with prompts, runner logic,
analyzer logic, and feedback adapters.

Each runtime event should include:

- `event`
- `trigger`
- `severity`
- `status`
- `purpose`
- `inputs`
- `outputs`
- `checks`
- `evidence`
- `warnings`
- `hypothesis`
- `suggested_target`
- `error`

Important triggers include:

- `runtime_observation`
- `runtime_check_failed`
- `runtime_anomaly`
- `fallback_used`
- `exception`
- `answer_contract_check`

## Script-Level Signals

Each mainline project script should eventually emit `script_run_report.json`.

The script report should include:

- inputs;
- operations;
- outputs;
- checks;
- self-feedback;
- evolution hints;
- suggested target modules.

See `script_run_report_schema.md`.

## Analyzer Output

`experiments/analyze_agent_error.py` should produce structured observations and
problem candidates. It should not select a single primary signal and should not
decide how to repair the project.

Problem candidates should include:

- problem id;
- operation or artifact involved;
- problem type;
- evidence;
- confidence;
- uncertainty;
- suggested target modules.

## Later Feedback

After the minimal loop works, add:

- data completeness;
- data validity;
- schema grounding;
- transformation integrity;
- answer contract checks;
- held-out comparison signals.

## 中文说明

本文档描述 project-level meta-agent 使用的反馈信号。

## Object-Level 信号

生成的 `solve.py` 应该 import 注入到 run 目录里的本地 `runtime_observer.py`，并把
adaptive runtime logs 写到 `STAGE_TRACE_PATH`。为了兼容，文件名仍然可以是
`stage_trace.json`，但内容应该是由本地执行代码产生的 runtime events，而不是
fixed reasoning-stage protocol。

runtime observer 是项目代码组件，不只是 prompt instruction。meta-agent 后续可以
同时演进它、prompts、runner、analyzer 和 feedback adapters。

每个 runtime event 应包含：

- `event`
- `trigger`
- `severity`
- `status`
- `purpose`
- `inputs`
- `outputs`
- `checks`
- `evidence`
- `warnings`
- `hypothesis`
- `suggested_target`
- `error`

重要 trigger 包括：

- `runtime_observation`
- `runtime_check_failed`
- `runtime_anomaly`
- `fallback_used`
- `exception`
- `answer_contract_check`

## Script-Level 信号

每个主线项目脚本后续都应该输出 `script_run_report.json`。

script report 应包含：

- inputs；
- operations；
- outputs；
- checks；
- self-feedback；
- evolution hints；
- suggested target modules。

详见 `script_run_report_schema.md`。

## Analyzer 输出

`experiments/analyze_agent_error.py` 应该输出 structured observations 和 problem
candidates。它不应该选择唯一 primary signal，也不应该决定如何修复项目。

problem candidates 应包含：

- problem id；
- 涉及的 operation 或 artifact；
- problem type；
- evidence；
- confidence；
- uncertainty；
- suggested target modules。

## 后续反馈

最小 loop 跑通后，再加入：

- data completeness；
- data validity；
- schema grounding；
- transformation integrity；
- answer contract checks；
- held-out comparison signals。
