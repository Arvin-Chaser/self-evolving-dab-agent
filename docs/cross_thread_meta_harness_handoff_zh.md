# 跨对话 Handoff：DAB / Meta-Harness / 细粒度反馈演进项目

更新时间：2026-07-26  
项目目录：`/home/m0st1ma/research/text2sql`

这个文档用于在新 Codex 对话中恢复上下文。新对话开始时，建议先让 Codex 阅读：

- `AGENTS.md`
- `docs/cross_thread_meta_harness_handoff_zh.md`
- `docs/fine_grained_feedback_chain_zh.md`
- `docs/query1_fine_grained_evolution_report_zh.md`
- `docs/full_trace_observer_architecture.md`

## 1. 当前项目主线

当前研究主线已经从早期 one-shot `generated_solve.py` 链路，切换到 DAB / DataAgentBench 多轮工具型 DataAgent 演进链路。

当前完整循环是：

```text
DAB DataAgent 多轮 LLM/tool workflow
  -> 原始运行日志
  -> full_execution_trace.jsonl
  -> observer agent 生成细粒度反馈
  -> deterministic checker / evidence sufficiency 判断证据是否足够
  -> archive-aware parent/evidence selection
  -> Codex/meta-agent 生成 candidate patch
  -> isolated child eval
  -> archive update / parent selection
  -> 下一轮演进
```

当前主入口：

```text
experiments/run_meta_agent_evolution_loop.py
```

几个关键子入口：

```text
experiments/run_dab_tool_agent.py              # 单独运行 DAB DataAgent
experiments/run_fine_grained_observer_agent.py # 单独运行 fine-grained observer
experiments/analyze_dab_tool_agent_trace.py    # deterministic trace checker
experiments/evidence_sufficiency.py            # 判断证据是否足够
experiments/run_codex_native_repair_launcher.py # Codex-native meta-agent repair launcher
experiments/archive_selector.py                # archive-aware parent/evidence selection
```

## 2. Legacy 边界

不要把旧 Text2SQL demo 或旧 one-shot generated-solve DAB 链路当成当前主线。

旧链路已归档到：

```text
legacy/cleanup_20260724_observer_trace_realign/
legacy/text2sql_demo/
```

这些文件只作为历史参考，不作为当前主要 repair target：

```text
experiments/run_dab_agent.py
experiments/analyze_agent_error.py
experiments/extract_primary_signal.py
experiments/build_meta_agent_evidence_pack.py
```

## 3. DAB DataAgent 如何记录行为

DAB upstream DataAgent 本身已有基础日志能力。代码在：

```text
/home/m0st1ma/research/DataAgentBench_upstream/common_scaffold/DataAgent.py
/home/m0st1ma/research/DataAgentBench_upstream/common_scaffold/tools/BaseTool.py
```

每次运行会产生 upstream run dir：

```text
<query_dir>/logs/data_agent/<run_id>/
```

核心原生日志有三类：

```text
llm_calls.jsonl   -> 每次 LLM call
tool_calls.jsonl  -> 每次 tool exec
final_agent.json  -> agent 最终终止状态
```

它们对应到 normalized full trace 的事件：

```text
llm_calls.jsonl
  -> llm_request
  -> llm_response

tool_calls.jsonl
  -> tool_call_start
  -> tool_call_end

final_agent.json
  -> agent_termination
```

`llm_calls.jsonl` 记录每轮 LLM 看到的 `messages`、返回的 `response/tool_calls`、模型、耗时和错误。  
`tool_calls.jsonl` 记录工具名、参数、校验后参数、成功/失败、结果 preview 和耗时。  
`final_agent.json` 是最终快照，记录 `final_result`、`terminate_reason`、`llm_call_count`、`messages`、`result_storage`、`tools` 和日志路径。

## 4. 我们添加的 runtime patch / wrapper

我们没有重写 DAB DataAgent，而是在运行时用 wrapper 给 upstream DataAgent 加能力。

