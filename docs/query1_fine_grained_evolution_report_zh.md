# Query1 演进报告：细粒度反馈如何推动脚本演进与 near-miss repair

## 1. 核心结论

PATENTS query1 从一个 basic / zero-start DAB tool-agent 出发，经过 4 次 meta-agent candidate 演进，最终得到一个 strict-pass agent。

最终 agent：

```text
data_agent_shadow_codex_native_near_miss_refine_iter001_20260715_090844
```

最终结果：

```text
PATENTS query1 strict_match_passed = true
precision = 1.0
recall = 1.0
F1 = 1.0
```

这条线最值得汇报的不是“query1 过了”，而是：

```text
细粒度反馈逐步改变了 meta-agent 的修复粒度：
从没有答案 → 构建本地 helper
从 extra 太多 → 修候选筛选逻辑
从 high-F1 near miss → 修局部数学/边界假设
最终 strict pass
```

主要参考文件：

- Query1 workspace: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1`
- 演进链路: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patch_chain.json`
- 当前 query1 reproduction policy: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/agent/policy.txt`
- 当前 query1 parent 状态: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/state/current_parent.json`

## 2. 从 basic agent 到 passed agent，一共演进了多少次？

根据 `patch_chain.json`，query1 从 basic agent 到 passed agent 一共经历了 4 次 candidate 演进：

```text
base_agent_id  = dab_tool_agent_zero_start_current
final_agent_id = data_agent_shadow_codex_native_near_miss_refine_iter001_20260715_090844
candidate evolution count = 4
```

四次演进如下：

| 阶段 | Candidate | Patch | Parent F1 → Child F1 | 结果 |
|---|---|---|---:|---|
| 1 | `codex_native_iter10_script_first_iter001_20260715_074941` | `001_script_first.patch` | `0.0 → 0.5818` | 第一次生成可度量答案 |
| 2 | `codex_native_iter10_two_step_selfobs_iter001_20260715_081931` | `002_two_step_selfobs.patch` | `0.5818 → 0.9412` | 大幅提升，进入 high-F1 区间 |
| 3 | `codex_native_iter10_two_step_selfobs_iter002_20260715_082928` | `003_two_step_selfobs_refine.patch` | `0.9412 → 0.9505` | 小幅边界优化 |
| 4 | `codex_native_near_miss_refine_iter001_20260715_090844` | `004_near_miss_refine.patch` | `0.9505 → 1.0` | strict pass |

参考：

- `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patch_chain.json`

## 3. Stage 0：basic agent

起点：

```text
dab_tool_agent_zero_start_current
```

这个 basic agent 已经有 DAB multi-turn tool workflow，但还没有 query1 需要的专用计算能力。

第一轮 parent baseline 表现：

```text
F1 = 0.0
predicted_count = 0
expected_count = 50
missing_count = 50
```

含义：

- DataAgent 没有给出可用答案；
- 不是简单 prompt wording 问题；
- 它缺少一个稳定的本地计算路径，用来解析 CPC hierarchy、统计 filing year、计算 EMA。

这为后续“从 prompt 修复转向 helper/script 修复”提供了依据。

## 4. Stage 1：script-first helper creation

Candidate:

```text
codex_native_iter10_script_first_iter001_20260715_074941
```

