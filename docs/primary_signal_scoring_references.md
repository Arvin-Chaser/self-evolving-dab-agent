# Primary Signal Scoring 参考笔记

这份笔记整理了几个外部方向中对 DAB code-agent evolve loop 有用的思想。
当前目标不是立刻扩展更细粒度的 stage taxonomy，而是先把
`primary_signal` 从“最高频 stage”改成“更偏 root-cause 的候选信号打分”。

## 当前问题

DAB evolve loop 会先生成 `localized_errors`，再汇总出
`stage_distribution`，最后选择一个 `primary_signal` 用来进化 prompt。

旧机制的问题是：它直接选择出现次数最多的 stage。这个机制很容易选到表象：

- `S8_answer_synthesis_validation` 是最终输出阶段，天然容易积累最多错误。
- 下游症状可能覆盖上游根因，例如 S2/S7 的错误最终表现成 S8 output mismatch。
- 只看 stage 频率无法区分“最常出现”和“最值得修”。
- 有些 analyzer 规则会产生噪声，例如代码注释或 trace 中提到 `validate.py`，
  可能被误判成 `S4 evaluation_leakage`。

因此，新的 scoring 机制应该偏向选择：

- 反复出现的信号；
- 证据可信的信号；
- 更可能是上游根因的信号；
- 有明确 prompt 修复方向的信号；
- 能解释严重失败现象的信号；
- 不是单纯下游症状或疑似假阳性的信号。

## 案例 1：LLM Agent Debugging 与 AgentErrorTaxonomy

来源：[Where LLM Agents Fail and How They can Learn From Failures](https://arxiv.org/abs/2509.25370)

有价值的信息：

LLM agent 的失败经常是 cascade failure：早期一个 root-cause failure 会沿着
planning、action、tool use、final answer 等步骤传播，最后变成最终任务失败。
因此，调试系统不应该只看最终答案错在哪里，而应该识别模块化 failure mode，
并尽量定位根因。

对本项目的启发：

- `S8 output_set_mismatch` 应该默认视作可能的症状，而不是自动视作 primary target。
- 当 `S2_data_schema_grounding` 或 `S7_transformation_calculation` 的证据能解释
  下游 output mismatch 时，它们应该获得更高 root-cause 权重。
- `primary_signal` 的含义应该是“最值得用于 prompt repair 的信号”，而不是
  “出现次数最多的失败 stage”。

## 案例 2：AgentRx 与 Critical Failure Step Localization

来源：[AgentRx: Diagnosing AI Agent Failures from Execution Trajectories](https://arxiv.org/abs/2602.02475)

有价值的信息：

AgentRx 从失败 trajectory 中定位 critical failure step 和 failure category。
它通过约束检查、逐步 evidence log、以及可审计的验证记录来判断任务是从哪一步开始
不可恢复地偏离目标。

对本项目的启发：

- 优先选择有具体 trace evidence、validator evidence、runtime evidence 的信号。
- 优先选择最早违反任务约束、且能解释后续失败的 stage。
- 输出 `candidate_signals` 和 score components，让 primary signal 的选择过程可审计。

## 案例 3：RCA Agents 的 Process-Level Failure Analysis

来源：[Why Do AI Agents Systematically Fail at Cloud Root Cause Analysis?](https://arxiv.org/abs/2602.09937)

有价值的信息：

只看 final answer correctness 不足以解释 agent 为什么失败。process-level failure
analysis 能暴露反复出现的 pitfall；有些高频失败甚至不是单个模型输出的问题，而是
agent architecture 或 communication protocol 的问题。

对本项目的启发：

- 继续保留并强化 `stage_trace.json`，因为它记录了过程级证据。
- 如果某个失败在多轮 evolve 后仍反复出现，要考虑 trace protocol 或 analyzer
  是否没有表达清楚真正可修的目标。
- 不要覆盖原始 observation，而是在输出里增加 scoring 字段，方便跨轮比较。

## 案例 4：Spectrum-Based Fault Localization

来源：[Spectrum-based Software Fault Localization: A Survey of Techniques, Advances, and Challenges](https://arxiv.org/abs/1607.04347)

有价值的信息：

Spectrum-based fault localization 不只是统计“哪个组件出现最多”，而是给候选组件
计算 suspiciousness score。一个好的故障定位信号，应该和失败行为强相关，而不是
单纯出现频率高。

对本项目的启发：

- 排名单位应该是每条 `localized_error`，而不是仅仅是 stage。
- 频率只是一个分项，应和 confidence、root-cause likelihood、severity、
  specificity、penalty 等因素组合。
- 保留 top candidate list，因为单一最高分不一定永远正确，后续可以审计和调参。

## 案例 5：Grounded Theory 与迭代式 Codebook Refinement

来源：

- [Grounded theory](https://en.wikipedia.org/wiki/Grounded_theory)
- [Axial coding](https://en.wikipedia.org/wiki/Axial_coding)

有价值的信息：

Grounded theory 会通过反复比较 incidents 来发展 categories。当某个粗粒度类别中
持续出现不同模式时，研究者会逐步归纳出 properties、subcategories 和更稳定的
理论结构。

对本项目的启发：

- 不要过早拆 stage。
- 先收集 scored candidate signals，观察哪些高层 stage 在多轮 evolve 后仍然模糊。
- 如果 `S7_transformation_calculation` 反复获胜但仍太粗，再引入子类。
- 当前阶段先用 scoring 暴露“到底是 metadata grounding、granularity、
  execution，还是 final output”的问题。

## 当前 Scoring 设计

第一版 scoring 不新增 taxonomy label，而是在现有 `localized_errors` 上打分。

主要分项：

- `recurrence`：stage 出现次数，加上 error type 出现次数的一半。
- `root_cause_weight`：更可能是上游根因或转换根因的 stage 分数更高，例如 S2/S7；
  S8 作为下游答案阶段分数较低。
- `confidence`：高置信度 analyzer evidence 高于中低置信度 observation。
- `repairability`：metadata grounding、granularity、cardinality、runtime 等
  有明确修复方向的信号加权。
- `severity`：严重失败现象加权，例如 `expected 50, got 12193`。
- `downstream_symptom_penalty`：S8 answer-set 类症状降权，尤其当输出数量爆炸时。
- `false_positive_penalty`：疑似假阳性信号降权，当前主要针对弱 `S4 evaluation_leakage`。

这会让 `expected 50, got 12193` 这类场景优先选择
`S7_transformation_calculation.over_broad_filtering_or_granularity_error`，
而不是泛泛选择 `S8_answer_synthesis_validation.output_set_mismatch`。

## 输出格式

新的 primary signal JSON 会包含：

- `selected_stage`
- `selected_signal`
- `selection_method`
- `selected_score`
- `selected_score_components`
- `candidate_signals`

这样，后续每次 evolve 不仅知道选了什么，也知道为什么选它、其他候选项是什么。
