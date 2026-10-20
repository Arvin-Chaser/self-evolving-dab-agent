# 学校 API 工具调用兼容层 v1 / v2

最新状态（2026-10-08 上海 11:30）：v2 小规模在线工具往返已通过，53 项本地回归通过。尚未完成真实 SDK、目标评测服务器和完整 DAB 接入验证；没有替换或恢复 Gen7。

## 范围

- 上游固定 `http://10.27.130.10:32788/v1`，允许模型 ID 固定 `qwen3.8-27b`。ID 是接口返回的别名，不证明实际权重或部署后端。
- 接入点为本机 `127.0.0.1` 上的 `/v1/chat/completions`。现有 DAB 显式兼容 API 参数可接入，不需要修改封存候选、提示词、工具或验证器。
- 仅支持非流式、单候选回复、标准 function 工具协议。当前 DAB 使用非流式；流式/Responses/旧 functions 协议不在 v1 范围。
- 最多 3 个同时请求；每次只发送一次上游请求；不执行工具、不自动重试、不恢复评测、不变更学校服务。

## 转换规则

实测学校强制调用回复可能为 `content='[{"name":"add_numbers","parameters":{"a":3,"b":4}}]'`，同时 `tool_calls=null`。自动模式还会返回带 `</think>` 分隔的 `<tool_call><function=...><parameter=...>` 格式，因此单独的 JSON v1 不足以接入自动工具调用。

只有完整、无额外文字的严格 JSON 数组，且每项恰含 `name` 和 `parameters`，才能投影成标准 `tool_calls`。工具名必须在本次 advertised tools 中，参数必须通过其原有 JSON Schema。转换生成稳定 call ID，把参数序列化为 JSON 字符串，并将投影后的结束类型标为 `tool_calls`；原始 `stop` 不被隐藏，保留在来源元数据中。

拒绝未知工具、重复 JSON 键、NaN/Inf、错误/多余参数、错误的工具结果配对、重复 call ID、混合两套调用格式、截断或过滤回复、代码围栏/散文中嵌入的调用。只允许 schema 文档内部引用，不访问远程 schema。普通无标签文本答案不改写；不会猜补参数，也不会让第二个模型修复答案。

