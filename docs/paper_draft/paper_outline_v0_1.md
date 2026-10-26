# 论文大纲 v0.1：History-Guided, Auditable Self-Evolution for Data Agents

更新日期：2026-09-26

## 0. 当前推荐的论文主线

### 暂定题目

1. **History-Guided and Auditable Self-Evolution for Tool-Using Data Agents**
2. **From Execution Traces to Executable Evolution: An Auditable Memory Loop for Data Agents**
3. **When Ideas Do Not Become Mechanisms: Auditing History-Guided Evolution in Data Agents**

推荐暂用第 1 个题目。第 3 个更突出目前最重要的实验发现，可以作为投稿前根据最终结果选择的备选。

### 一句话问题定义

现有 DataAgent 通常在固定 prompt、固定工具集合和固定 harness 中完成任务；即使系统保存了历史轨迹或反思，也缺少一个可审计的闭环，来证明历史经验如何改变下一代设计、设计是否落实为可执行机制，以及机制是否真的进入运行并改善任务结果。

### 一句话方法

我们把每代经验组织为不可变的 `intent → candidate → execution result → review` transaction，分离 code parent 与 information parent，由 MetaAgent 基于经过过滤的 history 提出下一代机制，再通过 seal、admission、materialization、trace verification 和 hash chain 对演进过程进行端到端审计。

### 当前最稳妥的论文结论

结构化 history 能够支持跨代的设计方向分化，但“产生新想法”不等于“形成可执行的新机制”。我们的实验揭示了一个关键的 **intent-to-realization gap**：受限 candidate DSL、代码合同、准入规则和运行时控制边界会压缩或阻断 MetaAgent 的设计。只有同时记录 intent、source、trace engagement 和 canonical outcome，才能判断 DataAgent 是否真正发生了演进。

### 当前不能声称的结论

- 不能声称 history 已经因果性地提高了正确率。
- 不能声称更多代数会带来单调性能提升。
- 不能声称当前方法优于 matched no-history control；该 control 尚未完整结束。
- 不能把存在于 source 中但未被 trace 调用的结构算作有效机制。
- 不能把 M2.5a Gen6 的 3/5 直接当作正式主结果，因为该 replay 存在 source-identity protocol deviation。

---

## 1. Abstract（待最终实验后填写）

建议采用五段式摘要：

1. **背景与问题**：DataAgent 在多轮工具调用中会产生大量可复用经验，但现有系统主要进化 prompt、context 或 skill，缺少对 harness/candidate 演进过程的可审计验证。
2. **方法**：提出 history-guided evolution protocol，将 sealed intent、candidate source、canonical execution outcome 和 post-run review 组织为 hash-linked transactions，并分离 information lineage 与 code lineage。
3. **关键机制**：MetaAgent 基于匿名化历史选择演进维度与具体机制；admission、materialization、runtime probe 和 trace verification 验证机制是否真正可执行、被调用并产生结果。
4. **实验**：在 DataAgentBench 的异构任务上进行 matched history projection、多代三任务演进、五任务扩展以及 fixed-intent full-source replay。
5. **结论**：填写最终 matched-control 与 repeated-run 结果；无论结果正负，都突出 intent diversity、realization fidelity 和可审计边界。

---

## 2. Introduction

### 2.1 背景

- DataAgent 需要在数据库、文件、代码和外部工具之间进行长程交互。
- 单次 prompt engineering 无法持续吸收过去执行中的成功策略、失败模式和工具控制经验。
- 自进化 Agent 研究开始关注 context、memory、skill 和 experience reuse，但 DataAgent 的真实执行环境还要求处理工具合同、状态、超时、数据源差异和可复现评测。

### 2.2 现有方法的不足

- 只保存 raw trace：上下文长、噪声高，难以直接复用。
- 只保存 review：可能出现 review 与 canonical outcome 不一致。
- 只比较最终正确率：无法知道改进来自 history、candidate、模型随机性还是基础设施。
- 只检查生成代码：无法知道结构是否被加载、调用并影响了行为。
- context/skill evolution 与 harness/source evolution 往往被混在一起讨论。

### 2.3 本文研究问题

