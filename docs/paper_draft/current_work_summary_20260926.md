# 当前工作总结（截至 2026-09-26）

## 1. 项目目标如何演变

项目最初关注的是：能否让 MetaAgent 根据 DataAgent 的真实执行反馈，自动修改下一代 agent/harness。

随后问题逐渐收敛为：

> 将每代的 intent、candidate、execution result 和 review 保存为结构化 history 后，后代 MetaAgent 是否能提出不同且更有效的机制？这些机制是否真的被实现、调用，并改善多个 DataAgentBench query？

目前我们已经建立了完整的协议链，也完成了多代真实执行；但尚未完成足以估计 history causal effect 的 matched no-history control。

---

## 2. 已完成的基础协议工作（M1）

### 2.1 冻结基线与信息边界

- 固定 DataAgent baseline、runtime ABI、工具协议和评测入口。
- MetaAgent 不读取 ground truth、validator 文本、query ID、数据库值或未授权 raw trace。
- 将 candidate 的 code parent 与 MetaAgent 可见的 information parent 分开。

### 2.2 Sealed intent

- MetaAgent 先生成 pre-generation intent。
- intent 在 candidate source 生成之前 seal，并记录 SHA-256。
- candidate 必须引用对应 intent，防止看到结果后回写目标。

### 2.3 Source artifact、claim 与 materialization

- 保存不可混淆的 source artifact、bundle claim、admission report。
- materialization 前重新读取 artifact source，而不是依赖内存缓存。
- M1.6a 验证 source、artifact、materialized source 三处 hash 一致。

### 2.4 Admission 与 fail-closed

- 检查 AgentHarness ABI、工具接口、禁止访问的资源和敏感信息。
- 身份、hash 或合同不一致时不执行 candidate。

### 2.5 Execution、outcome 与 review

- 保存完整 execution trace、terminal state 和 operator outcome。
- canonical outcome 与 MetaAgent review 分离；review 只能解释事实，不能改写结果。
- history transaction 以 append-only hash chain 连接。

### 已完成结论

我们已经证明：可以把真实 MetaAgent 生成的 intent 和 candidate 经过 seal、admission、artifact provenance 与 materialization 安全地接入 DAB 演进协议。

这证明的是协议可运行和可审计，不是 history 提升了 DataAgent 性能。

---

## 3. matched_history_fork：首次测试 history 信息投影

### 3.1 实验设计

三臂共享同一个冻结历史种子，只改变 MetaAgent 可见的信息：

- A：只见匿名 outcome=`error`；
- B：outcome + seed intent；
- C：outcome + seed intent + seed review。

### 3.2 观察

- A 选择 control topology / error recovery；
- B 明确选择与 seed 相反的 processing granularity 路线；
- C 直接引用 review 中的 retry-loop 问题，提出 bounded retry/fallback。

### 3.3 边界

- 每臂只有一个样本。
- 初期执行受 WSL/CE、模型 endpoint、工具合同和 Windows 换行 hash 问题阻断。
- 因此只能说 structured history **与不同的生成方向一致**，不能说 history 因果性地改善了 candidate 或答案。

### 3.4 技术修复

- 增加候选工具合同说明和 preflight。
- 用二进制 materialization 修复 LF/CRLF hash mismatch。
- 恢复 provider 后确认 candidate 能进入 `solve()`；同时发现 candidate runtime contract 仍可能失败。

---

## 4. M2.2：首次多代尝试及控制器缺陷

### 4.1 原目标

- 三个 query；
- 五代 full-history 单线演进；
- 每代保存 intent、result、review 并写回 history。

### 4.2 结果

- 行政上完成 5/5 代和 5 个 history transaction；
- 但 15/15 任务都在 candidate admission 阶段停止，没有真实 DAB execution。

### 4.3 原因

- Gen1 存在 `AnnAssign` 静态 gate false negative；
- Gen2–Gen5 还存在真实 candidate contract 缺失。

### 4.4 结论

M2.2 标记为 `inconclusive_control_defect`，不能用于评估 history effect。

---

## 5. M2.3/M2.4：三 query、五代真实执行

### 5.1 任务

- Bookreview q2；
- Yelp q3；
- Civic unstructured q3。

### 5.2 执行完整性

- 5/5 generations；
- 15/15 DAB executions；
- 0 个未执行槽位；
- history chain、source lineage 和 trace hash 验证通过。

### 5.3 每代 intent

