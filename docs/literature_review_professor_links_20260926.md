# 教授推荐资料与论文综述（2026-09-26）

## 1. 一页结论

教授发来的资料可以分成三组：

1. **与我们研究问题直接相关的自演进方法**：ACE、EvolveR、EvoDS。
2. **用于定位 Data Agent 领域和挑选 benchmark 的地图**：Awesome Data Agents 及其两篇配套综述。
3. **用于提高实验和写作自动化程度的工程框架**：ARIS。

三篇自演进工作的核心区别，是它们演进的对象不同：

| 工作 | 主要演进对象 | 历史如何进入下一轮 | 是否产生可执行结构 | 主要实验领域 |
|---|---|---|---|---|
| ACE | 上下文中的结构化 playbook | 从执行轨迹提炼 insight，再增量写入 context | 否，主要改 context | Agent、金融、医疗、BIRD-SQL |
| EvolveR | 可检索的抽象策略原则 | 从成功/失败轨迹自蒸馏原则，在线检索复用 | 原则本身不是新工具 | 多跳问答 |
| EvoDS | 可执行 skill 与上下文管理策略 | 在线合成、验证、缓存 skill，并主动压缩 context | 是，可生成可复用 skill | 数据科学 Agent |
| 我们当前路线 | DataAgent 的候选程序 / harness 行为结构 | 保存 intent、canonical result、review 和 provenance，后代读取后提出并实现新 candidate | 是，而且要求真实执行、trace 和 admission 验证 | DAB / 多轮数据库工具 Agent |

因此，我们并不是简单重复其中任何一篇。最接近我们的两个参照是：

- **EvolveR**证明“执行经验 → 可复用策略 → 后续决策改善”这条逻辑；
- **EvoDS**证明 data agent 可以让 action space 随可执行 skill 的产生而扩张。

我们的潜在差异点是：不仅演进记忆、提示词或单个 skill，而是研究**带有可审计历史的可执行 agent/harness 结构演进**，并要求 intent 最终落实到 source、tool dispatch、真实执行轨迹和结果中。

---

## 2. ACE：Agentic Context Engineering

资料：

