# ADB 演进交接说明

## 已完成的 DAB 清理

本次工作从 `/srv/text2sql` 的 `experiments/`、`adapters/`、`prompts/`、反馈原型和历史运行目录开始审计。DAB 的实际演进被拆成四层：

1. **运行层**：parent/child 在固定 development batch 上执行，外层 workflow observer 和生成代码 runtime observer 记录调用、工具、状态、验证和终止事件。
2. **反馈层**：trace analyzer 把执行事实压缩成 feedback cards、diagnosis、failure evidence 和 repair seed。反馈提供证据，不直接规定修复。
3. **候选层**：meta-agent 根据累计 lineage/evidence 提出一个机制 intent；candidate workspace 从 parent 创建隔离 source snapshot，绑定 parent hash 和 intent hash，完成 source admission 后才进入评测。
4. **评审与谱系层**：child 在同一批次上评测；parent、child、intent、child execution evidence 和 review 追加进不可变 lineage。下一代 meta-agent 读取整个 lineage，自行选择要继续使用的 source。

核心语义已经固定：parent 和 child 是 source version；result 是 child transition 上的 evidence；result 不是节点；系统没有“新提出边”机制。

## clean export 的结构

`evolution_core/` 是 benchmark-neutral 实现：

- `models.py`：`SourceVersion`、`Intent`、`ExecutionEvidence`、`Review` 和 `EvolutionRecord`；
- `lineage.py`：source version 列表、parent/child 记录、hash chain 和 meta-agent snapshot；
- `observer.py`：有界 JSONL 观察；
- `feedback.py`：从观察生成 evidence cards；
- `workspace.py`：隔离 source snapshot 和 source manifest；
- `interfaces.py`：runner/evaluator/meta-agent/source-builder 协议；
- `loop.py`：通用 generation orchestration shell。

`LineageGraph.snapshot()` 同时暴露 `source_versions` 和每代的 `records`。meta-agent 可以通过 `select_parent()` 从累积 source 中选择 parent，而不是被固定绑定到上一代 child。

## ADB 需要实现的适配器

ADB 只需要提供四类接口：

1. `RunnerAdapter.run(source, batch_id, output_dir)`：调用 ADB agent，写出 ADB 自己的 runtime/workflow artifacts，并返回 `ExecutionEvidence`。
2. `EvaluatorAdapter.evaluate(evidence)`：读取 ADB 官方 evaluator，返回 score、完成数、错误数等指标。不要把 evaluator 代码复制进核心库。
3. `MetaAgentAdapter.propose(...)`：读取 lineage snapshot 和 feedback，提出一个机制级 intent。不要读取 hidden answers 或直接写任务答案。
4. `SourceBuilder.build(...)`：从 parent 做隔离 source snapshot，应用候选改动并返回 child `SourceVersion`。

可选地实现 `MetaAgentAdapter.select_parent(...)`，让下一代根据历史 evidence 选择任一 source；返回 `None` 时默认沿用当前 head。

## ADB 实验边界

- ADB 的 task manifest、prompt、数据库/环境、官方 scorer 和 provider 配置只能存在 adapter 或外部运行环境中。
- 每一代固定使用同一 development batch，保留 batch hash 和 source hash。
- 每代必须同时保存 parent/child source identity、intent、child evidence、review 和 artifact references。
- ADB 的 evaluator 输出应作为 measurement/evidence 注入，不应改写 lineage 选择逻辑。
- held-out 评测只能作为最终报告或独立验证，不能作为 development feedback 输入。
- baseline、candidate、provider/API 错误和 timeout 必须分开记录，避免把基础设施故障误判成机制效果。

## 推荐的 ADB 起始顺序

1. 固定并哈希 ADB development batch。
2. 实现 `RunnerAdapter` 和 `EvaluatorAdapter`，先跑 baseline，确认官方 evaluator 输出可复现。
3. 用 baseline 运行日志构造第一份 generic feedback card。
4. 实现最小 `MetaAgentAdapter` 和 `SourceBuilder`，只允许一个机制 intent。
5. 先做一代 child 的 source admission 和小批次 smoke test，再跑完整 development batch。
6. 将 parent/child/evidence/review 写入 `LineageGraph`，检查 hash chain 和 source selection。
7. 通过后再考虑 held-out 复测和论文表格。

## 当前仓库状态

本目录只完成本地 clean export 和 Git 初始提交准备，没有包含 DAB/ADB 数据、凭据或运行日志。推送前需要绑定目标 GitHub repository；目标 URL 不在当前会话中，因此当前提交会保持未设置 remote 的状态，等待绑定后执行 `git push`。
