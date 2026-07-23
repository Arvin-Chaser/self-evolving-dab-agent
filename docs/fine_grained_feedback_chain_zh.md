# 细粒度反馈机制：观察内容、触发者与完整利用链路

本文总结当前 DAB / DataAgentBench 演进主线中的细粒度反馈机制。它不是一个单独脚本，而是一条闭环：

```text
DataAgent 多轮执行
  ↓
记录 LLM / tool / workflow / final answer / self-observation
  ↓
analyzer 抽取结构化细粒度反馈
  ↓
evidence pack + repair_seed 写给 meta-agent
  ↓
Codex/meta-agent 根据反馈生成 DataAgent patch
  ↓
child eval 验证 parent → child 是否改善
  ↓
archive 记录 candidate 表现
  ↓
下一轮 parent selection 使用这些表现
```

当前主线相关代码：

- `/home/m0st1ma/research/text2sql/experiments/run_dab_tool_agent.py`
- `/home/m0st1ma/research/text2sql/experiments/analyze_dab_tool_agent_trace.py`
- `/home/m0st1ma/research/text2sql/experiments/build_dab_tool_agent_evidence_pack.py`
- `/home/m0st1ma/research/text2sql/experiments/run_meta_agent_evolution_loop.py`
- `/home/m0st1ma/research/text2sql/experiments/run_codex_native_repair_launcher.py`
- `/home/m0st1ma/research/text2sql/experiments/archive_selector.py`

---

## 1. 细粒度反馈观察了哪些东西？

目前细粒度反馈主要观察五类信息。

### 1.1 DataAgent 的工作流过程

由 `/home/m0st1ma/research/text2sql/experiments/run_dab_tool_agent.py` 记录。

每次 DataAgent 运行后，会生成一组原始运行证据：

```text
summary.json
workflow_trace.jsonl
llm_calls.jsonl
tool_calls.jsonl
final_answer.txt
validation.jsonl
agent_self_observations.jsonl
```

这部分观察：

- LLM 调用了几轮；
- 每轮有没有生成 tool call；
- 调用了哪些工具；
- 工具调用是否成功；
- 是否调用了 `query_db`；
- 是否调用了 `execute_python`；
- 是否调用了 evolved helper；
- 是否调用了 `return_answer`；
- 是否因为 `max_iterations` 停止；
- 最终答案是否为空；
- 是否出现 wrapper/runtime/environment 错误。

因此它回答的问题是：

> DataAgent 是在哪一步卡住的？

典型结构化信号包括：

```text
no_llm_activity
no_tool_calls
query_db_never_called
execute_python_never_called
max_iterations_reached
missing_final_answer
tool_call_failed
empty_tool_result
```

---

### 1.2 最终答案质量

由 `/home/m0st1ma/research/text2sql/experiments/analyze_dab_tool_agent_trace.py` 中的 `compute_answer_quality()` 计算。

analyzer 会读取 query validator，把最终答案和 ground truth 做比较。对 PATENTS query 来说，它主要观察：

```text
expected_count
predicted_count
true_positive_count
missing_count
extra_count
duplicate_count
precision
recall
f1
missing_codes_sample
extra_codes_sample
predicted_codes_sample
strict_match_passed
strict_match_reason
```

这部分回答的问题是：

> DataAgent 不只是“错了”，而是“错成什么形状”。

例如 query1 的某个阶段曾经出现：

```text
expected_count = 50
predicted_count = 60
missing_count = 18
extra_count = 28
precision = 0.5333
recall = 0.64
f1 = 0.5818
```

这个反馈说明：DataAgent 不是完全没有找到答案，而是候选集合太宽，extra 太多。这个错误形状后来推动 meta-agent 去修改 CPC helper 的筛选逻辑。

---

### 1.3 evolved helper 是否真正被使用

由 `/home/m0st1ma/research/text2sql/experiments/analyze_dab_tool_agent_trace.py` 中的 `compute_helper_usage_summary()` 观察。

它检查：

```text
helper_tool_enabled
registered_helper_names
helper_tool_called
helper_call_count
helper_call_indexes
return_answer_indexes
return_answer_after_helper
final_answer_dependency_status
helper_call_samples
```

