# Script Run Report Schema

Each mainline script should emit a structured execution report. This report is a
script-level trajectory: it tells the meta-agent how the project script itself
ran, what evidence it used, what outputs it produced, and what it thinks may
need evolution.

When multiple scripts write into the same run directory, use script-specific
filenames such as `script_run_report.run_dab_agent.json` and
`script_run_report.analyze_agent_error.json` so reports are not overwritten.

## Recommended Shape

```json
{
  "script_name": "experiments/analyze_agent_error.py",
  "script_role": "feedback_analyzer",
  "started_at": "ISO-8601 timestamp",
  "ended_at": "ISO-8601 timestamp",
  "status": "success|failed|partial",
  "inputs": [
    {
      "name": "run_dir",
      "path": "logs/dab_agent/run_xxx"
    }
  ],
  "operations": [
    {
      "name": "load_operation_trajectory",
      "status": "completed",
      "inputs": [],
      "outputs": {
        "operation_event_count": 12
      },
      "checks": []
    }
  ],
  "outputs": [
    {
      "name": "agent_error_summary",
      "path": "logs/dab_agent/run_xxx/agent_error_summary.json"
    }
  ],
  "checks": [
    {
      "name": "has_problem_candidates",
      "passed": true,
      "message": "Analyzer produced at least one problem candidate."
    }
  ],
  "self_feedback": {
    "confidence": "high|medium|low",
    "uncertainties": [],
    "evolution_hints": [],
    "suggested_target_modules": []
  }
}
```

## Purpose

The meta-agent should use script reports to decide whether to evolve:

- the object-level prompt;
- the runner;
- the analyzer;
- feedback adapters;
- task packaging;
- loop orchestration.

## 中文说明

每个主线脚本都应该输出结构化执行报告。这个报告是 script-level trajectory：它告诉
meta-agent 项目脚本自己是怎么运行的、用了哪些证据、产出了什么、以及它自己认为哪里可能需要演进。

当多个脚本写入同一个 run 目录时，使用带脚本名的文件名，例如
`script_run_report.run_dab_agent.json` 和
`script_run_report.analyze_agent_error.json`，避免报告互相覆盖。

## 目的

meta-agent 应该根据 script reports 判断是否需要演进：

- object-level prompt；
- runner；
- analyzer；
- feedback adapters；
- task packaging；
- loop orchestration。