- **RQ1 — History influence**：不同 history projection 是否会系统性地改变 MetaAgent 的设计方向？
- **RQ2 — Long-horizon evolution**：完整的 intent、result、review history 能否支持多代、多任务的持续演进，而不是重复同一个候选？
- **RQ3 — Realization fidelity**：MetaAgent 的 intent 有多少真正落实为 executable candidate mechanism？
- **RQ4 — Behavioral engagement**：已实现结构是否进入真实 tool-agent loop，并在 trace 中被调用？
- **RQ5 — Task effect**：真正被调用的机制是否改善正确率、完成率、工具效率或超时率？
- **RQ6 — Reliability boundary**：在 admission、runtime contract、review inconsistency 和 infrastructure interruption 下，怎样避免伪造“自我改进”结论？

### 2.4 贡献点（投稿前按最终实验收敛）

1. **Auditable evolution protocol**：提出面向 DataAgent 的 sealed-intent、source provenance、admission、materialization、execution 和 review 闭环。
2. **Dual-lineage history model**：显式分离 code parent 与 information parent，使“从什么代码演进”和“看到了哪些经验”可独立审计。
3. **Intent-to-realization evaluation**：联合比较 intent claim、candidate source、runtime probe、trace engagement 与 canonical outcome，而不是把代码存在等同于行为改变。
4. **Multi-generation DataAgent study**：在多个异构数据库 query 上记录八代设计方向，以及从受限 DSL 到 full-source realization 的演进瓶颈。
5. **Empirical lessons**：展示 history-guided ideation、implementation fidelity 和 task performance 三者并不等价，并给出可靠自进化所需的协议条件。

---

## 3. Related Work

### 3.1 Data Agents and Benchmarks

- DataAgent 的自主等级、数据管理/准备/分析任务分类。
- DataAgentBench：真实企业数据复杂度、多数据库工具交互、可执行结果验证。
- 后续从 Awesome Data Agents 中选择 1–2 个外部 benchmark，优先满足：可执行反馈、多轮工具调用、公开评测器、可重复运行。
- 候选扩展：BIRD-SQL、Spider 2.0、AgenticDataBench；最终选择需要根据适配成本与投稿时间冻结。

### 3.2 Context and Memory Evolution

- **ACE / Agentic Context Engineering**：通过 Generator、Reflector、Curator 迭代维护 context playbook，强调增量更新、避免 context collapse，并在 BIRD-SQL 等任务上评测。
- 与本文区别：ACE 主要演进 context；本文重点追踪 history 如何驱动 candidate/harness source 改动，以及改动是否被准入、调用和验证。

### 3.3 Experience and Strategy Evolution

- **EvolveR**：把交互轨迹离线蒸馏为可复用策略原则，在线检索并通过策略强化继续积累经验。
- 与本文区别：EvolveR 的核心资产是抽象原则库；本文的核心资产是带身份、代码和 canonical execution evidence 的 generation transaction。

### 3.4 Skill and Context Self-Evolution for Data Science Agents

- **EvoDS**：Autonomous Skill Acquisition + Adaptive Context Compression，并通过 agentic RL 联合优化任务完成、skill acquisition 与 context regulation。
- 与本文区别：EvoDS 更接近 skill/context 自演进；本文关注尚未被充分覆盖的 harness/candidate structural evolution，以及其可审计执行边界。

### 3.5 Automated Research Workflows

- **ARIS**：plan → draft → adversarial review → iterate → persist 的研究自动化工作流。
- ARIS 可用于后续批量实验编排、对抗审稿和论文写作，但它不是本文的方法 baseline，也不能替代 frozen protocol、canonical evaluator 和 artifact audit。

---

## 4. Problem Formulation

### 4.1 对象定义

- DataAgent / execution policy：`A_t`
- 第 `t` 代 sealed intent：`I_t`
- candidate source / harness：`C_t`
- 一组评测任务：`Q = {q_1, ..., q_n}`
- canonical execution outcome：`O_t`
- post-run review：`R_t`
- generation transaction：`T_t = (I_t, C_t, O_t, R_t)`
- history：`H_t = {T_1, ..., T_{t-1}}`

### 4.2 两条 lineage

- **Code lineage**：本代 candidate 从哪个 source parent 继续修改。
- **Information lineage**：本代 MetaAgent 可见哪些 intent、outcome、review。
- 两者分离后，可以进行 outcome-only、outcome+intent、outcome+intent+review 和 full-history 等 matched projection。

### 4.3 三层效果定义

1. **Idea effect**：history 是否改变 intent 方向与 proposed mechanism。
2. **Realization effect**：intent 是否变成可执行 source，并通过 admission/probe。
3. **Task effect**：机制是否进入 trace，并改变 correctness、terminal state、tool efficiency 或 timeout。

只有第三层可以支持“效果改善”；第一层不能替代第二、三层。

