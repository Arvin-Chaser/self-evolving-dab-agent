# DAB 演进代码与机制审计

审计对象是 `/srv/text2sql` 中的源代码、协议脚本、prompt、适配器和运行目录。运行日志、数据库副本、候选归档和 benchmark 数据没有复制到干净导出。

## 论文主线

DAB 的可复述主线是：一个可运行的 agent 先在固定开发批次上执行；系统记录外层工作流和生成代码的运行观察；分析器把观察压缩成反馈证据；meta-agent 根据累积的演进状态提出一个可复用的机制；候选机制在隔离的源代码工作区中实现；候选和父版本使用同一批任务评测；评审分别判断实现、接入、激活、行为影响和任务影响；下一代 meta-agent 读取父版本、候选版本和所有附着证据，再选择继续沿用哪个源版本并提出下一步机制。

这里的“graph”保存的是源版本的谱系、机制意图和证据关系。parent 和 child 是 agent/source 版本；执行结果是 child transition 上的证据；review 是对 transition 的解释。没有“新提出边”这个实验机制，也不应把 result 说成独立的图节点。图上的关系是 parent→child 的继承关系，以及意图、运行证据和评审对这次演进的引用关系。

## 实际代码分层

### 1. 对象级运行层

- `experiments/run_dab_tool_agent.py`：当前 DAB tool-agent runner。负责多轮模型调用、工具调用、运行时观察注入、重试和交互步数限制、数据库容器/连接准备，以及标准化的 run artifacts。
- `experiments/run_multi_query_baseline.py`：固定批次执行器。维护 query queue，逐题运行 parent/child，聚合每题反馈和批次指标，并生成后续分析所需的 repair seed。
- `adapters/workflow_observer.py`：记录外层 LLM、tool、answer、validation、termination 事件。
- `adapters/runtime_observer.py`：被生成脚本导入，记录代码内部的执行事件。

这两类 observer 只提供事实和上下文；它们不选择修复。

### 2. 证据与反馈层

- `experiments/analyze_dab_tool_agent_trace.py`：把 workflow trace、tool calls、stage trace、结果和错误压缩成结构化观察。
- `adapters/feedback/common_trace_checks.py`：benchmark-neutral 的运行轨迹检查。
- `adapters/feedback/dab_patents_checks.py`：PATENTS/CPC 专用检查，必须作为可选适配器留在 benchmark 外部。
- `experiments/feedback_v1/core.py`：受约束的 feedback stream、signal card、intervention review、outcome projection 和 generation retrieval。它的原则是“证据先于修复决定”。
- `experiments/open_diagnosis.py`、`near_miss_causal_diagnosis.py`、`evidence_sufficiency.py`、`interpret_failure.py`：把观察整理成开放诊断、近失因果线索和证据充分性说明。

### 3. 候选实现与准入层

- `experiments/intent_candidate_workspace.py`：从 parent 做有界源快照，绑定 intent 和 parent hash，生成 candidate workspace，检查 changed files、Python 语法、实现文件和 claim-to-source。
- `experiments/call_meta_agent.py`：调用 coding/meta-agent，解析结构化编辑，生成并检查 patch。
- `experiments/apply_candidate_patch.py`、`check_candidate_patch_replay.py`、`check_patch_local_contracts.py`：只在候选工作区应用和检查 patch。
- `experiments/gate_policy.py`、`contract_eval.py`：把安全/协议执行性 gate 与软观察、候选 contract 证据分开；硬 gate 保护实验边界，软 gate 留给后续 meta-agent 学习。

### 4. 演进状态与选择层

- `experiments/dab_roadmap_protocol.py`：append-only 的受 hash 保护的 campaign protocol。核心阶段是 `ready_for_intent → intent_sealed → candidate_admitted → result_recorded → review_recorded`。它冻结 parent hash、intent hash、candidate source hash、批次摘要和 review，随后回到下一代 `ready_for_intent`。
- `experiments/archive_observation.py`：从 candidate manifest、child evaluation、metric delta、validation 和失败观察生成 archive observation。
- `experiments/archive_selector.py`：把 parent pool 与 evidence pool 分开。可作为下一代 source parent 的候选和只能作为负例/诊断证据的候选不会混淆。
- `experiments/run_meta_agent_evolution_loop.py`：旧的高层 loop，把 parent selection、parent run、trace analysis、repair seed、candidate launcher、child evaluation、archive observation、handoff 和下一代 seed 串起来。它是当前历史 DAB 实验的胶水，内部仍包含 DAB/PATENTS 路径、prompt 和 archive 约定，不能直接当成 ADB 通用主程序。

