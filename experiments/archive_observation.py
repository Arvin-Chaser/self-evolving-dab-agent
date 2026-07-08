"""Archive observation extraction for meta-agent evolution candidates.

This module defines a neutral observation schema for candidate archives.  It is
not a promotion selector and it does not decide a fixed failure taxonomy.  It
extracts what happened to a candidate so later meta-agents can use failed
candidates as evidence, negative examples, or self-improvement material.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

try:
    from experiments.gate_policy import summarize_gate_policy
except Exception:  # pragma: no cover
    summarize_gate_policy = None  # type: ignore[assignment]

try:
    from experiments.contract_eval import evaluate_contracts
except Exception:  # pragma: no cover
    evaluate_contracts = None  # type: ignore[assignment]
ARCHIVE_OBSERVATION_SCHEMA_VERSION = "archive_observation_v001"
PROPOSED_CONTRACTS_SCHEMA_VERSION = "proposed_contracts_v001"
PARENT_F1_TOLERANCE = 0.03


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def extract_first_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(text[start : idx + 1])
                    return value if isinstance(value, dict) else {}
                except Exception:
                    return {}
    return {}


def load_patch_spec(candidate_dir: Path) -> dict[str, Any]:
    validated = load_json(candidate_dir / "validated_patch_spec.json")
    if validated:
        return validated
    raw_path = candidate_dir / "patch_spec_raw.txt"
    if raw_path.exists():
        return extract_first_json_object(raw_path.read_text(encoding="utf-8", errors="replace"))
    return {}


def metric_delta(child: dict[str, Any], parent: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in ("precision", "recall", "f1", "jaccard"):
        child_v = to_float(child.get(key))
        parent_v = to_float(parent.get(key))
        if child_v is not None or parent_v is not None:
            delta[key] = {
                "parent": parent_v,
                "child": child_v,
                "delta": None if child_v is None or parent_v is None else round(child_v - parent_v, 6),
            }
    for key in ("expected_count", "predicted_count", "true_positive", "false_positive", "false_negative"):
        child_v = to_int(child.get(key))
        parent_v = to_int(parent.get(key))
        if child_v is not None or parent_v is not None:
            delta[key] = {
                "parent": parent_v,
                "child": child_v,
                "delta": None if child_v is None or parent_v is None else child_v - parent_v,
            }
    return delta


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def sample_list(value: Any, limit: int = 24) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []





def normalize_answer_quality_metrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if value.get("available") is False and not any(key in value for key in ("f1", "precision", "recall")):
        return {}
    metrics = dict(value)
    if "true_positive" not in metrics and "true_positive_count" in metrics:
        metrics["true_positive"] = metrics.get("true_positive_count")
    if "false_positive" not in metrics and "extra_count" in metrics:
        metrics["false_positive"] = metrics.get("extra_count")
    if "false_negative" not in metrics and "missing_count" in metrics:
        metrics["false_negative"] = metrics.get("missing_count")
    return metrics


def first_answer_quality(*sources: Any) -> dict[str, Any]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        direct = normalize_answer_quality_metrics(source.get("answer_quality"))
        if direct:
            return direct
        feedback = source.get("feedback_summary") if isinstance(source.get("feedback_summary"), dict) else {}
        direct = normalize_answer_quality_metrics(feedback.get("answer_quality"))
        if direct:
            return direct
        workflow = source.get("workflow_feedback_summary") if isinstance(source.get("workflow_feedback_summary"), dict) else {}
        direct = normalize_answer_quality_metrics(workflow.get("answer_quality"))
        if direct:
            return direct
        fine = source.get("fine_grained_feedback") if isinstance(source.get("fine_grained_feedback"), dict) else {}
        direct = normalize_answer_quality_metrics(fine.get("answer_quality"))
        if direct:
            return direct
    return {}


def first_helper_usage_summary(*sources: Any) -> dict[str, Any]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("helper_usage_summary", "helper_usage"):
            value = source.get(key)
            if isinstance(value, dict) and value:
                return value
        feedback = source.get("feedback_summary") if isinstance(source.get("feedback_summary"), dict) else {}
        value = feedback.get("helper_usage_summary")
        if isinstance(value, dict) and value:
            return value
        workflow = source.get("workflow_feedback_summary") if isinstance(source.get("workflow_feedback_summary"), dict) else {}
        value = workflow.get("helper_usage_summary")
        if isinstance(value, dict) and value:
            return value
    return {}


def normalize_proposed_contracts(value: Any) -> dict[str, Any]:
    """Preserve meta-agent proposed contracts with only light normalization.

    The archive should remember what a candidate believed its repair contract
    was, without forcing every future meta-agent into a fixed human-authored
    taxonomy. This keeps the raw payload and extracts only generic indexing
    fields that later contract eval can use.
    """

    if value in (None, "", [], {}):
        return {
            "schema_version": PROPOSED_CONTRACTS_SCHEMA_VERSION,
            "present": False,
            "source": "patch_spec.proposed_contracts",
            "contracts": [],
            "raw": value,
            "summary": {
                "contract_count": 0,
                "target_files": [],
                "expected_observable_effects": [],
            },
        }

    raw_contracts = value if isinstance(value, list) else [value]
    contracts: list[dict[str, Any]] = []
    target_files: list[str] = []
    effects: list[str] = []

    def add_unique(items: list[str], item: Any) -> None:
        if item is None:
            return
        text = str(item)
        if text and text not in items:
            items.append(text)

    for idx, item in enumerate(raw_contracts):
        if isinstance(item, dict):
            statement = (
                item.get("contract")
                or item.get("statement")
                or item.get("contract_statement")
                or item.get("expected_behavior")
                or item.get("intended_change")
                or item.get("rationale")
            )
            scope = item.get("scope") or item.get("risk_scope") or item.get("target_layer")
            files = item.get("target_files") or item.get("files") or item.get("target_file")
            effect = (
                item.get("expected_observable_effect")
                or item.get("observable_effect")
                or item.get("success_condition")
                or item.get("validation_hint")
            )
            validation_hint = item.get("validation_hint") or item.get("test") or item.get("test_hint")
            if isinstance(files, str):
                files_list = [files]
            elif isinstance(files, list):
                files_list = [str(file) for file in files if file is not None]
            else:
                files_list = []
            for file in files_list:
                add_unique(target_files, file)
            add_unique(effects, effect)
            contracts.append(
                {
                    "contract_id": str(item.get("contract_id") or item.get("id") or f"contract_{idx + 1}"),
                    "statement": None if statement is None else str(statement),
                    "scope": None if scope is None else str(scope),
                    "target_files": files_list,
                    "expected_observable_effect": None if effect is None else str(effect),
                    "validation_hint": None if validation_hint is None else str(validation_hint),
                    "source_index": idx,
                    "raw": item,
                }
            )
        else:
            contracts.append(
                {
                    "contract_id": f"contract_{idx + 1}",
                    "statement": str(item),
                    "scope": None,
                    "target_files": [],
                    "expected_observable_effect": None,
                    "validation_hint": None,
                    "source_index": idx,
                    "raw": item,
                }
            )

    return {
        "schema_version": PROPOSED_CONTRACTS_SCHEMA_VERSION,
        "present": bool(contracts),
        "source": "patch_spec.proposed_contracts",
        "contracts": contracts,
        "raw": value,
        "summary": {
            "contract_count": len(contracts),
            "target_files": target_files,
            "expected_observable_effects": effects,
        },
    }


def validation_observations(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in manifest.get("validation_results") or []:
        if not isinstance(item, dict):
            continue
        is_warning = bool(item.get("warning")) or item.get("hard_fail") is False
        failed = item.get("exit_code") not in (None, 0)
        if not is_warning and not failed:
            continue
        observations.append(
            {
                "name": item.get("name"),
                "reason": item.get("reason"),
                "gate_layer": item.get("gate_layer"),
                "gate_type": item.get("gate_type"),
                "exit_code": item.get("exit_code"),
                "hard_fail": item.get("hard_fail"),
                "warning": bool(item.get("warning")),
                "source": "manifest.validation_results",
            }
        )
    return observations


def interface_mediation_observation(candidate_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Extract interface mediation as archive evidence, not only pass/fail state."""

    report_path = candidate_dir / "validation/interface_mediation_report.json"
    report = load_json(report_path)
    validation_results = manifest.get("validation_results") if isinstance(manifest.get("validation_results"), list) else []
    gates = [
        item
        for item in validation_results
        if isinstance(item, dict)
        and str(item.get("name") or "") in {
            "patch_local_contract_checks",
            "interface_mediation",
            "interface_mediation_post_apply_gate",
            "patch_local_contract_checks_after_mediation",
        }
    ]
    if not report and not gates:
        return {"present": False}
    before_gate = next((item for item in gates if item.get("name") == "patch_local_contract_checks"), {})
    mediation_gate = next((item for item in gates if item.get("name") == "interface_mediation"), {})
    after_gate = next((item for item in gates if item.get("name") == "patch_local_contract_checks_after_mediation"), {})
    return {
        "present": True,
        "status": report.get("status") or mediation_gate.get("mediation_status"),
        "recoverable": report.get("recoverable"),
        "recoverability_reason": report.get("recoverability_reason"),
        "semantic_patch_changed": report.get("semantic_patch_changed"),
        "before_local_contract_exit_code": before_gate.get("exit_code"),
        "before_local_contract_reason": before_gate.get("reason"),
        "after_local_contract_exit_code": after_gate.get("exit_code"),
        "after_local_contract_reason": after_gate.get("reason"),
        "applied": report.get("applied") if isinstance(report.get("applied"), list) else [],
        "report": str(report_path) if report_path.exists() else None,
        "validation_gates": gates,
    }


