# 从 baseline 重新开始的 DAB Research Graph 演进线

状态：研究工作流约定；G0 baseline 已自然结束。其原有四节点记录保持冻结，新增 baseline 根视图是明确标记的事后结构投影，不改写预注册历史。G1 才是第一代真正的四节点研究实验。本文描述目标流程，不表示现有 `dab_research_route.py` 已实现此契约。

## 前瞻性简化工作流（2026-10-18 修订）

本节是后续有效代际的当前工作流规范，取代本文较早写下的默认 Observer、多轮 readiness 判断和分散工程 gate；G0--G3 的历史文件、失败记录和哈希保持不变。研究主线压缩为：

```text
冻结公共评测协议
        ↓
上一代 Graph + 确定性 Evidence
        ↓
Research Meta（LLM 1）
Problem / Hypothesis / Experiment / measurement_plan
        ↓
Implementation Meta（LLM 2）
候选实现 / 专属记录与提取器 / 局部契约测试
        ↓
确定性工程准入 + 统一 preflight
        ↓
唯一正式固定 56 题执行
        ↓
确定性生成 Evidence 并补全四节点 Graph
        ↓
下一代 Research Meta
```

### 1. 公共协议只冻结一次

研究线固定 baseline、56 题、base/no-hint 输入、每题 1200 秒上限和 `strict_pass/56` 主指标；超时属于失败并保留在固定分母中。每代只引用并机械核验这份协议，同时绑定本代唯一代码父代、候选源码哈希和 run ID，不重新讨论计分规则。

### 2. Evidence 的通用事实与专属测量

固定基础设施对每代生成通用结果事实，包括完整 56 题的正常完成、超时、其他失败、strict 真值或未知、trace/记录覆盖和运行有效性。它只按固定规则计算，不选择研究方向，也不解释失败原因。

研究专属字段由该代 Research Meta 在 `Experiment.measurement_plan` 中于运行前规定：数据来源、记录 hook、逐题正例/反例/未知规则、覆盖率、聚合方法以及支持或否定条件。随后同代 Implementation Meta 负责实现所需运行时记录、Evidence 专属提取器和合成测试。编排者只调度并机械核验，不临时发明、补写或改变研究信号。运行后不得因结果不理想而修改规则；事后新线索只能另存为明确标记的探索性补充，不能冒充预注册 Evidence。

### 3. 不设默认独立 Observer

下一代 Research Meta 直接读取上一代四节点、通用事实和按预注册规则产生的专属 Evidence。Meta 在同一次研究决策中先列出有事实 ID 支持的观察、主要反例和未知项，再提出本代 `Problem/Hypothesis/Experiment`。数字由确定性产物提供，Meta 不自行重算。独立 Observer 不再是每代必经调用或 gate；只有需要额外独立复核时才可按需调用，且不成为 Graph 的第五类节点。

从 G8 起，Research Meta 输入必须完整包含本新线 G0 至最新有效代的全部冻结四节点 Graph，且为**每一代**提供相同字段、相同粒度的可引用事实索引：固定 56 题结果分区（strict 通过、已判 strict 失败、completed strict 未知、超时及其他失败）和该代 Evidence 的信号、状态、陈述与局限。索引只是 Graph 导航，不代替任何旧节点，也不得只为最新诊断代附加一组更细的事实卡。Meta 先逐代引用事实 ID 列出观察、反例和未知；机械核验须确认其观察覆盖每代的结果分区和 Evidence 范围两个事实 ID，但不评判选题价值。之后 Meta 横向比较各结果队列的规模及证据边界；不预设超时或任何其它队列优先，也不以队列规模作为机械否决。专属 Evidence 的差异保留在各代原 Graph 中；若未来需要额外细节，应对相关各代按统一白名单和同构规则补充，不能单独放大上一代信号。构建、核验和调用入口分别为 `experiments/research_graph_balanced_meta_packet.py` 和 `experiments/run_research_graph_balanced_meta.py`。G0--G7 已冻结的 Research Meta 输入与结果均不回写。

G8 重新选题起，在上述均衡事实扫描后，同一次 Research Meta 调用还须按六个前瞻性能力视角分别提出候选或说明缺口：任务理解与规划、数据/模式发现与定位、工具选择执行与错误处理、跨轮状态与证据跟踪、结果核验与答案合成、预算终止与恢复。六视角是新线的机会扫描框架，不导入旧研究线产物或预设六个干预。尽量提出至少三个实质不同、事实 ID 可追溯的方向；证据不足时逐项说明，不虚构候选。Meta 对所有提出的方向显式比较证据、反例、未知、测量与接口风险，然后自主选择至多一个作为本代 `Problem/Hypothesis/Experiment`，也可不选。接口尚未验证是待工程核验的风险，不能伪称已存在，也不能在比较时悄悄删掉方向。未入选方向不是 Graph 节点，不启动额外评测；机械核验只检查六视角扫描、事实引用与比较完整性，不以研究价值或预计收益代替 Meta 选题。

### 4. Research Meta 只做研究决策

Research Meta 每代至多**选定**一个组合：`Problem_g` 定义要研究的现象及范围，`Hypothesis_g` 给出可证伪解释或诊断性预测，`Experiment_g` 规定行为干预或诊断仪表、唯一代码父代、固定评测与 `measurement_plan`。G8 重新选题起，选定前必须输出上述六视角候选扫描和逐候选比较；旧 G8 Meta 尝试原样留存，不补写其未生成的比较。

探索代和诊断代均被允许；信号是否新颖、能否从旧 trace 提取、预期收益是否高，只作为局限记录，不能否决一个安全且可执行的正式代。Research Meta 的输出冻结研究语义，但尚不是启动授权。