入口：

```text
experiments/run_dab_tool_agent.py
```

它导入 upstream DataAgent：

```python
data_agent_module = importlib.import_module("common_scaffold.DataAgent")
```

然后动态安装：

```text
install_query_capacity_guard
install_configurable_llm_retry
install_self_observation_tool
install_evolved_helper_tool
```

这些 runtime patches 的作用：

1. 接入本地 Qwen / DashScope / 百炼兼容 OpenAI API。
2. 替换 `call_llm()`，增强 retry、timeout、last_error、retry_config 日志。
3. 添加 `run_evolved_helper`，让 meta-agent 生成的新 helper 可以作为 DataAgent 工具使用。
4. 添加 `record_self_observation`，以及普通工具的 `self_observation` sidecar。
5. 添加 query capacity guard，阻止无界大表 SELECT，避免大表直接塞给 LLM 或撑爆本地环境。

推荐表述：

```text
DAB logs what happened;
our wrapper makes it observable, extensible, and usable for meta-agent evolution.
```

## 5. 典型 run directory 文件解释

推荐展示目录：

```text
logs/multi_query_baseline/observer_multiquery_parent_20260724_031351/runs/observer_multiquery_parent_20260724_031351_q02_stockindex_query1/
```

里面的关键文件：

- `llm_calls.jsonl`：每次 LLM 调用的原始日志。
- `tool_calls.jsonl`：每次工具调用的原始日志。
- `final_agent.json`：Agent 结束时的完整状态快照。
- `agent_self_observations.jsonl`：DataAgent 运行过程中的开放式观察日志。
- `execute_python_artifacts.jsonl`：`execute_python` 工具内部执行证据。
- `workflow_trace.jsonl`：轻量流程摘要。
- `full_execution_trace.jsonl`：把 LLM 调用、工具调用和最终终止状态整合成统一时间线。
- `summary.json`：本次 run 总览。
- `final_answer.txt` / `raw_final_answer.txt`：normalized / raw final answer。
- `observer_raw_behavior_input.json`：实际喂给 observer agent 的输入 payload。
- `observer_fine_grained_feedback.json`：observer agent 生成的细粒度反馈。
- `feedback_summary.json`：deterministic checker 生成的机器可读摘要。
- `observations.json`：deterministic analyzer 输出的问题观察列表。
- `meta_agent_seed.json`：下一轮 meta-agent 可用 seed。

注意：`full_execution_trace.jsonl` 不是把所有文件都合并进去，它主要合并 `llm_calls.jsonl`、`tool_calls.jsonl`、`final_agent.json`。`agent_self_observations.jsonl` 和 `execute_python_artifacts.jsonl` 通常作为旁路 raw artifacts 一起给 observer 看。

## 6. 当前细粒度反馈链路

核心链路：

```text
DataAgent raw logs
  -> full_execution_trace.jsonl / raw artifacts
  -> observer_raw_behavior_input.json
  -> observer_fine_grained_feedback.json
  -> feedback_summary / observations / evidence_sufficiency
  -> meta_agent_seed
  -> Codex/meta-agent repair
```

observer 代码：

```text
experiments/run_fine_grained_observer_agent.py
```

核心函数：

```text
build_observer_payload()
build_prompt()
run_llm_observer()
deterministic_feedback()
```

observer prompt 的核心要求：

```text
Read raw DataAgent behavior.
Do not choose from a fixed failure taxonomy.
Do not rely on prebuilt evidence pack or pre-inferred selected_stage/selected_signal.
Infer failure structure directly from artifacts.
Do not write patches.
Return strict JSON.
```

observer 输出字段包括：

```text
failure_narrative
evidence_chain
inferred_failure_mechanisms
answer_quality_shape
repair_affordances
logging_gaps
next_observation_requests
confidence
```

关键研究表述：

```text
固定的是 trace event schema，不固定 failure interpretation。
```