它可以区分：

```text
helper 没注册
helper 注册了但没被调用
helper 调用了但最终答案没有用到
helper 调用了并且 return_answer 在 helper 后发生
```

这对我们的研究很重要，因为演进过程中经常会出现一种失败：

> meta-agent 生成了 helper，但 DataAgent 没有真正调用它，或者调用了但没有用它的输出。

所以这类反馈回答的问题是：

> meta-agent 生成的 patch 有没有真正接进 DataAgent 的执行链路？

---

### 1.4 DataAgent 自己写下来的开放式 self-observation

这是当前机制中最重要的新部分之一。

在 `/home/m0st1ma/research/text2sql/experiments/run_dab_tool_agent.py` 中，runner 会给 DataAgent 注入一个开放工具：

```text
record_self_observation
```

这个工具不是固定错误模板，而是允许 DataAgent 自己记录：

```text
freeform
current_goal
what_i_know
uncertainties
why_this_action
intended_next_step
failure_if_stopped_now
evidence_refs
claims
```

代码中的设计意图是：

```text
The DataAgent can record its own local reasoning state, uncertainty,
evidence references, and intended next step in free text.
```

此外，runner 还会给普通工具动作加一个 `self_observation` sidecar。也就是说，DataAgent 调用某个工具时，可以顺手记录：

- 为什么调用这个工具；
- 当前知道什么；
- 当前还不确定什么；
- 如果现在停止会失败在哪里；
- 下一步应该做什么。

这部分回答的问题是：

> DataAgent 自己认为当前运行状态是什么？

它比单纯的 precision / recall 更接近“过程性反馈”。

---

### 1.5 child eval 之后的 parent-child delta

每个 candidate 生成后，不会直接 merge，而是在隔离 child workspace 中重新运行。

child eval 会比较：

```text
parent_answer_quality
child_answer_quality
parent_selected_stage
child_selected_stage
parent_selected_signal
child_selected_signal
F1 是否提升
答案是否通过
是否引入新的错误
helper 是否被使用
```

这部分回答的问题是：

> 这次 meta-agent 生成的 patch 到底有没有改善 DataAgent？

child eval 结果会进入 archive，影响下一轮 parent selection。

---

## 2. 谁触发细粒度反馈？

细粒度反馈不是由单一组件触发的，而是由三层触发者共同完成。

### 2.1 DataAgent runner 触发原始日志记录

触发者：

```text
/home/m0st1ma/research/text2sql/experiments/run_dab_tool_agent.py
```

它负责启动 DataAgent workflow，并自动记录：

```text
llm_calls.jsonl
tool_calls.jsonl
workflow_trace.jsonl
summary.json
final_answer.txt
agent_self_observations.jsonl
```

这一步是每次 DataAgent run 自动发生的。

---

### 2.2 DataAgent 自己触发 self-observation

当 DataAgent 在工具列表中看到：

```text
record_self_observation
```

或者在普通工具参数里看到：

```text
self_observation
```

它可以主动写下开放式观察。

所以这一层的触发者是 DataAgent 本身。

这部分不是 analyzer 预设的错误标签，而是 DataAgent 在运行过程中自己产生的局部理解。

---

### 2.3 evolution loop 触发 analyzer 和 evidence pack

触发者：

```text
/home/m0st1ma/research/text2sql/experiments/run_meta_agent_evolution_loop.py
```

其中 `analyze_dab_tool_agent_and_seed()` 会调用：

```text
/home/m0st1ma/research/text2sql/experiments/analyze_dab_tool_agent_trace.py
/home/m0st1ma/research/text2sql/experiments/build_dab_tool_agent_evidence_pack.py
```

然后生成：

```text
observations.json
feedback_summary.json
meta_agent_seed.json
fine_grained_evidence_pack.json
fine_grained_evidence_pack.md
repair_seed.json
```

因此可以概括为：

```text
DataAgent 负责产生 raw trace；
analyzer 负责结构化整理；
loop runner 负责把它们打包成 meta-agent 输入。
```

---

## 3. 从生成到被利用的完整链路

### Step 1：运行 parent DataAgent

入口通常是：