def helper_usage_observations(helper_usage: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    interface: list[dict[str, Any]] = []
    contract: list[dict[str, Any]] = []
    if not helper_usage:
        return interface, contract
    status = helper_usage.get("status")
    if status and status != "helper_called_by_child_generated_code":
        interface.append({"kind": "helper_usage_status", "status": status, "source": "child_eval.helper_usage"})
    final_dep = helper_usage.get("final_answer_dependency") if isinstance(helper_usage.get("final_answer_dependency"), dict) else {}
    dep_status = final_dep.get("status")
    if final_dep.get("required") and dep_status != "helper_output_used_for_final_answer":
        interface.append(
            {
                "kind": "helper_output_sink_mismatch",
                "status": dep_status,
                "tainted_vars": final_dep.get("tainted_vars"),
                "assignment_events": final_dep.get("assignment_events"),
                "final_answer_sinks": final_dep.get("final_answer_sinks"),
                "log_sinks": final_dep.get("log_sinks"),
                "source": "child_eval.helper_usage.final_answer_dependency",
            }
        )
        contract.append(
            {
                "kind": "helper_output_not_used_for_final_answer",
                "contract_statement": "If a helper is intended to affect answer selection, its output should reach final_answer construction.",
                "observed_status": dep_status,
                "source": "child_eval.helper_usage.final_answer_dependency",
            }
        )
    return interface, contract


def infer_failure_tags(
    *,
    manifest: dict[str, Any],
    child_eval: dict[str, Any],
    patch_spec: dict[str, Any],
    soft_gate_observations: list[dict[str, Any]],
    interface_mismatch_evidence: list[dict[str, Any]],
    contract_failure_evidence: list[dict[str, Any]],
) -> list[str]:
    tags: list[str] = []

    def add(tag: str) -> None:
        if tag and tag not in tags:
            tags.append(tag)

    if patch_spec.get("open_diagnosis"):
        add("has_open_diagnosis")
    if patch_spec.get("proposed_contracts"):
        add("has_proposed_contracts")
    reason = str(child_eval.get("child_validation_reason") or child_eval.get("validation_reason") or "").lower()
    if "missing_final_answer_file_or_empty_answer" in reason or "empty" in reason and "answer" in reason:
        add("empty_final_answer")
    for item in child_eval.get("child_failure_gates") or []:
        add(str(item))
    answer_quality = first_answer_quality(child_eval)
    if answer_quality.get("strict_match_passed") is False:
        add("answer_quality_mismatch")
    helper_usage_summary = first_helper_usage_summary(child_eval)
    helper_status = helper_usage_summary.get("status")
    if helper_status:
        add(str(helper_status))
    for item in soft_gate_observations:
        name = str(item.get("name") or "")
        reason_text = str(item.get("reason") or "")
        if name:
            add(name)
        if "diagnostics_only" in reason_text:
            add("diagnostics_only_warning")
        if "weak_filtering" in reason_text:
            add("weak_filtering_warning")
    for item in interface_mismatch_evidence:
        add(str(item.get("kind") or "interface_mismatch"))
    for item in contract_failure_evidence:
        add(str(item.get("kind") or "contract_failure"))
    if manifest.get("status"):
        add(f"manifest_{manifest.get('status')}")
    if child_eval.get("final_status"):
        add(str(child_eval.get("final_status")))
    mediation_status = None
    for item in interface_mismatch_evidence:
        if item.get("kind") == "interface_mediation_status":
            mediation_status = item.get("status")
            if item.get("before_local_contract_exit_code") not in (None, 0) and item.get("after_local_contract_exit_code") == 0:
                add("local_contract_failed_then_mediated")
            if item.get("recoverable") is True:
                add("interface_mismatch_recoverable")
    if mediation_status:
        add(str(mediation_status))
    return tags


def build_archive_observation(candidate_dir: Path) -> dict[str, Any]:
    candidate_dir = candidate_dir.resolve()
    manifest = load_json(candidate_dir / "manifest.json")
    child_eval = load_json(candidate_dir / "child_eval/child_eval_report.json") or load_json(candidate_dir / "child_eval/generic_child_eval_report.json")
    patch_spec = load_patch_spec(candidate_dir)
    next_seed = load_json(candidate_dir / "child_eval/next_data_agent_repair_seed.json") or load_json(candidate_dir / "next_data_agent_repair_seed.json")
    child_metrics = child_eval.get("child_answer_metrics") if isinstance(child_eval.get("child_answer_metrics"), dict) else {}
    if not child_metrics:
        child_metrics = first_answer_quality(child_eval, next_seed)
    parent_metrics = child_eval.get("parent_answer_metrics") if isinstance(child_eval.get("parent_answer_metrics"), dict) else {}
    if not parent_metrics:
        parent_metrics = normalize_answer_quality_metrics(child_eval.get("parent_answer_quality"))
    deltas = metric_delta(child_metrics, parent_metrics)
    helper_usage = child_eval.get("helper_usage") if isinstance(child_eval.get("helper_usage"), dict) else {}
    if not helper_usage:
        helper_usage = first_helper_usage_summary(child_eval, next_seed)
    soft_obs = validation_observations(manifest)
    mediation_obs = interface_mediation_observation(candidate_dir, manifest)
    interface_obs, contract_obs = helper_usage_observations(helper_usage)
    if mediation_obs.get("present"):
        interface_obs.append({
            "kind": "interface_mediation_status",
            "status": mediation_obs.get("status"),
            "recoverable": mediation_obs.get("recoverable"),
            "before_local_contract_exit_code": mediation_obs.get("before_local_contract_exit_code"),
            "after_local_contract_exit_code": mediation_obs.get("after_local_contract_exit_code"),
            "source": "candidate.validation.interface_mediation_report",
        })
    open_diag = patch_spec.get("open_diagnosis") if isinstance(patch_spec.get("open_diagnosis"), dict) else None
    proposed_contracts = normalize_proposed_contracts(patch_spec.get("proposed_contracts"))
    open_diag_evidence = child_eval.get("open_diagnosis_evidence") if isinstance(child_eval.get("open_diagnosis_evidence"), dict) else next_seed.get("open_diagnosis_evidence") if isinstance(next_seed.get("open_diagnosis_evidence"), dict) else None
    not_to_repeat: list[Any] = []
    if isinstance(open_diag, dict):
        not_to_repeat.extend(sample_list(open_diag.get("not_to_repeat"), 20))
    if child_eval.get("child_failure_gates"):
        not_to_repeat.extend([f"avoid repeating failure gate: {item}" for item in child_eval.get("child_failure_gates") or []])
    if child_eval.get("child_validation_reason"):
        not_to_repeat.append(f"avoid child validation failure: {child_eval.get('child_validation_reason')}")
    child_f1 = to_float(child_metrics.get("f1"))
    parent_f1 = to_float(parent_metrics.get("f1"))
    passed = bool(child_eval.get("child_passed") or child_eval.get("final_status") == "candidate_child_eval_passed")
    severe = "severe_child_answer_regression" in (child_eval.get("child_failure_gates") or [])
    catastrophic = any(
        item in (child_eval.get("child_failure_gates") or [])
        for item in (
            "child_lost_nonempty_answer",
            "missing_final_answer_file_or_empty_answer",
            "child_execution_failed_after_executable_parent",
            "child_answer_cardinality_explosion",
        )
    )
    f1_close_enough = parent_f1 is None or child_f1 is None or child_f1 >= parent_f1 - PARENT_F1_TOLERANCE
    eligible = bool(passed and not severe and not catastrophic and f1_close_enough)
    promotion_reason = "child_eval_passed" if eligible else "not_parent_eligible"
    if severe:
        promotion_reason = "severe_child_answer_regression"
    elif child_eval.get("child_validation_reason"):
        promotion_reason = str(child_eval.get("child_validation_reason"))[:240]
    gate_policy_summary = summarize_gate_policy(manifest.get("validation_results") or [], child_eval) if summarize_gate_policy else {}
    contract_eval = evaluate_contracts(
        proposed_contracts,
        child_eval=child_eval,
        metric_delta=deltas,
        interface_mismatch_evidence=interface_obs,
        contract_failure_evidence=contract_obs,
        soft_gate_observations=soft_obs,
    ) if evaluate_contracts else {}
    observations = {
        "schema_version": ARCHIVE_OBSERVATION_SCHEMA_VERSION,
        "candidate_id": candidate_dir.name,
        "promotion": {
            "eligible_as_parent": eligible,
            "reason": promotion_reason,
            "promotion_score": max(0.0, deltas.get("f1", {}).get("delta") or 0.0) if isinstance(deltas.get("f1"), dict) else 0.0,
            "parent_f1_tolerance": PARENT_F1_TOLERANCE,
            "f1_close_enough": f1_close_enough,
            "catastrophic_answer_failure": catastrophic,
        },
        "gate_policy_summary": gate_policy_summary,
        "observations": {
            "open_diagnosis": open_diag,
            "open_diagnosis_evidence_summary": open_diag_evidence,
            "proposed_contracts": proposed_contracts,
            "contract_eval": contract_eval,
            "soft_gate_observations": soft_obs,
            "interface_mediation": mediation_obs,
            "interface_mismatch_evidence": interface_obs,
            "contract_failure_evidence": contract_obs,
            "helper_usage": helper_usage,
            "answer_quality": child_metrics,
            "parent_answer_quality": parent_metrics,
            "metric_delta": deltas,
            "answer_delta_details": {
                "missing_codes_sample": sample_list(child_metrics.get("missing_codes")),
                "extra_codes_sample": sample_list(child_metrics.get("extra_codes")),
                "predicted_codes_sample": sample_list(child_metrics.get("predicted_codes_sample")),
            },
            "not_to_repeat": not_to_repeat,
            "failure_observation_tags": [],
        },
        "reuse_policy": {
            "can_be_parent": eligible,
            "can_seed_next_repair": True,
            "use_as_negative_example": not eligible,
        },
        "source_artifacts": {
            "candidate_dir": str(candidate_dir),
            "manifest": str(candidate_dir / "manifest.json") if (candidate_dir / "manifest.json").exists() else None,
            "patch_spec_raw": str(candidate_dir / "patch_spec_raw.txt") if (candidate_dir / "patch_spec_raw.txt").exists() else None,
            "child_eval_report": str(candidate_dir / "child_eval/child_eval_report.json") if (candidate_dir / "child_eval/child_eval_report.json").exists() else None,
            "next_repair_seed": str(candidate_dir / "child_eval/next_data_agent_repair_seed.json") if (candidate_dir / "child_eval/next_data_agent_repair_seed.json").exists() else None,
        },
    }
    observations["observations"]["failure_observation_tags"] = infer_failure_tags(
        manifest=manifest,
        child_eval=child_eval,
        patch_spec=patch_spec,
        soft_gate_observations=soft_obs,
        interface_mismatch_evidence=interface_obs,
        contract_failure_evidence=contract_obs,
    )
    contract_eval_status = (observations["observations"].get("contract_eval") or {}).get("status")
    if contract_eval_status and contract_eval_status != "not_evaluated_no_proposed_contracts":
        observations["observations"]["failure_observation_tags"].append(contract_eval_status)
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--write", type=Path, help="Optional path to write extracted observation JSON.")
    args = parser.parse_args()
    observation = build_archive_observation(args.candidate_dir)
    if args.write:
        write_json(args.write, observation)
    print(json.dumps(observation, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
