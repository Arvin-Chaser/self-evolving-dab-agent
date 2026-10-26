# Meta-Agent Response Schema

This file defines the first-version output contract for the project-level
meta-agent. The meta-agent must propose code changes as structured edits instead
of editing files directly or hand-writing unified diffs.

中文说明：这个文件定义第一版项目级 meta-agent 的输出格式。meta-agent 只生成
结构化 edits，不直接修改仓库文件，也不手写 unified diff；本地脚本会把 edits
转换成 `patch.diff`，是否应用 patch 由本地安全门决定。

## Required Blocks

The response must contain these fenced blocks:

```json
{
  "candidate_id": "iter_002_child",
  "goal": "Short description of the intended improvement.",
  "repair_target": "object_prompt | runner | analyzer | feedback_adapter | task_packaging | loop_guard | meta_agent_policy",
  "evidence_quality": "sufficient | coarse | contradictory | missing",
  "why_this_target": "Explain why this project component should be evolved for the observed failure.",
  "why_not_prompt_only": "Explain why a prompt-only edit is or is not sufficient.",
  "feedback_layer_sufficient": false,
  "evidence": [
    "Concrete artifact or runtime signal used to justify the change."
  ],
  "changed_files": [
    "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt"
  ],
  "edits": [
    {
      "path": "prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt",
      "mode": "exact_replace | insert_after | append_to_file",
      "find": "Exact text that appears once in the current file.",
      "replace": "Replacement text for that exact span.",
      "anchor": "Short exact text that appears once, used by insert_after.",
      "insert": "Text to insert after anchor, used by insert_after.",
      "content": "Text to append, used by append_to_file."
    }
  ],
  "expected_effect": "What should improve in the next child run.",
  "risks": [
    "Known risk or uncertainty."
  ],
  "validation_plan": [
    "Run parent/child comparison on the same DAB case."
  ]
}
```

Edit rules:

- `path` must be repo-relative.
- `mode` defaults to `exact_replace` when omitted.
- For `exact_replace`, `find` must be a short exact contiguous span from the
  current file and must match exactly once. `replace` should include the
  complete replacement span, not a diff.
- For `insert_after`, `anchor` must be short exact current text that matches
  exactly once, and `insert` is inserted immediately after that anchor.
- For `append_to_file`, provide `content`; the local script appends it to the
  end of the file and generates the unified diff.
- Prefer `append_to_file` for new helper functions and `insert_after` for small
  local insertions. Avoid large `exact_replace` spans.
- Keep edits small and reviewable.
- Feedback/analyzer edits must be wired into the extraction or analysis path in
  the same patch. Do not only append a helper function that no caller invokes.
- Do not include validator answers, ground truth, or historical log edits.
- `repair_target` must match the primary changed component.
- `runtime_observer` is not a valid `repair_target`; changes to
  `adapters/runtime_observer.py` must use `feedback_adapter`.
- If `repair_target` is `object_prompt`, `feedback_layer_sufficient` must be
  true and `why_not_prompt_only` must explain why feedback/analyzer/runner/task
  packaging is already adequate for this prompt edit.
- If `evidence_quality` is `coarse`, `contradictory`, or `missing`, prefer
  `runner`, `analyzer`, `feedback_adapter`, `task_packaging`, `loop_guard`, or
  `meta_agent_policy` over `object_prompt`.

中文说明：

- `path` 必须是仓库相对路径。
- `mode` 省略时默认为 `exact_replace`。
- `exact_replace` 需要短的、精确的 `find`，且只能匹配一次；`replace`
  写完整替换文本，不要写 diff。
- `insert_after` 需要短的、唯一的 `anchor`，并用 `insert` 表达插入内容。
- `append_to_file` 用 `content` 表达追加到文件末尾的内容。
- 新增 helper 函数优先用 `append_to_file`，小范围插入优先用
  `insert_after`，避免大段 `exact_replace`。
- edits 要小而可审查。
- feedback/analyzer 修改必须在同一个 patch 里接入实际提取或分析路径；
  不要只追加一个没有调用者的 helper 函数。

```markdown
# Change Summary

## Evidence

Explain which run artifacts, runtime logs, analyzer outputs, or script reports
motivated the change.

## Change

Explain the edited component and why it is inside the allowed evolution scope.
Also explain why this component is the correct repair target rather than
defaulting to an object-level prompt edit.

## Expected Transfer

Explain why this may help future DAB data-agent runs beyond the single case.

## Risks

Explain what could fail or regress.

## Validation

List the next commands or evaluation artifacts to inspect.
```

Do not output a `diff` block in the normal path. The local script generates
`patch.diff` from the structured edits and then runs `git apply --check`.

中文说明：正常情况下不要输出 `diff` block。本地脚本会从结构化 edits 生成
`patch.diff`，然后运行 `git apply --check`。

## Allowed Targets

Prefer bounded changes to:

- `prompts/dab/`
- `prompts/dab/meta_agent/`
- `adapters/runtime_observer.py`
- `adapters/feedback/`
- `experiments/analyze_agent_error.py`
- `experiments/build_evolution_task.py`
- `experiments/run_meta_agent_loop.py`
- `experiments/call_meta_agent.py`
- `experiments/apply_candidate_patch.py`
- `meta_agent/`

中文说明：优先演进 data-agent prompt、runtime observer、反馈提取脚本、错误分析脚本、
任务构建脚本、meta-agent loop 脚本和 meta-agent 文档。

## Forbidden Targets

Do not edit:

- `legacy/`
- validators or ground truth files
- old run logs as a way to improve scores
- validator-only expected counts, missing-answer examples, or extra-answer
  examples as new prompt constraints
- `.git/`
- `.env`
- `llm_client.py`, unless explicitly approved by the user

中文说明：不要修改 legacy、验证器、标准答案、旧运行记录、环境文件或 LLM 客户端配置。
也不要把 validator 输出里的 expected 数量、missing 示例、extra 示例写成 agent
规则，除非原始自然语言任务明确要求这些数量或具体答案。

## Reasoning Rules

- Treat runtime logs as evidence, not as final truth.
- Separate infrastructure failures from data-agent quality failures.
- Do not hard-code benchmark answers.
- Do not use the validator's expected cardinality as a target output count
  unless the original task text explicitly states that count.
- Keep patches small enough for review.
- If evidence is insufficient, improve logging, feedback extraction, or task
  packaging rather than guessing a case-specific fix.

中文说明：runtime log 是演进信号，不是最终答案。要区分模型接口失败和 agent 能力失败。
不要写死 benchmark 答案；如果证据不够，应优先改进 log、反馈提取或任务打包。
