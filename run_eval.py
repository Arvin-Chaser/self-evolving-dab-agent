import argparse

from evaluator import run_eval


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--prompt",
        required=True,
        help="Path to prompt file, e.g. prompts/text2sql_prompt_v001.txt",
    )

    parser.add_argument(
        "--version",
        required=True,
        help="Prompt version, e.g. v001",
    )

    parser.add_argument(
        "--cases",
        default=None,
        help="Optional path to eval cases jsonl file.",
    )

    args = parser.parse_args()

    run_eval(
        prompt_path=args.prompt,
        prompt_version=args.version,
        cases_path=args.cases,
    )