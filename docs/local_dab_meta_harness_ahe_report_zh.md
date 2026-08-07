# 本地 DAB 小规模实验：Meta-Harness 与 AHE 汇报报告

> 范围：本报告整理本地 DataAgentBench（DAB）九题小规模实验中 Meta-Harness 与 Agentic Harness Engineering（AHE）的运行机制、可审计工件、结果与解释。本文将**已观察到的实验结果**和**后续研究设想**明确分开。

## 1. 实验目的与范围

本轮目的不是比较两个系统在完整 DAB 上的最终 SOTA，而是在同一套本地 DAB 环境中观察两种 agent evolution / harness evolution 方法会产生什么行为与代码结构。

评测集包含 9 个 query：

| 数据集 | Query |
|---|---|
| `bookreview` | q1, q2, q3 |
| `music_brainz_20k` | q1, q2, q3 |
| `stockindex` | q1, q2, q3 |

三个数据集均通过本地 DAB 数据库与官方 DAB validator 评测。这个 9-query 集合只能作为机制观察用的小样本，不能证明对完整 DAB 或未见任务的泛化能力。

## 2. 两种方法的核心差异

```text
Meta-Harness
完整 trace + 评测回报
→ meta proposer 生成新的可运行 solver
→ 重跑 9 题，以通过数选优

AHE
agent trace + Debugger / 评测诊断
→ evolve agent 修改 prompt、memory、middleware、工具等 harness 组件
→ 保留 NexAU LLM tool-using agent 主体后重跑
```

| 维度 | Meta-Harness 本地实现 | AHE 本地实现 |
|---|---|---|
| 演进对象 | 可整体替换的 `AgentHarness` / solver 程序 | agent 周边的 workspace/harness 组件 |
| 是否保留 LLM tool loop | 不保证；最佳候选已经去掉 | 保留 |
| 典型产物 | 新 Python candidate solver | middleware、prompt、memory、配置变更 |
| 反馈形式 | trace、工具日志、每题 pass/fail、历史候选回报 | Debugger 的任务级诊断与运行 trace |
| 当前小样本最佳结果 | 8/9 | 首轮 5/9，后续未稳定提高 |

## 3. Meta-Harness：运行机制与结果

### 3.1 基线 agent 与 trace

Meta-Harness 的初始 baseline 是固定模型的循环式 DAB tool-using agent：模型根据问题反复调用 `list_db`、`query_db` 和可选的 `execute_python`，直到直接输出最终文本答案或达到轮数/超时限制。

为使 meta proposer 可审计地读取执行过程，baseline 显式写入 append-only JSONL trace。单次 run 的事件序列为：

```text
run_start
→ model_request
→ model_response
→ tool_call
→ tool_result
→ storage_delta（若适用）
→ final_answer / exception
→ run_end
```

每个事件有 `seq`、`run_id` 和 timestamp；工具事件还保存解析后的参数、原始工具 payload、call ID 和异常 traceback。这比单纯 conversation messages 更易于定位某次工具调用、返回值和状态改变之间的关系。

### 3.2 Meta-Harness 的评价指标

每个候选 agent 必须先可 import 并可实例化。之后它独立运行九个 DAB task，每题由 DAB validator 给出 `passed` 或 `failed`。

本轮真正用于 frontier 选优的核心目标是：

```text
score(candidate) = Σ_i DABValidator(candidate, task_i)
pass_rate = pass_count / 9
```

单题耗时、平均耗时、模型调用数、工具调用数会被记录，但并未作为本轮 selection objective 的显式组成部分。也没有给代码长度、通用性、token、保留 LLM loop、避免回归或 held-out 泛化加约束。

### 3.3 九题演进结果

| 代际 | 通过数 | 通过率 | 平均耗时 | 观察 |
|---|---:|---:|---:|---|
| baseline fixed tool loop | 2/9 | 22.2% | 225.473 s | 两题 600 秒超时；存在长工具循环与猜测性结束 |
| candidate_001 | 6/9 | 66.7% | 0.668 s | 首次转为确定性数据库 solver |
| candidate_002 | 7/9 | 77.8% | 0.872 s | 补充日期与音乐数据变体处理 |
| candidate_003 | **8/9** | **88.9%** | **0.967 s** | 最佳 frontier；仅 music q3 未通过 |
| candidate_004 | 6/9 | 66.7% | 1.342 s | 音乐标题清洗修改后回归 |
| candidate_005 | 6/9 | 66.7% | 2.529 s | 转向数据库连接重试 |
| candidate_006 | 6/9 | 66.7% | 18.377 s | 增强重试仍受数据库连接拒绝影响 |