**研究孵化修订（2026-10-19，G11 独立修订起前瞻适用）。** 上述单次决策不再要求所有值得研究的方向在选题时已有可运行接口或完整 `measurement_plan`。Research Meta 仍逐代均衡读取已冻结 Graph，并扫描六个视角，但先比较问题的重要性、机制可能性、现有反例、关键未知、最小无任务验证路径；将当前实现便利单列，不得以熟悉的 hook 代替研究价值。它至多选择一个 `research_target`，状态为 `experiment_ready`、`interface_investigation` 或 `none`。`interface_investigation` 是有来源、有证伪问题的研究孵化记录，不冻结正式前三节点，不生成候选代码，不占用 56 题评测；可以缺少尚待接口探查才能确定的运行测量细节。只有研究目标经过有界、无真实任务的源码契约与合成接口检查后，Research Meta 才另出可执行的 `Problem/Hypothesis/Experiment/measurement_plan` 修订，进入同代 Implementation Meta。失败时保存具体阻塞和新核验的接口事实，不自动退回现成的小闸门，也不伪称该假设被评测否定。

**Research Graph 双层记忆（2026-10-19，前瞻适用）。** Research Graph 是唯一研究记忆主体，但包含两个严格分型的层。正式演进层继续保存每个已执行代的四节点 `Problem/Hypothesis/Experiment/Evidence`；只有该层的 `Evidence` 表示冻结评测实际观察。研究孵化层以追加节点保存 `research_target`、`interface_investigation`、`interface_finding` 以及后续修订后的新 `research_target`。Research Meta 的目标、Implementation Meta 的探索性接口实现和独立核验后的能力边界由 `investigates`、`derived_from`、`informed_by`、`revises` 等边连接。孵化节点统一标为 `interface_research_not_benchmark_evidence`，不得携带或暗示 strict 收益、答案正确性或正式假设检验结论。

两层通过少量显式边相连：孵化目标可用 `motivated_by` 引用正式 `Evidence`；研究目标只有达到 `experiment_ready`，经 Implementation Meta 正式实现及确定性准入后，才能以 `promoted_to` 连接到新代 `Experiment`。晋升创建新的正式四节点，不删除或回写孵化历史。原机会档案和接口能力图降为孵化层中哈希绑定的启动快照或索引附件，不再构成与 Graph 并列的权威研究记忆。统一根视图由 `experiments/research_graph_memory.py` 校验，当前 G11 迁移由 `experiments/build_research_graph_g011_memory.py` 确定性生成；未来 Research Meta 输入使用 `experiments/research_graph_layered_meta_packet.py` 同时投影两个层，并保持两类证据边界。

未来独立选题的入口问题保持中性，只要求 Meta 比较当前关键未知并选择至多一个研究目标；不得在入口问题中点名计划、证据账本、回答核验或其它候选机制。具体方向只能来自两层 Graph、六视角扫描和 Meta 自己的比较。

**解题循环与跨视角机制修订（2026-10-20，后续独立选题前瞻适用）。** G8--G11 已冻结的旧六轴扫描继续作为历史输入保留，但不再作为“每轴生成一个候选、最后选择一个轴”的选题结构。新的六个视角统一为同一抽象层级的解题循环：任务表示与分解、假设生成与搜索、证据获取与数据 grounding、状态/记忆/信念更新、行动/工具策略与恢复、综合/核验与终止。预算是所有机制共同承担的约束，不再单列为候选轴；历史孵化节点中的 `axis_id` 只是旧协议标签，不能限定新目标。

六视角今后只做非互斥的覆盖复盘，逐项记录已观察缺口和关键未知，不含 `candidate` 槽。Research Meta 在完成复盘后自由提出任意数量的 `mechanism_candidate`；每个机制以唯一 `mechanism_id` 标识，可标注一个 `primary_lens` 和多个 `related_lenses`，多个机制可以共享同一主视角，也不要求每个视角都有候选。比较和最终选择的单位必须是完整机制而非 lens。先忽略现成 hook、代码距离、工程成本和短期可启动性，按对解题行为的杠杆、研究价值、信息增益、正式事实与反例排序机制；锁定第一名后才检查接口并赋予 `interface_investigation` 或 `experiment_ready`，不得因实现困难换成次优但方便的机制。若没有足够研究价值的机制则选择 none，不回退到熟悉边界。该协议由 `experiments/research_graph_solution_loop_meta_packet.py` 校验，版本化输入由 `experiments/export_research_graph_solution_loop_packet.py` 生成；旧 packet 和 Meta 产物不覆盖、不补写。

研究输入另附版本化的**机会档案**和**接口能力图**：前者保留未入选或工程受阻的想法、阻塞来源及下一项可证伪检查；后者只陈述哈希绑定源码中已经核验的读取、写入和生命周期能力，并把未知标为未知。两者均非四节点 Graph、非正式 Evidence、非分数依据；不能覆盖、修改或替代任何已冻结 Graph。每个六视角使用相同机会字段，缺少既往构想不等于不存在机会。研究选择可以复用这些档案，但不得把其中的假设写成已证实事实。

`interface_investigation` 所需的隔离原型由 **Implementation Meta 的探索调用**编写，编排者只提供哈希绑定的相关源码、已选研究目标、能力图和无真实任务的合成场景，并独立复核源码边界、测试与失败记录。原型目录和报告明确标记 `not_formal_candidate`，不得组装正式候选、冻结 Experiment、运行 benchmark 或创建 launch claim。Implementation Meta 可以证明接口存在或构建新的内部绑定契约，但不能仅凭写出代码宣称语义支持可靠；需要对矛盾、缺证、歧义和失败回退给出可复现合成检查。原型通过也只解除相应接口未知，正式研究规格仍由后续独立 Research Meta 修订，再走第 5--8 节的实现和准入。

**内容边界按主体区分。** Research Meta、机会档案、Graph 和诊断 sidecar 不读取或接收原始任务、答案、hints、validator、工具参数/结果或答案承载日志。运行中的 DataAgent 原本就合法接收任务描述、数据库描述和工具结果；未来行为机制可以在其既有隔离环境内利用这些 agent 可见信息来规划或更新证据，但须单独证明不会向 Meta、sidecar 或其他任务泄漏，不改变固定 no-hint 输入和评测规则。不能把“Meta 不看内容”误写成“agent 运行时不能使用自身上下文”。无任务合成探针可以验证接口；真实任务只在正式准入之后运行。