参考文件：

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/001_script_first.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_script_first_iter001_20260715_074941`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_script_first_iter001_20260715_074941/candidate_state.json`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_script_first_iter001_20260715_074941/child_eval/child_eval_report.json`

改动文件：

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

结果：

```text
parent F1 = 0.0
child F1 = 0.5818
precision = 0.5333
recall = 0.64
missing_count = 18
extra_count = 28
predicted_count = 60
expected_count = 50
```

这一轮 meta-agent 添加了最关键的脚本能力：

```python
cpc_level_ema_best_year
```

同时添加了一组辅助函数：

```python
_helper_path
_patents_data_paths
_cpc_copy_columns
_load_cpc_level_symbols
_filing_year
_cpc_level_group
_ema_best_year
```

这个 helper 的作用：

```text
读取 patent_publication.db
读取 patent_CPCDefinition.sql
解析 CPC hierarchy level
提取 filing year
统计 yearly counts
计算 EMA
返回 target year 中 EMA peak 的 CPC codes
```

细粒度反馈发挥的作用：

在 basic agent 阶段，反馈显示：

```text
F1 = 0
predicted_count = 0
missing_count = 50
```

这说明问题不是“答案格式小错”，而是 DataAgent 没有稳定完成核心计算。因此 meta-agent 没有只改 prompt，而是把计算逻辑固化成本地 helper。

这一阶段是 query1 中最能体现“细粒度反馈推动脚本生成”的例子。

## 5. Stage 2?primary CPC filtering / self-observation refinement

Candidate:

```text
codex_native_iter10_two_step_selfobs_iter001_20260715_081931
```

?????

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/002_two_step_selfobs.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/candidate_state.json`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/child_eval/child_eval_report.json`

?????

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

???

```text
parent F1 = 0.5818
child F1 = 0.9412
precision = 0.9231
recall = 0.96
missing_count = 2
extra_count = 4
predicted_count = 52
expected_count = 50
```

?????

???

```python
_payload_bool
```

?? `cpc_level_ema_best_year` ?????

```python
primary_only
inventive_only
unique_per_publication
```

?????

```python
if primary_only and item.get("first") is not True:
    continue
if inventive_only and item.get("inventive") is not True:
    continue
```

???????????

?????????? ?extra ???????????????????????????? validation failure ???????????

???answer-quality feedback ?????????

```text
predicted_count = 60
expected_count = 50
extra_count = 28
precision = 0.5333
recall = 0.64
```

??? agent ??????????????????????????????????precision ??? extra ???

???trace / helper-level evidence ? meta-agent ?????????????Stage 1 ? helper ??? `publicationinfo.cpc` ????? publication ?? CPC assignments ?????????? primary / secondary / inventive ???????????????????????????????

```text
CPC assignment selection policy ???
```

?? meta-agent ??????????? helper ??????????? prompt?

```python
primary_only = _payload_bool(payload, "primary_only", True)
inventive_only = _payload_bool(payload, "inventive_only", False)

if primary_only and item.get("first") is not True:
    continue
if inventive_only and item.get("inventive") is not True:
    continue
```

?? policy ??? DataAgent ? PATENTS CPC EMA ???????

```json
{"primary_only": true}
```

??????????????????

```text
? recall + ? precision + extra_count ?
? ????????
? trace ?? helper ????? CPC assignments
? CPC ??????? primary / secondary / inventive ??
? ?? helper selection policy
? F1 ? 0.5818 ??? 0.9412
```

????????????????? F1 ???????????? trace / helper diagnostics ? meta-agent ?????????????

## 6. Stage 3?sparse false-positive filtering

Candidate:

```text
codex_native_iter10_two_step_selfobs_iter002_20260715_082928
```

?????

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/003_two_step_selfobs_refine.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter002_20260715_082928`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter002_20260715_082928/candidate_state.json`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter002_20260715_082928/child_eval/child_eval_report.json`

?????

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

???

```text
parent F1 = 0.9412
child F1 = 0.9505
precision = 0.9412
recall = 0.96
missing_count = 2
extra_count = 3
predicted_count = 51
expected_count = 50
```

?????

?????

```python
min_target_year_count
```

?????

```python
target_count = yearly_counts.get(target_year, 0)
if best_year == target_year and target_count >= min_target_year_count:
    scores.append(...)
```

???????????

Stage 2 ????????????????????

```text
F1 = 0.9412
precision = 0.9231
recall = 0.96
missing_count = 2
extra_count = 4
```

????? helper ?????????????????????????????????????????????????

