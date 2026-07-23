"""Helpers for writing script-level trajectory reports.

The meta-agent uses these reports to understand how project scripts executed,
which artifacts they read, and which outputs they produced.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def path_ref(name: str, path: Path | str, role: str | None = None) -> dict[str, Any]:
    path = Path(path)
    ref: dict[str, Any] = {
        "name": name,
        "path": str(path),
        "exists": path.exists(),
    }

    if role:
        ref["role"] = role

    if path.exists() and path.is_file():
        ref["size_bytes"] = path.stat().st_size

    return ref


def write_script_run_report(
    output_dir: Path,
    script_name: str,
    script_role: str,
    started_at: str,
    status: str,
    inputs: list[dict[str, Any]] | None = None,
    operations: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    checks: list[dict[str, Any]] | None = None,
    self_feedback: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    report_stem: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = report_stem or Path(script_name).stem
    report_path = output_dir / f"script_run_report.{stem}.json"

    report: dict[str, Any] = {
        "script_name": script_name,
        "script_role": script_role,
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "status": status,
        "inputs": inputs or [],
        "operations": operations or [],
        "outputs": outputs or [],
        "checks": checks or [],
        "self_feedback": self_feedback
        or {
            "confidence": "medium",
            "uncertainties": [],
            "evolution_hints": [],
            "suggested_target_modules": [],
        },
    }

    if error:
        report["error"] = error

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return report_path, report
