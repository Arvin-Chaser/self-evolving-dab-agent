#!/usr/bin/env python3
"""Extract the primary stage-level failure signal from DAB agent analysis."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


STAGE_KEYS = ("stage", "stage_name", "failed_stage", "failure_stage", "phase", "step")
MESSAGE_KEYS = ("observation", "failure", "error", "message", "reason", "summary", "stderr", "traceback")
SUCCESS_KEYS = ("success", "passed", "ok", "is_success")


def load_jsonish(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"message": line})
        return rows
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        return [{"message": text}]


def iter_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        records.append(value)
        for child in value.values():
            records.extend(iter_records(child))
    elif isinstance(value, list):
        for item in value:
            records.extend(iter_records(item))
    return records


def first_text(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        text = str(value).strip()
        if text:
            return text
    return ""


def looks_failed(record: dict[str, Any]) -> bool:
    for key in SUCCESS_KEYS:
        if key in record:
            return not bool(record[key])
    status = str(record.get("status", record.get("result", ""))).lower()
    if status in {"failed", "failure", "error", "timeout", "exception"}:
        return True
    return any(record.get(key) for key in ("error", "exception", "traceback", "stderr"))


def signal_from_error_summary(summary_path: Path) -> dict[str, Any] | None:
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    stage_distribution = data.get("stage_distribution") or {}
    localized_errors = data.get("localized_errors") or []
    if not stage_distribution and not localized_errors:
        return None
    selected_stage = "unknown"
    if stage_distribution:
        selected_stage = max(stage_distribution.items(), key=lambda item: item[1])[0]
    selected_error = next(
        (error for error in localized_errors if str(error.get("stage", "unknown")) == selected_stage),
        localized_errors[0] if localized_errors else {},
    )
    selected_signal = (
        selected_error.get("message")
        or selected_error.get("evidence")
        or selected_error.get("summary")
        or selected_error.get("reason")
        or selected_error.get("error")
        or selected_error.get("validation_reason")
        or selected_error.get("subtype")
        or selected_error.get("type")
        or f"Stage {selected_stage} has the highest failure count."
    )
    return {
        "stage": selected_stage,
        "message": str(selected_signal),
        "selected_stage": selected_stage,
        "selected_signal": str(selected_signal),
        "stage_distribution": stage_distribution,
        "error_distribution": data.get("error_distribution") or {},
        "supporting_observations": localized_errors[:5],
        "source": str(summary_path),
    }


def extract_failure_observations(log_dir: Path) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for path in sorted(log_dir.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in {".json", ".jsonl", ".txt", ".log"}:
            continue
        for item in load_jsonish(path):
            for record in iter_records(item):
                if not looks_failed(record):
                    continue
                stage = first_text(record, STAGE_KEYS) or "unknown"
                message = first_text(record, MESSAGE_KEYS) or "Stage failed without a structured message."
                observations.append({"stage": stage, "message": message[:2000], "source": str(path)})
    return observations


def choose_primary_signal(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        return {
            "stage": "unknown",
            "message": "No structured stage-level failure was found in the run logs.",
            "selected_stage": "unknown",
            "selected_signal": "No structured stage-level failure was found in the run logs.",
            "count": 0,
            "supporting_observations": [],
        }
    stage_counts = Counter(obs["stage"] for obs in observations)
    primary_stage, count = stage_counts.most_common(1)[0]
    supporting = [obs for obs in observations if obs["stage"] == primary_stage][:5]
    return {
        "stage": primary_stage,
        "message": supporting[0]["message"],
        "selected_stage": primary_stage,
        "selected_signal": supporting[0]["message"],
        "count": count,
        "supporting_observations": supporting,
    }


def extract_primary_signal(input_path: Path) -> dict[str, Any]:
    if input_path.is_file():
        summary_signal = signal_from_error_summary(input_path)
        if summary_signal is not None:
            return summary_signal
        observations = []
        for item in load_jsonish(input_path):
            observations.extend(record for record in iter_records(item) if looks_failed(record))
    else:
        observations = extract_failure_observations(input_path)
    signal = choose_primary_signal(observations)
    signal["total_observations"] = len(observations)
    return signal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path)
    parser.add_argument("--error-summary", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    input_path = args.error_summary or args.log_dir
    if input_path is None:
        raise SystemExit("Either --error-summary or --log-dir is required.")
    signal = extract_primary_signal(input_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(signal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(signal, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