本修订不回写 G0--G10 Graph、G11 首次 Research Meta 或已准备的 G11 候选。G11 研究重选须使用新的独立版本与哈希；在用户要求的比较阶段停止于 Research Meta，不自动调用 Implementation Meta、生成候选或启动正式评测。第 6--8 节的安全、preflight、唯一运行及 Evidence 追溯硬门槛保持不变。

### 5. Implementation Meta 落实同代实验

第二次 LLM 调用接收已经冻结语义的前三节点草案、`measurement_plan`、唯一代码父代、相关接口和无泄漏边界，输出候选代码、必要记录、专属提取器、局部契约测试、源码清单和变更说明。它不能重新选择 Problem、改变 Hypothesis 或看过结果后调整测量定义。

测试只覆盖本代新增机制、关键失败路径和必须保持不变的直接契约，使用合成输入或接口桩；它证明实现符合规格，不证明假设成立，也不预测 strict 得分。实现失败时，将具体机械错误交回同一代 Implementation Meta 做有界修复；若冻结规格在真实接口上不可实现，则记录工程不可实现，由新的 Research Meta 决策重新定义实验。

### 6. 工程准入只检查事实

不调用 LLM 的统一准入报告核验父代与源码哈希、变更边界、测试结果、固定评测协议、无答案/无 hint/无 validator 边界、运行与结果写回契约，以及专属记录和提取器对 `measurement_plan` 的忠实实现。诊断 sidecar 还必须证明不进入 agent 输入、工具结果、控制流或计分。

准入不得用信号新颖性、旧 trace 可提取性、预计收益或“研究是否必要”拒绝候选。现有分散的 source admission、接口卡、prepare 检查和 engineering gate 应逐步合并为这一份机器可读报告。

### 7. 统一 preflight 与唯一启动

启动前一次性核验冻结 56/base/no-hint/1200 秒绑定、源码哈希、数据库、Python 与 DAB 环境、至少 5 GiB 可用空间，并执行不含任务内容的最小模型通路检查，覆盖 DNS、TLS、凭证、模型名称和响应协议。全部通过后创建 exclusive launch claim，并只启动一次正式评测。preflight 失败不产生得分、不解释为假设失败，环境恢复后可对同一冻结候选重新 preflight。

正式运行一旦启动，56 题全部按协议走完；不设置基础设施自动熔断，不热改、不手停、不补跑单题、不因阶段分数提前结束。每 20 分钟只读监测运行计数、预注册记录覆盖、PID/源码绑定、磁盘和基础设施异常，不读取答案内容或参与研究决策。

### 8. 确定性 Evidence 与 Graph 封闭

有效运行结束后，通用层与同代 Meta 预先实现的专属提取器共同生成 `Evidence_g`。预注册结论状态至少区分 `supported`、`contradicted` 和 `inconclusive`；任何结论都受已声明的覆盖范围和未知项限制，未配对分数差异不能写成因果效果。

若完整运行受到统一基础设施故障影响，记录不可变 execution incident，并将研究状态标为 `invalid_infrastructure / hypothesis_not_tested`。此时不把观测 strict 计数解释为候选质量，不最终封闭 `Evidence_g`，也不进入下一代；环境恢复后允许对完全相同的前三节点、候选源码和测量规则重新执行。正式运行仍须让 56 题全部自然结束。

**G10 一次性修复例外（2026-10-19，用户明确授权）。** G10 原始固定 56 题运行的 5 项 PostgreSQL 加载失败均发生在模型调用前；仅这 5 项使用同一冻结候选、base/no-hint 与 1200 秒规则在独立运行中补测。允许按原批次顺序逐题取原始结果或对应补测结果，构成恰好 56 项的 G10 修复视图，并用运行前冻结的专属提取器补全 G10 Evidence/Graph，供 G11 研究输入使用。原始 56 题结果、`invalid_infrastructure` incident 和补测结果均不可改写；Graph/Evidence 必须同时绑定两次运行、逐题来源和两个分数，显著标明修复视图不是一次完整有效的单次运行，不能把 32/56 冒充原始 27/56 或作因果比较。此例外不自动扩展到其他代，也不修改 G10 的前三节点或测量规则。

有效 `Evidence_g` 生成后，由确定性程序绑定运行产物、专属提取结果、源码哈希和节点边，补全本代 Graph 并校验结构。无需运行后 Diagnosis LLM、`record-result` Meta 或 Graph append Meta；下一代 Research Meta 负责解释已冻结 Evidence。

### Evidence 在跨代研究中的作用

四类节点不是只供线性流水线使用。未来 Meta 可以把不同代的 Problem 组合成更一般的问题，复用或细化旧 Hypothesis，也可以用新的 Experiment 再次检验同一 Hypothesis。`Evidence` 的职责是为这些组合提供经验约束：它记录“哪个冻结 Experiment 在什么协议、覆盖和有效性条件下实际观察到了什么”，并把结果限定地反馈到被检验的 Hypothesis 和相关 Problem。

因此 Evidence 不等于分数总结，也不负责永久判决一个 Hypothesis。一次 Evidence 可以支持、反驳、保持不确定，或表明假设根本未被有效测试；未来不同 Experiment 可以为同一 Hypothesis 产生多份一致或冲突的 Evidence。下一代 Meta 应沿边读取这些结果和适用范围，而不是只看最近一代或把一次失败推广到整个问题。

为维持“每代四节点”，每代仍创建代际作用域的 `Problem_g/Hypothesis_g/Experiment_g/Evidence_g`。若复用旧问题或假设，新节点明确使用 `reuses`、`refines`、`competes_with` 或 `combines` 边连接旧节点；它可以保持相同陈述，也可以声明本代的收窄范围。`Evidence_g` 始终直接观察本代 `Experiment_g`，并通过 `tests` 关系约束本代 Hypothesis。这样 Graph 既能重组旧思想，也不会让新实验脱离实际执行结果。

## 目标与边界

