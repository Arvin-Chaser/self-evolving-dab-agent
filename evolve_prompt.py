import argparse
import json
from pathlib import Path


EVOLUTION_RULES = {
    "projection_error": """
# Added rule for projection_error
8. Do not use SELECT * unless the question explicitly asks for all columns.
9. When the question asks to list employees, projects, or departments, return only the requested column, such as name, project_name, or department_name.
10. Match the output granularity of the question. If the question asks for names, return names only.
""",

    "filter_or_join_error": """
# Added rule for filter_or_join_error
8. Carefully identify the required filtering condition before writing SQL.
9. Use JOIN only when columns from multiple tables are needed.
10. Make sure the WHERE clause matches the natural language condition exactly.
""",

    "schema_grounding_error": """
# Added rule for schema_grounding_error
8. Only use tables and columns that appear in the provided schema.
9. Before writing SQL, internally check whether every table and column exists in the schema.
""",

    "sql_syntax_error": """
# Added rule for sql_syntax_error
8. The SQL must be valid SQLite syntax.
9. Avoid unsupported SQL features.
10. Return exactly one executable SQL query.
""",

    "result_mismatch": """
# Added rule for result_mismatch
8. Carefully check that the selected columns, filters, joins, grouping, and aggregation match the question exactly.
"""
}


def evolve_prompt(parent_prompt_path: Path, error_summary_path: Path, output_prompt_path: Path):
    if not parent_prompt_path.exists():
        raise FileNotFoundError(f"Parent prompt not found: {parent_prompt_path}")

    if not error_summary_path.exists():
        raise FileNotFoundError(f"Error summary not found: {error_summary_path}")

    parent_prompt = parent_prompt_path.read_text(encoding="utf-8")

    with open(error_summary_path, "r", encoding="utf-8") as f:
        error_summary = json.load(f)

    error_distribution = error_summary.get("error_distribution", {})

    new_rules = []

    for error_type, count in error_distribution.items():
        if count <= 0:
            continue

        if error_type in EVOLUTION_RULES:
            new_rules.append(
                f"\n# Evolution signal: {error_type}, count = {count}\n"
            )
            new_rules.append(EVOLUTION_RULES[error_type])

    if not new_rules:
        new_rules.append("""
# General improvement rule
8. Carefully check that the selected columns, filters, joins, grouping, and aggregation match the question exactly.
""")

    evolved_prompt = parent_prompt.rstrip()
    evolved_prompt += "\n\n"
    evolved_prompt += "# Automatically added evolution rules\n"
    evolved_prompt += "\n".join(new_rules).strip()
    evolved_prompt += "\n"

    output_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    output_prompt_path.write_text(evolved_prompt, encoding="utf-8")

    metadata = {
        "parent_prompt_path": str(parent_prompt_path),
        "output_prompt_path": str(output_prompt_path),
        "source_error_summary": str(error_summary_path),
        "error_distribution": error_distribution,
        "modification_summary": build_modification_summary(error_distribution),
    }

    metadata_path = output_prompt_path.with_suffix(".meta.json")

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"Evolved prompt saved to: {output_prompt_path}")
    print(f"Metadata saved to: {metadata_path}")

    return metadata


def build_modification_summary(error_distribution: dict) -> str:
    if not error_distribution:
        return "No specific failure type was found. Added a general exact-match rule."

    parts = []

    for error_type, count in error_distribution.items():
        parts.append(f"{count} {error_type}")

    return "Added targeted prompt rules based on failure types: " + ", ".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parent", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)

    args = parser.parse_args()

    evolve_prompt(
        parent_prompt_path=Path(args.parent),
        error_summary_path=Path(args.summary),
        output_prompt_path=Path(args.out),
    )