也就是我们规定记录哪些行为，但不规定错误应该如何解释；解释交给 observer agent。

## 7. deterministic checker 是什么

当前主要有两个 deterministic checker。

### 7.1 `analyze_dab_tool_agent_trace.py`

路径：

```text
experiments/analyze_dab_tool_agent_trace.py
```

作用：

```text
读取 run_dir
生成 observations.json
生成 feedback_summary.json
生成 meta_agent_seed.json
```

它是纯 Python 脚本，不调用 LLM。

### 7.2 `evidence_sufficiency.py`

路径：

```text
experiments/evidence_sufficiency.py
```

核心函数：

```python
assess_evidence_sufficiency(...)
```

它判断当前证据是否足够支持下一轮 meta-agent repair。

它检查的 evidence signals 包括：

```text
has_stage_signal
has_action_trace_or_behavior_input
has_answer_quality_metric
has_failure_mechanism
has_failure_evidence_chain
has_parent_child_delta
has_tool_runtime_evidence
has_full_child_traceback
```

常见 missing evidence：

```text
selected_stage_or_signal
raw_action_trace_or_behavior_input
answer_quality_or_failure_mechanism
parent_child_delta
full_child_rerun_stderr_or_traceback
pre_query_failure_traceback
runtime_helper_tool_list_or_call_trace
closed_answers_to_observer_open_questions
```

它不是决定怎么修，而是判断：

```text
证据够不够？
如果不够，先演进 observer/trace/evidence pipeline。
如果够，再让 meta-agent 修 DataAgent。
```

## 8. Meta-Harness / harness search 的关系

Harness 指模型外部的运行框架，包括：

```text
prompt
tools
tool descriptions
memory
retrieval
logging
verifier
retry
stopping rule
answer format
helper scripts
workflow controller
```

Harness search 就是：

```text
不训练模型权重，而是自动搜索如何组织模型、工具、记忆、反馈和验证流程。
```

我们与 Meta-Harness 不应表述为“完全不同”。更准确的说法：

```text
我们的系统可以看作 DAB 上的 Meta-Harness-style evolution loop；
但我们的研究变量是 feedback representation / feedback abstraction。
```

核心区别：

```text
Meta-Harness 关注 harness 能不能被自动搜索出来；
我们关注 meta-agent 在 harness search 时应该看到什么反馈。
```

推荐表达：

```text
Meta-Harness focuses on harness search.
Our project focuses on feedback abstraction for harness search.
```

或者：

```text
Meta-Harness 证明 harness 可以自动演进；
我们研究演进过程中反馈该如何表示。
```

## 9. 为什么 LLM observer 仍然算细粒度反馈

教授可能质疑：observer 也是 LLM，那这还算细粒度反馈吗？

建议回答：

```text
算。fine-grained feedback 不是指必须由规则或人工生成，
而是指它比 final score/pass-fail 更细，能指出行为链、失败机制、证据来源和 repair affordance。
```

observer 和 meta-agent 的角色不同：

```text
observer:
  输入 DataAgent raw logs
  输出 failure_narrative / evidence_chain / failure_mechanism / repair_affordance
  不改代码，不生成 patch，不决定 parent

meta-agent:
  输入 observer feedback + deterministic checker + archive
  输出 candidate patch
  可以修改 DataAgent/harness/observer/eval pipeline
```

关键说法：

```text
It is LLM-generated fine-grained feedback,
not hand-coded feedback.
```

为了证明不是单纯多用一个 LLM，需要 matched-budget 对比实验：

```text
A. score-only feedback
B. full-log direct feedback
C. observer-generated fine-grained feedback
```

控制：

```text
总 token budget
LLM call 数
DataAgent run 数
wall-clock budget
```

## 10. 当前研究叙事

核心题目可以表述为：

```text
Fine-Grained Feedback as a Semantic Bottleneck for Harness Evolution
```

或者：