- 新线从一个哈希固定的 baseline 源码开始，不导入旧演进线的 Graph、候选源码、研究结论或代码父代。旧记录保留为独立档案，不参与新线的研究决策。
- Research Graph 是主要的研究决策记忆；运行账本只记录不可改写的执行事实，不构成第二套选题机制。
- G1 起，每个正式研究代恰好有 `Problem`、`Hypothesis`、`Experiment`、`Evidence` 四个节点。不保留旧 `intent`，也不增加 intent 替代节点。G0 是例外的 baseline 根事实层。
- 同一问题或机制可跨代继续研究，但每代都要记录该代评测前的具体问题、可证伪假设和实验。跨代关系解释继承、细化、竞争和代码来源；不能事后改写旧节点。

## 每代四节点契约

| 节点 | 何时冻结 | 内容与职责 |
| --- | --- | --- |
| `Problem_g` | 正式执行前 | 本代针对的可观察问题、适用范围，以及来自既有 Graph 的依据。 |
| `Hypothesis_g` | 正式执行前 | 对问题的可检验解释；行为代预测机制变化，诊断代预测新信号的可观测性，并列出证伪条件、潜在反例与适用范围。 |
| `Experiment_g` | 正式执行前 | 行为干预或只读诊断仪表、唯一代码父代、候选源码哈希、固定任务与运行协议、预算和必要对照。它承担过去 intent 的实施职责。 |
| `Evidence_g` | 执行结束后 | 实际结果、完整 trace 的不可变引用、任务级计数、失败与超时、机制观察及其局限。未知项保持未知。 |

代内基本关系为 `Hypothesis_g --explains--> Problem_g`、`Experiment_g --tests--> Hypothesis_g`、`Evidence_g --observes--> Experiment_g`。跨代关系可记录某个假设对旧假设的细化或竞争、问题受哪些已有证据启发，以及实验的唯一代码父代。研究父代提供理由，不等于代码父代。

## 从 baseline 启动

1. 冻结 baseline 源码、固定任务集、no-hint 输入规则、工具协议和评测口径。新 Graph 不以 Gen15 或其他历史候选为根。
2. 基线执行记作 `G0`。历史执行前确实预注册了 `Problem_0`、`Hypothesis_0` 和 `Experiment_0`，执行后追加了 `Evidence_0`；原文件及哈希保持不变。研究导航另建哈希绑定的根视图 `Baseline Protocol -> Baseline Agent -> Baseline Execution -> Baseline Evidence`，只引用这些已冻结事实，明确标明为事后投影，不把原基线校准假设伪装为机制假设。
3. 之后的每代只可从这条新线内部选择代码父代；第一代候选的代码父代是 baseline。失败实验仍保留 Evidence，但不自动成为可复用源码。

## 逐代闭环

1. **观察上一代。** G1 的 Observer 读取 baseline 根视图和从 G0 已有 trace 确定性提取的无答案计数；其后读取上一研究代的四节点，尤其是 `Evidence`。完整 trace 是可追溯的事实源，但答案正文、工具参数/结果及原始消息不进入模型输入。数值和补数由确定性程序计算、交叉校验并绑定原文件哈希；Observer 只引用指标名作定性解释，列出反例和未知项，不直接创建下一代节点、不选修补方案、不改代码。越界输出不得送入 Research Meta。
   每次选题前，事实卡须先覆盖固定任务全集的互斥结果队列：strict 通过、已判 strict 失败、strict 判定未知、runner 超时及其他运行失败。比较各队列的任务数、可观察机制、证据缺口和对固定分母主指标的相关性；按队列规模归一化行为计数，不能用最新补证方向代替总体机会比较，也不能把工具失败标记或终止调用出现直接当作错误原因。针对某队列的有界补证只能在这张全局分布之后追加。
2. **生成下一代前三节点草案。** Research Meta 结合 Graph 和 Observer 的事实总结，在一次研究决策中比较可研究方向，提出至多一个 `Problem_{g+1}`、`Hypothesis_{g+1}`、`Experiment_{g+1}` 组合。先判断研究问题及可证伪假设是否成立（`research_ready`），再判断行为干预或诊断仪表的作用边界、预期机制或可观测性、证伪条件、唯一代码父代和固定评测是否足够具体，可交给工程实现（`experiment_spec_ready`）。Meta 不凭 Evidence 预先证明源码接口、取消语义或写回安全性；这些是下一步的工程判定。`research_ready=true` 而规格未就绪时，保留哈希绑定草案和缺失条件，但不冻结正式代前三节点、不启动评测。实验可以在**下一代唯一的正式固定评测**中做有界、无答案的机制定位；它不是额外 probe、第二臂或追分重跑。Research Meta 说明为什么检验此假设、预期观察到什么、什么结果会否定它，并分别选择研究依据与唯一代码父代。不设独立 Selection Meta，也不设常规 `diagnose / probe / implement / stop` 四选一阶段。
   对以任务进展为机制的假设，`Experiment` 必须包含评测前定义的 `measurement_plan`：同一套算法如何仅从该题正常可见输入实例化待办事项，哪些执行事件算新增证据、无进展或未知，覆盖不足如何处理，按任务而非原始总调用量如何聚合，哪种观察会证伪假设。每题的具体事项可不同，但不能按题 ID、事后 strict 判定或官方答案人工改规则。进展代理不是答案正确性；若无法定义非循环、可观测的规则，不能把“调用较多”直接写成“无进展”。可提出以测量缺口为问题的诊断代，但必须按下节的独立契约预注册，不能把未测量的进展假设伪装成已支持的行为干预。
3. **工程准入、实现和冻结。** 对规格就绪的草案，先从哈希绑定的候选代码父代核验具体 hook、现有终止/取消/结果写回语义、失败回退和可观测记录；不能证明安全时明确拒绝或退回研究草案，不得用空答案伪装正常完成。通过后 Codex Repair Meta 才在隔离工作区实现 `Experiment`。必要测试与来源、协议、预算、无泄漏检查通过后，把实际源码哈希及评测绑定写入并冻结前三节点。Meta 的布尔值不是启动授权；工程准入也不是第五个 Graph 节点、额外 probe 或正式评测。没有单独的 intent 文件或节点。
4. **执行固定评测。** DataAgent 在冻结任务和协议上运行，生成完整的确定性执行 trace 与结果。运行中不热改候选、不补跑以改变同一代结果。
5. **补全 Evidence。** 自然结束、自动超时和失败均按实际发生情况记录。`Evidence_{g+1}` 绑定 trace、结果和可复算测量；不把未配对的分数差异写成因果结论。四节点完整后，下一轮 Observer 才使用它们。

