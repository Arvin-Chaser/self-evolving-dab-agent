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

Your task is to improve the parent agent prompt based on structured runtime-log and component feedback.

Important principles:

1. Do NOT add ground-truth answers.
2. Do NOT add dataset-specific final answers.
3. Do NOT add rules that only memorize this one case.
4. Do NOT patch the prompt by naming specific answer codes.
5. You MAY add general rules motivated by the failure.
6. Prefer component-level, transferable improvements grounded in local execution evidence.
7. Preserve the original role of the parent prompt: generating solve.py for local data-analysis tasks.
8. The revised prompt should remain useful for other DAB data-analysis cases.
9. If a failure is tied to schema grounding, granularity mapping, runtime execution, answer synthesis,
   or runtime-observer coverage, add general instructions for that component.
10. Output only the full revised prompt. Do not include commentary outside the prompt.

Feedback schema:

- component_distribution: counts of component/runtime signals observed by the analyzer.
- error_distribution: counts of component-qualified error types.
- localized_errors: concrete evidence extracted from result.json, generated code, validator output,
  and runtime logs produced by the generated solve.py.
- runtime logs are local execution evidence, not chain-of-thought. Use them to decide which
  data-agent code behavior should become more observable or more robust.

Component examples:

- schema_grounding: required data sources, metadata files, schemas, fields, auxiliary tables, and definition files.
- planning_decomposition: executable substeps and local verification plan.
- tool_dependency_policy: allowed files, forbidden files, dependencies, and execution order.
- code_generation: generated SQL/Python/code structure and API robustness.
- runtime_execution: local execution failures, timeouts, missing outputs, and environment errors.
- transformation_calculation: joins, filters, grouping, ranking, hierarchy mapping, and calculations.
- granularity_mapping: mapping raw data values to metadata-defined levels/categories/granularity.
- answer_synthesis: final answer set, formatting, completeness, duplicates, missing items, and over-broad outputs.
- runtime_observer_policy: whether generated code logs enough local evidence for future evolution.

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
    component_distribution = error_summary.get("component_distribution") or error_summary.get("stage_distribution", {})

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
        "component_distribution": component_distribution,
        "stage_distribution": component_distribution,
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

    print("\n=== Component/runtime feedback used ===")
    print(json.dumps({
        "component_distribution": meta["component_distribution"],
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