- [ACE 论文](https://arxiv.org/abs/2510.04618)
- [ACE 项目主页](https://ace-agent.github.io/)
- [教授发送的 OpenReview 页面](https://openreview.net/forum?id=eC4ygDs02R)

### 它解决什么问题

ACE 研究的不是模型权重更新，而是如何让 Agent 的 **context 随经验持续变好**。论文指出已有 context adaptation 容易出现两个问题：

- **brevity bias**：反复优化后只剩下很短、很泛化的提示，丢失具体经验；
- **context collapse**：每轮整体重写旧 context，长期积累的知识会被突然压缩或遗忘。

### 核心机制

ACE 把 context 看成一份不断增长和修订的“操作手册”，由三个角色完成更新：

1. **Generator**：使用当前 context 解决任务并产生 reasoning / execution trajectory；
2. **Reflector**：检查成功和失败，从轨迹中提取具体、可复用的 insight；
3. **Curator**：把 insight 转成结构化 delta，增量合并进 playbook。

它不让模型每轮重写整份记忆，而是把记忆拆成带 ID、内容以及 helpful/harmful 统计的条目，只更新相关条目，并做去重和 pruning。这就是论文所谓的 **incremental delta update** 与 **grow-and-refine**。

### 实验和结果

ACE 在 AppWorld 等 Agent 任务以及金融、医疗、Text-to-SQL 任务上测试。论文报告 Agent benchmark 平均提升约 10.6%，金融任务平均提升约 8.6%，并减少 adaptation latency 与 rollout 成本。教授特别指出的 SQL 实验是 **BIRD-SQL**；需要注意，该实验使用 LLM-as-a-judge，而不是数据库 execution accuracy，因此它可以作为相关证据，但不能直接替代我们在 DAB 中的真实工具执行与 trace 验证。

### 对我们的价值

ACE 给我们的最重要启发不是照搬三角色，而是两条设计原则：

- history 不应只是一段不断被重写的摘要，而应是**结构化、增量、可追踪的条目集合**；
- review 必须被转成下一轮可消费的更新，否则它只是报告，不构成演进闭环。

我们的 intent / result / review history 可以借鉴 ACE 的条目化、引用计数、去重和局部更新。但 ACE 主要优化“传给模型的 context”，没有验证 intent 是否真的变成新的 agent 代码、工具调度或 harness 机制。这正是我们可以拉开差异的位置。

---

## 3. EvolveR：从执行经历中蒸馏可复用策略

资料：

- [EvolveR 论文](https://arxiv.org/abs/2510.16079)
- [EvolveR 代码](https://github.com/Edaizi/EvolveR)
- [教授发送的中文论文笔记](https://github.com/demo234kun/SELF-EVOLUTION/blob/main/papers/03-agents/EvolveR.md)

### 它解决什么问题

EvolveR 认为，Agent 虽然能调用工具，却没有系统地从自己过去行动的后果中学习。保存原始轨迹并不等于学习，因为轨迹冗长、噪声多，而且不一定能迁移到新任务。

### 核心机制

它建立了一个经验驱动的闭环：

1. **Offline Self-Distillation**：Agent 查看自己的成功或失败轨迹，提炼一条自然语言策略原则，并配合结构化知识三元组；
2. **Online Interaction**：执行新任务时，通过 `search_experience` 检索相关原则，同时可通过 `search_knowledge` 查外部知识；
3. **Policy Evolution**：把新在线轨迹用于强化学习，继续更新策略参数；
4. 新轨迹再进入下一轮蒸馏，形成闭环。

它还给原则做效用评分和 pruning。论文对原则质量的人工抽样显示，高分原则中“正确且可执行”的比例显著高于低分原则；这说明 memory 不能无条件累积，必须评价“是否真的有用”。

### 实验和结果

EvolveR 在 Natural Questions、HotpotQA、TriviaQA、PopQA、2Wiki、MuSiQue、Bamboogle 等多跳问答数据集上评估。以 Qwen2.5-3B 为例，论文表中的平均得分达到 0.382；在消融中关闭 experience retrieval 后降到 0.340，说明推理时主动取回历史原则确实有独立贡献。

### 对我们的价值

EvolveR 与我们“把 intent 和 review 放进 history log，供后代读取”的理念非常接近，但有两个关键差别：

- 它把历史压缩为**抽象原则**；我们目前保存的是更加审计友好的 intent、canonical outcome、review、source hash 和 trace 证据；
- 它主要验证 QA 决策策略；我们还要验证策略有没有落实成可执行 candidate，以及 candidate 是否真的改变工具 Agent 的行为。

我们可直接借鉴的是：为 review 增加“actionable / vague / misleading”质量分类和使用统计，并在下一代 intent 中明确引用自己采用了哪条历史经验。这样才能判断 history 被“看到”还是被“使用”。

---

## 4. EvoDS：Data Agent 的 skill 与 context 自演进

资料：

- [EvoDS 论文](https://arxiv.org/abs/2606.03841)
- [EvoDS 代码仓库](https://github.com/usail-hkust/EvoDS)

### 它解决什么问题

EvoDS 是教授找到的、与 data agent 自演进最直接相关的工作。它针对两个限制：

- 许多 Data Science Agent 依赖固定 workflow 和静态 action space；
- 长任务中 context 不断增大，造成干扰、超长和决策不稳定。

### 核心机制

EvoDS 有三部分：

1. **Hierarchical Multi-Agent Architecture**：Manager 负责拆分任务和调度，Cleaner、Featurizer、Modeler、Visualizer 等专门 Agent 完成子任务；
2. **Autonomous Skill Acquisition（ASA）**：按需合成、验证、缓存并复用带名称、说明和可执行代码的 skill，让 action space 在执行中增长；
3. **Adaptive Context Compression（ACC）**：Agent 学习何时压缩历史以及如何压缩，而不是固定按长度截断。

系统先用 SFT 做稳定初始化，再用 multi-agent RL 联合优化任务结果、子任务完成度、context 长度和交互轮数。换句话说，它不仅奖励答对，也奖励有效调度和上下文效率。

### 实验和结果

EvoDS 在四个数据科学 benchmark 上评估：**DABench、DA-Code、ScienceAgentBench、MLE-Dojo**。论文报告 EvoDS-8B 相对最强开源基线平均提升 28.9%，EvoDS-evo 又高于不启用自主 skill acquisition 的版本。它使用 Qwen3-8B，并通过 DeepSeek-V3.1 生成训练轨迹；训练成本包括 SFT、RL 和多 GPU 环境，因此完整复现成本不低。

### 对我们的价值

它是我们 related work 中最应该正面比较的一篇，原因是它同时具备 data agent、可执行 skill 和 self-evolution。

但教授指出的边界是准确的：EvoDS 的演进单位主要是 **skill 和 context policy**，离“harness 自演进”仍有距离。它没有把 admission、probe、执行路由、失败处置、证据选择等整个控制结构作为开放演进对象。

对我们最实际的用途有两个：

- 把 DABench、DA-Code、ScienceAgentBench、MLE-Dojo 纳入 benchmark 候选池；
- 把“生成工具”定义为真正可执行、可验证、可缓存和可调用的能力，而不是只在 candidate source 中出现一个从未被 dispatch 的函数。

---

## 5. Awesome Data Agents 与两篇配套综述

资料：

- [Awesome Data Agents 资料库](https://github.com/HKUSTDial/awesome-data-agents)
- [A Survey of Data Agents: Emerging Paradigm or Overstated Hype?](https://arxiv.org/abs/2510.23587)
- [Data Agents: Levels, State of the Art, and Open Problems](https://arxiv.org/abs/2602.04261)

### 它提供什么

这个仓库不是单一方法，而是 Data Agent 论文、系统、benchmark 和教程的持续更新索引。两篇配套工作用 L0–L5 描述 Data Agent 的自治程度：

- L0：完全人工；
- L1：问答式辅助；
- L2：按既定过程执行；
- L3：在监督下自主编排端到端流程；
- L4：主动、自我管理；
- L5：能生成新范式的完全自治。

综述认为当前最关键的跃迁是 **L2 → L3**：系统从执行人类预设步骤，转为自己感知环境、分解任务并编排工具。论文列表按自治等级以及 Data Management、Data Preparation、Data Analysis 分类，最适合用作领域地图。

### 对我们的价值

这套分类可以帮助我们更准确地表述目标：我们不是只提高一次 SQL query 的正确率，而是在研究 Data Agent 如何依据执行历史，逐代改变其工具和控制策略，使它从“程序化执行”向“基于经验的自主编排”靠近。

仓库也可以用来建立 benchmark 选择表。建议至少按以下条件筛选：

1. 是否需要多步工具使用，而不是一次性文本回答；
2. 是否提供真实执行环境和机器可判定结果；
3. 是否暴露足够细的 trace，支持 observer / review；
4. 是否允许测试跨任务、跨 query 的经验迁移；
5. 复现成本是否适合当前实验资源。

因此，Awesome Data Agents 的作用是**找坐标和选实验场**，不是作为我们方法的直接 baseline。

---

## 6. ARIS：自动化科研执行与独立审计

资料：

- [ARIS 论文](https://arxiv.org/abs/2605.03042)
- [ARIS 代码仓库](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)

### 它解决什么问题

ARIS 关注长时自动科研流程中的“看起来成功，但证据不充分”。它认为 Agent 的能力不仅取决于模型，也取决于包围模型的 harness：存什么、取什么、把什么证据呈现给模型、怎样检查结论。

### 核心机制

ARIS 默认由不同模型家族承担 executor 和 reviewer，以减少单模型自我审查的共同偏差。它分为三层：

1. **Execution**：大量 Markdown skill、模型桥接、持久 research wiki、确定性图表；
2. **Orchestration**：把 idea、实验、review、写作等组织成端到端 workflow；
3. **Assurance**：做实验完整性检查、result-to-claim 映射、claim audit、文稿和 PDF 检查。

各阶段通过版本化文件交接，例如实验日志进入 review loop，review 后的证据再进入 paper writing。它还包含一个 prototype meta-optimization outer loop，但 harness 修改需要 reviewer 批准。

### 对我们的价值

ARIS 更像科研生产系统，而不是我们要比较的核心算法。它最适合在实验协议稳定后，用来：

- 自动批量启动和恢复实验；
- 让不同模型独立审查 trace、结果表和论文 claim；
- 维护实验记录、结果到结论的证据链；
- 自动生成图表、报告和论文草稿。

但它不能替代我们自己的 canonical outcome、admission gate、trace validation 或 preregistration。过早把 ARIS 接入核心实验，反而可能引入新的变量，使我们更难判断 history log 本身是否有效。

---

## 7. 横向比较：这些工作各自回答了什么

| 问题 | ACE | EvolveR | EvoDS | ARIS | 我们当前需要回答 |
|---|---|---|---|---|---|
| 历史如何保存 | 结构化 context bullets | 抽象原则库 | trajectory + compressed context + skill cache | research wiki / artifacts | sealed intent + outcome + review + provenance |
| 历史如何影响后续 | Generator 读取 playbook | 主动检索原则 | Manager 调 skill 并控制压缩 | 后续 workflow 消费工件 | 下一代 MetaAgent 读取历史后产生 candidate |
| 演进对象 | context | strategy + policy | executable skill + context policy | research workflow | executable candidate / harness behavior |
| 是否验证实际使用 | helpful/harmful 统计与任务结果 | retrieval 消融 | skill 调用和 benchmark 结果 | artifact/claim audit | 需同时验证 source、dispatch、trace、outcome |
| 主要风险 | context 膨胀或错误记忆 | 原则空泛/错误 | 高训练成本、skill 仍局部 | 自动化产生“伪成功” | intent 未落实、gate 误拦截、结果不可比 |

这张表也解释了我们前面实验暴露的问题：只看到每代 intent 不同，还不足以证明演进；必须证明历史改变了后续决策，而且这个决策落实进 candidate，在真实 DAB 执行中产生了可识别行为，最终再由 canonical result 和 review 评价。

---

## 8. 从教授意见中提取出的研究指示

1. **研究定位优先放在数据库 / Data Agent 社区。** 先围绕 VLDB、SIGMOD 等数据库方向组织问题、benchmark 和证据，再根据实验成熟度判断是否投 AI venue。
2. **不要把“有 history”本身当贡献。** ACE、EvolveR 都已有成熟的经验积累机制；我们必须强调可执行结构、harness 行为和严格审计。
3. **EvoDS 是必须正面处理的最近邻工作。** 论文中要明确区分 skill/context self-evolution 与 harness-level self-evolution。
4. **扩展实验材料。** 从 Data Agent 列表和 EvoDS 的四个 benchmark 中选择可执行、可观测、可复现的任务，避免结论只依赖三个 query。
5. **在想法跑通以后再提高自动化。** ARIS 可用于批量实验、独立 review 和论文生产，但不能让自动化掩盖研究协议或改变评测条件。

---

## 9. 建议的精读优先级

1. **EvoDS**：最近邻方法与 benchmark 来源，优先读方法、skill validation、四个 benchmark 和消融。
2. **ACE**：优先读 delta update、grow-and-refine、online adaptation 和 BIRD-SQL 评测细节。
3. **EvolveR**：优先读 principle schema、检索策略、quality scoring 与 retrieval ablation。
4. **Awesome Data Agents / 两篇综述**：建立领域 taxonomy、benchmark shortlist 和 related-work 目录。
5. **ARIS**：在实验协议冻结以后，再选择性吸收 cross-model review、artifact contract 和 claim audit。

## 10. 最核心的研究判断

这些资料共同支持一个方向：**Agent 的长期改进不应只是“多看历史”，而应把历史转化为可检索、可执行、可评价的结构，并用真实环境反馈决定保留什么。**

对我们来说，下一步真正要证明的不是“history log 存在”，而是下面这条因果链：

> 前代执行结果与 review → 后代产生有证据来源的新 intent → intent 落实为不同的可执行 candidate / harness 行为 → 在新任务上产生可复现的 trace 和 outcome 改善。

如果这条链能通过 matched no-history control、跨 query 泛化和严格 trace 审计得到支持，我们的工作就能与 ACE 的 context evolution、EvolveR 的 strategy evolution、EvoDS 的 skill evolution形成清晰区分。
