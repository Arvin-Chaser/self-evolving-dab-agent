# Qwen Meta-Agent API Setup

This project can use separate LLM backends for the data-agent and the
meta-agent.

中文说明：本项目现在支持 data-agent 和 meta-agent 使用不同的模型接口。建议
data-agent 先继续使用本地 `4141`，meta-agent 使用更稳定的 Qwen/百炼 API。

## Environment Variables

Put secrets in `.env`. Do not commit real API keys.

```bash
# Data-agent: keep using the local OpenAI-compatible Copilot endpoint.
DATA_AGENT_BASE_URL=http://localhost:4141/v1
DATA_AGENT_API_KEY=dummy
DATA_AGENT_MODEL=gpt-5-mini

# Meta-agent: use Alibaba Cloud DashScope / Model Studio.
META_AGENT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
META_AGENT_API_KEY=sk-your-qwen-or-dashscope-key
META_AGENT_MODEL=qwen-plus
META_AGENT_TIMEOUT_SEC=120
META_AGENT_MAX_TOKENS=4096
```

You can also use DashScope-compatible names:

```bash
DASHSCOPE_API_KEY=sk-your-qwen-or-dashscope-key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

`META_AGENT_*` takes priority over `DASHSCOPE_*`.

## Smoke Test

After editing `.env`, run:

```bash
.venv/bin/python - <<'PY'
from llm_client import call_meta_llm, describe_llm_config
print(describe_llm_config()["meta"])
print(call_meta_llm("Say exactly OK."))
PY
```

Expected output contains `OK`.

## Generate A Meta-Agent Candidate

```bash
.venv/bin/python experiments/run_meta_agent_loop.py \
  --parent-run-dir <PARENT_RUN_DIR> \
  --loop-id iter002_qwen_meta \
  --child-candidate-id iter_002_qwen_child \
  --auto-meta-agent
```

This writes:

- `candidates/dab/iter_002_qwen_child/meta_agent_prompt.txt`
- `candidates/dab/iter_002_qwen_child/meta_agent_raw_output.txt`
- `candidates/dab/iter_002_qwen_child/proposal.json`
- `candidates/dab/iter_002_qwen_child/change_summary.md`
- `candidates/dab/iter_002_qwen_child/patch.diff`

## Apply The Candidate Patch

Inspect the patch first, then run:

```bash
.venv/bin/python experiments/apply_candidate_patch.py \
  --candidate-dir candidates/dab/iter_002_qwen_child
```

中文说明：`apply_candidate_patch.py` 会检查 patch 是否只修改允许演进的文件范围，
并运行 `git apply --check`。通过后才会真正应用。

## WSL Proxy Note for DashScope / Qwen

If `curl.exe` on Windows only works with the explicit proxy and WSL reports
`APIConnectionError`, set the Windows proxy explicitly inside WSL before running
preflight or evolution loops. Do not rely on the TUN/fake-ip `198.18.x.x` route.

```bash
source ~/.bashrc >/dev/null 2>&1 || true
export http_proxy="http://172.17.240.1:17891"
export https_proxy="http://172.17.240.1:17891"
export HTTP_PROXY="http://172.17.240.1:17891"
export HTTPS_PROXY="http://172.17.240.1:17891"
export all_proxy="http://172.17.240.1:17891"
export ALL_PROXY="http://172.17.240.1:17891"
export no_proxy="localhost,127.0.0.1,::1"
export NO_PROXY="localhost,127.0.0.1,::1"
```

Then run the current DataAgent LLM preflight:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import tempfile, json
from experiments.run_meta_agent_evolution_loop import run_dab_tool_agent_llm_preflight
p = Path(tempfile.mkdtemp(prefix="manual_llm_preflight_proxy."))
print(json.dumps(run_dab_tool_agent_llm_preflight(p, "manual_proxy"), indent=2, ensure_ascii=False))
print(p)
PY
```