```text
Observer-Mediated Feedback Compression for Agent Harness Search
```

中文：

```text
面向 Agent 演进的细粒度反馈压缩机制
```

核心主张：

```text
完整执行日志信息太多、噪声太大、上下文成本高；
只给最终分数又太粗；
observer-generated fine-grained feedback 是 raw log 和 meta-agent 之间的语义压缩层。
```

研究问题：

```text
从完整 execution log 中抽取出的 compact fine-grained feedback，
是否比 score-only 或 full-log direct 更高效地驱动 meta-agent evolution？
```

## 11. 推荐展示案例

### 11.1 细粒度反馈从 trace 中产生

推荐主展示目录：

```text
logs/multi_query_baseline/observer_multiquery_parent_20260724_031351/runs/observer_multiquery_parent_20260724_031351_q01_PATENTS_query1/
```

该 run 特点：

```text
query = PATENTS/query1
llm_call_count = 10
tool_call_count = 10
full_execution_event_count = 41
terminate_reason = max_iterations
final_answer_nonempty = false
```

observer 指出的失败机制包括：

```text
schema misalignment via literal column assumption
dialect-blind query generation
no fallback to local computation under SQL failure
answer submission abandonment
```

### 11.2 stockindex final_agent.json 展示

路径：

```text
logs/multi_query_baseline/observer_multiquery_parent_20260724_031351/runs/observer_multiquery_parent_20260724_031351_q02_stockindex_query1/final_agent.json
```

核心状态：

```text
final_result = ""
terminate_reason = max_iterations
llm_call_count = 10
max_iterations = 10
deployment_name = qwen-plus
```

结论：

```text
不是崩溃；
不是 API 失败；
而是多轮工具 workflow 跑满后没有调用 return_answer。
```

关键过程：

```text
execute_python 过滤 Date >= 2020 后返回 []
agent 重复空结果逻辑
无界 SELECT DISTINCT 被 capacity guard 拦截
最后一轮才用 LIMIT 10 查到 HSI / 000001.SS / N225
但已经没有剩余轮次提交答案
```

### 11.3 observer/evidence pipeline 自身演进

推荐 candidate：

```text
candidates/dab/codex_native_observer_sufficiency_v7_iter001_20260724_062040/
```

它适合讲：

```text
当 evidence_sufficiency 判断证据不足时，
meta-agent 没有继续盲目修 DataAgent，
而是开始修 observer / child-eval / evidence preservation infrastructure。
```

重要字段：

```text
missing_evidence:
  full_child_rerun_stderr_or_traceback
  parent_child_delta
  pre_query_failure_traceback

recommended_evolution_target:
  observer_feedback_pipeline

recommended_observer_subtarget:
  runtime_evidence_acquisition
```

## 12. Query1 已有成果

之前在 PATENTS query1 上，我们经历了从基础 DataAgent 到高 F1 / 通过版本的演进。

重要结论：

```text
细粒度反馈显著改变了 meta-agent 的 repair 方向。
```

早期阶段：

```text
precision 低，recall 较高，extra_count 多
```

说明候选集合太宽。meta-agent 由此转向：

```text
减少 noisy secondary CPC classifications
优先 primary CPC assignments
```

后期 near-miss 阶段：

```text
F1 > 0.95
missing/extra 很少
```

于是进入 near-miss refinement：

```text
检查 missing 的少数项目
倒推 boundary / filtering / formatting 原因
做小范围修复
```

这说明细粒度反馈不是只给“错了”，而是给出错误形状和下一步修复 affordance。

## 13. Multi-query 当前进展

目前小范围 multi-query 主要使用：

```text
PATENTS/query1
stockindex/query1
```

原因：

```text
完整 DAB 数据和 Docker/MongoDB 资源消耗太大；
本地 C 盘/WSL VHDX 容量有限；
先用 1-2 个 query 验证机制。
```

multi-query 目前展示出的问题：

