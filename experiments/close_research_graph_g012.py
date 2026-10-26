#!/usr/bin/env python3
"""Close independently reviewed G12 Evidence and append it to two-layer memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import build_research_memory, validate_research_memory
from experiments.run_research_graph_balanced_meta import graph_path
from experiments.run_research_graph_g011_incubation_meta import GRAPH_HASHES


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
RUN = BASE / "g012_formal_001"
POSTRUN = RUN / "postrun"
PREVIOUS = BASE / "research_graph_memory_v11.json"
G11_GRAPH = BASE / "g011_solution_loop_safe_snapshot/g011_solution_loop_graph.json"
OUT_DIR = BASE / "g012_safe_snapshot"
OUT_MEMORY = BASE / "research_graph_memory_v12.json"

EXPECTED = {
    "pre_execution": "e7f6d802bc5c633168d3d90fde34e8bd54f13e2cee6b4d1961f94ea7b9d75848",
    "preflight": "3a1c864714a4205f60d567a66e312caccd5236723110436747150ac296b2eeae",
    "launch_claim": "11bf6ab4c23519a6cfa0c9c618f8655feb3c3a28441d5f0c9fd343d09d5b2838",
    "launch_manifest": "f63ada35052b8d08ca6186ab2658ca3483f78f9b8c400b529dad9a883f5ce93c",
    "outcome": "5dd03f24c67fc5f03c75224a6504c12938ad60b9cc6a9ffef0e4f69250fb82c8",
    "specialized": "beb7969dc1e33b547e343537ff7d07a83f4a99e953774cef3582b3a9f889b76a",
    "evidence_draft": "8eba8f42a75cb9b94f59c2ad14f4a3f5de2e2222dcdd22c9b33640d08e980495",
    "closure_draft": "82249dda01bd2e477cf11ca0fd82718ad55cd991283b60030bfcfc399a283dba",
    "deterministic_verification": "df441b931c2a2441b9547b493aba6604339da2c3a96318c67691831622240524",
    "privacy": "31f30c96f5750baa05394d0714e9bd1a26a643d60d923a22e6769519fe44ec8e",
    "terminal_receipt": "86ac90a7b925daf58a7f9453619cad258b0df54c4ba4f1ffb3d064a6821a8fb1",
    "previous_memory": "99c72fe89f1e2a8028a6d9edd239f1d65bd0f8be567879198916fdfa4b2f12f8",
    "g11_graph": "e0a8e0a032cfb1f91506cb3d8fa0b463955e6bc48b85b3566262c8a0ec8163a4",
}
PATHS = {
    "pre_execution": RUN / "pre_execution.json",
    "preflight": RUN / "preflight.json",
    "launch_claim": RUN / "launch_claim.json",
    "launch_manifest": RUN / "launch_manifest.json",
    "outcome": POSTRUN / "outcome_partition.json",
    "specialized": POSTRUN / "g012_specialized_evidence.json",
    "evidence_draft": POSTRUN / "evidence_draft.json",
    "closure_draft": POSTRUN / "graph_closure_input_draft.json",
    "deterministic_verification": POSTRUN / "deterministic_verification.json",
    "privacy": POSTRUN / "privacy_export_audit.json",
    "terminal_receipt": POSTRUN / "terminal_receipt.json",
    "previous_memory": PREVIOUS,
    "g11_graph": G11_GRAPH,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def write_new(path: Path, value: dict) -> None:
    content = canonical(value)
    if path.exists():
        require(path.read_text(encoding="utf-8") == content, f"Existing output differs: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def verify_inputs() -> tuple[dict, dict, dict, dict, dict]:
    for name, path in PATHS.items():
        require(digest(path) == EXPECTED[name], f"Frozen G12 closure input differs: {name}")

    pre = read(PATHS["pre_execution"])
    outcome = read(PATHS["outcome"])
    special = read(PATHS["specialized"])
    draft = read(PATHS["evidence_draft"])
    privacy = read(PATHS["privacy"])
    terminal = read(PATHS["terminal_receipt"])
    verification = read(PATHS["deterministic_verification"])
    closure = read(PATHS["closure_draft"])

    require(
        pre.get("schema_version") == "g012_formal_pre_execution_binding_v1"
        and pre["binding"]["generation"] == 12
        and pre["binding"]["query_count"] == 56
        and pre["binding"]["query_timeout_sec"] == 1200
        and pre["binding"]["description_mode"] == "full_db_description_no_hints"
        and pre["binding"]["candidate_tree_sha256"]
        == "47dbf42636bbaa234c5f58256a37821a2ac891d29b34fcce13fe350207e7e344",
        "G12 pre-execution binding differs",
    )
    require(
        outcome.get("ended") == 56
        and outcome.get("completed") == 51
        and outcome.get("timeout_failures") == 5
        and outcome.get("other_terminal_failures") == 0
        and outcome.get("strict_pass") == 30
        and outcome.get("known_strict_fail") == 18
        and outcome.get("completed_strict_verdict_unknown") == 3
        and outcome.get("strict_score") == "30/56"
        and outcome.get("recorded_llm_call_count") == 1381,
        "G12 outcome partition differs",
    )
    cohort_rows = list(special.get("cohorts", {}).values())
    require(
        special.get("overall_status") == "untested"
        and special.get("observed_task_count") == 56
        and special.get("protocol_complete") is True
        and sum(row.get("denominator", 0) for row in cohort_rows) == 56
        and sum(row.get("record_attempt_count", 0) for row in cohort_rows) == 0
        and sum(row.get("accepted_record_count", 0) for row in cohort_rows) == 0
        and sum(row.get("adoption_visible_ref_count", 0) for row in cohort_rows) == 0
        and sum(row.get("directive_count", 0) for row in cohort_rows) == 0
        and sum(row.get("consistent_action_count", 0) for row in cohort_rows) == 0
        and sum(row.get("contradicted_action_count", 0) for row in cohort_rows) == 0
        and sum(row.get("guidance_suppressed_no_state_count", 0) for row in cohort_rows) == 0,
        "G12 specialized Evidence or no-state correction differs",
    )
    require(
        special.get("formal_run_performed") is False
        and special.get("evaluation_run") is False,
        "G12 mechanism-only no-claim flags differ",
    )
    require(
        draft.get("status") == "pending_independent_review"
        and draft.get("formal_attempt_complete") is True
        and draft.get("execution_integrity_passed") is True
        and draft.get("mechanism_overall_status") == "untested"
        and draft.get("outcome") == outcome,
        "G12 Evidence draft differs",
    )
    require(
        privacy.get("status") == "passed"
        and privacy.get("content_blind_export") is True
        and privacy.get("known_task_identifier_match_count") == 0
        and privacy.get("raw_content_read") is False
        and privacy.get("credentials_exported") is False,
        "G12 privacy boundary differs",
    )
    require(
        terminal.get("formal_attempt_complete") is True
        and terminal.get("ended") == 56
        and terminal.get("strict_score") == "30/56"
        and terminal.get("evidence_draft_sha256") == EXPECTED["evidence_draft"]
        and terminal.get("specialized_evidence_sha256") == EXPECTED["specialized"]
        and terminal.get("privacy_export_audit_sha256") == EXPECTED["privacy"],
        "G12 terminal receipt differs",
    )
    require(
        verification.get("status") == "passed_pending_independent_research_review"
        and verification.get("formal_attempt_count") == 1
        and verification.get("matching_remote_process_count_after_completion") == 0
        and verification.get("all_terminal_receipt_hash_links_rechecked") is True
        and verification.get("raw_task_answer_sql_or_tool_content_copied") is False
        and verification.get("credential_value_copied_or_persisted") is False,
        "G12 deterministic verification differs",
    )
    require(
        closure.get("status") == "pending_independent_review_not_applied"
        and closure.get("generation") == 12
        and closure.get("graph_written_or_promoted") is False
        and closure.get("evidence_draft_sha256") == EXPECTED["evidence_draft"],
        "G12 closure draft differs",
    )
    return pre, outcome, special, draft, privacy


def main() -> None:
    pre, outcome, special, draft, privacy = verify_inputs()
    previous = read(PREVIOUS)
    validate_research_memory(previous, root=ROOT)
    require(
        [row["generation"] for row in previous["formal_evolution_layer"]["generation_refs"]]
        == list(range(12)),
        "Previous memory is not complete through G11",
    )

    OUT_DIR.mkdir(exist_ok=True)
    review_path = OUT_DIR / "g012_independent_review.json"
    evidence_path = OUT_DIR / "g012_evidence.json"
    graph_path_out = OUT_DIR / "g012_graph.json"
    closure_path = OUT_DIR / "g012_graph_closure_receipt.json"

    review = {
        "schema_version": "g012_independent_research_review_v1",
        "generation": 12,
        "status": "passed_with_documentation_correction",
        "formal_run_status": "completed",
        "evidence_status": "independently_validated",
        "graph_closure_eligible": True,
        "verified_counts": {
            "ended": 56,
            "completed": 51,
            "timeout_failure": 5,
            "other_terminal_failure": 0,
            "strict_pass": 30,
            "known_strict_fail": 18,
            "completed_strict_verdict_unknown": 3,
        },
        "mechanism_status": "untested",
        "mechanism_counts": {
            "record_attempt": 0,
            "accepted_record": 0,
            "visible_ref": 0,
            "directive": 0,
            "consistent_action": 0,
            "contradicted_action": 0,
        },
        "documentation_correction": {
            "recorded_llm_call_count": 1381,
            "guidance_suppressed_no_state_count": 0,
            "note": (
                "The 1,381 value counts recorded LLM calls; it is not a no-active-state "
                "suppression count. The specialized extractor's formal_run_performed=false and "
                "evaluation_run=false are mechanism-only no-claim fields; formal completion is "
                "established by the terminal receipt and Evidence draft together."
            ),
        },
        "privacy_status": privacy["status"],
        "source_hashes": {name: EXPECTED[name] for name in (
            "pre_execution", "preflight", "launch_claim", "launch_manifest", "outcome",
            "specialized", "evidence_draft", "closure_draft", "deterministic_verification",
            "privacy", "terminal_receipt",
        )},
        "claim_boundaries": draft["claim_boundaries"],
    }
    write_new(review_path, review)

    evidence_node = {
        "id": "evidence:g012",
        "kind": "evidence",
        "statement": (
            "G12 completed one frozen 56-task formal run at 30/56 strict. No model-authored "
            "record, visible reference, directive, or post-directive action was observed, so all "
            "pre-registered mechanism endpoints remain untested."
        ),
        "frozen_task_count": 56,
        "ended_count": 56,
        "completed_count": 51,
        "timeout_failure_count": 5,
        "other_terminal_failure_count": 0,
        "strict_pass_count": 30,
        "strict_pass_rate_all": round(30 / 56, 6),
        "known_strict_fail_count": 18,
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "specialized_signal_kind": "uncertainty_typed_evidence_state_and_gap_action",
        "specialized_status": "untested",
        "mechanism_endpoints": draft["mechanism_endpoints"],
        "limits": [
            "No model-authored record attempt, accepted record, visible reference, directive, or post-directive action was observed; the mechanism is untested.",
            "The 30/56 score is one unpaired descriptive outcome and is not a causal or benefit claim.",
            "Structural validation does not establish semantic support, relevance, correctness, coverage, or truth.",
            "Three completed strict verdicts remain unknown and are not reclassified.",
            "The five runner wall timeouts remain failures in the fixed 56 denominator.",
        ],
        "artifact_refs": {
            **{f"{name}_sha256": value for name, value in EXPECTED.items()
               if name not in {"previous_memory", "g11_graph"}},
            "independent_review_sha256": digest(review_path),
        },
    }
    evidence = {
        "schema_version": "dab_research_graph_evidence_v2",
        "generation": 12,
        "status": "independently_validated",
        "node": evidence_node,
    }
    write_new(evidence_path, evidence)

    mechanism_id = pre["binding"]["mechanism_id"]
    problem_node = {
        "id": "problem:g012", "kind": "problem", "mechanism_id": mechanism_id,
        **pre["problem"],
    }
    hypothesis_node = {
        "id": "hypothesis:g012", "kind": "hypothesis", "mechanism_id": mechanism_id,
        **pre["hypothesis"],
    }
    experiment_node = {
        "id": "experiment:g012", "kind": "experiment", "mechanism_id": mechanism_id,
        "statement": pre["experiment_label"],
        "candidate_source_tree_sha256": pre["binding"]["candidate_tree_sha256"],
        "evaluation_run_id": outcome["run_id"],
        "activation_flag": pre["binding"]["formal_activation_flag"],
        "binding": pre["binding"],
        "measurement_plan": pre["measurement_plan"],
    }
    graph = {
        "schema_version": "dab_research_graph_generation_v1",
        "generation": 12,
        "status": "four_nodes_complete",
        "pre_execution_sha256": EXPECTED["pre_execution"],
        "evidence_sha256": digest(evidence_path),
        "independent_review_sha256": digest(review_path),
        "binding": pre["binding"],
        "nodes": [problem_node, hypothesis_node, experiment_node, evidence_node],
        "edges": [
            {"source": "problem:g012", "target": "evidence:g011", "relation": "motivated_by"},
            {"source": "hypothesis:g012", "target": "problem:g012", "relation": "explains"},
            {"source": "experiment:g012", "target": "hypothesis:g012", "relation": "tests"},
            {"source": "experiment:g012", "target": "experiment:g011", "relation": "derives_code_from"},
            {"source": "evidence:g012", "target": "experiment:g012", "relation": "observes"},
            {"source": "evidence:g012", "target": "hypothesis:g012", "relation": "tests"},
        ],
    }
    write_new(graph_path_out, graph)
    persisted = read(graph_path_out)
    require(
        persisted["status"] == "four_nodes_complete"
        and [node["kind"] for node in persisted["nodes"]]
        == ["problem", "hypothesis", "experiment", "evidence"]
        and persisted["evidence_sha256"] == digest(evidence_path),
        "G12 four-node Graph verification failed",
    )

    promotion = {
        "source": "research_target:g012:003",
        "relation": "promoted_to",
        "target": "experiment:g012",
    }
    require(promotion not in previous["cross_layer_edges"], "G12 promotion already exists")
    formal_paths = {generation: graph_path(generation) for generation in range(11)}
    formal_paths[11] = G11_GRAPH
    formal_paths[12] = graph_path_out
    formal_hashes = {**GRAPH_HASHES, 11: EXPECTED["g11_graph"], 12: digest(graph_path_out)}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=formal_paths,
        formal_graph_hashes=formal_hashes,
        incubation_nodes=previous["research_incubation_layer"]["nodes"],
        incubation_edges=previous["research_incubation_layer"]["edges"],
        cross_layer_edges=[*previous["cross_layer_edges"], promotion],
    )
    validate_research_memory(memory, root=ROOT)
    require(
        [row["generation"] for row in memory["formal_evolution_layer"]["generation_refs"]]
        == list(range(13))
        and memory["research_incubation_layer"] == previous["research_incubation_layer"]
        and memory["cross_layer_edges"][:-1] == previous["cross_layer_edges"]
        and memory["cross_layer_edges"][-1] == promotion,
        "G12 append-only memory verification failed",
    )
    write_new(OUT_MEMORY, memory)

    closure_receipt = {
        "schema_version": "g012_graph_closure_receipt_v1",
        "generation": 12,
        "status": "four_nodes_complete_and_memory_appended",
        "review_sha256": digest(review_path),
        "evidence_sha256": digest(evidence_path),
        "graph_sha256": digest(graph_path_out),
        "previous_memory_sha256": EXPECTED["previous_memory"],
        "memory_sha256": digest(OUT_MEMORY),
        "formal_generations": list(range(13)),
        "incubation_node_count": len(previous["research_incubation_layer"]["nodes"]),
        "incubation_edge_count": len(previous["research_incubation_layer"]["edges"]),
        "promotion_edge": promotion,
        "privacy_status": "passed",
        "next_generation_started": False,
    }
    write_new(closure_path, closure_receipt)

    print(json.dumps({
        "status": "four_nodes_complete_and_memory_appended",
        "review_sha256": digest(review_path),
        "evidence_sha256": digest(evidence_path),
        "graph_sha256": digest(graph_path_out),
        "closure_receipt_sha256": digest(closure_path),
        "memory_sha256": digest(OUT_MEMORY),
        "formal_generations": list(range(13)),
        "promotion_edge": promotion,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
