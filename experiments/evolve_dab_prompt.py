#!/usr/bin/env python3
"""Evolve a DAB code-agent prompt from one primary failure signal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EVOLUTION_HEADER = """

## Targeted Evolution Note

The previous run exposed the following primary stage-level failure signal:

- Stage: {stage}
- Observation: {message}

When handling this stage, explicitly verify assumptions, preserve intermediate
evidence in the stage trace, and prefer the smallest corrective action that can
be checked by the generated code before finalizing the answer.
""".lstrip()


def load_signal(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def deterministic_evolution(parent_prompt: str, signal: dict[str, Any]) -> str:
    stage = str(signal.get("stage") or signal.get("selected_stage") or "unknown")
    message = str(signal.get("message") or signal.get("selected_signal") or "No message was provided.")
    note = EVOLUTION_HEADER.format(stage=stage, message=message)
    return parent_prompt.rstrip() + "\n\n" + note


def llm_evolution(parent_prompt: str, signal: dict[str, Any]) -> str:
    from llm_client import call_llm

    instruction = {
        "task": "Revise the DAB code-agent prompt with a minimal targeted change.",
        "constraints": [
            "Keep the existing prompt structure where possible.",
            "Address the primary stage-level failure signal.",
            "Return only the revised prompt text.",
        ],
        "primary_signal": signal,
        "parent_prompt": parent_prompt,
    }
    response = call_llm(json.dumps(instruction, ensure_ascii=False, indent=2))
    text = str(response).strip()
    return text or deterministic_evolution(parent_prompt, signal)


def evolve_prompt(
    parent_prompt_path: Path,
    signal_path: Path,
    output_path: Path,
    use_llm_evolver: bool = False,
) -> dict[str, Any]:
    parent_prompt = parent_prompt_path.read_text(encoding="utf-8")
    signal = load_signal(signal_path)
    child_prompt = llm_evolution(parent_prompt, signal) if use_llm_evolver else deterministic_evolution(parent_prompt, signal)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(child_prompt.rstrip() + "\n", encoding="utf-8")
    return {
        "parent_prompt": str(parent_prompt_path),
        "child_prompt": str(output_path),
        "signal": signal,
        "use_llm_evolver": use_llm_evolver,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-prompt", required=True, type=Path)
    parser.add_argument("--signal", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--use-llm-evolver", action="store_true")
    args = parser.parse_args()

    summary = evolve_prompt(
        args.parent_prompt,
        args.signal,
        args.output,
        use_llm_evolver=args.use_llm_evolver,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