### 冻结产物的有界证据补充

如果 Research Meta 因某项明确的无答案测量缺失而给出 `experiment_spec_ready=false`，先核对该测量能否从上一代**已经冻结**的产物确定性提取。可以做一次有界的只读补充：按白名单读取事件类型、时间、工具名、成功标记、预注册机制记录及粗粒度失败阶段，校验源文件哈希与任务覆盖，仅向 Meta 提供匿名计数和事实卡；原始消息、参数、结果、答案、validator 和 hints 不进入模型输入。补充产物使用新版本和新哈希，不修改原 Evidence、Graph 或先前 Meta 输出。之后以新的独立 Observer 和 Research Meta 修订重新判断。若仍无法从冻结产物可靠提取，但可以在受审源码接口上预注册一个安全的新信号，则允许提出下节的正式诊断代；否则记录未知并停在评测前。不自动扩大到原始内容审阅、额外 probe 评测或无限循环。只读补证是 Evidence 到 Observer 的输入完整性修复，不是第五类节点，也不是新研究代。

### 正式诊断代的边界

- 诊断代也恰好有 `Problem/Hypothesis/Experiment/Evidence` 四节点，占用下一代唯一正式固定 56 题、base/no-hint、每题 1200 秒评测；超时仍算失败，主指标仍报告 strict/56。它不另开 probe 臂，也不声称或预期 strict 得分提升。
- `Problem` 指明上一代冻结产物无法可靠提供的机制信号；`Hypothesis` 预测新增仪表能否达到预注册的任务级覆盖与可区分性门槛。`Experiment` 先写明父代缺口的事实卡绑定、来源字段和实际采集 hook、逐题正/负/未知规则、覆盖不足处理、聚合和证伪规则。预测若未达到门槛，在 `Evidence` 中判为未能提供所需观察，不补改规则或补跑。
- 仪表只能写无答案、匿名、有限字段的 sidecar，不向 agent 回馈，不改变工具执行、调度、终止、模型输入、结果写回或计分。不能仅把已可从冻结 trace 复算的计数重新记录一代；也不能用结果 digest、完全重复调用等代理直接宣称任务相关性、无进展或答案正确。
- Research Meta 的 `experiment_spec_ready=true` 仅表示诊断规格完整。工程准入还须独立验证源码 hook 与数据生命周期、只读惰性、sidecar 字段、异常/超时行为、预算、来源与无泄漏，再冻结前三节点；任何未知项阻止启动。旧 Meta 修订及 G0--G2 Graph 均不回写。

研究价值和安全准入分层：信号已可从旧 trace 提取、创新性弱、可能没有分数收益等属于**软研究观察**，须如实记录，不阻断安全的探索代。只有来源、no-hint/无泄漏、固定协议、可执行性、唯一运行，以及“只读诊断不影响 agent/工具/计分”等才是启动前硬门槛。覆盖门槛是预注册的运行后解释规则；即使未达到，仍补齐本代 `Evidence`，再决定是否晋升代码父代。此修订只前瞻适用，不回写此前的拒绝记录。

G3 的独立 Research Meta 入口 `run_research_graph_g003_diagnostic_meta.py` 及其诊断规格校验器仅允许在当时已知的 G2 覆盖缺口上研究派发前的“拟议调用重复”信号，预注册两类已判 strict 队列各至少 80% 完整任务覆盖；该信号不同于已执行调用重复，也不能当作无进展或答案错误。入口本身不运行评测、不自动冻结 G3；其后续 Meta 结果与工程必要性复核见下文。旧 `g003_research_meta_009/010` 及拒绝记录保持原样。

上述 `experiment_spec_ready` 从 G3 的下一次独立 Research Meta 决策开始适用。G0--G2 和先前 G3 草案中的 `implementation_ready` 均按各自产生时的契约解释，冻结输出、哈希和 Graph 不回写。工程关口至少分别记录规格绑定、源码 hook 与生命周期、在途调用及取消/写回的竞态、超时与异常回退、无答案机制计数、固定 56/no-hint/1200 秒协议和聚焦测试；任何一项未知或失败都阻止正式节点冻结与启动。

首次按新契约生成的 `g003_research_meta_003` 给出了调用准入门控规格（`experiment_spec_ready=true`），但独立源码关口记录 `g003_engineering_gate_001.md` 判为未准入：现有 agent loop 无可直接提交的已支持非空候选，也无消费所提结构化拒绝结果的分支。G3 仍未冻结、未启动；这一区分正是规格就绪与工程可行性分离的目的。

随后用冻结 G2 summary、Graph 和 54 份哈希核验的 completed trace 只读提取全队列匿名聚合，`g002_balanced_behavior_v1.json` SHA-256 为 `1e81b876b25b50d11e04ce3c1ae8b9ffd3af11f825d446f5719559ef8d637ca1`。21 个已判 strict 失败、2 个超时、3 个判定未知均显式进入选题比较；20/21 个已判失败和 30/30 个 strict 通过有工具失败标记，说明该标记出现与否不足以区分结果。新 Observer（SHA-256 `956f000b32a047a847be08874fcab90023e41773a671cca022e65f7aa5a9c163`）与 Research Meta（SHA-256 `7ec61c89a7bbba79446aaa4a10118c15276852c80760b4662624438ceabd0bcf`）输出为版本化补充，不回写原 Evidence 或此前 Meta。`g003_research_meta_004` 选择已判 strict 失败队列为研究优先方向，但 `experiment_spec_ready=false`，因为聚合活动量不能区分必要探索与无进展重复。故仍无 G3 正式节点或运行。

在 `Experiment.measurement_plan` 新契约下，独立 G3 Research Meta 修订 `g003_research_meta_006/result.json`（SHA-256 `a9aa98d03f5d9ec70dca22e5f0c68521d82cbf8b7cc5a2923e434b008aa1a9a5`）给出评测前的任务级义务/证据进展定义，并判 `experiment_spec_ready=true`；首次输出 `g003_research_meta_005` 因事实卡类别和代码父代别名错误而原样保留、不采用。源码层 `g003_measurement_engineering_gate_001.md` 判未准入：G2 父代没有把工具事件唯一绑定到请求义务的结构化键，仅凭结果 digest 不能证明任务相关性。未实现候选、未冻结 G3、未启动评测。