?? meta-agent ???????????? remaining extra ???? target year ???????????? CPC peaks???????????????? helper ???

```python
min_target_year_count
```

????????????? CPC group ? target year ? filing count ????????????? EMA peak?

```python
target_count = yearly_counts.get(target_year, 0)
if best_year == target_year and target_count >= min_target_year_count:
    scores.append(...)
```

????????

```text
F1: 0.9412 ? 0.9505
extra_count: 4 ? 3
missing_count: 2 ? 2
```

??????????? meta-agent ???????????????????????????meta-agent ?????????????`min_target_year_count` ????? extra?????? missing?????? near-miss repair ?????????????????

?? Stage 3 ??????????????????????????????? hypothesis-test-refine?

```text
high-F1 + ?? extra
? ?? sparse peaks ?? false positives
? ? min_target_year_count
? ????????
? ? Stage 4 ? near-miss hypothesis revision ????
```

## 7. Stage 4?near-miss refinement?????

Candidate:

```text
codex_native_near_miss_refine_iter001_20260715_090844
```

?????

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/004_near_miss_refine.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/candidate_state.json`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/child_eval/child_eval_report.json`

?????

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

???

```text
parent F1 = 0.9505
child F1 = 1.0
precision = 1.0
recall = 1.0
missing_count = 0
extra_count = 0
predicted_count = 50
expected_count = 50
strict_match_passed = true
```

??????EMA ?????????

????

```python
for year in range(min(counts), max(counts) + 1):
    ema = alpha * counts.get(year, 0) + (1.0 - alpha) * ema
```

????

```python
for year in sorted(counts):
    ema = alpha * counts[year] + (1.0 - alpha) * ema
```

???

```text
??????????? filing ?????
????? observed years ??? EMA?
```

????????????? target-year count ???

```python
min_target_year_count = 1
```

policy ??????

```text
Do not add an arbitrary minimum target-year filing threshold unless the user asks for one;
sparse CPC groups can still have a valid observed-year EMA peak.
```

???????????

???? near-miss repair ?????????????????????????? meta-agent ???????????

?? Stage 4 ???????

```text
F1 = 0.9505
precision = 0.9412
recall = 0.96
missing_count = 2
extra_count = 3
```

???????? pipeline ????????????????????????Stage 3 ?????????????????? missing??? meta-agent ?????????????????????????? helper ???????????

?? near-miss repair ?????????????

```text
1. EMA ????????????????? filing ?????
2. sparse target-year peak ????? arbitrary threshold ???
```

meta-agent ???????? helper???????????/?????

???? EMA ??????????? observed years?

```python
# before
for year in range(min(counts), max(counts) + 1):
    ema = alpha * counts.get(year, 0) + (1.0 - alpha) * ema

# after
for year in sorted(counts):
    ema = alpha * counts[year] + (1.0 - alpha) * ema
```

????? Stage 3 ????????

```python
min_target_year_count = 1
```

??????

```text
F1: 0.9505 ? 1.0
missing_count: 2 ? 0
extra_count: 3 ? 0
strict_match_passed = true
```

?? Stage 4 ???? near-miss feedback ???????? meta-agent ??????????????? missing/extra ????????????? helper ????????????????

???????????

```text
high-F1 near miss
+ missing/extra ??
+ ??????????
? ????????
? observed-year EMA + ?? arbitrary threshold
? strict pass
```

## 8. 演进过程中实际添加了哪些脚本或能力？

需要注意：query1 是历史链路。当时 meta-agent 还没有完全转向 query-local helper registry，所以它没有创建单独的 query-local `.py` helper 文件，而是把 helper 写进了全局 runner：

```text
/home/m0st1ma/research/text2sql/experiments/run_dab_tool_agent.py
```

主要新增能力：

```python
cpc_level_ema_best_year
```

辅助函数：

```python
_helper_path
_patents_data_paths
_cpc_copy_columns
_load_cpc_level_symbols
_filing_year
_cpc_level_group
_ema_best_year
_payload_bool
```

