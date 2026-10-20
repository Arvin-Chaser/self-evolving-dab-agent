import json
from pathlib import Path
from unittest.mock import patch

from experiments import dab_roadmap_protocol as graph


def test_repair_branch_links_are_content_bound(tmp_path: Path):
    branch = tmp_path / "gen015_composition_cap_r1"
    branch.mkdir()
    paths = {name: branch / f"{name}.json" for name in (
        "candidate_ref", "terminal_audit", "evaluation_result", "mechanism_evidence", "detailed_review")}
    ref = {
        "branch_id": branch.name,
        "branch_of_node_id": "gen_015_two_phase_frozen_evidence_handoff",
        "source_tree_sha256": "source", "parent_source_tree_sha256": "parent",
        "repair_delta_sha256": "delta", "changed_files": ["experiments/phase_evidence_handoff.py"],
    }
    for name, path in paths.items():
        path.write_text(json.dumps(ref if name == "candidate_ref" else {"name": name}), encoding="utf-8")
    record = {
        "schema": "dab_engineering_repair_branch_v1", "node_id": "repair_gen015_composition_cap_r1",
        "generation": 15, "branch_of_node_id": ref["branch_of_node_id"],
        "main_head_at_append_sha256": "main", "previous_branch_record_sha256": None,
        "parent_edges": [{"node_id": ref["branch_of_node_id"], "role": "code_base"}],
        "candidate": {key: ref[key] for key in (
            "source_tree_sha256", "parent_source_tree_sha256", "repair_delta_sha256", "changed_files")},
        "detail_links": {name: str(path) for name, path in paths.items()},
        "repair_ref_sha256": graph.sha256_file(paths["candidate_ref"]),
        "terminal_audit_sha256": graph.sha256_file(paths["terminal_audit"]),
        "evaluation_result_sha256": graph.sha256_file(paths["evaluation_result"]),
        "mechanism_evidence_sha256": graph.sha256_file(paths["mechanism_evidence"]),
        "diagnosis_response_sha256": graph.sha256_file(paths["detailed_review"]),
    }
    record["record_sha256"] = graph.record_hash(record)
    main = [{"node_id": ref["branch_of_node_id"], "generation": 15, "record_sha256": "main"}]
    with patch.object(graph, "load_repair_branches", return_value=[record]):
        assert graph.verify_repair_branches(tmp_path, main)["ok"]
        paths["detailed_review"].write_text('{"changed": true}', encoding="utf-8")
        result = graph.verify_repair_branches(tmp_path, main)
        assert not result["ok"]
        assert "repair branch 1: detailed_review missing or changed" in result["errors"]


def test_second_repair_branch_binds_its_actual_code_parent(tmp_path: Path):
    main_id = "gen_015_two_phase_frozen_evidence_handoff"
    cap_id = "repair_gen015_composition_cap_r1"
    reach_id = "repair_gen015_handoff_reach_r1"
    records = []
    for index, (node_id, branch_id, source, parent_source) in enumerate((
        (cap_id, "gen015_composition_cap_r1", "cap-tree", "original-tree"),
        (reach_id, "gen015_handoff_reach_r1", "reach-tree", "cap-tree"),
    )):
        branch = tmp_path / branch_id
        branch.mkdir()
        paths = {name: branch / f"{name}.json" for name in (
            "candidate_ref", "terminal_audit", "evaluation_result", "mechanism_evidence", "detailed_review")}
        ref = {"branch_id": branch_id, "branch_of_node_id": main_id,
               "source_tree_sha256": source, "parent_source_tree_sha256": parent_source,
               "repair_delta_sha256": f"delta-{index}", "changed_files": ["experiments/phase_evidence_handoff.py"]}
        if index:
            ref["code_parent_branch_node_id"] = cap_id
        for name, path in paths.items():
            path.write_text(json.dumps(ref if name == "candidate_ref" else {"name": name}), encoding="utf-8")
        record = {
            "schema": "dab_engineering_repair_branch_v2" if index else "dab_engineering_repair_branch_v1",
            "node_id": node_id, "generation": 15, "branch_of_node_id": main_id,
            "main_head_at_append_sha256": "main",
            "previous_branch_record_sha256": records[-1]["record_sha256"] if records else None,
            "parent_edges": ([{"node_id": cap_id, "role": "code_base"},
                              {"node_id": main_id, "role": "intent_base"}] if index else
                             [{"node_id": main_id, "role": "code_base"}]),
            "candidate": {key: ref[key] for key in (
                "source_tree_sha256", "parent_source_tree_sha256", "repair_delta_sha256", "changed_files")},
            "detail_links": {name: str(path) for name, path in paths.items()},
            "repair_ref_sha256": graph.sha256_file(paths["candidate_ref"]),
            "terminal_audit_sha256": graph.sha256_file(paths["terminal_audit"]),
            "evaluation_result_sha256": graph.sha256_file(paths["evaluation_result"]),
            "mechanism_evidence_sha256": graph.sha256_file(paths["mechanism_evidence"]),
            "diagnosis_response_sha256": graph.sha256_file(paths["detailed_review"]),
        }
        if index:
            record["code_parent_branch_node_id"] = cap_id
        record["record_sha256"] = graph.record_hash(record)
        records.append(record)
    main = [{"node_id": main_id, "generation": 15, "record_sha256": "main"}]
    with patch.object(graph, "load_repair_branches", return_value=records):
        assert graph.verify_repair_branches(tmp_path, main)["ok"]
        records[1]["candidate"]["parent_source_tree_sha256"] = "unrelated-tree"
        records[1]["record_sha256"] = graph.record_hash(records[1])
        result = graph.verify_repair_branches(tmp_path, main)
        assert not result["ok"]
        assert "repair branch 2: repair code parent lineage mismatch" in result["errors"]