```text
DataAgent 往往仍会卡在 workflow completion；
meta-agent 有时更倾向生成 query-specific helper，而不是高层结构；
observer feedback 已能识别失败机制；
但如何让 meta-agent 更稳定利用 observer feedback 仍是下一阶段重点。
```

## 14. Docker / WSL 容量问题经验

本地环境：

```text
Windows + WSL Ubuntu + Docker Desktop
```

问题：

```text
C 盘突然被占满，主要来自 WSL / Docker Desktop 的 VHDX 膨胀。
```

原因：

1. 下载 DAB 多 query 数据集。
2. Docker image pull 解压多个 layer。
3. Postgres / MongoDB container / volume 占用空间。
4. WSL ext4.vhdx 只会自动增长，不会自动缩小。

关键机制：

```text
在 WSL 内删除文件，只释放 Linux 文件系统内部空间；
Windows C 盘看到的 VHDX 不会自动变小；
必须 compact / Optimize-VHD 才能把空间还给 Windows。
```

短期策略：

```text
只保留 PATENTS + stockindex 等少数 query
暂时不卡在 MongoDB
避免反复 pull 大镜像
定期清理 logs/candidates/cache
必要时 compact WSL VHDX
```

长期策略：

```text
把 WSL / Docker data root 迁移到新硬盘
使用 sparse checkout / selective dataset download
按 query workspace 隔离数据和 archive
给 loop 加 disk usage monitor
```

## 15. 代理 / 网络经验

WSL 中常用代理：

```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY

export http_proxy="http://172.17.240.1:17891"
export https_proxy="http://172.17.240.1:17891"
export HTTP_PROXY="http://172.17.240.1:17891"
export HTTPS_PROXY="http://172.17.240.1:17891"
export all_proxy="http://172.17.240.1:17891"
export ALL_PROXY="http://172.17.240.1:17891"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="localhost,127.0.0.1,::1"
```

Windows 代理软件：

```text
代理地址：127.0.0.1:17891
局域网代理：开启
```

WSL 里通常用宿主机网关：

```text
172.17.240.1:17891
```

DashScope / 百炼：

```text
DASHSCOPE_API_KEY
https://dashscope.aliyuncs.com/compatible-mode/v1
qwen-plus
```

Windows `curl.exe` 曾出现 TLS revocation / schannel 问题，比如：

```text
CRYPT_E_REVOCATION_OFFLINE
```

这更多是 Windows curl / schannel 证书吊销检查问题，不一定代表 WSL/Python 也失败。

## 16. 常用运行环境建议

在 WSL 项目目录：

```bash
cd /home/m0st1ma/research/text2sql
source .venv/bin/activate
export PYTHONPATH=/home/m0st1ma/research/text2sql
```

常用环境变量：

```bash
export DAB_TOOL_AGENT_MODEL=qwen-plus
export DAB_TOOL_AGENT_MAX_ITERATIONS=10
export DAB_TOOL_AGENT_CHILD_MAX_ITERATIONS=10
export PG_CLIENT=/home/m0st1ma/research/text2sql/tools/psql_via_docker.sh
export PATH=/home/m0st1ma/research/text2sql/tools/local_bin:$PATH
```

如果用 DashScope：

```bash
export DASHSCOPE_API_KEY=...
```

不要把 key 发给 Codex，只要确认当前 shell 可见即可。

## 17. 已遇到的重要工程问题和修复经验

### 17.1 Qwen/Codex 工具续轮问题

早期用 Qwen 扮演 Codex meta-agent 时，出现过：

```text
apply_patch 被当普通文本输出
首轮只读不修改
patch.diff 为空
```

曾经做过 smoke test，证明底层 command execution 可行，但 Qwen editor protocol 不稳定。

解决方向：

```text
structured patch spec
deterministic executor apply
first-action gate
empty patch gate
fail-fast validation
```