| Gen | Primary direction | Proposed idea | Pass count |
|---:|---|---|---:|
| 1 | uncertainty retention | 工具结果 confidence register | 3/3 |
| 2 | composable tools | schema → evidence → SQL | 2/3 |
| 3 | multi-evidence | ambiguity queue | 1/3 |
| 4 | multi-evidence | Top-K evidence | 2/3 |
| 5 | uncertainty retention | uncertainty ledger | 2/3 |

### 5.4 关键发现

- intents 有明显多样性；
- 但 Gen2–Gen5 的 source diff 基本只有一行，candidate 受 M2.4 DSL/template 强烈压缩；
- Gen3/Gen4 的新结构没有被真实调用；
- 因此不能把 intent 多样性等同于 executable evolution。

### 5.5 研究边界

- 这是 protocol-clean 的 descriptive single-line evidence。
- matched no-history arm 在 Gen4 admission/normalization circuit breaker 停止，未形成完整对照。
- history effect 仍不可估计。

---

## 6. M2.5：扩展到五 query，并继续 Gen6–Gen8

### 6.1 新增任务

- Stockmarket q2；
- USAspending q4。

### 6.2 五任务结果

| Generation | Intent direction | Pass / 5 | Mechanism-engaged tasks | Custom calls |
|---:|---|---:|---:|---:|
| Gen5 expanded baseline | source Gen5 | 2/5 | 3/5 | 93 |
| Gen6 | combine / composable tools | 2/5 | 4/5 | 158 |
| Gen7 | explore / control topology | 2/5 | 1/5 | 8 |
| Gen8 | explore / processing granularity | 2/5 | 2/5 | 3 |

### 6.3 具体设计方向

- Gen6：ReEvaluateGate，每 5 次工具调用重新评估 confidence，并选择 continue/replan/escalate。
- Gen7：finalize guard、spin detector、harness turn counter、evidence fallback。
- Gen8：schema/evidence/join/SQL/verify phase frame 与 granularity ledger。

### 6.4 关键发现

- 三代 intent 和 proposal hash 均不同；
- 但 Gen7/Gen8 主要把机制写进 DSL/tool description，没有形成所声称的 harness/pre-dispatch 控制路径；
- pass rate 在 Gen5–Gen8 始终为 2/5；
- 不能据此判断 history 无效，因为主要瓶颈是 intent 没有忠实落实成 executable mechanism。

---

## 7. M2.5a：冻结 intent，重新生成 full-source candidate

### 7.1 目的

不改变 Gen6–Gen8 intent，只放宽 candidate source 的实现空间，用来回答：

> 如果 MetaAgent 的想法保持不变，完整代码权限能否让它真正实现这些机制？

### 7.2 Gen6

- full-source candidate 实现 counter、confidence scoring、continue/replan/escalate 和自定义 solve loop。
- 正式运行 5 个 query，结果 3/5；Bookreview、Yelp、Civic 通过，Stockmarket 和 USAspending timeout。
- 但正式 evaluation source 与最后一次 repair source 不一致；后者 probe 通过但未被评测。
- 状态：`completed_with_protocol_deviation`，可作诊断证据，不能直接作为主表正式提升。

### 7.3 Gen7

- `_HarnessController` 实现 finalize guard、spin detector、turn counter 和 fallback context。
- admission 检出 provider secret / `os.environ` 访问，正式 DAB 为 0。
- 探索性 override 运行 5 个 query，0/5；其中 3 个 correctness failure、2 个 runtime error。
- override 不计 preregistration-compliant 结果。

### 7.4 Gen8

- 实现 phase classifier、phase frame、granularity ledger、phase-spin hint 和自定义 solve。
- admission 通过；mechanism probe 报告 finalize 路径错误注入 phase frame。
- 正式 DAB 为 0，状态为 `realization_failed`。

### 7.5 结论

放开 full-source 权限后，intent 确实能够形成更实质的控制机制；同时也暴露了新的安全、生命周期和 dispatch-boundary 问题。

---

## 8. 到目前为止可以支持的结论

### 已支持

1. 已建立可审计的 DataAgent evolution lifecycle。
2. 不同 history projection 会对应不同的 MetaAgent 设计方向；目前是定性单样本观察。
3. full-history 多代运行能够产生跨维度的 intent 序列。
4. intent diversity、source diversity、runtime engagement 和 correctness 是四个不同层次，不能互相替代。
5. constrained DSL 会显著压缩 intent-to-source fidelity。
6. full-source realization 能产生真实 harness/controller 代码，但需要更强的 contract-aware generation 和 pre-dispatch probe。
7. canonical outcome 必须高于 review prose；review 可能出现事实不一致。