基线的强反馈是：在这九题中，通用 LLM loop 会出现长路径探索、超时、跨库关联不完整、从局部结果推断最终答案等问题。后续候选在当前 objective 下选择了更直接的策略：将已知题型编译为明确数据库查询与 Python 聚合。

### 3.4 `candidate_003.py`：最佳候选实际是什么

最佳代码并非通用 data agent，而是一个 **benchmark-specialized deterministic solver**。

其执行逻辑为：

```text
读取 task.question 与 schema_description
→ 以数据集和题面关键词识别当前 9 个题型之一
→ 路由至专用 Python 函数
→ 调用真实 DAB QueryDBTool
→ 在 Python 中完成 join、清洗、聚合、排序
→ 返回纯文本答案
```

它仍使用真实 DAB 数据库工具，但不再调用模型、没有自主规划，也没有对陌生任务的 fallback。题面不匹配当前九种路径时会抛出 `Unsupported task question`。

其 9 个路径可以概括为：

| 数据集 | 代表性专用机制 |
|---|---|
| Bookreview | 在 Python 中通过 `purchaseid_N → bookid_N` 的本地数据约定做跨库关联；计算评分聚合、出版年代或 2020 后评论 |
| MusicBrainz | 清洗 artist/title/album/编码变体；按 track 聚合 sales 后在规范化的 `(title, artist)` 实体层合并、排序 |
| Stockindex | 多格式日期解析；计算日内波动、2018 涨跌日、按月固定投资回报；部分 index-country 映射直接写在代码中 |

`candidate_003` 能够在当前题集达到 8/9，是因为它把 baseline trace 中反复出现的难点固化为程序：跨库关联、日期格式、音乐标题变体、全量聚合、排序和输出格式。它不能据此被称为通用 data agent：其关键词路由、表名、字段名、本地 ID 映射和股票国家映射都与当前 9 题强绑定。

### 3.5 Meta-Harness 在本地实验中暴露出的局限

1. **小样本专化。** 仅以九题通过数为目标时，最优策略是题型路由与专用函数，而非通用 agent。
2. **没有变更保护。** candidate_003 达到 8/9 后，后续改动又降至 6/9；当前 selector 没有将已通过任务回归作为硬约束。
3. **基础设施与语义信号混杂。** candidate_005/006 处理的是数据库连接拒绝，而非 data reasoning 能力。
4. **效率仅是副产物。** candidate 的低耗时被记录，但当前目标不直接奖励 token 或速度。

## 4. AHE：运行机制与结果

### 4.1 AHE 的 agent 主体

AHE 使用 NexAU 的通用循环式 database agent。它保留 LLM，根据 system prompt 和工具返回结果决定下一步 `list_db` 或 `query_db` 调用；配置的最大迭代数为 80。其 agent config 还启用了 `InMemoryTracer`。

因此 AHE 的“演进”并不是每轮新写一个全新 solver，而是保留下列主体：

```text
LLM
→ 判断下一步工具调用
→ list_db / query_db
→ 得到工具结果
→ LLM 下一轮判断
→ 最终答案或 iteration limit
```

再由 evolve agent 改其外围 workspace：system prompt、long-term memory、middleware、tool 描述、配置等。

### 4.2 AHE trace 与 Debugger

NexAU 的 `InMemoryTracer` 保存顶层输入、最终输出、system prompt、latency、conversation messages 和 LLM spans。DAB adapter 同时另存 `tool_calls.jsonl`、运行日志、结果与 verifier 工件。

通用 `agent-debugger-cli` 的过程是：

```text
InMemoryTracer spans
→ 取最长 messages history 并按顺序补齐 assistant outputs
→ 规范化为 {trace_id, messages}
→ 单独的 debugger LLM 使用 read/search 工具阅读 trace
→ 输出 issue_type、summary、evidence、message_index
```

Debugger 具有 20 次工具调用预算；其通用 `check` 输出的 issue type 受限于：工具错误、幻觉、循环、不合规、截断。

本地 DAB pipeline 中的 `analysis/overview.md` 是比通用 `adb check` 更丰富的任务级后验诊断：它结合了 trace、工具日志、评测结果及 verifier 工件。因此文本中出现 “ground truth” 或明确的正确答案时，不能理解为 Debugger 仅凭 agent trace 推断出的信息；该信息来自评测器工件，适合作为离线错误归因，不应原样喂给未见测试题上的在线 agent。

### 4.3 AHE 的九题结果