后来逐步转向 Codex-native meta-agent，因为原生 Codex 更适合多轮工具循环。

### 17.2 Candidate patch 与 child workspace 不对齐

曾经出现：

```text
candidate patch 生成基线
和 child eval parent materialized workspace
不完全一致
```

这会导致 patch 不能应用，或者 child eval 测不到真实效果。

修复方向：

```text
确保 parent materialization 和 candidate patch baseline 一致
child eval 中保留 patch apply stdout/stderr
失败时不得吞掉 traceback
```

### 17.3 batch lineage 丢失

v7 里曾出现：

```text
batch query_ids 为空
query_count = 0
child rerun 没真正跑 multi-query
```

已在 `run_meta_agent_evolution_loop.py` 和 `meta_agent_cycle.py` 增加 batch recovery / preservation。

### 17.4 observer/harness patch 不能用普通 child eval

如果 candidate 修改的是 observer / loop / evidence infrastructure，它不能用普通 DataAgent child eval 证明自己。

已增加 observer-infrastructure child eval 路由，用 patched child workspace 的 harness 做 smoke。

### 17.5 helper 逻辑错 vs helper 没接上分不清

以前常见：

```text
meta-agent 生成了 helper
但 child 没改善
不知道是 helper 逻辑错，还是 helper 没注册/没暴露/没调用/结果没进入答案
```

现在 evidence sufficiency 里有：

```text
runtime_helper_tool_list_or_call_trace
```

当 observer 认为 helper 相关但没有 helper runtime evidence，会提示先修 evidence pipeline。

## 18. 建议下一阶段实验

建议做 matched-budget ablation：

```text
A. score-only
   meta-agent 只看 pass/fail、precision、recall、f1、missing/extra。

B. full-log direct
   meta-agent 直接看 full_execution_trace / llm_calls / tool_calls。

C. observer feedback
   meta-agent 看 observer 生成的 compact fine-grained feedback。
```

控制变量：

```text
同样 query set
同样 parent starting point
同样 meta-agent model
同样 DataAgent model
同样最大 iteration
同样 LLM-call/token budget
```

评价指标：

```text
最终 pass rate / F1
达到 near-miss 或 pass 所需轮数
meta-agent prompt token 数
无效 candidate 比例
patch 是否可应用
是否生成 reusable helper / workflow improvement
跨 query 泛化
archive parent selection 是否更稳定
```

## 19. 新对话启动建议

在新对话中可以这样开场：

```text
请先阅读 docs/cross_thread_meta_harness_handoff_zh.md 和 AGENTS.md。
我们现在要在本地执行 Meta-Harness 相关对照实验：
比较 score-only、full-log direct、observer-generated fine-grained feedback
三种 feedback interface 对 DAB DataAgent harness evolution 的影响。
请先检查当前工作区状态、确认主入口和现有 artifacts，然后给出最小可运行实验计划。
```

如果要直接跑本地实验，先确认：

```text
Docker Desktop 是否启动
Postgres container 是否可用
DASHSCOPE_API_KEY 是否在当前 WSL shell 可见
代理是否可用
C 盘/WSL 空间是否足够
```

不要一上来下载完整 DAB 或拉 MongoDB 镜像。当前更稳的策略是：

```text
先用 PATENTS/query1 + stockindex/query1 做小范围 multi-query。
```

## 20. 最后一句话

当前项目已经有一条完整故事线：

```text
DAB DataAgent 原始执行日志
  -> full trace
  -> LLM observer 生成细粒度反馈
  -> deterministic sufficiency 判断证据是否足够
  -> meta-agent 根据反馈演进 DataAgent / harness / observer pipeline
  -> child eval
  -> archive parent selection
```

下一步最值得推进的是：

```text
把它和 Meta-Harness 放在同一实验框架下，
证明 observer-mediated compact fine-grained feedback
相对于 score-only 和 full-log direct
能在更低 context 成本下更有效地驱动 harness evolution。
```

