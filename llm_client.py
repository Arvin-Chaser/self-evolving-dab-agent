import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
BASE_URL = os.getenv("COPILOT_BASE_URL", "http://localhost:4141/v1")
API_KEY = os.getenv("COPILOT_API_KEY", "dummy")

PROMPT_PATH = Path("prompts/text2sql_prompt.txt")
SCHEMA_PATH = Path("schema.sql")

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
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


def call_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )

    return response.choices[0].message.content


def generate_sql(question: str) -> str:
    prompt = build_prompt(question)
    content = call_llm(prompt)
    return clean_sql(content)