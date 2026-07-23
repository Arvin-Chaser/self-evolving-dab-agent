# Candidate Schema

This file describes how parent and child data-agent candidates should be stored.

## Candidate Directory

Each candidate under `candidates/dab/` should eventually contain:

- `manifest.json`: candidate id, parent id, created time, changed files, and
  evaluation cases.
- `patch.diff`: project-level diff from the parent candidate.
- `change_summary.md`: short human-readable rationale and expected effect.
- `scores.json`: parent/child pass counts and case-level outcomes, when
  available.

## Manifest Fields

`manifest.json` should eventually include:

- `candidate_id`: stable candidate id, such as `iter_001_child`.
- `parent_id`: parent candidate id, or `null` for the root parent.
- `created_at`: creation timestamp.
- `role`: `parent` or `child`.
- `changed_files`: project files changed relative to the parent.
- `patch_path`: path to `patch.diff`.
- `change_summary_path`: path to `change_summary.md`.
- `trajectory_refs`: trajectory packages used as evidence.
- `search_cases`: cases shown to the meta-agent for diagnosis.
- `heldout_cases`: cases reserved for later generalization evaluation.
- `scores_path`: path to `scores.json`, when available.
- `meta_agent_log_refs`: raw meta-agent logs for this candidate.

## Candidate Identity

Use stable iteration-style ids:

- `iter_000_parent`
- `iter_001_child`
- `iter_002_child`

## Search vs Evaluation

The minimal loop may re-run the same cases first. Later experiments should
separate:

- `search_cases`: cases shown to the meta-agent for diagnosis and repair.
- `heldout_cases`: cases used only to measure generalization.

## Patch Discipline

A candidate is not just a prompt file. It should be able to represent any
bounded project change to the data-agent system, including prompts, runners,
analysis scripts, adapters, and feedback checks.

## Scores Shape

`scores.json` should eventually contain:

```json
{
  "candidate_id": "iter_001_child",
  "parent_id": "iter_000_parent",
  "search": {
    "total": 1,
    "passed": 0,
    "accuracy": 0.0,
    "case_results": []
  },
  "heldout": {
    "total": 0,
    "passed": 0,
    "accuracy": null,
    "case_results": []
  },
  "comparison_to_parent": {
    "improved_cases": [],
    "regressed_cases": [],
    "unchanged_failed_cases": []
  }
}
```

## 中文说明

这个文件描述 parent/child data-agent candidate 应该如何保存。

## Candidate 目录

`candidates/dab/` 下的每个 candidate 后续应该包含：

- `manifest.json`：candidate id、parent id、创建时间、修改文件和评估 cases。
- `patch.diff`：相对于 parent candidate 的项目级 diff。
- `change_summary.md`：简短的人类可读修改理由和预期效果。
- `scores.json`：可用时保存 parent/child pass counts 和 case-level 结果。

## Manifest 字段

`manifest.json` 后续建议包含：

- `candidate_id`：稳定 candidate id，例如 `iter_001_child`。
- `parent_id`：parent candidate id；root parent 可为 `null`。
- `created_at`：创建时间。
- `role`：`parent` 或 `child`。
- `changed_files`：相对于 parent 修改的项目文件。
- `patch_path`：`patch.diff` 路径。
- `change_summary_path`：`change_summary.md` 路径。
- `trajectory_refs`：作为证据使用的 trajectory packages。
- `search_cases`：展示给 meta-agent 用于诊断和修复的 cases。
- `heldout_cases`：后续用于泛化评估的 cases。
- `scores_path`：`scores.json` 路径，如果存在。
- `meta_agent_log_refs`：该 candidate 对应的 meta-agent 原始日志。

## Candidate 命名

使用稳定的 iteration-style id：

- `iter_000_parent`
- `iter_001_child`
- `iter_002_child`

## Search 与 Evaluation

最小闭环可以先重复跑相同 cases。后续实验应该区分：

- `search_cases`：meta-agent 可以看到、用于诊断和修复的 cases。
- `heldout_cases`：只用于衡量泛化，不提供给 meta-agent 修改时参考。

## Patch 纪律

candidate 不只是一个 prompt 文件。它应该能表示对 data-agent 系统的任何有边界的
项目级修改，包括 prompt、runner、analysis script、adapter 和 feedback check。

## Scores 格式

`scores.json` 后续建议包含：

```json
{
  "candidate_id": "iter_001_child",
  "parent_id": "iter_000_parent",
  "search": {
    "total": 1,
    "passed": 0,
    "accuracy": 0.0,
    "case_results": []
  },
  "heldout": {
    "total": 0,
    "passed": 0,
    "accuracy": null,
    "case_results": []
  },
  "comparison_to_parent": {
    "improved_cases": [],
    "regressed_cases": [],
    "unchanged_failed_cases": []
  }
}
```
