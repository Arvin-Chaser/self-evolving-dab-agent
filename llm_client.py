import os
import re
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DATA_AGENT_MODEL = os.getenv("DATA_AGENT_MODEL") or os.getenv("OPENAI_MODEL", "gpt-5-mini")
DATA_AGENT_BASE_URL = os.getenv("DATA_AGENT_BASE_URL") or os.getenv(
    "COPILOT_BASE_URL",
    "http://localhost:4141/v1",
)
DATA_AGENT_API_KEY = os.getenv("DATA_AGENT_API_KEY") or os.getenv("COPILOT_API_KEY", "dummy")

META_AGENT_MODEL = os.getenv("META_AGENT_MODEL") or os.getenv("QWEN_MODEL", "qwen-plus")
META_AGENT_BASE_URL = (
    os.getenv("META_AGENT_BASE_URL")
    or os.getenv("DASHSCOPE_BASE_URL")
    or "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
META_AGENT_API_KEY = (
    os.getenv("META_AGENT_API_KEY")
    or os.getenv("DASHSCOPE_API_KEY")
    or DATA_AGENT_API_KEY
)
DATA_AGENT_TIMEOUT_SEC = float(os.getenv("DATA_AGENT_TIMEOUT_SEC", "120"))
META_AGENT_TIMEOUT_SEC = float(os.getenv("META_AGENT_TIMEOUT_SEC", "120"))
DATA_AGENT_LLM_RETRIES = int(os.getenv("DATA_AGENT_LLM_RETRIES", "4"))
META_AGENT_LLM_RETRIES = int(os.getenv("META_AGENT_LLM_RETRIES", "3"))
DATA_AGENT_LLM_RETRY_SLEEP = float(os.getenv("DATA_AGENT_LLM_RETRY_SLEEP", "10"))
META_AGENT_LLM_RETRY_SLEEP = float(os.getenv("META_AGENT_LLM_RETRY_SLEEP", "10"))
OPENAI_CLIENT_MAX_RETRIES = int(os.getenv("OPENAI_CLIENT_MAX_RETRIES", "2"))
DATA_AGENT_MAX_TOKENS = os.getenv("DATA_AGENT_MAX_TOKENS")
META_AGENT_MAX_TOKENS = os.getenv("META_AGENT_MAX_TOKENS", "4096")

PROMPT_PATH = Path("prompts/text2sql_prompt.txt")
SCHEMA_PATH = Path("schema.sql")


def build_client(profile: Literal["data", "meta"] = "data") -> tuple[OpenAI, str]:
    if profile == "meta":
        return (
            OpenAI(
                api_key=META_AGENT_API_KEY,
                base_url=META_AGENT_BASE_URL,
                timeout=META_AGENT_TIMEOUT_SEC,
                max_retries=OPENAI_CLIENT_MAX_RETRIES,
            ),
            META_AGENT_MODEL,
        )

    return (
        OpenAI(
            api_key=DATA_AGENT_API_KEY,
            base_url=DATA_AGENT_BASE_URL,
            timeout=DATA_AGENT_TIMEOUT_SEC,
            max_retries=OPENAI_CLIENT_MAX_RETRIES,
        ),
        DATA_AGENT_MODEL,
    )


def build_prompt(question: str) -> str:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    template = PROMPT_PATH.read_text(encoding="utf-8")

    return template.format(
        schema=schema,
        question=question,
    )


def clean_sql(text: str) -> str:
    text = text.strip()

    text = re.sub(r"^```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^SQL:\s*", "", text, flags=re.IGNORECASE)

    return text.strip()


def call_llm(prompt: str, profile: Literal["data", "meta"] = "data") -> str:
    client, model = build_client(profile)
    max_tokens = META_AGENT_MAX_TOKENS if profile == "meta" else DATA_AGENT_MAX_TOKENS
    request = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0,
    }
    if max_tokens:
        request["max_tokens"] = int(max_tokens)

    retries = META_AGENT_LLM_RETRIES if profile == "meta" else DATA_AGENT_LLM_RETRIES
    retry_sleep = META_AGENT_LLM_RETRY_SLEEP if profile == "meta" else DATA_AGENT_LLM_RETRY_SLEEP
    last_exc: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            response = client.chat.completions.create(**request)
            return response.choices[0].message.content
        except Exception as exc:
            last_exc = exc
            if attempt >= max(1, retries):
                break
            if retry_sleep > 0:
                time.sleep(retry_sleep)
    assert last_exc is not None
    raise last_exc


def call_meta_llm(prompt: str) -> str:
    return call_llm(prompt, profile="meta")


def describe_llm_config() -> dict[str, dict[str, str]]:
    return {
        "data": {
            "model": DATA_AGENT_MODEL,
            "base_url": DATA_AGENT_BASE_URL,
            "api_key_env": "DATA_AGENT_API_KEY or COPILOT_API_KEY",
            "timeout_sec": str(DATA_AGENT_TIMEOUT_SEC),
            "max_tokens": DATA_AGENT_MAX_TOKENS or "",
            "retries": str(DATA_AGENT_LLM_RETRIES),
            "retry_sleep_sec": str(DATA_AGENT_LLM_RETRY_SLEEP),
        },
        "meta": {
            "model": META_AGENT_MODEL,
            "base_url": META_AGENT_BASE_URL,
            "api_key_env": "META_AGENT_API_KEY or DASHSCOPE_API_KEY",
            "timeout_sec": str(META_AGENT_TIMEOUT_SEC),
            "max_tokens": META_AGENT_MAX_TOKENS,
            "retries": str(META_AGENT_LLM_RETRIES),
            "retry_sleep_sec": str(META_AGENT_LLM_RETRY_SLEEP),
        },
    }


def generate_sql(question: str) -> str:
    prompt = build_prompt(question)
    content = call_llm(prompt)
    return clean_sql(content)
