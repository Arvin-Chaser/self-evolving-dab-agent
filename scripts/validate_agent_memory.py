"""Validate the bounded, tiered cross-session research-memory layout."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "docs" / "agent_memory"
INDEX = MEMORY / "MEMORY_INDEX.json"
BRIEF = MEMORY / "CURRENT_STATE_BRIEF.md"
AGENTS = ROOT / "AGENTS.md"

MAX_BRIEF_BYTES = 8_192
MAX_INDEX_BYTES = 8_192
MAX_AGENTS_BYTES = 12_288

COLD_NAMES = {
    "CONTEXT_COST_AUDIT_20261021.md",
    "CURRENT_STATE.md",
    "HANDOFF.md",
    "PROJECT_OVERVIEW.md",
    "DECISIONS.md",
    "EXPERIMENTS.md",
    "ENVIRONMENT.md",
    "HISTORY_INDEX.md",
}


def require_size(path: Path, maximum: int) -> None:
    size = path.stat().st_size
    if size > maximum:
        raise SystemExit(f"{path.relative_to(ROOT)} is {size} bytes; limit is {maximum}")


def main() -> None:
    governed = (
        AGENTS,
        BRIEF,
        INDEX,
        MEMORY / "MEMORY_POLICY.md",
        MEMORY / "CONTEXT_COST_AUDIT_20261021.md",
    )
    for path in governed:
        if not path.is_file():
            raise SystemExit(f"missing required memory file: {path.relative_to(ROOT)}")
        content = path.read_bytes()
        if not content.endswith(b"\n"):
            raise SystemExit(f"missing final newline: {path.relative_to(ROOT)}")
        for number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
            if line.rstrip(" \t") != line:
                raise SystemExit(
                    f"trailing whitespace: {path.relative_to(ROOT)}:{number}"
                )

    require_size(AGENTS, MAX_AGENTS_BYTES)
    require_size(BRIEF, MAX_BRIEF_BYTES)
    require_size(INDEX, MAX_INDEX_BYTES)

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    required = data.get("startup", {}).get("required")
    expected = ["docs/agent_memory/CURRENT_STATE_BRIEF.md"]
    if required != expected:
        raise SystemExit(f"startup.required must be exactly {expected!r}")

    if not data.get("startup", {}).get("full_cold_preload_forbidden"):
        raise SystemExit("startup must forbid full cold-memory preload")

    cold_paths = {Path(value).name for value in data.get("cold_records", [])}
    missing_cold = sorted(COLD_NAMES - cold_paths)
    if missing_cold:
        raise SystemExit(f"cold_records missing: {', '.join(missing_cold)}")

    for value in data.get("cold_records", []):
        path = ROOT / value
        if not path.is_file():
            raise SystemExit(f"cold_records points to missing file: {value}")

    for route in data.get("routes", []):
        for value in route.get("read", []):
            path = ROOT / value
            if not path.is_file():
                raise SystemExit(f"route points to missing file: {value}")

    print(
        "agent memory valid: "
        f"AGENTS={AGENTS.stat().st_size}B, "
        f"brief={BRIEF.stat().st_size}B, "
        f"index={INDEX.stat().st_size}B"
    )


if __name__ == "__main__":
    main()