## 一次 generation 的准确顺序

1. 选择当前 source parent，并核对 source tree hash。
2. 在固定 development batch 上运行 parent，保存外层和内层观察。
3. 分析运行证据，生成 bounded feedback、diagnosis 和 repair seed。
4. meta-agent 读取 roadmap/archive snapshot，选择一个 mechanism-level intent；`invoke-intent` 是协议脚本的内部命令，不是论文中的独立科学阶段。
5. 在隔离 workspace 中从 parent 生成 child，并做 source admission。
6. 使用 child 在同一个固定批次上运行和评测。
7. 将 parent 与 child 的执行指标、逐题反馈和原始 artifact 路径作为该 generation 的 transition evidence。
8. review 判断机制是否真正实现、接入、激活，是否改变行为，以及是否带来任务影响；证据不足时标为 inconclusive。
9. 将 parent source、child source、intent、evidence、review 追加到不可变 lineage/roadmap。
10. 下一代 meta-agent 读取累积状态，选择继续使用哪个 source；它可以保留旧 parent、提升 child，或从历史 source 重新分叉，但选择发生在下一代读取状态时，而不是由一个固定的“边生成器”自动替代。

## 文件分类

### 可泛化演进核心

`adapters/workflow_observer.py`、`adapters/runtime_observer.py`、`adapters/feedback/common_trace_checks.py`、`experiments/feedback_v1/core.py`、`experiments/intent_candidate_workspace.py`、`experiments/dab_roadmap_protocol.py` 中的 hash/append-only/intent/candidate/result/review 边界、`experiments/archive_observation.py` 的中性证据抽取部分、`experiments/archive_selector.py` 的 parent/evidence pool 思路、`experiments/gate_policy.py`、`experiments/contract_eval.py`、`experiments/evidence_sufficiency.py`、`experiments/open_diagnosis.py`、`experiments/near_miss_causal_diagnosis.py`、`experiments/call_meta_agent.py` 的结构化 patch 约束。

### DAB 或 PATENTS 适配器

`experiments/run_dab_tool_agent.py`、`run_multi_query_baseline.py`、`analyze_dab_tool_agent_trace.py`、`build_dab_*`、`extract_dab_fixed_query_signals.py`、`scan_dab_queries.py`、`run_dab_eval.py`、`experiments/dab_answer_utils.py`、`adapters/dab_validator.py`、`adapters/feedback/dab_patents_checks.py`、`adapters/agentic_data_bench/`、`adapters/dab_tool_agent_helpers/`、`prompts/dab/`、`meta_agent/` 中带 DAB/PATENTS 任务契约的内容。

### 历史或运行产物

`audit_tmp/`、`evolution_runtime/`、`logs/`、`eval_candidates/`、`baseline_runs/`、`research_private/`、`experiments/dab_evolution_campaigns/`、各种 `probe_*`、旧 `.pre-openai-compat-*` 文件、缓存和 `__pycache__`。这些内容不应进入 GitHub 主实验仓库。

### 明确排除

`experiments/adb_dab_workflow.py`、`experiments/adb_evolution.py` 以及 `evolution_runtime/adb_*` 是临时桥接/错误流程实验，不属于 clean export。数据库、provider key、外部 benchmark、gold/validator、完整 trace 和历史候选也不属于 clean export。

## 这次生成的 clean export

`dab_clean_experiment_export/` 提供了 benchmark-neutral 的最小实现：observer、feedback cards、source workspace、adapter protocols、parent/child lineage、hash chain 和 loop shell。它保留 DAB 演进的论文主线，但把 query、validator、prompt、数据库和 provider 全部移到 adapter 接口外部。`tests/` 和 `examples/` 已通过本地检查。

