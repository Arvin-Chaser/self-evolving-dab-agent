"""Record and diagnose the r6 Gen15 repair as a hash-bound Graph branch."""

import argparse
import json
import os
import shutil
from pathlib import Path

from experiments import dab_roadmap_protocol as graph
from experiments.extract_gen015_handoff_reach_r6_evidence import build_card


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "experiments/dab_evolution_campaigns/dataset17_half56_deepseek_v1_20261011"
BRANCH = CAMPAIGN / "repair_branches/gen015_handoff_reach_r6"
DEPLOY = BRANCH / "deployment_revision_001"
SUMMARY = BRANCH / "evaluation/multi_query_summary.json"
AUDIT = DEPLOY / "terminal_audit_v1.json"
CARD = DEPLOY / "mechanism_evidence_card.json"
REF = BRANCH / "repair_ref.json"
INTENT = CAMPAIGN / "generations/gen_015/sealed_intent.json"
PARENT = CAMPAIGN / "repair_branches/gen015_handoff_reach_r5/evaluation/multi_query_summary.json"
REVIEW = BRANCH / "meta_agent/diagnosis/diagnosis_response.json"
RESULT = BRANCH / "result.json"
GRAPH_PATH = CAMPAIGN / "repair_branches/branch_graph.jsonl"
NODE_ID = "repair_gen015_handoff_reach_r6"


def read(path):
    return graph.read_json(path)


def write_once(path, value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Existing artifact differs: {path}")
        return
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)


def validated_inputs():
    verification = graph.verify_roadmap(CAMPAIGN)
    assert verification["ok"] and verification["record_count"] == 19
    assert verification["repair_branch_count"] == 4
    state = read(CAMPAIGN / "campaign_state.json")
    assert state["stage"] == "ready_for_intent" and state["next_generation"] == 20
    ref, audit, summary, intent = (read(path) for path in (REF, AUDIT, SUMMARY, INTENT))
    assert ref["branch_of_node_id"] == "gen_015_two_phase_frozen_evidence_handoff"
    assert ref["code_parent_branch_node_id"] == "repair_gen015_handoff_reach_r5"
    assert ref["graph_anchor_repair_head_sha256"] == verification["repair_branch_head_sha256"]
    assert ref["graph_anchor_head_sha256"] == verification["head_record_sha256"]
    assert audit["complete"] and audit["natural_end"] and audit["hashes_verified"]
    assert audit["exact_ids"] == 56 and audit["ids_match_order"]
    assert audit["summary_sha256"] == graph.sha256_file(SUMMARY)
    assert graph.source_tree_hash(Path(ref["repo"])) == ref["source_tree_sha256"]
    expected_card = build_card(AUDIT, SUMMARY, REF, INTENT)
    assert read(CARD) == expected_card
    assert read(PARENT)["query_count"] == 56
    return verification, ref, audit, summary, intent, expected_card


def record_result():
    _, ref, audit, summary, intent, card = validated_inputs()
    parent = read(PARENT)
    result = {
        "schema": "dab_engineering_repair_result_v1",
        "branch_id": ref["branch_id"], "generation": 15,
        "branch_of_node_id": ref["branch_of_node_id"],
        "code_parent_branch_node_id": ref["code_parent_branch_node_id"],
        "summary": graph.compact_result(summary),
        "parent_summary": graph.compact_result(parent),
        "strict_pass_delta": None,
        "parent_comparison_status": "not_causally_comparable_unmatched_control",
        "intent_binding": graph.intent_result_binding(intent),
        "candidate": {"generation": 15, "source_tree_sha256": ref["source_tree_sha256"],
                      "patch_sha256": ref["repair_delta_sha256"]},
        "mechanism_evidence": card,
        "evaluation_binding": {"result_type": "engineering_repair_branch", "homogeneous_runtime": True,
            "input_policy": "base_only_no_hint",
            "comparability": "causal strict delta suppressed; unmatched repair-branch runs are not controls"},
        "batch_summary_path": str(SUMMARY), "terminal_audit_path": str(AUDIT),
        "terminal_audit_sha256": graph.sha256_file(AUDIT),
        "mechanism_evidence_path": str(CARD), "mechanism_evidence_sha256": graph.sha256_file(CARD),
    }
    write_once(RESULT, result)
    print(json.dumps({"status": "repair_result_recorded", "result": str(RESULT),
                      "summary": result["summary"]}, indent=2))


