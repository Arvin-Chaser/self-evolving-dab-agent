import argparse
import json
import re
from pathlib import Path


CONFIDENCE_SCORE = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}


SIGNAL_CATALOG = {
    "missing_required_metadata_source": {
        "signal_id": "missing_required_metadata_source",
        "generality": 0.9,
        "repair_guidance": 0.9,
        "case_specificity": 0.2,
        "suggested_repair": "metadata_grounding_prompt_evolution",
    },
    "metadata_source_format_not_understood": {
        "signal_id": "metadata_source_format_not_understood",
        "generality": 0.9,
        "repair_guidance": 1.0,
        "case_specificity": 0.3,
        "suggested_repair": "environment_introspection_or_metadata_preview",
    },
    "level_inferred_from_surface_pattern": {
        "signal_id": "level_inferred_from_surface_pattern",
        "generality": 0.85,
        "repair_guidance": 0.9,
        "case_specificity": 0.25,
        "suggested_repair": "metadata_grounded_transformation_rule",
    },
    "output_cardinality_explosion": {
        "signal_id": "output_cardinality_explosion",
        "generality": 0.8,
        "repair_guidance": 0.75,
        "case_specificity": 0.25,
        "suggested_repair": "answer_set_audit_or_exact_output_rule",
    },
    "generated_code_runtime_error": {
        "signal_id": "generated_code_runtime_error",
        "generality": 0.9,
        "repair_guidance": 0.7,
        "case_specificity": 0.15,
        "suggested_repair": "traceback_driven_code_generation_rule",
    },
    "stage_trace_missing": {
        "signal_id": "stage_trace_missing",
        "generality": 0.9,
        "repair_guidance": 0.8,
        "case_specificity": 0.1,
        "suggested_repair": "trace_protocol_prompt_evolution",
    },
    "empty_final_answer": {
        "signal_id": "empty_final_answer",
        "generality": 0.75,
        "repair_guidance": 0.55,
        "case_specificity": 0.2,
        "suggested_repair": "inspect_upstream_stage_or_final_answer_audit",
    },
    "output_set_mismatch": {
        "signal_id": "output_set_mismatch",
        "generality": 0.75,
        "repair_guidance": 0.65,
        "case_specificity": 0.25,
        "suggested_repair": "final_answer_exactness_rule",
    },
}


def infer_signal_id(err: dict, validation_reason: str) -> str:
    text = json.dumps(err, ensure_ascii=False).lower()
    reason = validation_reason.lower()

    if "missing_required_metadata_source" in text:
        return "missing_required_metadata_source"

    if "metadata" in text and (
        "could not parse" in text
        or "not understood" in text
        or "no insert" in text
        or "no cpc mapping" in text
        or "no explicit level" in text
    ):
        return "metadata_source_format_not_understood"

    if (
        "level_inferred_from_string_shape" in text
        or "slash" in text
        or "string shape" in text
        or "surface pattern" in text
    ):
        return "level_inferred_from_surface_pattern"

    if "output_cardinality_explosion" in text or "over_broad" in text:
        return "output_cardinality_explosion"

    if "stage_trace_missing" in text:
        return "stage_trace_missing"

    if "agent_code_execution_error" in text or "nameerror" in reason or "indexerror" in reason:
        return "generated_code_runtime_error"

    if "output_set_mismatch" in text:
        return "output_set_mismatch"

    if "missing_final_answer_file_or_empty_answer" in reason or "empty answer" in reason:
        return "empty_final_answer"

    return "unknown_signal"


def score_signal(signal: dict) -> float:
    confidence = CONFIDENCE_SCORE.get(signal.get("confidence", "medium"), 0.7)
    recurrence = signal.get("recurrence", 0.5)

    return (
        signal["generality"]
        + signal["repair_guidance"]
        + confidence
        + recurrence
        - signal["case_specificity"]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    summary_path = Path(args.summary)
    out_path = Path(args.out)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    validation_reason = summary.get("validation_reason", "")
    localized_errors = summary.get("localized_errors", [])

    candidates = []

    for err in localized_errors:
        signal_id = infer_signal_id(err, validation_reason)

        if signal_id == "unknown_signal":
            continue

        base = SIGNAL_CATALOG[signal_id].copy()

        candidate = {
            **base,
            "stage": err.get("stage"),
            "source_error_type": err.get("type"),
            "source_error_subtype": err.get("subtype"),
            "confidence": err.get("confidence", "medium"),
            "evidence": err.get("evidence", ""),
            "target_modules": err.get("target_modules", []),
            "recurrence": 0.5,
        }

        candidate["score"] = round(score_signal(candidate), 4)
        candidates.append(candidate)

    # If analyzer did not localize anything, fall back to validation_reason.
    if not candidates:
        signal_id = infer_signal_id({}, validation_reason)

        if signal_id != "unknown_signal":
            base = SIGNAL_CATALOG[signal_id].copy()
            candidate = {
                **base,
                "stage": "unknown_or_upstream",
                "source_error_type": "validation_reason_only",
                "source_error_subtype": None,
                "confidence": "medium",
                "evidence": validation_reason,
                "target_modules": [],
                "recurrence": 0.5,
            }
            candidate["score"] = round(score_signal(candidate), 4)
            candidates.append(candidate)

    if not candidates:
        raise RuntimeError("No candidate signal extracted.")

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    primary = candidates[0]

    signal_focused_summary = {
        "mode": "signal_focused_error_summary",
        "source_summary_path": str(summary_path),
        "run_dir": summary.get("run_dir"),
        "passed": summary.get("passed"),
        "question": summary.get("question"),
        "validation_reason": validation_reason,

        "primary_signal": primary,
        "candidate_signals": candidates,

        "selected_repair_action": primary["suggested_repair"],
        "selection_reason": (
            "Selected the highest-scoring signal to support focused repair and "
            "credit assignment. Other signals are kept as candidates but not used "
            "as primary evolution targets in this iteration."
        ),

        "stage_distribution": {
            primary["stage"]: 1
        },
        "error_distribution": {
            f"{primary['stage']}.{primary['signal_id']}": 1
        },
        "localized_errors": [
            {
                "stage": primary["stage"],
                "type": primary["signal_id"],
                "subtype": primary.get("source_error_subtype"),
                "confidence": primary["confidence"],
                "evidence": primary["evidence"],
                "target_modules": primary.get("target_modules", []),
                "suggested_repair": primary["suggested_repair"],
            }
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(signal_focused_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(signal_focused_summary, indent=2, ensure_ascii=False))
    print(f"\nSaved signal-focused summary to: {out_path}")


if __name__ == "__main__":
    main()