再收紧的 G3 输入用哈希绑定的 G2 源码接口卡列出真实事件字段，禁止没有绑定键却声称任务义务进展，也禁止把冻结 trace 已可复算的结构计数单独包装成新一代正式评测。`g003_research_meta_007` 因额外节点 ID 未通过精确 schema；独立重生成的 `g003_research_meta_008` 通过规格校验，提出阻止同任务完全重复工具调用的行为干预，但 `g003_exact_repeat_engineering_gate_001.md` 判工程未准入：所谓 `tool_call_start` 是运行后构建的 trace 事件，不是实时派发 hook，`validated_args` 也未在现有派发接口中预先可得；重复调用可能是合法重查，终止调用和工具结果回写的安全性未获证明。`experiment_spec_ready=true` 不覆盖这些失败项。仍无 G3 正式前三节点或评测。

后续修订的 `g003_g002_runtime_interface_card_v3.json`（SHA-256 `f9a05ed3c9dcc171b3db4c1cef69d61ecd9625a646abbf90f95baddd56e37025`）在父代源码树及两份关键源码哈希绑定下，明确分开运行后归一化 trace 字段与实时包装层派发 hook。它列出派发前可见的工具名、原始及解析参数，明确 `validated_args`、事后枚举的调用序号和事件时间不能被当成派发前输入，也明确阻断后的工具消息、终止及结果存储契约尚未验证。未来 Meta 的规格校验要求单独声明实时 hook、派发前输入和仍需验证的阻断契约；事后测量字段不能冒充实时控制输入。旧 v1 卡、Meta 输出及工程拒绝记录保持不变；此修订本身未生成新 Meta、候选或 G3 评测。

按预先固定的 exact-repeat 规则对冻结 G2 的 54 份完整 trace 做一次只读、无答案复算，`g002_exact_repetition_v1.json` SHA-256 为 `2551dfd2cb852b5e5aacbba25859a368c23f31f9714215af5af4bb918a158a40`。仅 3/21 已判失败和 4/30 strict 通过任务达到全调用覆盖，低于两组各 80% 的预设门槛；已覆盖调用的 1 对 0 次重复不能被解释为组间差异，假设保持未检验。哈希绑定事实卡、独立 Observer 和 Research Meta 的终审记录见 `g003_exact_repetition_gate_002.md`。Meta `g003_research_meta_010` 判 `research_ready=true`、`experiment_spec_ready=false`、`experiment=null`；其关于语义错配占比的进一步猜测缺乏本次结构计数支持，不提升为 Graph 事实。未创建 G3 正式节点或评测，也不在同一证据上反复生成候选。

用户随后允许把测量缺口作为**正式诊断代**研究。独立的 `g003_research_meta_011` 按新契约给出 `diagnostic_instrumentation` 规格，`research_ready=true`、`experiment_spec_ready=true`，但后续工程必要性关口拒绝准入：此前 exact-repeat 提取器只查看事后 `validated_args`，忽略了冻结 G2 trace 内 LLM 响应的拟议 `tool_calls`。独立只读复算 `g002_proposed_call_coverage_v2.json`（SHA-256 `88ff0e5eedbfde9c4d2888102ca2f0f985fc3cbbab82f806c4b886a8b3984233`）显示已判失败 21/21、strict 通过 29/30 题的全部拟议调用可解析为对象，均超过所提 80% 覆盖门槛。详细来源与边界见 `g003_diagnostic_engineering_gate_001.md`。这不证明重复调用造成失败，但推翻了“该拟议信号必须新跑一代才能观察”的必要性前提；G3 仍未冻结或启动，旧 Meta 输出不回写。

用户进一步明确：Graph 应允许有界探索和诊断代，不能把“是否值得跑/是否已能提取”当作硬 gate。前述必要性拒绝记录保留；前瞻性修订见 `g003_gate_policy_revision_001.md`。后续 G3 规格必须承认 v2 只读补证已恢复拟议信号，并把新增正式代定位为实时 hook 与事后 trace 的一致性/复现探索，而非首次发现该信号；仍须通过安全与协议硬 gate 才能启动。

## 超时与通过率口径

- 每题预设 wall-clock 上限为 1200 秒（20 分钟）。达到上限由 runner 自动终止并标记 `status=timeout`，属于**超时失败**；不作为缺失样本，也不从通过率分母剔除。这里的每题上限与每 20 分钟一次的运行监测是两个不同约定。
- 正式 strict 通过率的分母是本代执行前冻结的全部任务数；当前 G0 为 56。分子只计未超时、正常完成且 `strict_match_passed=true` 的任务。因此 G0 的主指标是 `strict_pass / 56`，而不是 `strict_pass / completed` 或 `strict_pass / strict_evaluated`。
- Evidence 同时列出正常完成、超时失败、其他失败、strict 判定缺失的数量。判定缺失不得冒充 strict 失败的已判定结果，但也不得被剔除以抬高主通过率；若影响结果解释，应单独标明评测有效性限制。
- G0 已按 1200 秒上限启动，不热改运行中的 runner 或已冻结的前三节点。本节记录其执行期间明确的计分解释，后续各代在执行前将同一口径写入 `Experiment`。

Observer 的反馈可作为哈希绑定的辅助产物供 Research Meta 阅读，但不是第五类 Graph 节点。Research Meta 可以继续检验旧问题或提出竞争解释；不能为了满足形式要求虚构新的问题或声称已有证据支持未知机制。

## 保持研究主线简洁