def invoke_review():
    _, _, audit, _, _, _ = validated_inputs()
    result = read(RESULT)
    intent, ref = read(INTENT), read(REF)
    campaign, _ = graph.load_campaign(CAMPAIGN)
    snapshot = graph.build_snapshot(CAMPAIGN)
    snapshot.pop("safe_detail_access", None)
    session = REVIEW.parent
    assert not REVIEW.exists(), "Diagnosis already exists; use append-review to resume"
    session.mkdir(parents=True, exist_ok=True)
    write_once(session / "output_schema.json", graph.review_output_schema())
    write_once(session / "roadmap_snapshot.json", snapshot)
    candidate = {"generation": 15, "source_tree_sha256": ref["source_tree_sha256"],
                 "patch_sha256": ref["repair_delta_sha256"]}
    prompt = (
        "This is a new independent engineering repair branch of the existing Gen15 sealed intent, "
        "with the audited r5 reach repair as its code parent; it is not a new mechanism selection. "
        "Diagnose this result without rewriting earlier nodes. Do not recommend a patch or select a future intent. "
        f"The user-facing strict denominator is non-timeout completed={audit['completed']}, "
        f"not strict-scored={audit['strict_scored']}; strict={audit['strict_pass']}, "
        f"runner timeout={audit['runner_timeout']}. Do not report strict/scored as strict/completed.\n\n"
        + graph.build_review_prompt(intent, candidate, result, snapshot)
    )
    prompt_path = session / "prompt.md"
    assert not prompt_path.exists(), "Existing diagnosis prompt; inspect before resuming"
    prompt_path.write_text(prompt, encoding="utf-8")
    response = graph.invoke_codex_json(campaign=campaign, session=session, prompt=prompt,
        schema_path=session / "output_schema.json", output_name=REVIEW.name)
    known = set(graph.selectable_parent_descriptors(CAMPAIGN))
    errors = graph.validate_review(response, known)
    if errors:
        raise ValueError("Repair diagnosis invalid: " + "; ".join(errors))
    print(json.dumps({"status": "repair_diagnosis_ready", "response": str(REVIEW)}))


def retry_review():
    _, ref, audit, _, intent, _ = validated_inputs()
    assert REVIEW.is_file(), "Original diagnosis must be preserved before retry"
    attempt = next(number for number in range(2, 10)
                   if not (BRANCH / f"meta_agent/diagnosis_retry{number:03d}").exists())
    session = BRANCH / f"meta_agent/diagnosis_retry{attempt:03d}"
    session.mkdir(parents=True)
    shutil.copy2(REVIEW, session / "diagnosis_response_attempt001.json")
    campaign, _ = graph.load_campaign(CAMPAIGN)
    snapshot = graph.build_snapshot(CAMPAIGN)
    snapshot.pop("safe_detail_access", None)
    result = read(RESULT)
    candidate = {"generation": 15, "source_tree_sha256": ref["source_tree_sha256"],
                 "patch_sha256": ref["repair_delta_sha256"]}
    prompt = (
        "Independently rediagnose this Gen15 engineering repair branch. The earlier "
        "response was rejected; do not copy it. Fall-back rows may overlap composition-delivery "
        "rows. Context sizes are characters, not bytes. Distinguish completed from strict-scored "
        f"coverage: strict={audit['strict_pass']}, non-timeout completed={audit['completed']}, "
        f"strict-scored={audit['strict_scored']}, runner timeout={audit['runner_timeout']}. "
        "Source and input hashes were verified by the terminal audit. Diagnose only the seven-link "
        "causal chain; do not recommend a patch, select an intent, or attribute a single-run "
        "difference to this intervention. Keep the entire JSON response under 12000 characters.\n\n"
        + graph.build_review_prompt(intent, candidate, result, snapshot)
    )
    write_once(session / "output_schema.json", graph.review_output_schema())
    write_once(session / "roadmap_snapshot.json", snapshot)
    (session / "prompt.md").write_text(prompt, encoding="utf-8")
    response = graph.invoke_codex_json(campaign=campaign, session=session, prompt=prompt,
        schema_path=session / "output_schema.json", output_name="diagnosis_response.json")
    errors = graph.validate_review(response, set(graph.selectable_parent_descriptors(CAMPAIGN)))
    if errors:
        raise ValueError("Repair diagnosis retry invalid: " + "; ".join(errors))
    shutil.copy2(session / "diagnosis_response.json", REVIEW)
    print(json.dumps({"status": "repair_diagnosis_retry_ready", "response": str(REVIEW)}))