| Iteration | 通过数 | 通过率 | 注释 |
|---|---:|---:|---|
| 1 | 5/9 | 55.6% | 初始 AHE-DAB 评测，并产生 Debugger 分析 |
| 2 | 0/9 | 0.0% | 链路/运行异常轮，不能作为能力退化解释 |
| 3 | 4/9 | 44.4% | 未超过第 1 轮 |
| 4 | 4/9 | 44.4% | 未超过第 1 轮 |

任务级历史显示不同 task 不会单调改善：`bookreview_q2`、`music_q1`、`music_q3`、`stock_q3` 在已记录轮次中持续困难；另一些已通过题也会在后续轮次回归。

### 4.4 AHE Debugger 识别到的主要失败模式

| 失败模式 | 示例 | Debugger 的解释 |
|---|---|---|
| 需求覆盖不足 | `bookreview_q2` | 只验证类别/语言，未计算每本书平均分是否恰为 5.0 |
| JOIN/聚合不完整 | `music_q1` | 未完成精确 artist-title-store-country 条件与收入聚合 |
| 跨库映射未验证 | `music_q3` | sales 的 track ID 与 tracks 标题之间的关系未可靠验证 |
| 全量枚举不足 | `stock_q3` | 未先建立完整候选指数集合再计算/排名 |
| 过度纠错 | `stock_q1`（iteration 3） | 初始正确证据被低质量后续验证推翻 |
| 轨迹耗尽 | `stock_q3`（iteration 3） | 达到 maximum iteration limit |
| 输出/评测异常 | `bookreview_q3`、`music_q1`（iteration 4） | 可能输出截断；也观察到数据库结果与 ground truth 不一致 |

这些是对 DAB 与 agent 行为的有价值离线观察，但它们目前是自由文本诊断，而非已验证的细粒度反馈机制。

### 4.5 一个具体 AHE 演进代码：StructuralValidationMiddleware

第 1 轮 evolve agent 基于四个失败任务，将根因概括为 “structural validation failures”，并在历史 commit `9c457c1` 中增加：

```text
middleware/structural_validation.py
systemprompt.md 的结构化验证原则
LongTermMEMORY.md 的持久规则
code_agent.yaml 中的 middleware 注册
```

它的注册位置是：

```text
LLM 生成 tool call
→ StructuralValidationMiddleware.before_tool_call()
→ 执行 DAB query_db/list_db
→ 工具结果回到 LLM
```

middleware 对三类情况尝试加入提示：

1. 看到 `WHERE`、`GROUP BY`、聚合、`ORDER BY` 或 `LIMIT` 时，提醒先枚举候选；
2. 看到明显缺 `ON` 的 JOIN 或模糊列引用时，提醒检查 SQL；
3. 看到疑似跨库查询时，提醒在另一数据库验证关联。

它说明 AHE 的典型风格：保留一个通用 LLM agent，不为每题写函数，而是把诊断转成可复用的 harness 行为约束。

但本地代码也显示其限制：它最终仍返回原始 `params`，不会拒绝、修改或强制重试当前 SQL；主要作用是向 context 追加自然语言提醒。枚举判断只查看最近五条消息并依赖字符串启发式；跨库检查要求单条 SQL 同时含两个数据库相关词，而 DAB 往往使用两次独立查询；SQL 修复规则也只覆盖非常表面的语法模式。因此它更像弱执行力的建议层，而不是严格 validator。

该 middleware 后续已被 workspace 回滚提交 `f036c54` 删除；报告它的目的，是展示 AHE 在本次实验中实际尝试过怎样的 evolved harness 组件，而不是将其误称为当前生效的代码。

## 5. Trace 写法的对比

| 维度 | Meta-Harness | AHE / NexAU |
|---|---|---|
| 原始结构 | 逐事件 append-only JSONL | 顶层 trace + messages + LLM spans |
| 记录重点 | 请求、响应、工具参数、工具结果、状态变更、异常 | 通用会话与运行观测 |
| 工具事件 | `tool_call` / `tool_result` 显式配对 | messages/spans 中体现；DAB adapter 另存 tool log |
| 状态变化 | 显式 `storage_delta` | 通常需从 conversation 重建 |
| Debugger 输入 | 可直接读取精确事件序列 | 先将 spans 重建/规范化为 messages |
| 对本次观察的适配性 | 便于精确追溯 solver 何时做了什么 | 便于通用 agent 诊断与 workspace 演进 |

二者都记录模型可见的消息、工具行为与外部执行状态，不记录模型不可见的内部思维链。

## 6. 汇报结论（仅基于当前小样本）