- `diagnose` 仍是 Observer 和 Research Meta 的正常分析工作；只有通过上述准入、在下一代唯一正式评测中预注册新测量的 `diagnostic_instrumentation` 才成为一代。不设置默认 probe 分支或额外的探针评测；既不能提出可靠行为假设，又不能定义安全可证伪的新信号时，暂停候选并说明缺口。
- 工程校验仅用于确保候选可运行、输入隔离、结果可追溯，不作为独立研究路线或循环追分机制。
- 不读取或向研究模型提供官方答案、hints、validator 内容或 held-out 数据。由于旧对话曾意外暴露历史答案片段，新线的实际候选设计和 no-hint 评测必须在独立的无答案执行上下文中进行。
- G0 启动使用已核定的 baseline 源码哈希与冻结任务清单；后续代仍需在各自启动前重新验证来源与协议。

## 与现有实现的关系

当前 `experiments/dab_research_route.py` 可把历史已完成代投影为四类节点，但其导航及 handoff 仍围绕旧 intent/route 契约。新线实现时应以本文的四节点、baseline 起步和逐代冻结时序为准；不得把历史投影视作已完成的新线实现。

## G0 启动记录

- 远端独立目录：`/srv/text2sql/evolution_runtime/research_graph_baseline_20261016`。
- baseline 源码树 SHA-256：`93e4d9ebf9d8e8b0f4d6b8b356926b7ab7a66a125dc9652d30aac86e930d4eb9`；冻结 56 任务清单 SHA-256：`576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7`。
- G0 的三个执行前节点位于 `graph/g000_pre_execution.json`；56/56 prepare-only 准入通过。运行时不输入旧 Graph 或旧结果，不使用 hints，执行期间跳过 Observer。由于同一 baseline 的历史汇总此前已存在，G0 仅作新线的独立控制重跑，不把其预测视为盲的发现性结果。
- 唯一正式运行于 2026-10-16T05:48:35Z 启动，PID `174606`，运行 ID `baseline_g000_nohint_56_v1`；已自然结束，56/56 ended、50 completed、6 timeout failures、33 strict passes，主通过率 33/56=58.929%。3 个 completed 的 strict verdict 缺失，保持未知并留在固定分母内。
- `Evidence_0` 已依据本次 summary、progress 和 50 份存在的完整 trace 哈希补入；远端 `graph/g000_graph.json` SHA-256 为 `256570b3813f79bced5332994c5e3506765cd88ebdbaf6371115e9e3290bc86e`，`graph/g000_evidence.json` SHA-256 为 `a915af3cebbb09bfbecfd31584e19af85ba393fafeab0dde1ed00e9d87c5ec5d`。原执行前节点未改写；超时计分口径标明是在运行中澄清。新增的 `g000_root_view_v1.json` 不替代这些冻结文件。
- 独立 DeepSeek Observer 只读 G0 四节点及聚合 Evidence，未读取原始 trace。其原始输出有一条补数算错的反例以及读取最终答案的越界建议；研究 Meta 输入排除了反例和 trace 回查建议，保留可核对事实与未知项。原始 Observer 产物保留，不把有误陈述写入 Graph。
- 首轮独立 Research Meta 的 `implementation_ready=false`，`Problem_1`、`Hypothesis_1`、`Experiment_1` 均为空：聚合计数不足以区分超时循环、工具错误或答案质量问题。它要求先从 G0 现有产物做无答案的任务级行为刻画；这不是新 probe 评测。未调用 Repair Meta、未冻结 G1 前三节点，也未启动 G1 评测。

## G0 根视图与 G1 Observer 修复记录

- `g000_root_view_v1.json` 将 G0 投影为 Protocol、Agent、Execution、Evidence 四个根事实对象，绑定原 `g000_graph.json` 哈希；它是事后导航视图，不修改或冒充执行前预注册节点。
- `g000_behavior_v1.json` 仅从 G0 summary 和 50 份已哈希绑定的 trace 提取 cohort、工具调用与工具成功标记的计数；不输出题 ID、消息、参数、工具结果或答案。6 个 timeout 没有完整 trace，内部行为未知。
- Observer 首次修复尝试 `g001_observer_002` 不遵守结构化输出格式；第二次 `g001_observer_003` 格式正确但包含与确定性计数相矛盾的断言。两份原始产物保留，均未交给 Research Meta。
- 最终采用 `g000_fact_cards_v1.json` 中由代码计算的事实卡；独立 `g001_observer_004` 只能选择卡片 ID，不能自行补数或增添事实。验证器检查 ID、类别、唯一性及输出范围，七项聚焦测试通过。它选择了工具失败并非严格失败充分条件、组大小不等不能比较原始总量、超时 trace 缺口等事实与不确定性。
- 独立 `g001_research_meta_002` 仍判定 `implementation_ready=false`，不生成 `Problem_1`、`Hypothesis_1`、`Experiment_1`。工具失败在已判未通过任务中普遍出现，但也出现在大多数 strict 通过任务中；当时的只读计数不能支持一个具体的修复机制。未调用 Repair Meta、未冻结 G1 前三节点、未启动 G1 正式评测。

## 后续证据补充与启动门槛修订

- 用户将**后续 G1 起正式运行**的启动可用空间门槛由原先的至少 20 GiB 改为至少 **5 GiB（5 × 1024³ 字节）**。旧 G0 launcher 中的 22 GiB 检查是已结束运行的历史准入记录，不回写；未来 G1 launcher 必须在唯一正式启动前以 5 GiB 检查实际目标文件系统。低于 5 GiB 禁止启动，运行期继续只读监测空间。
- 先前的提取只扫描 G0 正常完成项的归一化完整 trace，因此把 6 个 timeout 标为“无完整 trace”。只读检查发现，它们在实际 DAB 根目录仍有原始、未归一化的部分 `llm_calls.jsonl` 和 `tool_calls.jsonl`。`g000_timeout_partial_v1.json` 以源日志 SHA-256 绑定匿名计数、时间与工具成功标记；不导出题 ID、消息、工具参数/结果或答案，也不改写冻结的 `Evidence_0`。
- 6 个 timeout 的部分日志分别记录 50、69、11、11、11、20 次已完成 LLM 调用及 79、84、44、30、30、34 次已完成工具调用。前两个案例的已记录事件跨度约 1136、1178 秒；其余四例只覆盖约 153–238 秒。后四例剩余时间耗在哪里仍未知，因为被中断的最后一次调用可能没有落盘。不能仅凭这些计数断言循环、模型慢或工具阻塞。
- 因此阻碍 G1 的主要原因是**Evidence 输入层遗漏了超时项的部分原始事件**，不是 baseline 完全没有可观察证据。旧 Observer 确有算术和越界建议的问题；修复后的卡片式 Observer 又只接收了不完整的事实卡。下一轮需把新增 sidecar 经确定性核验后接入 Observer/Research Meta，重新判断能否提出有针对性的可证伪假设；不因门槛降低就绕过研究准入。

