#!/usr/bin/env python3
"""Fixed wrapper for structured_patch_spec_v4.

This preserves the original v4 artifact and only overrides the deterministic
errors-initialization edit order. The initial v4 executor inserted the new
initialization and then removed the first duplicate block, which deleted its own
fresh insertion. This wrapper removes the old block first, then inserts the
top-of-function initialization.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


BASE_PATH = Path(__file__).with_name("structured_patch_spec_v4.py")
SPEC = importlib.util.spec_from_file_location("structured_patch_spec_v4_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"failed to load {BASE_PATH}")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)


def move_errors_init_to_function_top(path: Path, anchor: str) -> None:
    text = path.read_text(encoding="utf-8")
    if anchor not in text:
        raise ValueError("anchor not found for move_errors_init_to_function_top")

    duplicate = (
        "\n"
        + "    errors: list[dict[str, Any]] = []\n"
        + "    if stage_trace_info.get(\"error\"):\n"
        + "        return errors\n"
    )
    if duplicate not in text:
        raise ValueError("later duplicate errors initialization block not found")
    text = text.replace(duplicate, "\n", 1)

    top_pattern = (
        anchor
        + "\n"
        + "    # Detect zero-parsed-patents signal from patent_aggregation_summary event\n"
    )
    if top_pattern not in text:
        raise ValueError("expected comment after extract_patents_trace_errors anchor not found")
    text = text.replace(
        top_pattern,
        anchor
        + "\n"
        + "    errors: list[dict[str, Any]] = []\n"
        + "    if stage_trace_info.get(\"error\"):\n"
        + "        return errors\n"
        + "\n"
        + "    # Detect zero-parsed-patents signal from patent_aggregation_summary event\n",
        1,
    )
    path.write_text(text, encoding="utf-8")


base.move_errors_init_to_function_top = move_errors_init_to_function_top


if __name__ == "__main__":
    raise SystemExit(base.main())

