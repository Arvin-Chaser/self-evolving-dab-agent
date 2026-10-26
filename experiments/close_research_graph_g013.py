#!/usr/bin/env python3
"""Close independently reviewed G13 Evidence and append it to two-layer memory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.research_graph_memory import build_research_memory, validate_research_memory


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
RUN = BASE / "g013_formal_001"
POSTRUN = RUN / "postrun"
PREVIOUS = BASE / "research_graph_memory_v16.json"
CONTRACT = BASE / "g013_formal_research_contract.json"
IMPLEMENTATION = BASE / "g013_formal_implementation_009/candidate_patch/implementation_manifest.json"
SOURCE_REVIEW = BASE / "g013_formal_implementation_009/source_review_006.json"
ADMISSION = BASE / "g013_admission_007/admission_result.json"
ADMISSION_REVIEW = BASE / "g013_admission_007/independent_admission_review.json"
OUT_DIR = BASE / "g013_safe_snapshot"
OUT_MEMORY = BASE / "research_graph_memory_v17.json"

EXPECTED = {
    "contract": "5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c",
    "previous_memory": "fc206dac718781d9e3d9eb0dc79e2f6593e98d5e25cb9be3448124c8e15fe54e",
    "implementation": "d8bd9714718343c51b30290e4ab1b8c8db5a077543a128f163cd48c34e36b5e1",
    "source_review": "095d36fa7b32a4f0b4b9f6bb048dffacacb9274574b8d993ac4566dee4629880",
    "admission": "2f1759d93ef77337e88a501b7b286b381fb4860ef421dfe94f32ef84741bae5e",
    "admission_review": "8d499cd636b651dc30faf7b83b8bc0180a2d599f2650f6246898025233926341",
    "failure_receipt": "8d5d777f11de27b0ccb02f911cd4f8e42cf66d3f40bec8926ce9cedec158ddda",
    "recovery_preflight": "91deed93b40661183538006f252f7883153c5ec69aafdbaca250706560864b7c",
    "recovery_binding": "35056b5e8d8baddc8d3cee5c845117d357cdba31b1d38dc1daa2bd8062b895ec",
    "recovery_execution": "5f8999d7c650124415400dabb5e0785714d812f0c83fe7e5abc335313b413607",
    "environment_attestation": "160d131451a9bf15249aaefe62b1bf1b105656a852c7f230db51eb4003786435",
    "outcome": "c4bdcb7f23682d286b15e5003ff6ba9dc74413564220e04157954c1cab5f29f3",
    "specialized": "5961a68f3641380b717f07c09792c2d904ccf2827b7e56492e6ca60f12576afb",
    "evidence_draft": "cca47010fe711b2de4aa4f190fcd4d415d47baa59d7016c396ad1c6c5a3797f5",
    "privacy": "0e18d16a35ee581e7cab5ed4b17185fe1bfde9c852846eb7f6000d1cf067f1b3",
    "closure_draft": "b146f7aeb62159b144aa2b1e1b26ccc631ae27eec349de3b1d640d81cffe4b69",
    "terminal_receipt": "a9f7ad3152116cd8b117f7705980b289f785f26fe0146258669f54c19e141b62",
}
PATHS = {
    "contract": CONTRACT,
    "previous_memory": PREVIOUS,
    "implementation": IMPLEMENTATION,
    "source_review": SOURCE_REVIEW,
    "admission": ADMISSION,
    "admission_review": ADMISSION_REVIEW,
    "failure_receipt": RUN / "finalizer_attempt_001_failure.json",
    "recovery_preflight": RUN / "finalizer_recovery_preflight.json",
    "recovery_binding": RUN / "finalizer_recovery_attempt_002/binding.json",
    "recovery_execution": RUN / "finalizer_recovery_attempt_002/execution_receipt.json",
    "environment_attestation": RUN / "finalizer_recovery_attempt_002/post_execution_environment_attestation.json",
    "outcome": POSTRUN / "outcome_partition.json",
    "specialized": POSTRUN / "g013_specialized_evidence.json",
    "evidence_draft": POSTRUN / "evidence_draft.json",
    "privacy": POSTRUN / "privacy_export_audit.json",
    "closure_draft": POSTRUN / "graph_closure_input_draft.json",
    "terminal_receipt": POSTRUN / "terminal_receipt.json",
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


def verify_inputs() -> tuple[dict, dict, dict, dict, dict, dict]:
    for name, path in PATHS.items():
        require(path.is_file(), f"Missing G13 closure input: {name}")
        require(digest(path) == EXPECTED[name], f"Frozen G13 closure input differs: {name}")

    contract = read(CONTRACT)
    outcome = read(PATHS["outcome"])
    special = read(PATHS["specialized"])
    draft = read(PATHS["evidence_draft"])
    privacy = read(PATHS["privacy"])
    terminal = read(PATHS["terminal_receipt"])
    failure = read(PATHS["failure_receipt"])
    recovery = read(PATHS["recovery_execution"])
    attestation = read(PATHS["environment_attestation"])
    closure = read(PATHS["closure_draft"])

    protocol = contract["formal_spec"]["fixed_protocol"]
    require(
        contract.get("status") == "experiment_ready_not_implemented_or_admitted"
        and contract.get("mechanism_id") == "mech_requirement_observation_coverage"
        and contract.get("selected_target_id") == "research_target:g013:002"
        and protocol == {
            "arms": 1,
            "hint_mode": "base_no_hint",
            "primary_metric": "strict_pass_over_56",
            "task_count": 56,
            "wall_timeout_seconds_per_task": 1200,
        },
        "G13 frozen contract differs",
    )
    require(
        outcome.get("ended") == 56
        and outcome.get("completed") == 52
        and outcome.get("timeout_failures") == 4
        and outcome.get("other_terminal_failures") == 0
        and outcome.get("strict_pass") == 31
        and outcome.get("known_strict_fail") == 18
        and outcome.get("completed_strict_verdict_unknown") == 3
        and outcome.get("strict_score") == "31/56",
        "G13 outcome partition differs",
    )
    require(
        special.get("protocol_complete") is True
        and special.get("observed_task_count") == 56
        and special.get("records_seen") == 0
        and special.get("accepted_record_count") == 0
        and special.get("directive_delivered_count") == 0
        and special.get("view_count") == 0
        and sum(special.get("selected_action_counts", {}).values()) == 0
        and special.get("raw_token_count_persisted") == 0
        and special.get("raw_tokens_exported") is False,
        "G13 specialized Evidence differs",
    )
    require(
        draft.get("status") == "pending_independent_review"
        and draft.get("formal_attempt_complete") is True
        and draft.get("execution_integrity_passed") is True
        and draft.get("draft_endpoint_status") == {
            "behavioral_action_choice": "untested",
            "coverage_state_behavior": "untested",
            "real_model_authorship": "untested",
            "structural_binding": "untested",
        }
        and draft.get("outcome") == outcome,
        "G13 Evidence draft differs",
    )
    require(
        privacy.get("status") == "passed"
        and privacy.get("content_blind_export") is True
        and privacy.get("known_task_identifier_match_count") == 0
        and privacy.get("raw_content_read") is False
        and privacy.get("parsed_tool_args_read") is False
        and privacy.get("credentials_exported") is False,
        "G13 privacy boundary differs",
    )
    require(
        terminal.get("formal_attempt_complete") is True
        and terminal.get("ended") == 56
        and terminal.get("strict_score") == "31/56"
        and terminal.get("evidence_draft_sha256") == EXPECTED["evidence_draft"]
        and terminal.get("specialized_evidence_sha256") == EXPECTED["specialized"]
        and terminal.get("privacy_export_audit_sha256") == EXPECTED["privacy"],
        "G13 terminal receipt differs",
    )
    require(
        failure.get("status") == "failed_preserved_no_evidence_written"
        and failure.get("postrun_absent") is True
        and failure.get("error_stage") == "dynamic_import_before_sidecar_aggregation",
        "G13 initial finalizer failure receipt differs",
    )
    require(
        recovery.get("status") == "recovered_finalization_complete_pending_independent_review"
        and recovery.get("formal_run_restarted") is False
        and recovery.get("finalizer_execution_count_for_recovery_attempt") == 1
        and recovery.get("graph_mutated") is False
        and recovery.get("next_generation_started") is False
        and recovery.get("terminal_receipt_sha256") == EXPECTED["terminal_receipt"],
        "G13 finalizer recovery receipt differs",
    )
    require(
        attestation.get("executed_interpreter_sha256")
        == "3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66",
        "G13 recovery interpreter attestation differs",
    )
    require(
        closure.get("status") == "pending_independent_review_not_applied"
        and closure.get("generation") == 13
        and closure.get("graph_written_or_promoted") is False
        and closure.get("evidence_draft_sha256") == EXPECTED["evidence_draft"],
        "G13 closure draft differs",
    )
    return contract, outcome, special, draft, privacy, recovery


def main() -> None:
    contract, outcome, special, draft, privacy, recovery = verify_inputs()
    previous = read(PREVIOUS)
    validate_research_memory(previous, root=ROOT)
    require(
        [row["generation"] for row in previous["formal_evolution_layer"]["generation_refs"]]
        == list(range(13)),
        "Previous memory is not complete through G12",
    )

    OUT_DIR.mkdir(exist_ok=True)
    review_path = OUT_DIR / "g013_independent_review.json"
    evidence_path = OUT_DIR / "g013_evidence.json"
    graph_path_out = OUT_DIR / "g013_graph.json"
    closure_path = OUT_DIR / "g013_graph_closure_receipt.json"

    review = {
        "schema_version": "g013_independent_research_review_v1",
        "generation": 13,
        "status": "passed_with_recovery_procedure_notes",
        "formal_run_status": "completed",
        "evidence_status": "independently_validated",
        "graph_closure_eligible": True,
        "verified_counts": {
            "ended": 56,
            "completed": 52,
            "timeout_failure": 4,
            "other_terminal_failure": 0,
            "strict_pass": 31,
            "known_strict_fail": 18,
            "completed_strict_verdict_unknown": 3,
        },
        "mechanism_status": "untested",
        "mechanism_counts": {
            "record_attempt": 0,
            "accepted_record": 0,
            "directive": 0,
            "view": 0,
            "post_directive_action": 0,
        },
        "recovery_review": {
            "initial_failure_before_postrun": True,
            "recovery_attempt_count": 1,
            "formal_run_restarted": False,
            "wrapper_exit_one_is_transport_capture_error": True,
            "original_finalizer_stdout_complete": True,
            "original_finalizer_stderr_empty": True,
            "interpreter_path_verified": "/srv/text2sql/.venv/bin/python",
            "interpreter_sha256": "3008abbb48c1e2b0fa3072ae72334b9b352e1346ea3a20d34126a455f0c7bc66",
            "interpreter_sha_not_prebound": True,
            "note": (
                "The first finalizer failed before postrun creation because the frozen source root "
                "was absent from sys.path. The only recovery changed PYTHONPATH, not source or "
                "extractor semantics. The outer wrapper later misreported exit 1 after finalizer "
                "completion. The interpreter identity was verified but its SHA was not pre-bound."
            ),
        },
        "privacy_status": privacy["status"],
        "source_hashes": {name: EXPECTED[name] for name in EXPECTED},
        "claim_boundaries": draft["claim_boundaries"],
    }
    write_new(review_path, review)

    evidence_node = {
        "id": "evidence:g013",
        "kind": "evidence",
        "statement": (
            "G13 completed one frozen 56-task formal run at 31/56 strict. No model-authored "
            "record, accepted record, directive, view, or post-directive action was observed, "
            "so all pre-registered mechanism endpoints remain untested."
        ),
        "frozen_task_count": 56,
        "ended_count": 56,
        "completed_count": 52,
        "timeout_failure_count": 4,
        "other_terminal_failure_count": 0,
        "strict_pass_count": 31,
        "strict_pass_rate_all": round(31 / 56, 6),
        "known_strict_fail_count": 18,
        "strict_verdict_missing_completed_count": 3,
        "score_policy": "completed_and_strict_true_over_all_56;timeout_is_failure",
        "query_wall_timeout_sec": 1200,
        "workers": 4,
        "same_dataset_family_serialized": True,
        "specialized_signal_kind": "requirement_observation_coverage",
        "specialized_status": "untested",
        "mechanism_endpoints": draft["draft_endpoint_status"],
        "limits": [
            "No model-authored record, accepted record, directive, view, or post-directive action was observed; the mechanism is untested.",
            "The 31/56 score is one unpaired descriptive outcome and is not a causal or benefit claim.",
            "Structural coverage is non-semantic and does not establish support, relevance, correctness, completeness, or truth.",
            "Three completed strict verdicts remain unknown and are not reclassified.",
            "The four runner wall timeouts remain failures in the fixed 56 denominator.",
            "The recovery interpreter SHA was verified after execution rather than pre-bound; this procedural limitation is retained in the independent review.",
        ],
        "artifact_refs": {
            **{f"{name}_sha256": value for name, value in EXPECTED.items() if name != "previous_memory"},
            "independent_review_sha256": digest(review_path),
        },
    }
    evidence = {
        "schema_version": "dab_research_graph_evidence_v2",
        "generation": 13,
        "status": "independently_validated",
        "node": evidence_node,
    }
    write_new(evidence_path, evidence)

    target = contract["research_target"]
    formal = contract["formal_spec"]
    mechanism_id = contract["mechanism_id"]
    binding = {
        "generation": 13,
        "mechanism_id": mechanism_id,
        "research_target_id": "research_target:g013:003",
        "contract_selected_target_id": contract["selected_target_id"],
        "research_contract_sha256": EXPECTED["contract"],
        "parent_generation": formal["code_parent"]["generation"],
        "parent_tree_sha256": formal["code_parent"]["candidate_tree_sha256"],
        "candidate_tree_sha256": "31277b0514798b52b7547bb5cc12900c63d556fca0fc4919bff0b8be4902322c",
        "implementation_manifest_sha256": EXPECTED["implementation"],
        "runtime_admission_sha256": EXPECTED["admission"],
        "task_manifest_sha256": "576a7d718bbe54d94ce6b7c32b92530394f55b39865d718a376320a5b11d51f7",
        "task_count": 56,
        "query_timeout_sec": 1200,
        "description_mode": "base_no_hint",
        "workers": 4,
        "same_dataset_family_serialized": True,
    }
    problem_node = {
        "id": "problem:g013",
        "kind": "problem",
        "mechanism_id": mechanism_id,
        "statement": target["problem"],
        "why_now": target["why_now"],
    }
    hypothesis_node = {
        "id": "hypothesis:g013",
        "kind": "hypothesis",
        "mechanism_id": mechanism_id,
        "statement": formal["hypothesis"],
        "claim_boundaries": formal["measurement_plan"]["claim_boundaries"],
    }
    experiment_node = {
        "id": "experiment:g013",
        "kind": "experiment",
        "mechanism_id": mechanism_id,
        "statement": "One frozen base/no-hint 56-task formal evaluation of requirement-observation coverage.",
        "candidate_source_tree_sha256": binding["candidate_tree_sha256"],
        "evaluation_run_id": outcome["run_id"],
        "binding": binding,
        "measurement_plan": formal["measurement_plan"],
    }
    graph = {
        "schema_version": "dab_research_graph_generation_v1",
        "generation": 13,
        "status": "four_nodes_complete",
        "pre_execution_sha256": read(PATHS["closure_draft"])["pre_execution_sha256"],
        "evidence_sha256": digest(evidence_path),
        "independent_review_sha256": digest(review_path),
        "binding": binding,
        "nodes": [problem_node, hypothesis_node, experiment_node, evidence_node],
        "edges": [
            {"source": "problem:g013", "target": "evidence:g012", "relation": "motivated_by"},
            {"source": "hypothesis:g013", "target": "problem:g013", "relation": "explains"},
            {"source": "experiment:g013", "target": "hypothesis:g013", "relation": "tests"},
            {"source": "experiment:g013", "target": "experiment:g007", "relation": "derives_code_from"},
            {"source": "evidence:g013", "target": "experiment:g013", "relation": "observes"},
            {"source": "evidence:g013", "target": "hypothesis:g013", "relation": "tests"},
        ],
    }
    write_new(graph_path_out, graph)
    persisted = read(graph_path_out)
    require(
        persisted["status"] == "four_nodes_complete"
        and [node["kind"] for node in persisted["nodes"]]
        == ["problem", "hypothesis", "experiment", "evidence"]
        and persisted["evidence_sha256"] == digest(evidence_path),
        "G13 four-node Graph verification failed",
    )

    promotion = {
        "source": "research_target:g013:003",
        "relation": "promoted_to",
        "target": "experiment:g013",
    }
    require(promotion not in previous["cross_layer_edges"], "G13 promotion already exists")
    formal_paths = {
        row["generation"]: ROOT / row["graph"]["path"]
        for row in previous["formal_evolution_layer"]["generation_refs"]
    }
    formal_hashes = {
        row["generation"]: row["graph"]["sha256"]
        for row in previous["formal_evolution_layer"]["generation_refs"]
    }
    formal_paths[13] = graph_path_out
    formal_hashes[13] = digest(graph_path_out)
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
        == list(range(14))
        and memory["research_incubation_layer"] == previous["research_incubation_layer"]
        and memory["cross_layer_edges"][:-1] == previous["cross_layer_edges"]
        and memory["cross_layer_edges"][-1] == promotion,
        "G13 append-only memory verification failed",
    )
    write_new(OUT_MEMORY, memory)

    closure_receipt = {
        "schema_version": "g013_graph_closure_receipt_v1",
        "generation": 13,
        "status": "four_nodes_complete_and_memory_appended",
        "review_sha256": digest(review_path),
        "evidence_sha256": digest(evidence_path),
        "graph_sha256": digest(graph_path_out),
        "previous_memory_sha256": EXPECTED["previous_memory"],
        "memory_sha256": digest(OUT_MEMORY),
        "formal_generations": list(range(14)),
        "incubation_node_count": len(previous["research_incubation_layer"]["nodes"]),
        "incubation_edge_count": len(previous["research_incubation_layer"]["edges"]),
        "promotion_edge": promotion,
        "privacy_status": "passed",
        "recovery_attempt_count": 1,
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
        "formal_generations": list(range(14)),
        "promotion_edge": promotion,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