策略改动位置：

```text
/home/m0st1ma/research/text2sql/prompts/dab/dab_tool_agent_policy_zero_start.txt
```

当前 query1 reproduction workspace 保存的最终 policy：

```text
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/agent/policy.txt
```

架构说明：

```text
query1 证明了 meta-agent 能从细粒度反馈中演进出 helper 逻辑；
query2 之后我们进一步把 helper 演进迁移到 query-local workspace：
query_workspaces/PATENTS/query2/agent/helpers/registry.py
```

所以汇报时可以说：

```text
query1 是“细粒度反馈推动 helper 逻辑产生”的正例；
query2 是“把这种 helper 演进 query-local 化，并测试 near-miss 泛化能力”的阶段。
```

## 9. 细粒度反馈在 query1 中的作用总结

### 9.1 从无答案到脚本化 helper

反馈：

```text
F1 = 0
predicted_count = 0
missing_count = 50
```

修复：

```text
新增 cpc_level_ema_best_year helper
```

作用：

```text
把 meta-agent 从 prompt-only repair 引导到 script/helper repair。
```

### 9.2 从 extra 太多到 primary CPC filtering

反馈：

```text
F1 = 0.5818
precision = 0.5333
extra_count = 28
```

修复：

```text
加入 primary_only / inventive_only / unique_per_publication
```

作用：

```text
细粒度指标指出候选过宽，meta-agent 因此收窄 CPC assignment 范围。
```

### 9.3 从 high-F1 到 sparse false-positive filtering

反馈：

```text
F1 = 0.9412
missing_count = 2
extra_count = 4
```

修复：

```text
加入 min_target_year_count
```

作用：

```text
meta-agent 开始做小范围边界修复，而不是重写整体 pipeline。
```

### 9.4 从 near-miss 到数学假设修正

反馈：

```text
F1 = 0.9505
missing_count = 2
extra_count = 3
```

修复：

```text
EMA 改为 observed-year iteration
取消 arbitrary min_target_year_count
```

作用：

```text
near-miss feedback 引导 meta-agent 检查局部数学假设，最终 strict pass。
```

## 10. 和 query2 的衔接

query1 可以作为正例：

```text
细粒度反馈 → helper/script 演进 → near-miss repair → strict pass
```

query2 可以作为当前不足：

```text
best parent F1 = 0.9545
missing = [A21, H03]
extra = []
```

query2 已经进入 near-miss 阶段，但最近一轮 near-miss patch 退化了：

```text
parent:
F1 = 0.9545
missing = [A21, H03]

child:
F1 = 0.9048
missing = [A21, B62, H02, H03]
```

说明当前 near-miss repair 已经能定位“需要补什么”，但还不能稳定保证“不破坏已有正确答案”。

下一步研究问题：

```text
near-miss repair 不仅要包含 missing / extra targets，
还需要包含 preserve set：
修 A21/H03 的同时，不能丢掉 B62/H02 等当前已正确 codes。
```

## 11. 可直接汇报的一段话

> Query1 从 basic agent 到 strict-pass agent 一共经历了四次 candidate 演进。最开始 basic agent 完全没有可用答案，细粒度反馈把问题定位为缺少稳定本地计算能力，于是 meta-agent 生成了 CPC EMA helper。之后，answer-quality metrics 显示 extra 很多，meta-agent 又加入 primary CPC filtering。再往后，F1 已经超过 0.94，错误集中在少量 missing/extra 上，meta-agent 开始做 sparse false-positive filtering。最后进入 near-miss repair，meta-agent 修正了 EMA 的 observed-year 计算方式并取消错误阈值，最终 query1 strict pass。这个过程说明细粒度反馈的价值不只是解释错误，而是逐步改变 meta-agent 的修复粒度和修复对象，从 prompt-level 走向 helper/script-level，再走向 near-miss boundary repair。
