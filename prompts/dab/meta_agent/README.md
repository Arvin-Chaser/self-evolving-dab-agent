# DAB Meta-Agent Prompts

This directory stores prompts for the coding/meta-agent that improves the DAB
data-agent project.

These prompts are separate from object-level prompts in `prompts/dab/`.
Object-level prompts instruct the data agent to solve DAB tasks. Meta-agent
prompts instruct a coding agent to inspect runtime-log evidence,
script-level reports, source files, and candidate metadata, then produce a
bounded project patch.

Expected prompt types:

- `project_evolve_prompt.txt`: asks the coding/meta-agent to propose and apply a
  bounded project-level improvement.
- optional review prompts for inspecting evidence without editing.

Keep these prompts focused on transferable project improvements. They should not
include case-specific ground-truth answers.

## 中文说明

这个目录保存 coding/meta-agent 使用的 prompts。

这些 prompts 和 `prompts/dab/` 下的 object-level prompts 不同。object-level prompt
指导 data agent 解 DAB 任务；meta-agent prompt 指导 coding agent 阅读
runtime-log evidence、script-level reports、source files 和 candidate metadata，
然后生成有边界的 project patch。

预期 prompt 类型：

- `project_evolve_prompt.txt`：让 coding/meta-agent 提出并应用项目级改进。
- 可选 review prompts：只阅读证据，不编辑文件。

这些 prompts 应该关注可迁移的项目改进，不能包含某个 benchmark case 的标准答案。