v2 必须显式选择 `--protocol v2`。它依据已实测的学校返回形状和 [Qwen 官方模板](https://huggingface.co/Qwen/Qwen3.5-27B/blob/main/chat_template.jinja) 解析完整闭合的工具标签，支持单个明确的 `</think>` 思考/答案边界（起始 `<think>` 可已在模板提示中）。思考移动至 `reasoning_content`，原文和字节仍全部保留；没有关闭思考或修改请求提示词。模式与 [vLLM 的协议解析源码](https://github.com/vllm-project/vllm/blob/main/vllm/parser/qwen3.py) 相符，但不证明学校用了 vLLM 或这份权重。

XML 参数依据工具 schema 中明确的参数类型解码：字符串只移除模板包裹的一对换行，保留空格、内部换行和 `007` 之类值；其他受支持类型只接受严格 JSON。重复/未知参数、缺失闭合标签、边界混杂、参数中的保留标签、类型未明确或引用型参数不猜测解码，直接拒绝。完整参数仍过原始 schema 校验。v1 遇到标签协议会明确拒绝，不再把未解析的工具标签当作最终答案。

请求 messages、tools、temperature、max_tokens 和工具结果原样转发。`assistant.tool_calls` 和 `role=tool` 历史只检查配对，不重写。请求 JSON 的序列化空白/键序可不同，字段语义不变。这里的格式解析不保证模型语义正确、能合理选择工具或可靠停止。

## 原始证据与安全

成功响应附 `school_tool_compat` 元数据：原始 assistant 消息、原始结束类型、请求摘要、上游原始字节 SHA256/base64、转换策略及单次请求信息。协议拒绝返回 422，并附原始回复证据；上游通信失败返回 424，避免 SDK 在模糊派发后重放。调用方仍需关闭 SDK/外层自动重试并按原流程记录证据。原始字节元数据可能包含任务数据，应遵守现有 trace 保存边界，不发送给 Meta。

只监听回环地址，需要 Bearer 认证，不打印密钥、请求、回复或上游错误正文，不自动写日志；原始证据随响应交给调用方。密钥从现有本地文件读取，不应提交至仓库。上游 URL 是学校提供的 HTTP 地址，兼容层不额外提供链路加密。上游遵循系统已配置的网络代理，但不允许 HTTP 重定向。

GET `/v1/models` 只返回本兼容层允许的模型，不是上游实时可用性检测。

## 本机启动（手动；当前未常驻运行）

在仓库根目录的 PowerShell 中，使用已经隔离安装的依赖：

```powershell
$taskPython = 'C:\Users\34934\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'C:\Users\34934\.codex\visualizations\2026\09\02\01a060f2-55f4-7c02-b876-da90418d29b9\school_tool_compat_dependencies_v1;C:\Users\34934\source\text2sql'
& $taskPython experiments/serve_school_tool_compat_v1.py --api-key-file 'C:\Users\34934\.config\dab\school_api_key.txt' --port 32789 --timeout 45 --protocol v2
```

前台运行，Ctrl+C 停止。其他环境安装 `adapters/school_tool_compat_v1.requirements.txt` 到独立环境，不必使用以上 Windows 路径。

将来接入新评测时，在另一个终端把密钥仅载入该进程环境，不打印：

```powershell
$env:DAB_TOOL_AGENT_API_KEY = (Get-Content -LiteralPath 'C:\Users\34934\.config\dab\school_api_key.txt' -Raw).Trim()
```

现有 runner 的接入参数为：

```text
--deployment-name qwen3.8-27b
--openai-compatible-base-url http://127.0.0.1:32789/v1
--openai-compatible-api-key-env DAB_TOOL_AGENT_API_KEY
--client-max-retries 0
```

这不是恢复 Gen7 的命令。切换模型须创建独立评测配置/运行，保留原 GLM 结果；不得把 Qwen 结果混入暂停的 Gen7 GLM 运行。

## 验证与剩余门槛

53 项离线/本机回环测试通过：包含严格解析、原始字节保留、错误不重试、认证、工具回传、61 条历史保留、3 并发隔离，以及新增思考/XML 的严格闭合、类型、空白保留和拒绝测试。

保留旧失败：两次合成首轮连接超时，未获模型回复；当时 GET `/models` 系统路径及直连也超时。用户随后说明为访问 Reddit 开启的 VPN 影响了内网，并恢复网络。恢复后两个模型列表检查均 HTTP 200。初始 v1 forced 已读到工具 token 并结束，但正文夹带思考导致严格答案不通过；auto 生成了 XML，v1 当时未识别，之后补了明确拒绝与 v2 解析。不会把这些旧失败改写成成功。

最新完整证据：本机代理 v2 → 真实学校模型，3 个并发会话各 2 请求，全部正常结束且准确读回只在工具结果中产生的随机 token，无重复调用，整组 4.417906 秒；额外 61 条消息历史会话 2 请求，3.939302 秒通过。8 份上游原始字节的 SHA256 全部独立校验通过，4 个会话 call ID 唯一，首轮回复不含随后才生成的 token。历史是合成用户/助手往返，不代表真实 DAB 长轨迹或复杂多工具能力。

另有初步 forced/auto v2 测试的汇总通过，但该次终端捕获截断；保留捕获限制，不将其用于 exact-byte admission。完整的 8 请求代理证据见可视化目录 `school_tool_bridge_attempt006_v2.json`，小规模报告见本活动 Gen7 目录 `school_tool_compat_v2_live_audit.json`。这些是基础设施验证，不是 Gen7 评测结果或模型质量比较。

下一步是检查实际 SDK、执行 trace 和目标评测服务器网络，以及独立的小规模 DAB 接入。当前未验证完整评测，不应直接全面替换 GLM；暂停的 Gen7 运行和其已有结果保持原样。