## G1 已预注册并启动（Evidence 待运行结束）

- 追加的 G0 超时部分事件 sidecar、`g000_fact_cards_v2.json` 和独立 Observer `g001_observer_005` 已接入独立 Research Meta。最终研究输出 `g001_research_meta_004/result.json` 的 SHA-256 为 `fc8bf2c66be8c53fbe4af12fc5af15d27f460351400fed44a7f9e50805be0459`，`implementation_ready=true`；先前不合格/中断的研究与修复草案仍保留，不作为正式候选。
- G1 研究问题是固定 1200 秒上限下的超时失败；假设是在最后 120 秒、且仍有 turn boundary 时提示剩余时间并要求尽早调用已有 `return_answer`，可能把部分晚期活跃超时转为正常结束。更早中断的四个超时项原因仍未知，严格正确率变化也未知。这是一次预先固定参数的探索性假设，不宣称因果收益。
- 隔离候选只更改 G0 的 runner、tool-agent 桥接、零起点策略和聚焦测试；真实 G0 runner 哈希 `6bff187bc483d92aa47ebf6471c79383d6e31f701aff2d52b3c5086974cf9baf`，候选源码树哈希 `8c96392f656d38454272257b7ba78583fc46f22ca1fa3863b9a066a9a20a387d`。本地完整聚焦测试与远端测试通过；真实 upstream dispatcher 正反探针确认触发前探索工具照常执行，触发后探索调用不能执行而 `return_answer` 可提交。
- G1 `Problem_1/Hypothesis_1/Experiment_1` 已在正式运行前冻结于远端 `graph/g001_pre_execution.json`，SHA-256 `4d6f3392d910588b43f12fcf512a623b43b597010c15f59e5f7babd804ef2088`。完整 56 题、base DB description、no-hint、1200 秒 prepare-only 已通过。
- 唯一正式 G1 评测凭 exclusive launch claim 启动，PID `257107`，run ID `baseline_g001_deadline_reserve_nohint_56_v1`，启动可用空间 `18484166656` 字节，高于 5 GiB 门槛。G1 执行中只读监测，不热改、手停、重启或补跑；超时仍按失败计入固定 56 题分母。`Evidence_1` 必须等运行自然结束、runner 退出和终审后再追加。

## G1 自然结束与终审

- 正式运行已自然结束且 PID `257107` 退出。无写入终审核对 exact 56、源码树/runner/agent/策略哈希、base DB description、no-hint、1200 秒上限、启动声明、逐题 reserve 记录与 trace 引用均通过；最后可用空间约 15.69 GiB。
- 结果为 56/56 ended、54 正常完成、0 runner 超时失败、2 其他运行失败、30 strict，通过率主指标为 **30/56=53.571%**；另有 3 个正常完成项的 strict 判定未知，仍计入固定分母。对照 G0 的 33/56=58.929% 只是两次独立运行的描述，不能归因为机制效果。
- 56 题均有匿名 reserve 记录，其中 5 次触发、51 次未触发；56 份 trace 有哈希绑定。这说明触发路径实际可达，不证明答案正确或超时下降的因果来源。
- `Evidence_1` 已在终审后追加，远端 `graph/g001_evidence.json` SHA-256 为 `86471222974901b812f481817a569ba225b5c47e8e702608512d1cbeff89a290`；四节点 `graph/g001_graph.json` SHA-256 为 `c8d35afeb677d018c76711737df8c30b468e1574c18d7450702188a857196b9b`，独立结构与哈希核验通过。没有自动设计或启动 G2。

## G2 的一次有界证据补充与 Meta 决定

- 首次 G2 Research Meta 在只看到 G1 触发与结果聚合计数后给出 `implementation_ready=false`。它指出已冻结产物中可能有任务级结构证据；因此按上面的有界补充规则回到 Evidence 输入层，不新增评测、不改写 G1 Graph，也不把原始答案承载内容交给 Observer 或 Meta。
- `g001_structural_v2.json` 从 G1 的 56 份哈希核验 trace 与 G0/G1 冻结结果中提取匿名任务位置、事件跨度、调用次数、`return_answer` 结束次数、reserve 触发和白名单错误签名；sidecar SHA-256 为 `2f5f98753408550c2a1caf8846d4be54011b56f78b94e53513de0bff2955b8e5`。两次 G1 `FatalError` 都没有记录到 LLM 或工具事件，且错误签名无法细分；这不是根因诊断。6 个 G0 超时任务在 G1 有 5 个正常完成、1 个运行失败，3 个触发 reserve；跨运行转移只作描述。
- 确定性事实卡 `g002_fact_cards_v2.json` SHA-256 为 `cb676f98db2b1e492fbf4b5bc327dd004866650be2364978c6dbd6b700a37de2`。独立 Observer 只选择卡片 ID，输出 SHA-256 为 `d25f8cfa9dd54a7da73ff0ab39fa6f190a189366dc696116f682c1277109b809`。
- 首次补充后的 Research Meta 输出 `g002_research_meta_002` 把 G1 的 reserve 增加误写为移除，并引用不在本次事实卡中的旧 ID，因此原样保留但判为无效，不写 Graph。独立输出修订 `g002_research_meta_003` 通过卡片 ID 绑定和人工事实核验，SHA-256 为 `cd286759bb1013da39295330e9c59d5ab101b826b9df1704c6b4a5726aa534d2`；它仍判 `implementation_ready=false`，`Problem_2/Hypothesis_2/Experiment_2` 保持空。原因是超时变化不是已证实的 strict 收益，两次零事件失败的根因仍未知，单次未配对运行不能归因。不调用 Repair Meta，不冻结 G2 前三节点，也不启动 G2 正式评测。