```text
/home/m0st1ma/research/text2sql/experiments/run_meta_agent_evolution_loop.py
```

它会先选择一个 parent agent，然后运行 DataAgent。

运行产物通常在：

```text
logs/dab_tool_agent/...
query_workspaces/PATENTS/query*/runs/...
```

生成原始证据：

```text
summary.json
workflow_trace.jsonl
tool_calls.jsonl
llm_calls.jsonl
final_answer.txt
agent_self_observations.jsonl
```

---

### Step 2：analyzer 把 raw logs 转成结构化反馈

脚本：

```text
/home/m0st1ma/research/text2sql/experiments/analyze_dab_tool_agent_trace.py
```

输出：

```text
observations.json
feedback_summary.json
meta_agent_seed.json
```

其中 `feedback_summary.json` 是摘要，通常包含：

```text
selected_stage
selected_signal
selected_problem_type
answer_quality
helper_usage_summary
agent_self_observation_summary
candidate_repair_layers
routing_policy
primary_signal
```

但是这里的 `selected_stage` / `selected_signal` 不是最终修复决策。

代码里明确写了：

```text
routing_policy.source = deterministic_observation_extractor_v002
routing_policy.role = weak_context_only
meta_agent_must_decide_repair_layer = True
meta_agent_may_override = True
```

也就是说，analyzer 只是告诉 meta-agent：

> 当前最显著的失败证据可能在哪里。

但真正决定怎么修的是 meta-agent。

---

### Step 3：构建 evidence pack

脚本：

```text
/home/m0st1ma/research/text2sql/experiments/build_dab_tool_agent_evidence_pack.py
```

输出：

```text
fine_grained_evidence_pack.json
fine_grained_evidence_pack.md
```

它会打包：

```text
artifact_paths
answer_quality
helper_usage_summary
agent_self_observation_summary
structured_observations
repair_guidance
```

它的作用是把 raw logs 和 analyzer 结果变成 Codex/meta-agent 可读的上下文包。

---

### Step 4：生成 repair_seed.json

在 `/home/m0st1ma/research/text2sql/experiments/run_meta_agent_evolution_loop.py` 中，`analyze_dab_tool_agent_and_seed()` 会把前面的结果汇总成：

```text
repair_seed.json
```

其中包含：

```text
fine_grained_feedback
selected_stage
selected_signal
answer_quality
helper_usage_summary
top_observations
structured_observations
full_evidence_pack_paths
candidate_context
archive_selection
```

这就是 meta-agent 每一轮看到的核心输入。

---

### Step 5：Codex/meta-agent 根据 repair_seed 生成 candidate patch

入口：

```text
/home/m0st1ma/research/text2sql/experiments/run_codex_native_repair_launcher.py
```

它会把 `repair_seed.json` 和 context pack 写入 Codex-native task prompt。

prompt 中明确要求：

```text
Prioritize DataAgent-authored open self-observations when present,
while treating analyzer selected_stage/selected_signal as weak context only.
```

也就是说，meta-agent 需要自己判断：

```text
这次应该改 prompt？
应该改 helper？
应该改 tool registry？
应该改 runner？
应该改 observer？
还是 no-op？
```

当前机制还加入了 script-first 倾向：

```text
优先考虑 reusable helper/script/tool/runner/observer repair，
不要一上来只改 prompt。
```

---

### Step 6：candidate 在隔离 child workspace 中验证

candidate patch 生成后，不直接 merge。

loop 会进入 child eval：

```text
run_dab_tool_agent_child_eval()
```

它会：

```text
创建 child workspace
应用 candidate patch
重新运行同一个 query
重新生成 trace / feedback / answer metrics
比较 parent 和 child
```

输出：

```text
child_eval_report.json
feedback_summary.json
observations.json
meta_agent_seed.json
next_data_agent_repair_seed.json
```

这一步会判断：

```text
candidate_child_eval_passed
candidate_child_eval_failed
candidate_child_eval_improved_but_failed
```

---

### Step 7：archive 保存 candidate 的效果

child eval 后，candidate 会被归档。

archive 会记录：

```text
candidate patch
parent-child delta
answer quality
selected_stage / selected_signal
helper usage
failure tags
reward
是否可作为下一轮 parent
是否只能作为 negative evidence
```