def append_review():
    verification, ref, audit, _, intent, card = validated_inputs()
    result, review = read(RESULT), read(REVIEW)
    known = set(graph.selectable_parent_descriptors(CAMPAIGN))
    errors = graph.validate_review(review, known)
    if errors:
        raise ValueError("Repair diagnosis invalid: " + "; ".join(errors))
    existing = graph.load_repair_branches(CAMPAIGN)
    assert not any(item["node_id"] == NODE_ID for item in existing), "Branch already appended"
    record = {
        "schema": "dab_engineering_repair_branch_v2",
        "node_id": NODE_ID, "generation": 15, "branch_of_node_id": ref["branch_of_node_id"],
        "code_parent_branch_node_id": ref["code_parent_branch_node_id"],
        "main_head_at_append_sha256": verification["head_record_sha256"],
        "previous_branch_record_sha256": verification["repair_branch_head_sha256"],
        "parent_edges": [
            {"node_id": ref["code_parent_branch_node_id"], "role": "code_base"},
            {"node_id": ref["branch_of_node_id"], "role": "intent_base"},
        ],
        "intent": {key: intent[key] for key in ("mechanism_key", "primary_dimension", "target_component",
                                                "proposed_mechanism", "expected_behavioral_change", "novelty_claim")},
        "candidate": {"source_tree_sha256": ref["source_tree_sha256"],
                      "parent_source_tree_sha256": ref["parent_source_tree_sha256"],
                      "repair_delta_sha256": ref["repair_delta_sha256"],
                      "changed_files": ref["changed_files"]},
        "result": result["summary"], "evaluation_binding": result["evaluation_binding"],
        "mechanism_evidence": card,
        "review": {key: review.get(key) for key in ("outcome_label", "source_reuse_recommendation",
                     "short_review", "failure_mechanism_key", "relations_to_prior", "causal_diagnosis")},
        "detail_links": {"sealed_intent": str(INTENT), "candidate_ref": str(REF),
                         "evaluation_result": str(RESULT), "detailed_review": str(REVIEW),
                         "batch_summary": str(SUMMARY), "terminal_audit": str(AUDIT),
                         "mechanism_evidence": str(CARD)},
        "repair_ref_sha256": graph.sha256_file(REF),
        "evaluation_result_sha256": graph.sha256_file(RESULT),
        "terminal_audit_sha256": graph.sha256_file(AUDIT),
        "mechanism_evidence_sha256": graph.sha256_file(CARD),
        "diagnosis_response_sha256": graph.sha256_file(REVIEW),
        "appended_at": graph.utc_now(),
    }
    record["record_sha256"] = graph.record_hash(record)
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GRAPH_PATH.open("a", encoding="utf-8") as stream:
        stream.write(graph.canonical_json(record) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    after = graph.verify_roadmap(CAMPAIGN)
    if not after["ok"] or after["head_record_sha256"] != verification["head_record_sha256"]:
        raise RuntimeError("Repair branch append failed graph verification")
    print(json.dumps({"status": "repair_branch_appended", "node_id": NODE_ID,
                      "record_sha256": record["record_sha256"], "graph": after}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("record-result", "invoke-review", "retry-review", "append-review"))
    args = parser.parse_args()
    {"record-result": record_result, "invoke-review": invoke_review,
     "retry-review": retry_review, "append-review": append_review}[args.action]()
