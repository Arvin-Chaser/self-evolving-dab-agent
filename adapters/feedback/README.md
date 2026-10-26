# Data-Agent Feedback Adapters

This directory contains reusable feedback adapters for the DAB data-agent
project.

Feedback adapters are part of the main diagnosis layer. They convert raw run
artifacts, runtime logs, generated code, and execution output into
structured observations/problem candidates for the meta-agent.

Current adapters:

- `common_trace_checks.py`: generic runtime-log/artifact checks.
- `dab_patents_checks.py`: PATENTS/CPC-specific checks.

Adapter outputs should be structured JSON-like records that include evidence,
confidence, uncertainty, and suggested target modules. The meta-agent should use
these records as evidence, not as fixed repair decisions.

## 中文说明

这个目录保存 DAB data-agent 项目的可复用 feedback adapters。

feedback adapters 是主线诊断层的一部分。它们把 raw run artifacts、runtime logs、
generated code 和 execution output 转换成 structured observations /
problem candidates，供 meta-agent 阅读。

当前 adapters：

- `common_trace_checks.py`：通用 runtime-log / artifact 检查。
- `dab_patents_checks.py`：PATENTS/CPC 特定检查。

adapter 输出应该是结构化 JSON-like records，包含 evidence、confidence、uncertainty
和 suggested target modules。meta-agent 应该把这些 records 当作证据，而不是固定修复决策。