---

## 5. Method

### 5.1 Generation lifecycle

`history snapshot → MetaAgent intent → seal → candidate generation → source artifact → admission → materialization → DAB execution → canonical outcome → review → append history`

### 5.2 History transaction

- Intent：观察到的前代限制、primary/secondary dimensions、proposed mechanism、风险、预期 trace、fallback。
- Result：canonical correctness、terminal state、trace hash、tool engagement、infrastructure/candidate failure distinction。
- Review：只基于允许的匿名事实解释 intent、source、trace 和 outcome 之间的关系。
- Hash chain：append-only record，检测覆盖、串线和身份不一致。

### 5.3 MetaAgent decision space

- 预注册抽象演进维度，但不预设具体机制。
- MetaAgent 选择 `exploit / explore / combine`，并提出具体结构。
- 论文中要明确：我们预设的是“坐标系”，不是每代路线。

### 5.4 Candidate safety and provenance

- seal 后 intent 不得修改。
- source artifact 与 bundle claim 绑定。
- admission 检查 ABI、工具合同、敏感信息和运行时边界。
- materialization 使用原始字节并验证 encoded/readback/disk hash。
- execution adapter fail-closed。

### 5.5 Realization fidelity

对每一代记录：

- intent 中声称的机制；
- source 中对应的类、函数和控制路径；
- mechanism probe 是否通过；
- trace 中是否真正调用；
- canonical outcome 是否变化。

---

## 6. Experimental Design

### 6.1 Benchmark and tasks

- 当前核心：DataAgentBench。
- 三任务阶段：Bookreview q2、Yelp q3、Civic unstructured q3。
- 五任务阶段：增加 Stockmarket q2、USAspending q4。
- 模型、provider、timeout、query order、重复次数和随机性必须预注册。

### 6.2 Experimental phases

| Phase | Purpose | Status |
|---|---|---|
| M1 | 建立 sealed intent、artifact、admission、materialization、trace、review 与 provenance | 已完成主要协议链 |
| matched history fork | outcome / +intent / +review 的单样本信息投影 | 观察到 intent 分化；无因果结论 |
| M2.2 | 首次五代运行 | admission/controller 缺陷，研究结论无效 |
| M2.3/M2.4 | 三 query、五代、完整 DAB execution | protocol-clean descriptive evidence |
| matched no-history | 因 Gen4 circuit breaker 未完成 | 不能用于因果比较 |
| M2.5 | 五 query、Gen6–Gen8 continuation | 完整执行，pass rate 保持 2/5 |
| M2.5a | 冻结 Gen6–Gen8 intent，full-source realization replay | Gen6 部分成功；Gen7/8 realization failed |

### 6.3 Metrics

- Correctness / pass rate。
- Terminal state 与 timeout rate。
- Candidate admission/probe pass rate。
- Intent-source conformance。
- Mechanism-engaged tasks 与 custom tool calls。
- Source diff/hash diversity。
- Tool calls、trace length、latency/token cost。
- History-chain validity、review consistency 和 provenance integrity。

### 6.4 必须补齐的正式实验

1. matched full-history vs no-history，至少多次重复；
2. outcome-only / +intent / +review 的 projection ablation；
3. full-source candidate 与 constrained DSL 对照；
4. frozen model、query order、timeout、repair budget；
5. intent-to-source-to-trace fidelity 自动评分；
6. 至少一个外部 DataAgent/Text-to-SQL benchmark。

---

## 7. Results（当前可写骨架）

### 7.1 RQ1: History projection changes design proposals

- matched fork 中 A/B/C 产生不同 primary directions。
- C 显式利用 review 中的 retry-loop 发现。
- 限制：每臂一个样本，不能做因果或统计结论。

### 7.2 RQ2: Multi-generation history supports diverse intents

- Gen1–Gen8 覆盖 uncertainty retention、composable tools、multi-evidence、control topology、processing granularity。
- 需要用重复实验判断这种多样性是否显著高于 no-history，而不是只做定性展示。

### 7.3 RQ3: Intent diversity does not guarantee executable diversity

- Gen2–Gen5 在受限 DSL 中 source diff 很小。
- Gen7/Gen8 的 intent 描述了 harness/pre-dispatch 机制，但 source 主要修改 DSL/tool description。
- 这是本文当前最强的诊断性发现。

### 7.4 RQ4: Mechanism engagement and task outcomes

