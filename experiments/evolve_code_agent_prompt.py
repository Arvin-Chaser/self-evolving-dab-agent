import argparse
import json
import re
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from llm_client import call_llm


META_EVOLVE_TEMPLATE = """
You are the meta-agent of a self-evolving data agent system.

Your task is to improve the parent agent prompt based on structured 8-stage error feedback.

Important principles:

1. Do NOT add ground-truth answers.
2. Do NOT add dataset-specific final answers.
3. Do NOT add rules that only memorize this one case.
4. Do NOT patch the prompt by naming specific answer codes.
5. You MAY add general rules motivated by the failure.
6. Prefer stage-level, transferable improvements.
7. Preserve the original role of the parent prompt: generating solve.py for local data-analysis tasks.
8. The revised prompt should remain useful for other DAB data-analysis cases.
9. If a failure is caused by S2, S7, or S8, add general instructions for those stages.
10. Output only the full revised prompt. Do not include commentary outside the prompt.

8-stage schema:

S1_task_understanding:
- Understand the task intent, constraints, target object, and output requirement.

S2_data_schema_grounding:
- Identify required data sources, metadata files, schemas, fields, auxiliary tables, and definition files.
- Use provided metadata or definition sources when the task involves hierarchy, level, category, mapping, code definition, title definition, or schema-specific meaning.
- Do not ignore auxiliary data sources when they are necessary to interpret the task.

S3_planning_decomposition:
- Decompose the task into executable substeps.

S4_tool_dependency_planning:
- Decide tools, dependencies, allowed files, forbidden files, and execution order.
- Do not read ground-truth files or validators from generated solve.py.

S5_query_code_generation:
- Generate correct SQL/Python/code.

S6_execution:
- Execute code/tools reliably and write required output files.

S7_transformation_calculation:
- Transform data correctly.
- Apply formulas, grouping, ranking, hierarchy mapping, granularity mapping, and filtering.
- Do not infer semantic levels or categories from superficial string shape when metadata is available.
- If the task asks for a specific level, category, or granularity, ground that concept in the provided schema or metadata source.

S8_answer_synthesis_validation:
- Produce the exact final answer set and format.
- Avoid missing, extra, duplicate, partial, or over-broad outputs.
- Before writing the final answer, perform consistency checks against the task constraints.

Parent prompt:

<<<PARENT_PROMPT
{parent_prompt}
PARENT_PROMPT>>>

Structured error summary:

<<<ERROR_SUMMARY
{error_summary}
ERROR_SUMMARY>>>

Now produce the full revised prompt.
"""


def extract_prompt(raw: str) -> str:
    text = raw.strip()

    m = re.search(r"```(?:text|markdown)?\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip() + "\n"

    return text + "\n"


def evolve(parent_path: Path, summary_path: Path, out_path: Path):
    parent_prompt = parent_path.read_text(encoding="utf-8")
    error_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    meta_prompt = META_EVOLVE_TEMPLATE.format(
        parent_prompt=parent_prompt,
        error_summary=json.dumps(error_summary, indent=2, ensure_ascii=False),
    )

    print("Calling meta-agent to evolve prompt...")

    raw_output = call_llm(meta_prompt)
    revised_prompt = extract_prompt(raw_output)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(revised_prompt, encoding="utf-8")

    meta = {
        "parent_prompt": str(parent_path),
        "error_summary": str(summary_path),
        "child_prompt": str(out_path),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage_distribution": error_summary.get("stage_distribution", {}),
        "error_distribution": error_summary.get("error_distribution", {}),
        "localized_errors": error_summary.get("localized_errors", []),
    }

    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    raw_path = out_path.with_suffix(".raw_meta_output.txt")
    raw_path.write_text(raw_output, encoding="utf-8")

    print(f"Saved child prompt to: {out_path}")
    print(f"Saved metadata to: {meta_path}")
    print(f"Saved raw meta-agent output to: {raw_path}")

    print("\n=== Stage-level feedback used ===")
    print(json.dumps({
        "stage_distribution": meta["stage_distribution"],
        "error_distribution": meta["error_distribution"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)

    args = parser.parse_args()

    evolve(
        parent_path=Path(args.parent),
        summary_path=Path(args.summary),
        out_path=Path(args.out),
    )