### 尚未支持

1. history 比 no-history 显著更好。
2. review 在统计上提高下一代 candidate 质量。
3. 八代演进产生单调提升。
4. 当前结果能够泛化到更多 benchmark、模型或数据库。
5. Gen6 的 3/5 是正式、无协议偏差的提升。

---

## 9. 当前最重要的研究洞见

### 9.1 History 的作用需要分层讨论

- history 可以先影响 MetaAgent 的思路；
- candidate generator 决定思路是否成为代码；
- harness 决定代码是否拥有真实控制权；
- trace 决定结构是否被调用；
- evaluator 决定是否改善任务结果。

### 9.2 当前主要瓶颈是 intent-to-realization gap

MetaAgent 已经能够 reason 出 uncertainty ledger、bounded replan、spin detector 和 phase-aware processing 等结构。现在的问题不主要是“想不出新方向”，而是：

- 如何把 intent 变成符合 ABI 的完整 source；
- 如何防止候选只修改描述而不修改控制流；
- 如何在执行前检测生命周期和 dispatch 语义；
- 如何确保被评测的 source 正是最后通过 probe 的 source。

### 9.3 这构成了可投稿的方法学问题

论文不必只讲“history 提升了多少分”。更稳健的故事是：

> DataAgent 自进化需要从 idea generation 扩展为 execution-grounded and provenance-preserving evolution；否则系统会把新颖描述、死代码或错误 review 误认为能力提升。

---

## 10. 与教授推荐工作的关系

| Work | 主要演进对象 | 与我们的关系 |
|---|---|---|
| ACE | context/playbook | 可借鉴 Generator–Reflector–Curator 和增量 memory；我们的重点是 executable source/harness 与 provenance |
| EvolveR | 从轨迹蒸馏的策略原则 | 可借鉴 experience lifecycle；我们的 transaction 额外绑定 code、trace 和 canonical outcome |
| EvoDS | reusable skills + context compression | 最接近 DataAgent self-evolution；但主要是 skill/context，而不是 harness source 自演进 |
| ARIS | 自动化科研工作流 | 可用于后续批量实验、对抗 review 和论文写作，不是实验 baseline |
| Awesome Data Agents | 文献与 benchmark 地图 | 用于选择外部 benchmark 和完善 related work |

---

## 11. 下一阶段优先级

### P0：把当前工作写成稳定论文骨架

- 固定问题定义、贡献、三层效果定义和 terminology。
- 整理一张系统图、一张 dual-lineage 图、一张 Gen1–Gen8 tree map。
- 将所有结果分为 formal、exploratory、blocked 三类。

### P1：完成可比较的 history-effect 实验

- 修复 matched no-history control。
- 冻结同一模型、query 顺序、timeout、repair budget 和 candidate contract。
- full-history 与 no-history 各自进行多次独立重复。
- 增加 outcome-only、+intent、+review projection ablation。

### P2：解决 full-source realization

- 给 MetaAgent contract-aware skeleton，但允许修改 harness 控制路径。
- admission 前加入 import、controller lifecycle、dispatch/finalize semantic probes。
- 被评测 source 必须等于最终 probe-passed source。
- 禁止 posthoc repair 替换正式 evaluation identity。

### P3：扩展 benchmark

- 从 Awesome Data Agents 中选择 1–2 个公开 benchmark。
- 优先：BIRD-SQL / Spider 2.0 / AgenticDataBench 中具有 executable feedback 的任务。
- 保留 DataAgentBench 作为主要多数据库、工具交互环境。

### P4：提高实验自动化

- 在协议冻结后，再借鉴 ARIS 自动化批量运行、日志整理、独立 reviewer 和论文更新。
- 自动化不能绕过 admission、canonical evaluator 或 source identity gate。

---

## 12. 当前项目状态的一句话总结

我们已经从“让 MetaAgent 生成一个候选代码”的 smoke，推进到“在多个 DataAgentBench query 上保存八代 intent/result/review history，并审计 intent 是否成为真实运行机制”的阶段；已经观察到 history-guided design diversification，也发现了关键的 intent-to-realization gap，但还差完整 matched control、重复实验和正式 full-source execution，才能回答 history 是否真正提高长期演进效果。