- M2.3 五代 pass count：`3/3, 2/3, 1/3, 2/3, 2/3`。
- M2.5 五任务扩展中 Gen5–Gen8 均为 `2/5`。
- Bookreview/Yelp 稳定，Civic/Stockmarket/USAspending 暴露超时与错误答案问题。
- 当前不能把稳定 2/5 解释为 history 有效或无效，因为 candidate fidelity 与 control 不完整。

### 7.5 RQ5: Full-source realization replay

- Gen6 正式 evaluation source 获得 3/5，但后续修复 source 未评测，存在 protocol deviation。
- Gen7 因 provider/environment access 被 admission 拒绝；探索性 override 为 0/5，不计正式结果。
- Gen8 admission 通过但 mechanism probe 在 finalize 边界失败，未进入正式 DAB。

### 7.6 RQ6: Review is useful but not authoritative

- M2.5 中出现 review synthesis 与 canonical outcomes 不一致。
- 因此 review 应作为下一代解释信号，而非覆盖 operator outcome 的真值来源。

---

## 8. Discussion

### 8.1 从“记忆有效吗”转向“记忆在哪一层有效”

- history 可能先改变 ideation；
- candidate generator 决定 ideation 是否可实现；
- runtime/harness 决定结构是否有控制权；
- task evaluator 最终决定是否产生效果。

### 8.2 自进化的瓶颈不是只有 reasoning

- MetaAgent 能提出多样化方案；
- 真正困难的是 source realization、runtime contract、state lifecycle 和 dispatch boundary。

### 8.3 DataAgent 场景为何需要审计

- 工具、数据库、模型 endpoint 和 evaluator 都可能失败；
- 如果不区分 infrastructure、candidate、runtime 和 correctness failure，会产生错误归因。

### 8.4 与 ACE / EvolveR / EvoDS 的互补性

- ACE：演进 context playbook；
- EvolveR：蒸馏并检索抽象原则；
- EvoDS：学习 skill 与 context management；
- 本文：验证经验如何驱动 executable harness/source evolution，并保留端到端 provenance。

---

## 9. Limitations and Threats to Validity

- query 数量和代数仍小。
- provider/model 曾发生切换和基础设施中断。
- no-history control 未完成。
- 早期 Gen1–Gen5 的 intent prompt 主要暴露 record IDs，Gen6–Gen8 才使用过滤后的完整 history。
- constrained DSL 限制了可实现结构。
- MetaAgent review 可能与 canonical outcome 不一致。
- 超时阈值会影响困难任务的终态。
- 当前没有统计显著性和跨 benchmark 结论。

---

## 10. Conclusion（待最终实验）

结论应围绕三点组织：

1. structured history 是否改变了 MetaAgent 的设计决策；
2. 哪些设计真正成为 executable and engaged mechanism；
3. 哪些变化最终改善 DataAgent 任务表现。

无论 matched control 最终为正、负或混合结果，本文都应避免把“新颖 intent”误写成“有效自进化”。

---

## 11. 计划中的图表

### Figures

1. 整体闭环：execution → trace → canonical outcome/review → history → MetaAgent → candidate。
2. Dual lineage：code parent 与 information parent。
3. 三层效果：idea → realization → task effect。
4. Gen1–Gen8 tree-shaped design space。
5. Intent-to-source-to-trace fidelity 示例。

### Tables

1. 与 ACE、EvolveR、EvoDS 的比较。
2. benchmark/query/model/provider 配置。
3. 多代 correctness、terminal state、engagement。
4. matched history projection 与 no-history control。
5. admission/probe/realization failure taxonomy。

---

## 12. Venue framing

- 按教授建议，优先面向数据库方向会议组织论文。
- 若投 VLDB/SIGMOD，主线应强调 DataAgent system、execution-grounded evolution、reproducibility、provenance 和 database-task evaluation。
- 是否转向通用 AI/Agent 会议，应在 matched control、benchmark 扩展和 full-source formal run 完成后决定。

---

## 13. 初始参考文献地图

- Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models. ICLR 2026. <https://openreview.net/forum?id=eC4ygDs02R>
- EvolveR: Self-Evolving LLM Agents through an Experience-Driven Lifecycle. <https://arxiv.org/abs/2510.16079>
- EvoDS: Self-Evolving Autonomous Data Science Agent with Skill Learning and Context Management. <https://arxiv.org/abs/2606.03841>
- Awesome Data Agents. <https://github.com/HKUSTDial/awesome-data-agents>
- DataAgentBench. <https://github.com/ucbepic/DataAgentBench>
- ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration. <https://arxiv.org/abs/2605.03042>