这就是 archive-based evolution 的基础。

它不是只看 pass / fail，而是会看：

```text
F1 有没有提高
是否从空答案变成有答案
是否进入 near-miss
是否修复了 helper 接线问题
是否引入新的运行错误
是否只是 prompt-only
candidate patch 是否能 replay
```

---

### Step 8：下一轮 parent selection 使用 archive

下一轮开始时：

```text
/home/m0st1ma/research/text2sql/experiments/archive_selector.py
```

会读取 archive 中的 candidate / agent 表现，选择新的 parent。

当前 parent selection 会考虑：

```text
query workspace
agent freshness
candidate reward
answer F1
strict pass
near-miss 状态
是否 repeat parent
是否存在 negative failure tags
是否 child eval 改善
```

所以细粒度反馈最终会影响：

```text
哪个 agent 作为下一轮 parent
哪些 candidate 作为 evidence
哪些失败经验被带入下一轮
```

---

## 4. query1 中的典型例子

query1 是目前最完整的例子。

### Stage 1：从空答案到能输出答案

最初 DataAgent 不能稳定生成有效答案。

细粒度反馈观察到：

```text
missing_final_answer
tool usage 不足
helper/tool capability 不足
```

meta-agent 因此没有只改 prompt，而是生成了 helper 方向的 patch。

---

### Stage 2：F1 = 0.5818，extra 很多

某一轮细粒度反馈显示：

```text
expected_count = 50
predicted_count = 60
missing_count = 18
extra_count = 28
precision = 0.5333
recall = 0.64
f1 = 0.5818
```

这告诉 meta-agent：

```text
不是完全找不到答案；
而是候选集合太宽；
应该收紧筛选逻辑。
```

于是 meta-agent 修改 helper，使 CPC 选择更偏向 primary / inventive / unique publication 逻辑。

结果：

```text
F1: 0.5818 → 0.9412
```

这是细粒度反馈有效的核心证据之一。

---

### Stage 3：进入 near-miss

当 F1 达到 0.94+，反馈形状变成：

```text
missing 很少
extra 很少
整体接近正确
```

这时不适合再大改，而是进入 near-miss refinement。

meta-agent 开始做小范围修正：

```text
检查 missing / extra 是哪几个
倒推 helper 的局部数学假设
调整 EMA 年份遍历逻辑
```

最终 query1 达到 strict pass。

---

## 5. 关键结论：这不是固定模板修复

当前系统里确实有结构化 analyzer，但它不负责决定“应该怎么修”。

它只做：

```text
观察
摘要
排序
给候选 repair layers
提供 raw evidence path
```

真正的修复推理由 Codex/meta-agent 完成：

```text
读取 trace
读取 answer delta
读取 helper usage
读取 self-observation
判断失败层
生成 patch
调试 patch
child eval
archive
```

因此可以这样总结：

> 细粒度反馈不是一个写死的修复规则库，而是把 DataAgent 的一次失败从粗粒度的 fail 展开成 answer-level、workflow-level、tool-level、helper-level、self-observation-level 的证据包。meta-agent 再基于这些证据自己决定下一步演进方向。

---

## 6. 汇报时可展示的文件

query1 的代表 evidence：

```text
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/child_eval/feedback_summary.json
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/child_eval/observations.json
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/child_eval/meta_agent_seed.json
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/child_eval/child_eval_report.json
```

near-miss 阶段：

```text
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/child_eval/feedback_summary.json
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/child_eval/meta_agent_seed.json
/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/child_eval/child_eval_report.json
```

query1 lineage：

```text
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patch_chain.json
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/001_script_first.patch
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/002_two_step_selfobs.patch
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/003_two_step_selfobs_refine.patch
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/004_near_miss_refine.patch
```

---

## 7. 一句话版本

细粒度反馈的完整作用链路是：

> 它先把 DataAgent 的一次失败拆解成“答案错法 + 工具路径 + helper 使用 + 自观察 + child delta”，再把这些证据交给 meta-agent 进行自由诊断和 patch 生成，最后通过 child eval 和 archive selection 把有效经验沉淀为下一轮 parent/evidence。
