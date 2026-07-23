#!/usr/bin/env python3
"""Extract the primary component/runtime feedback signal from DAB agent analysis."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from adapters.feedback.common_trace_checks import normalize_component


COMPONENT_KEYS = ("component", "stage", "stage_name", "failed_stage", "failure_stage", "phase", "step")
MESSAGE_KEYS = ("observation", "failure", "error", "message", "reason", "summary", "stderr", "traceback")
SUCCESS_KEYS = ("success", "passed", "ok", "is_success")

COMPONENT_ROOT_CAUSE_WEIGHT = {
    "task_understanding": 1.10,
    "schema_grounding": 1.35,
    "planning_decomposition": 1.20,
    "tool_dependency_policy": 0.95,
    "code_generation": 1.15,
    "runtime_execution": 1.00,
    "transformation_calculation": 1.25,
    "granularity_mapping": 1.40,
    "answer_synthesis": 0.70,
    "cpc_level5_fallback": 1.20,
    "unknown_component": 0.30,
}

CONFIDENCE_WEIGHT = {
    "high": 1.00,
    "medium": 0.60,
    "low": 0.25,
}


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


def first_signal_text(error: dict[str, Any], selected_component: str) -> str:
    selected_signal = (
        error.get("message")
        or error.get("evidence")
        or error.get("summary")
        or error.get("reason")
        or error.get("error")
        or error.get("validation_reason")
        or error.get("subtype")
        or error.get("type")
        or f"Component/runtime signal {selected_component} has the highest scored failure signal."
    )
    return str(selected_signal)


def component_for_error(error: dict[str, Any]) -> str:
    return normalize_component(
        error.get("component")
        or error.get("stage")
        or error.get("stage_name")
        or error.get("failed_stage")
        or error.get("failure_stage")
        or error.get("phase")
        or error.get("step"),
        fallback="unknown_component",
    )


def normalize_error(error: dict[str, Any]) -> dict[str, Any]:
    item = dict(error)
    component = component_for_error(item)
    item["component"] = component
    # Backward-compatible alias: values are component/runtime labels.
    item["stage"] = component
    return item


def normalize_count_map(raw: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for key, value in (raw or {}).items():
        counts[normalize_component(key, fallback="unknown_component")] += value
    return dict(counts)


def normalize_error_distribution(raw: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for key, value in (raw or {}).items():
        text = str(key)
        if "." in text:
            component, err_type = text.split(".", 1)
            normalized_key = f"{normalize_component(component, fallback='unknown_component')}.{err_type}"
        else:
            normalized_key = text
        counts[normalized_key] += value
    return dict(counts)


def repairability_score(error: dict[str, Any]) -> float:
    text = json.dumps(error, ensure_ascii=False, sort_keys=True).lower()
    score = 0.0
    if "metadata" in text or "definition" in text or "schema" in text:
        score += 0.75
    if "granularity" in text or "level" in text or "cardinality" in text:
        score += 0.85
    if "over_broad" in text or "output_cardinality_explosion" in text:
        score += 0.75
    if "execution" in text or "runtime" in text or "timeout" in text:
        score += 0.35
    if "answer_set_quality_check" in text:
        score -= 0.35
    if "output_set_mismatch" in text:
        score -= 0.15
    return score


def count_info_from_error(error: dict[str, Any], strict_info: dict[str, Any]) -> dict[str, int | None]:
    info = {
        "expected_unique": strict_info.get("expected_unique"),
        "got_unique": strict_info.get("got_unique"),
        "missing_count": strict_info.get("missing_count"),
        "extra_count": strict_info.get("extra_count"),
    }
    if info["expected_unique"] is not None and info["got_unique"] is not None:
        return info

    text = " ".join(
        str(error.get(key) or "")
        for key in ("evidence", "message", "validation_reason", "summary", "error")
    )
    m = re.search(r"expected\s+(\d+)\s+unique.*?got\s+(\d+)\s+unique", text, re.I | re.S)
    if m:
        info["expected_unique"] = int(m.group(1))
        info["got_unique"] = int(m.group(2))
    m = re.search(r"Missing .*?\((\d+)\)", text, re.I)
    if m:
        info["missing_count"] = int(m.group(1))
    m = re.search(r"Extra .*?\((\d+)\)", text, re.I)
    if m:
        info["extra_count"] = int(m.group(1))
    return info


def severity_score(error: dict[str, Any], strict_info: dict[str, Any]) -> float:
    component = component_for_error(error)
    err_type = str(error.get("type") or "")
    count_info = count_info_from_error(error, strict_info)
    expected = count_info.get("expected_unique")
    got = count_info.get("got_unique")
    missing_count = count_info.get("missing_count") or 0
    extra_count = count_info.get("extra_count") or 0

    score = 0.0
    if expected and got and got > expected * 2:
        if component in {"granularity_mapping", "transformation_calculation", "cpc_level5_fallback"}:
            score += 1.60
        elif component == "answer_synthesis":
            score += 0.45
    if missing_count and extra_count:
        score += 0.35
    if "stage_reported_failure" in err_type:
        score += 0.65
    if "agent_code_execution_error" in err_type:
        score += 0.55
    return score


def downstream_symptom_penalty(error: dict[str, Any], strict_info: dict[str, Any]) -> float:
    component = component_for_error(error)
    err_type = str(error.get("type") or "")
    count_info = count_info_from_error(error, strict_info)
    expected = count_info.get("expected_unique")
    got = count_info.get("got_unique")

    penalty = 0.0
    if component == "answer_synthesis":
        penalty += 0.60
        if err_type in {"answer_set_quality_check", "output_set_mismatch"}:
            penalty += 0.75
        if expected and got and got > expected * 2:
            penalty += 0.75
    return penalty


def false_positive_penalty(error: dict[str, Any]) -> float:
    component = component_for_error(error)
    err_type = str(error.get("type") or "")
    evidence = str(error.get("evidence") or "").lower()
    if component == "tool_dependency_policy" and err_type == "evaluation_leakage":
        if "appears to reference" in evidence:
            return 1.15
    return 0.0


def score_error_signal(
    error: dict[str, Any],
    component_distribution: dict[str, Any],
    error_distribution: dict[str, Any],
    strict_info: dict[str, Any],
) -> dict[str, Any]:
    error = normalize_error(error)
    component = str(error.get("component") or "unknown_component")
    err_type = str(error.get("type") or "unknown")
    confidence = str(error.get("confidence") or "").lower()
    error_key = f"{component}.{err_type}"

    component_count = float(component_distribution.get(component) or 0)
    error_count = float(error_distribution.get(error_key) or 0)
    recurrence = component_count + (0.50 * error_count)
    root_cause = COMPONENT_ROOT_CAUSE_WEIGHT.get(component, COMPONENT_ROOT_CAUSE_WEIGHT["unknown_component"])
    confidence_part = CONFIDENCE_WEIGHT.get(confidence, 0.40)
    repairability = repairability_score(error)
    severity = severity_score(error, strict_info)
    downstream_penalty = downstream_symptom_penalty(error, strict_info)
    fp_penalty = false_positive_penalty(error)

    score = recurrence + root_cause + confidence_part + repairability + severity - downstream_penalty - fp_penalty
    return {
        "component": component,
        "stage": component,
        "type": err_type,
        "subtype": error.get("subtype"),
        "confidence": error.get("confidence"),
        "score": round(score, 4),
        "components": {
            "recurrence": round(recurrence, 4),
            "root_cause_weight": root_cause,
            "confidence": confidence_part,
            "repairability": round(repairability, 4),
            "severity": round(severity, 4),
            "downstream_symptom_penalty": round(downstream_penalty, 4),
            "false_positive_penalty": round(fp_penalty, 4),
        },
        "message": first_signal_text(error, component),
        "source_error": error,
    }


def rank_error_signals(data: dict[str, Any]) -> list[dict[str, Any]]:
    component_distribution = normalize_count_map(data.get("component_distribution") or data.get("stage_distribution") or {})
    error_distribution = normalize_error_distribution(data.get("error_distribution") or {})
    strict_info = data.get("strict_info") or {}
    localized_errors = [normalize_error(error) for error in data.get("localized_errors") or []]

    if not localized_errors and component_distribution:
        localized_errors = [
            {
                "component": component,
                "stage": component,
                "type": "component_frequency_only",
                "confidence": "low",
                "message": f"Component/runtime signal {component} has {count} observed failure(s), but no localized error details.",
            }
            for component, count in component_distribution.items()
        ]

    ranked = [
        score_error_signal(error, component_distribution, error_distribution, strict_info)
        for error in localized_errors
    ]
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def signal_from_error_summary(summary_path: Path) -> dict[str, Any] | None:
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    component_distribution = normalize_count_map(data.get("component_distribution") or data.get("stage_distribution") or {})
    localized_errors = [normalize_error(error) for error in data.get("localized_errors") or []]
    if not component_distribution and not localized_errors:
        return None
    ranked_signals = rank_error_signals(data)
    selected = ranked_signals[0] if ranked_signals else {
        "component": "unknown_component",
        "stage": "unknown_component",
        "message": "No scored failure signal was found.",
        "score": 0.0,
        "source_error": {},
    }
    selected_component = str(selected.get("component") or selected.get("stage") or "unknown_component")
    selected_signal = str(selected.get("message") or "")
    return {
        "component": selected_component,
        "stage": selected_component,
        "message": selected_signal,
        "selected_component": selected_component,
        "selected_stage": selected_component,
        "selected_signal": selected_signal,
        "selection_method": "scored_localized_error",
        "selected_score": selected.get("score", 0.0),
        "selected_score_components": selected.get("components", {}),
        "component_distribution": component_distribution,
        "stage_distribution": component_distribution,
        "error_distribution": normalize_error_distribution(data.get("error_distribution") or {}),
        "candidate_signals": ranked_signals[:10],
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
                component = normalize_component(first_text(record, COMPONENT_KEYS), fallback="unknown_component")
                message = first_text(record, MESSAGE_KEYS) or "Component/runtime signal failed without a structured message."
                observations.append({"component": component, "stage": component, "message": message[:2000], "source": str(path)})
    return observations


def choose_primary_signal(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        return {
            "component": "unknown_component",
            "stage": "unknown_component",
            "message": "No structured component/runtime failure was found in the run logs.",
            "selected_component": "unknown_component",
            "selected_stage": "unknown_component",
            "selected_signal": "No structured component/runtime failure was found in the run logs.",
            "count": 0,
            "supporting_observations": [],
        }
    component_counts = Counter(obs["component"] for obs in observations)
    primary_component, count = component_counts.most_common(1)[0]
    supporting = [obs for obs in observations if obs["component"] == primary_component][:5]
    return {
        "component": primary_component,
        "stage": primary_component,
        "message": supporting[0]["message"],
        "selected_component": primary_component,
        "selected_stage": primary_component,
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