1. **Meta-Harness。** 在“固定九题、通过数最大化”的目标下，它从 2/9 演进到 8/9；代价是生成了对这九题高度专化的确定性 solver，而非通用 data agent。
2. **AHE。** 保留了通用的 LLM tool-using agent，并能通过 Debugger 给出具体的过程性诊断；但本地四轮尚未显示持续性能增益，首个 middleware patch 的执行约束较弱且过于泛化。
3. **两者的可解释性不同。** Meta-Harness 的“为什么改变”需要从 trace、candidate 代码和分数变化重建；AHE 有明确 Debugger 诊断，但诊断本身不等于修复一定有效。
4. **实验边界。** Meta 的 8/9 不能被解释成对未知 DAB task 的泛化；AHE 的 4–5/9 也不表示其原方法无效，其中包含接口/运行异常、数据/ground-truth 不一致和 patch 实现强度不足等因素。

## 7. 可选的后续研究讨论（未在本轮实验中验证）

若后续继续推进，可将问题从“让 observer/debugger 写一个更好的自然语言诊断”收敛为：从 agent trace 中识别并验证哪些细粒度信号在 DAB 上真的提高正确率、降低工具调用或减少 token。候选包括需求—证据覆盖、聚合/枚举完整性、跨库映射验证、重复调用、早停和输出完整性。

这只是研究设想，不应在汇报中表述为当前已完成结果。

## 8. 文件索引与汇报使用建议

### 正文建议引用（6 个核心工件）

| 目的 | 文件 |
|---|---|
| Meta 的各代通过数、耗时、评测摘要 | `external/harness_baselines/meta-harness/dab_meta_harness/runs/multi9_v1/logs/evolution_summary.jsonl` |
| Meta 最佳 frontier 与逐题 8/9 结果 | `external/harness_baselines/meta-harness/dab_meta_harness/runs/multi9_v1/logs/frontier.json` |
| Meta baseline tool-loop 与显式 trace 写入 | `external/harness_baselines/meta-harness/dab_meta_harness/agents/traced_baseline.py` |
| Meta 最佳确定性 solver | `external/harness_baselines/meta-harness/dab_meta_harness/runs/multi9_v1/agents/candidate_003.py` |
| AHE 各轮得分 | `external/harness_baselines/agentic-harness-engineering/experiments/dab-official-full-chain-v3/iteration_scores.md` |
| AHE 首轮 Debugger 诊断与修改总结 | `external/harness_baselines/agentic-harness-engineering/experiments/dab-official-full-chain-v3/runs/iteration_001/input/analysis/overview.md`；`.../runs/iteration_001/evolve/evolve_summary.md` |

### 备查工件

| 问题 | 文件 |
|---|---|
| Meta proposer 的外显命令与消息记录 | `external/harness_baselines/meta-harness/dab_meta_harness/runs/multi9_v1/logs/codex_sessions/` |
| Meta baseline 具体失败 trace | `external/harness_baselines/meta-harness/dab_meta_harness/runs/multi9_v1/evals/baseline_fixed_bookreview_q2/` |
| AHE 后续诊断、回归与评测异常 | `.../runs/iteration_003/input/analysis/overview.md`；`.../runs/iteration_004/input/analysis/overview.md` |
| AHE 每题跨轮 pass/fail | `external/harness_baselines/agentic-harness-engineering/experiments/dab-official-full-chain-v3/task_history.json` |
| AHE 原始 NexAU trace 样例 | `.../runs/iteration_001/input/dab_local_eval/bookreview_q2/agent/nexau_in_memory_tracer.cleaned.json` |
| AHE Debugger trace 正规化机制 | `.../evolve_agent/skills/agent-debugger-cli/_source/agent_debugger_core/trace_io.py` |
| AHE Debugger 系统提示与 schema | `.../evolve_agent/skills/agent-debugger-cli/_source/agent_debugger_core/runtime/system_prompt.md` |
| AHE 第 1 轮实际提交的 middleware | `git -C external/harness_baselines/agentic-harness-engineering/experiments/dab-official-full-chain-v3/workspace show 9c457c1:middleware/structural_validation.py` |

## 9. 推荐汇报顺序

1. 说明本地九题、三个数据集和共同 DAB validator。
2. 展示 Meta baseline 的完整 tool loop / trace 与 2/9。
3. 展示 Meta 的 2/9 → 8/9，及 `candidate_003.py` 的题型路由与确定性求解结构。
4. 说明这不是通用 data agent，而是当前九题的 specialized solver。
5. 展示 AHE 的 NexAU loop、Debugger 首轮四类诊断和第 1 轮 patch。
6. 展示 AHE 5/9 → 4/9 → 4/9，说明其本地 patch 没有形成持续增益。
7. 用一页表格总结：Meta 擅长直接优化当前评分；AHE 擅长诊断并维护通用 agent 主体，但 patch 的有效性仍需评测验证。
