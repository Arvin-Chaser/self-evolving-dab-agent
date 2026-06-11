import argparse
import json
from collections import Counter
from pathlib import Path


STAGE_LEVEL_EVOLUTION_RULES = {
    "S1_task_understanding.intent_or_constraint_misunderstanding": """
# Rule for task understanding failures
- Before solving the task, explicitly identify the main intent, target object, constraints, and required output.
- Do not start generating an answer before restating what the query is asking for.
""",

    "S2_data_schema_grounding.schema_grounding_error": """
# Rule for data/schema grounding failures
- Before querying or reasoning, map each required variable in the question to a specific database, table, field, or file.
- Do not assume that a field exists unless it appears in the provided database description.
""",

    "S3_planning_decomposition.missing_substep": """
# Rule for planning/decomposition failures
- Break complex data-analysis tasks into explicit substeps: filtering, linking, grouping, calculation, ranking, and final output.
- Check whether any required substep is missing before producing the final answer.
""",

    "S4_tool_dependency_planning.false_dependency_error": """
# Rule for tool/dependency planning failures
- Before executing multiple queries or tool calls, determine whether each step depends on previous results or can be executed independently.
- Do not force independent subtasks into a sequential pipeline.
""",

    "S5_query_code_generation.sql_generation_error": """
# Rule for query/code generation failures
- Generate executable SQL or Python that exactly matches the planned substeps.
- Verify selected fields, filters, joins, grouping, and aggregation before execution.
""",

    "S6_execution.tool_execution_error": """
# Rule for execution failures
- Check that required files, databases, tools, and dependencies are available before attempting execution.
- If execution is impossible, state the missing dependency clearly instead of guessing the answer.
""",

    "S7_transformation_calculation.calculation_error": """
# Rule for transformation/calculation failures
- For calculation-heavy tasks, explicitly state the formula, grouping key, time field, and ranking criterion.
- Verify that the calculation uses the exact parameters specified by the question.
""",

    "S8_answer_synthesis_validation.output_completeness_error": """
# Rule for answer completeness failures
- For tasks requiring a set of results, do not output only examples or a partial list.
- The final answer must include every item satisfying the query constraints.
- Before finalizing, perform a completeness check: ask whether any required item, row, pair, code, entity, title, or year may be missing.
- If the available execution trace is insufficient to guarantee completeness, explicitly indicate that the result may be incomplete rather than presenting guesses as complete.
""",

    "S8_answer_synthesis_validation.output_format_alignment_error": """
# Rule for output format/alignment failures
- Preserve the required relationship between fields in the final answer.
- If the answer requires pairs or triples, output each pair/triple together on the same line or row.
- Do not separate related entities, codes, titles, or years into unrelated lists.
""",

    "S8_answer_synthesis_validation.validation_failure": """
# Rule for generic validation failures
- Carefully match the final answer to the validator's expected unit, completeness, and format.
- Avoid extra unrelated items and avoid partial answers.
"""
}


def collect_error_keys(error_summary: dict) -> Counter:
    """
    Collect stage-level error keys from the new error_summary format.

    Expected key format:
    S8_answer_synthesis_validation.output_completeness_error
    """

    counter = Counter()

    error_distribution = error_summary.get("error_distribution", {})

    for key, count in error_distribution.items():
        counter[key] += count

    return counter


def find_rule_for_error_key(error_key: str) -> str | None:
    """
    Find an evolution rule for a specific stage-level error key.

    If there is no exact match, fall back to broader stage-level rules.
    """

    if error_key in STAGE_LEVEL_EVOLUTION_RULES:
        return STAGE_LEVEL_EVOLUTION_RULES[error_key]

    # Fallback by stage and broad type
    if error_key.startswith("S8_answer_synthesis_validation.output_completeness_error"):
        return STAGE_LEVEL_EVOLUTION_RULES[
            "S8_answer_synthesis_validation.output_completeness_error"
        ]

    if error_key.startswith("S8_answer_synthesis_validation.output_format_alignment_error"):
        return STAGE_LEVEL_EVOLUTION_RULES[
            "S8_answer_synthesis_validation.output_format_alignment_error"
        ]

    if error_key.startswith("S6_execution"):
        return STAGE_LEVEL_EVOLUTION_RULES[
            "S6_execution.tool_execution_error"
        ]

    return None


def build_modification_summary(error_counter: Counter) -> str:
    if not error_counter:
        return "No failure detected. No targeted evolution rule was added."

    parts = []

    for error_key, count in error_counter.items():
        parts.append(f"{count} {error_key}")

    return "Added generic stage-level prompt rules based on: " + ", ".join(parts)


def evolve_dab_prompt(parent_prompt_path: Path, error_summary_path: Path, output_prompt_path: Path):
    if not parent_prompt_path.exists():
        raise FileNotFoundError(f"Parent prompt not found: {parent_prompt_path}")

    if not error_summary_path.exists():
        raise FileNotFoundError(f"Error summary not found: {error_summary_path}")

    parent_prompt = parent_prompt_path.read_text(encoding="utf-8")

    with open(error_summary_path, "r", encoding="utf-8") as f:
        error_summary = json.load(f)

    error_counter = collect_error_keys(error_summary)

    added_rules = []

    for error_key, count in error_counter.items():
        if count <= 0:
            continue

        rule = find_rule_for_error_key(error_key)

        if rule:
            added_rules.append(
                f"\n# Evolution signal: {error_key}, count = {count}\n"
            )
            added_rules.append(rule)

    if not added_rules:
        added_rules.append("""
# General DAB improvement rule
- Carefully follow the query constraints, database descriptions, and required output format.
- Do not provide partial answers when the task asks for all qualifying results.
- If the task requires computation, avoid guessing and identify the required execution steps.
""")

    evolved_prompt = parent_prompt.rstrip()
    evolved_prompt += "\n\n# Automatically added generic stage-level evolution rules\n"
    evolved_prompt += "\n".join(added_rules).strip()
    evolved_prompt += "\n"

    output_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    output_prompt_path.write_text(evolved_prompt, encoding="utf-8")

    metadata = {
        "parent_prompt_path": str(parent_prompt_path),
        "output_prompt_path": str(output_prompt_path),
        "source_error_summary": str(error_summary_path),
        "stage_level_error_distribution": dict(error_counter),
        "modification_summary": build_modification_summary(error_counter),
    }

    metadata_path = output_prompt_path.with_suffix(".meta.json")

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Evolved DAB prompt saved to: {output_prompt_path}")
    print(f"Metadata saved to: {metadata_path}")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))

    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parent", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)

    args = parser.parse_args()

    evolve_dab_prompt(
        parent_prompt_path=Path(args.parent),
        error_summary_path=Path(args.summary),
        output_prompt_path=Path(args.out),
    )
