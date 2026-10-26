# Meta-Agent I/O Contract

This document defines what the coding/meta-agent should read and write during
one project-level evolution iteration.

## Inputs

The meta-agent should receive local file paths, not only copied summaries.

Required inputs:

- `agent_scope`: path to `meta_agent/agent_scope.md`.
- `loop_design`: path to `meta_agent/loop_design.md`.
- `component_map`: path to `meta_agent/component_map.md`.
- `feedback_schema`: path to `meta_agent/feedback_schema.md`.
- `script_run_report_schema`: path to `meta_agent/script_run_report_schema.md`.
- `parent_candidate`: path to the parent candidate manifest.
- `run_artifact_refs`: paths to raw `logs/dab_agent/run_*` artifacts.
- `analyzer_refs`: paths to analyzer outputs/problem candidates.
- `script_report_refs`: paths to script-level reports, when available.
- `source_refs`: relevant project files that may need inspection.

Optional inputs:

- held-out case list;
- prior candidate summaries;
- previous patches;
- human notes about desired research direction.

## Expected Outputs

Each meta-agent iteration should produce:

- `patch.diff`: project diff relative to the parent candidate.
- `change_summary.md`: rationale, evidence, expected effect, risks, and
  validation plan.
- `manifest.json`: child candidate metadata.
- `scores.json`: child scores after evaluation, when available.
- raw meta-agent logs under `logs/meta_agent/`.

## Change Summary Fields

`change_summary.md` should answer:

- What failed?
- Which runtime-log, analyzer, comparison, or script-level evidence supports that diagnosis?
- Which project component was changed?
- Why is this the right component to evolve, rather than defaulting to an
  object-level prompt edit?
- If the patch changes an object-level prompt, why is the current feedback,
  analyzer, runner, and task packaging already sufficient to justify a prompt
  change?
- Why is the change expected to transfer beyond one case?
- Which files were touched?
- What risks remain?
- How should the child candidate be validated?

## Source Inspection Rule

The meta-agent should inspect source files before editing them. It should not
modify files based only on summarized analyzer output when raw artifacts and
source files are available.

## 中文说明

本文档定义 coding/meta-agent 在一次项目级演进 iteration 中应该读什么、写什么。

## 输入

meta-agent 应该接收本地文件路径，而不是只接收短 summary。

必要输入：

- `agent_scope`：`meta_agent/agent_scope.md` 路径。
- `loop_design`：`meta_agent/loop_design.md` 路径。
- `component_map`：`meta_agent/component_map.md` 路径。
- `feedback_schema`：`meta_agent/feedback_schema.md` 路径。
- `script_run_report_schema`：`meta_agent/script_run_report_schema.md` 路径。
- `parent_candidate`：parent candidate manifest 路径。
- `run_artifact_refs`：原始 `logs/dab_agent/run_*` artifacts 路径。
- `analyzer_refs`：analyzer output / problem candidates 路径。
- `script_report_refs`：script-level reports 路径，如果存在。
- `source_refs`：可能需要检查的相关项目文件。

## 期望输出

每次 meta-agent iteration 应该产生：

- `patch.diff`：相对于 parent candidate 的项目 diff。
- `change_summary.md`：修改理由、证据、预期效果、风险和验证计划。
- `manifest.json`：child candidate metadata。
- `scores.json`：child scores，如果存在。
- `logs/meta_agent/` 下的原始 meta-agent 日志。

## Change Summary 字段

`change_summary.md` 应该回答：

- 失败是什么？
- 哪些 runtime-log、analyzer、comparison 或 script-level evidence 支持这个诊断？
- 修改了哪个项目组件？
- 为什么应该演进这个组件，而不是默认去改 object-level prompt？
- 如果 patch 修改的是 object-level prompt，为什么当前 feedback、analyzer、runner
  和 task packaging 已经足够支撑这个 prompt 修改？
- 为什么这个修改有可能迁移到不止一个 case？
- 触碰了哪些文件？
- 还剩哪些风险？
- 应该如何验证 child candidate？
