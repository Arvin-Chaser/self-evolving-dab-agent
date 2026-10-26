#!/usr/bin/env python3
"""Append-only graph protocol for DAB harness evolution.

This module separates six boundaries that were previously mixed inside
campaign-specific runners:

1. diagnose a completed generation with a standardized causal chain;
2. generate a sealed pool of competing mechanism-level intents;
3. independently select one pool member without rewriting it;
4. bind an admitted source candidate to that sealed intent;
5. record a fixed-batch DAB result without rewriting prior generations; and
6. append the compact diagnosis and immutable detail links to the roadmap.

Meta-agent invocations use Codex CLI with no subprocess wall-clock deadline.
Benchmark execution is deliberately external: run the admitted candidate's
``experiments/run_multi_query_baseline.py`` and then record its summary here.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import intent_candidate_workspace as candidate_workspace
from experiments.intent_candidate_workspace import canonical_hash, source_tree_hash
from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.dab_result_health import provider_failure
from experiments import dab_meta_detail_context_v1 as detail_context
from experiments.extract_dab_mechanism_evidence_v1 import build_card as build_mechanism_evidence_card_v1
from experiments.extract_gen009_shape_evidence import build_card as build_gen009_shape_evidence_card
from experiments.extract_dab_mechanism_evidence_v2 import build_card as build_mechanism_evidence_card_v2
from experiments.extract_dab_mechanism_evidence_v3 import build_card as build_mechanism_evidence_card_v3
from experiments.extract_gen001_evidence_grounded_gate_card import build_card as build_gen001_mechanism_evidence_card
from experiments.extract_gen002_tool_economy_card import build_card as build_gen002_mechanism_evidence_card
from experiments.gen003_tool_error_evidence import build_card as build_gen003_mechanism_evidence_card
from experiments.gen004_ledger_evidence import build_card as build_gen004_mechanism_evidence_card
from experiments.gen005_trajectory_evidence import build_card as build_gen005_mechanism_evidence_card
from experiments.gen006_protocol_channel_evidence import build_card as build_gen006_mechanism_evidence_card
from experiments.gen007_budget_governor_evidence import build_card as build_gen007_mechanism_evidence_card
from experiments.gen008_divergence_evidence import build_card as build_gen008_mechanism_evidence_card
from experiments.extract_gen010_grain_evidence import build_card as build_gen010_grain_evidence_card
from experiments.extract_gen011_divergence_evidence import build_card as build_gen011_divergence_evidence_card
from experiments.extract_gen012_obligation_evidence import build_card as build_gen012_obligation_evidence_card
from experiments.extract_gen013_grounding_evidence import build_card as build_gen013_grounding_evidence_card
from experiments.extract_gen014_recovery_evidence import build_card as build_gen014_recovery_evidence_card
from experiments.extract_gen015_handoff_evidence import build_card as build_gen015_handoff_evidence_card
from experiments.extract_gen016_digest_evidence import build_card as build_gen016_digest_evidence_card
from experiments.extract_gen017_referent_evidence import build_card as build_gen017_referent_evidence_card
from experiments.extract_gen018_tool_call_repair_evidence import build_card as build_gen018_tool_call_repair_evidence_card
from experiments.extract_gen019_empirical_repair_evidence import build_card as build_gen019_empirical_repair_evidence_card


SCHEMA_VERSION = "dab_roadmap_evolution_v002"
META_PROTOCOL_VERSION = "causal_diagnosis_competing_intents_v001"
ROOT_NODE_ID = "root_baseline"
MECHANISM_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
OUTCOME_LABELS = {
    "unimplemented",
    "implemented_not_integrated",
    "integrated_not_activated",
    "activated_no_behavioral_effect",
    "behavior_changed_no_task_gain",
    "effective",
    "contradicted",
    "inconclusive",
}
PARENT_ROLES = {"code_base", "mechanism_donor", "failure_evidence", "complementary_parent"}
SOURCE_REUSE_RECOMMENDATIONS = {"eligible_as_base", "evidence_only", "avoid"}

INTENT_FIELDS = (
    "decision",
    "primary_dimension",
    "target_component",
    "mechanism_key",
    "observed_prior_limitation",
    "proposed_mechanism",
    "planned_tool_control_flow_changes",
    "expected_behavioral_change",
    "validation_expectations",
    "fallback_or_bounding_rule",
    "potential_regressions",
    "novelty_claim",
)

REVIEW_FIELDS = (
    "outcome_label",
    "source_reuse_recommendation",
    "intent_realization",
    "activation_evidence",
    "behavioral_effect",
    "task_effect",
    "short_review",
    "failure_mechanism_key",
    "evidence_refs",
    "relations_to_prior",
    "causal_diagnosis",
)

CAUSAL_LINKS = (
    "opportunity",
    "integration",
    "activation",
    "delivery",
    "model_uptake",
    "downstream_behavior",
    "task_effect",
)
CAUSAL_LINK_STATUSES = {"positive", "measured_zero", "unknown", "confounded"}
CAUSAL_BOUNDARIES = {*CAUSAL_LINKS, "no_observed_failure", "undetermined"}
HYPOTHESIS_ID_RE = re.compile(r"^h[1-9][0-9]{0,2}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def require_new(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite immutable artifact: {path}")


def campaign_paths(campaign_root: Path) -> tuple[Path, Path, Path]:
    return (
        campaign_root / "campaign.json",
        campaign_root / "campaign_state.json",
        campaign_root / "roadmap.jsonl",
    )


def load_campaign(campaign_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign_path, state_path, _ = campaign_paths(campaign_root)
    from experiments.dab_api_routing import meta_route
    campaign = read_json(campaign_path)
    campaign['meta_agent'] = meta_route(campaign['meta_agent'])
    return campaign, read_json(state_path)


def generation_dir(campaign_root: Path, generation: int) -> Path:
    return campaign_root / "generations" / f"gen_{generation:03d}"


def root_node_path(campaign_root: Path) -> Path:
    return campaign_root / "root_node.json"


def materialize_root_node(campaign_root: Path, source_root: Path, result_path: Path | None) -> dict[str, Any]:
    """Freeze the initial bounded source tree as a selectable graph root."""
    destination = campaign_root / "root" / "repo"
    if destination.exists():
        raise SystemExit(f"Root source snapshot already exists: {destination}")
    destination.mkdir(parents=True)
    for source in candidate_workspace.source_paths(source_root):
        relative = source.relative_to(source_root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    upstream = source_root / "external/DataAgentBench_official/common_scaffold/DataAgent.py"
    if upstream.is_file() and not upstream.is_symlink():
        target = destination / "external/DataAgentBench_official/common_scaffold/DataAgent.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(upstream, target)
    descriptor = {
        "schema_version": SCHEMA_VERSION,
        "node_id": ROOT_NODE_ID,
        "kind": "initial_root",
        "source_root": str(destination),
        "source_tree_sha256": source_tree_hash(destination),
        "result_path": str(result_path.resolve()) if result_path else None,
        "materialized_at": utc_now(),
    }
    write_json(root_node_path(campaign_root), descriptor)
    return descriptor


def load_root_node(campaign_root: Path) -> dict[str, Any]:
    path = root_node_path(campaign_root)
    if not path.is_file():
        raise SystemExit(f"Graph root is missing; migrate the campaign first: {path}")
    return read_json(path)


def selectable_parent_descriptors(campaign_root: Path) -> dict[str, dict[str, Any]]:
    """Return every graph node that can inform or materialize a child."""
    root = load_root_node(campaign_root)
    result_path = Path(root["result_path"]) if root.get("result_path") else None
    root_result = compact_result(read_json(result_path)) if result_path and result_path.is_file() else None
    descriptors: dict[str, dict[str, Any]] = {
        ROOT_NODE_ID: {
            "node_id": ROOT_NODE_ID,
            "generation": 0,
            "kind": "initial_root",
            "source_root": root["source_root"],
            "source_tree_sha256": root["source_tree_sha256"],
            "source_available": Path(root["source_root"]).is_dir(),
            "result_path": root.get("result_path"),
            "result": root_result,
            "outcome_label": "baseline",
        }
    }
    for record in load_roadmap(campaign_root):
        candidate_ref_path = Path(record.get("detail_links", {}).get("candidate_ref") or "")
        candidate = read_json(candidate_ref_path) if candidate_ref_path.is_file() else {}
        repo = Path(candidate.get("repo") or "")
        descriptors[record["node_id"]] = {
            "node_id": record["node_id"],
            "generation": record["generation"],
            "kind": "generation",
            "source_root": str(repo) if candidate else None,
            "source_tree_sha256": record.get("candidate", {}).get("source_tree_sha256"),
            "source_available": bool(candidate and repo.is_dir()),
            "result_path": record.get("detail_links", {}).get("batch_summary"),
            "result": record.get("result"),
            "evaluation_binding": record.get("evaluation_binding", {}),
            "outcome_label": record.get("review", {}).get("outcome_label"),
            "source_reuse_recommendation": record.get("review", {}).get("source_reuse_recommendation"),
            "legacy_parent_decision": record.get("review", {}).get("parent_decision"),
            "mechanism_key": record.get("intent", {}).get("mechanism_key"),
            "short_review": record.get("review", {}).get("short_review"),
            "detail_links": record.get("detail_links", {}),
        }
    for record in load_repair_branches(campaign_root):
        ref_path = Path(record["detail_links"]["candidate_ref"])
        ref = read_json(ref_path)
        repo = Path(ref["repo"])
        descriptors[record["node_id"]] = {
            "node_id": record["node_id"], "generation": record["generation"],
            "kind": "engineering_repair_branch", "source_root": str(repo),
            "source_tree_sha256": record["candidate"]["source_tree_sha256"],
            "source_available": repo.is_dir(),
            "result_path": record["detail_links"]["evaluation_result"],
            "result": record["result"], "evaluation_binding": record["evaluation_binding"],
            "outcome_label": record["review"]["outcome_label"],
            "source_reuse_recommendation": record["review"]["source_reuse_recommendation"],
            "mechanism_key": record["intent"]["mechanism_key"],
            "short_review": record["review"]["short_review"],
            "detail_links": record["detail_links"],
        }
    return descriptors


def resolve_materialization_parent(campaign_root: Path, node_id: str) -> dict[str, Any]:
    descriptor = selectable_parent_descriptors(campaign_root).get(node_id)
    if descriptor is None:
        raise SystemExit(f"Unknown graph parent: {node_id}")
    source_root = Path(descriptor.get("source_root") or "")
    if not descriptor.get("source_available") or not source_root.is_dir():
        raise SystemExit(f"Selected code-base parent has no available source tree: {node_id}")
    actual_hash = source_tree_hash(source_root)
    if actual_hash != descriptor.get("source_tree_sha256"):
        raise SystemExit(f"Selected code-base parent source changed: {node_id}")
    return descriptor


def load_roadmap(campaign_root: Path) -> list[dict[str, Any]]:
    _, _, roadmap_path = campaign_paths(campaign_root)
    if not roadmap_path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(roadmap_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Roadmap line {line_number} is not an object")
        records.append(value)
    return records


def load_repair_branches(campaign_root: Path) -> list[dict[str, Any]]:
    path = campaign_root / "repair_branches/branch_graph.jsonl"
    if not path.is_file():
        return []
    records = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Repair branch line {index} is not an object")
            records.append(value)
    return records


def verify_repair_branches(campaign_root: Path, main_records: list[dict[str, Any]]) -> dict[str, Any]:
    branches = load_repair_branches(campaign_root)
    main_nodes = {record["node_id"] for record in main_records}
    main_hashes = {record["record_sha256"] for record in main_records}
    seen = set(main_nodes) | {ROOT_NODE_ID}
    previous = None
    prior_branches: dict[str, dict[str, Any]] = {}
    errors = []
    for index, record in enumerate(branches, start=1):
        label = f"repair branch {index}"
        node = record.get("node_id")
        parent = record.get("branch_of_node_id")
        schema = record.get("schema")
        if schema not in {"dab_engineering_repair_branch_v1", "dab_engineering_repair_branch_v2"}:
            errors.append(f"{label}: invalid schema")
        if not isinstance(node, str) or not node or node in seen:
            errors.append(f"{label}: missing or duplicate node_id")
        if parent not in main_nodes:
            errors.append(f"{label}: unknown mainline parent")
        elif record.get("generation") != next(
                item["generation"] for item in main_records if item["node_id"] == parent):
            errors.append(f"{label}: repair generation differs from parent")
        if record.get("main_head_at_append_sha256") not in main_hashes:
            errors.append(f"{label}: mainline anchor missing")
        if record.get("previous_branch_record_sha256") != previous:
            errors.append(f"{label}: previous branch hash mismatch")
        if record.get("record_sha256") != record_hash(record):
            errors.append(f"{label}: record hash mismatch")
        edges = record.get("parent_edges")
        if schema == "dab_engineering_repair_branch_v2":
            code_parent = record.get("code_parent_branch_node_id")
            prior = prior_branches.get(code_parent)
            if prior is None:
                errors.append(f"{label}: unknown earlier repair code parent")
            elif (prior.get("branch_of_node_id") != parent
                    or prior.get("candidate", {}).get("source_tree_sha256")
                    != record.get("candidate", {}).get("parent_source_tree_sha256")):
                errors.append(f"{label}: repair code parent lineage mismatch")
            if edges != [{"node_id": code_parent, "role": "code_base"},
                         {"node_id": parent, "role": "intent_base"}]:
                errors.append(f"{label}: repair parent edges mismatch")
        elif edges != [{"node_id": parent, "role": "code_base"}]:
            errors.append(f"{label}: repair must have its original code-base parent")
        ref_path = Path(record.get("detail_links", {}).get("candidate_ref") or "")
        if not ref_path.is_file() or sha256_file(ref_path) != record.get("repair_ref_sha256"):
            errors.append(f"{label}: repair reference missing or changed")
        else:
            ref = read_json(ref_path)
            candidate = record.get("candidate", {})
            if (ref.get("branch_of_node_id") != parent
                    or ref.get("branch_id") != Path(ref_path).parent.name
                    or ref.get("source_tree_sha256") != candidate.get("source_tree_sha256")
                    or ref.get("parent_source_tree_sha256") != candidate.get("parent_source_tree_sha256")
                    or ref.get("repair_delta_sha256") != candidate.get("repair_delta_sha256")
                    or ref.get("changed_files") != candidate.get("changed_files")):
                errors.append(f"{label}: repair source binding mismatch")
            if (schema == "dab_engineering_repair_branch_v2"
                    and ref.get("code_parent_branch_node_id") != record.get("code_parent_branch_node_id")):
                errors.append(f"{label}: repair code parent reference mismatch")
        for link, digest in (("terminal_audit", "terminal_audit_sha256"),
                             ("evaluation_result", "evaluation_result_sha256"),
                             ("mechanism_evidence", "mechanism_evidence_sha256"),
                             ("detailed_review", "diagnosis_response_sha256")):
            path = Path(record.get("detail_links", {}).get(link) or "")
            if not path.is_file() or sha256_file(path) != record.get(digest):
                errors.append(f"{label}: {link} missing or changed")
        if isinstance(node, str):
            seen.add(node)
            prior_branches[node] = record
        previous = record.get("record_sha256")
    return {"ok": not errors, "record_count": len(branches),
            "head_record_sha256": previous, "errors": errors}


def record_hash(record: dict[str, Any]) -> str:
    payload = dict(record)
    payload.pop("record_sha256", None)
    return sha256_text(canonical_json(payload))


def verify_roadmap(campaign_root: Path) -> dict[str, Any]:
    records = load_roadmap(campaign_root)
    errors: list[str] = []
    previous_hash: str | None = None
    seen_nodes: set[str] = {ROOT_NODE_ID}
    for index, record in enumerate(records, start=1):
        if record.get("generation") != index:
            errors.append(f"line {index}: generation is not contiguous")
        if record.get("previous_record_sha256") != previous_hash:
            errors.append(f"line {index}: previous hash mismatch")
        actual_hash = record_hash(record)
        if record.get("record_sha256") != actual_hash:
            errors.append(f"line {index}: record hash mismatch")
        node_id = str(record.get("node_id") or "")
        if not node_id or node_id in seen_nodes:
            errors.append(f"line {index}: missing or duplicate node_id")
        edges = record.get("parent_edges")
        if edges is not None:
            if not isinstance(edges, list) or not edges:
                errors.append(f"line {index}: parent_edges must be a nonempty list")
            else:
                code_base_count = 0
                for edge in edges:
                    if not isinstance(edge, dict):
                        errors.append(f"line {index}: malformed parent edge")
                        continue
                    if edge.get("node_id") not in seen_nodes:
                        errors.append(f"line {index}: parent edge references unknown or future node")
                    if edge.get("role") not in PARENT_ROLES:
                        errors.append(f"line {index}: invalid parent role")
                    code_base_count += edge.get("role") == "code_base"
                if code_base_count != 1:
                    errors.append(f"line {index}: exactly one code_base edge is required")
        seen_nodes.add(node_id)
        previous_hash = actual_hash
    branches = verify_repair_branches(campaign_root, records)
    errors.extend(branches["errors"])
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not errors,
        "record_count": len(records),
        "head_record_sha256": previous_hash,
        "repair_branch_count": branches["record_count"],
        "repair_branch_head_sha256": branches["head_record_sha256"],
        "errors": errors,
    }


def build_snapshot(campaign_root: Path) -> dict[str, Any]:
    campaign, state = load_campaign(campaign_root)
    verification = verify_roadmap(campaign_root)
    if not verification["ok"]:
        raise SystemExit("Roadmap verification failed: " + "; ".join(verification["errors"]))
    records = load_roadmap(campaign_root)
    repair_branches = load_repair_branches(campaign_root)
    mechanism_index: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record["intent"]["mechanism_key"]
        entry = mechanism_index.setdefault(
            key,
            {"attempt_count": 0, "generations": [], "latest_outcome": None, "latest_node_id": None},
        )
        entry["attempt_count"] += 1
        entry["generations"].append(record["generation"])
        entry["latest_outcome"] = record["review"]["outcome_label"]
        entry["latest_node_id"] = record["node_id"]
    for record in repair_branches:
        key = record["intent"]["mechanism_key"]
        entry = mechanism_index.setdefault(
            key, {"attempt_count": 0, "generations": [], "latest_outcome": None, "latest_node_id": None})
        entry["attempt_count"] += 1
        entry["generations"].append(record["generation"])
        entry["latest_outcome"] = record["review"]["outcome_label"]
        entry["latest_node_id"] = record["node_id"]
    root = load_root_node(campaign_root)
    parents = selectable_parent_descriptors(campaign_root)
    latest_result_path = state.get("active_result") or (
        records[-1].get("detail_links", {}).get("evaluation_result") if records else None
    )
    if latest_result_path and Path(latest_result_path).is_file():
        latest_result = visible_result(read_json(Path(latest_result_path)))
    else:
        latest_result = {"generation": 0, "summary": compact_metrics(parents[ROOT_NODE_ID].get("result") or {})}
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "next_generation": state["next_generation"],
        "context_policy": "compact_result_graph_v1",
        "latest_result": latest_result,
        "root_node": compact_parent_descriptor(parents[ROOT_NODE_ID]),
        "selectable_parents": [
            {key: item.get(key) for key in ("node_id", "source_available", "source_tree_sha256")}
            for item in parents.values()
        ],
        "nodes": [compact_graph_node(record) for record in records + repair_branches],
        "repair_branch_count": verification["repair_branch_count"],
        "repair_branch_head_sha256": verification["repair_branch_head_sha256"],
        "mechanism_index": mechanism_index,
        "selection_policy": {
            "selector": "meta_agent",
            "minimum_parents": 1,
            "one_materialization_base_required": True,
            "multiple_evidence_or_mechanism_parents_allowed": True,
            "review_recommendations_are_nonbinding": True,
        },
        "roadmap_head_sha256": verification["head_record_sha256"],
        "root_node_sha256": sha256_file(root_node_path(campaign_root)),
    }
    policy_path = campaign_root / "runtime_execution_policy.json"
    if policy_path.is_file():
        policy = read_json(policy_path)
        snapshot["execution_environment"] = {key: policy[key] for key in (
            "repair_policy", "input_policy", "workers", "overlay_contract", "concurrency_causality_status",
        ) if key in policy}
        if policy.get("required_parent_generation") == state["next_generation"]:
            snapshot["selection_policy"]["human_required_parent_nodes"] = policy.get("required_parent_nodes", [])
    if detail_context.active_policy(campaign_root):
        snapshot["context_policy"] = detail_context.POLICY
        snapshot["safe_detail_access"] = safe_detail_catalog(campaign_root, campaign, records)
    snapshot = strip_f1_context(snapshot)
    snapshot["snapshot_sha256"] = sha256_text(canonical_json(snapshot))
    return snapshot


def safe_detail_catalog(campaign_root: Path, campaign: dict[str, Any],
                        records: list[dict[str, Any]]) -> dict[str, Any]:
    """Index safe views, without eagerly expanding their prose in model prompts."""
    nodes = []
    for record in records:
        entry = {"node_id": record["node_id"], "generation": record["generation"]}
        try:
            value = detail_context.build_detail(campaign_root, campaign, record,
                compact_metrics(record.get("result", {})),
                compact_evaluation_binding(record.get("evaluation_binding", {})))
            entry.update({"status": "available", "safe_mechanism_detail": str(detail_context.detail_path(campaign_root, value)),
                          "sha256": detail_context.digest(detail_context.encoded(value)),
                          "bytes": len(detail_context.encoded(value))})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Do not silently fall back to raw archives or echo unsafe file text.
            entry.update({"status": "unavailable_or_invalid", "failure_class": type(exc).__name__})
        nodes.append(entry)
    return {"schema_version": detail_context.SCHEMA, "mode": "on_demand_safe_files",
            "original_archives_readable": False, "nodes": nodes}


def materialize_safe_details(campaign_root: Path, snapshot: dict[str, Any]) -> None:
    """New content-addressed context files only; existing generations stay intact."""
    access = snapshot.get("safe_detail_access")
    if not access:
        return
    campaign, _ = load_campaign(campaign_root)
    records = {record["node_id"]: record for record in load_roadmap(campaign_root)}
    pending = []
    for entry in access["nodes"]:
        if entry["status"] != "available":
            continue
        record = records[entry["node_id"]]
        value = detail_context.build_detail(campaign_root, campaign, record,
            compact_metrics(record.get("result", {})),
            compact_evaluation_binding(record.get("evaluation_binding", {})))
        raw = detail_context.encoded(value)
        destination = detail_context.detail_path(campaign_root, value)
        if detail_context.digest(raw) != entry["sha256"] or str(destination) != entry["safe_mechanism_detail"]:
            raise ValueError("Safe detail changed after the snapshot was built")
        # Validate all destinations before any writes. Never rewrite a prior view.
        if destination.parent.is_symlink() or destination.is_symlink():
            raise ValueError("Symlinked safe detail destination")
        if destination.exists() and destination.read_bytes() != raw:
            raise ValueError("Existing immutable safe detail was modified")
        pending.append((destination, raw))
    for destination, raw in pending:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            with destination.open("xb") as handle:
                handle.write(raw)


def short_text(value: Any, limit: int = 400) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…"


def compact_metrics(value: dict[str, Any]) -> dict[str, Any]:
    """Explicit allowlist prevents historical result details leaking forward."""
    return {key: value[key] for key in (
        "query_count", "strict_pass_count", "strict_evaluated_count",
        "final_answer_nonempty_count",
        "run_error_count", "nonzero_exit_count", "strict_pass_delta",
        "provider_error_count",
    ) if key in value and (value[key] is None or isinstance(value[key], (int, float)))}


def compact_parent_descriptor(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": item["node_id"], "generation": item["generation"],
        "source_available": item.get("source_available", False),
        "source_tree_sha256": item.get("source_tree_sha256"),
        "result": compact_metrics(item.get("result") or {}),
        "outcome_label": item.get("outcome_label"),
        "evaluation_binding": compact_evaluation_binding(item.get("evaluation_binding", {})),
    }


def compact_graph_node(record: dict[str, Any]) -> dict[str, Any]:
    intent, review = record.get("intent", {}), record.get("review", {})
    node = {
        "node_id": record["node_id"], "generation": record["generation"],
        "parent_edges": [{"node_id": edge.get("node_id"), "role": edge.get("role")}
                         for edge in record.get("parent_edges", [])],
        "intent": {key: short_text(intent.get(key)) for key in (
            "mechanism_key", "primary_dimension", "target_component", "proposed_mechanism",
        )},
        "result": compact_metrics(record.get("result", {})),
        "evaluation_binding": compact_evaluation_binding(record.get("evaluation_binding", {})),
        "review": {key: short_text(review.get(key)) for key in (
            "outcome_label", "source_reuse_recommendation", "short_review", "failure_mechanism_key",
        )},
        # These are archival references, not instructions to expand their contents.
        "detail_links": {key: path for key, path in record.get("detail_links", {}).items()
                         if key in {"sealed_intent", "candidate_ref", "evaluation_result", "detailed_review"}},
    }
    if "mechanism_evidence" in record:
        # Historical cards may contain an invalid partial-overlap metric. Do not
        # expose even its label to future Meta prompts; activation counters and
        # other mechanism evidence remain available.
        node["mechanism_evidence"] = strip_f1_context(record["mechanism_evidence"])
    if isinstance(review.get("causal_diagnosis"), dict):
        node["causal_diagnosis"] = strip_f1_context(review["causal_diagnosis"])
    if isinstance(intent.get("competition_binding"), dict):
        node["intent_competition"] = strip_f1_context(intent["competition_binding"])
    if record.get("schema") in {"dab_engineering_repair_branch_v1", "dab_engineering_repair_branch_v2"}:
        node["kind"] = "engineering_repair_branch"
        node["branch_of_node_id"] = record["branch_of_node_id"]
        node["main_head_at_append_sha256"] = record["main_head_at_append_sha256"]
        if record.get("schema") == "dab_engineering_repair_branch_v2":
            node["code_parent_branch_node_id"] = record["code_parent_branch_node_id"]
    return node


def strip_f1_context(value: Any) -> Any:
    """Remove the retired F1 signal from all future Meta context."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if "f1" in str(key).lower():
                continue
            sanitized = strip_f1_context(item)
            if sanitized is not None:
                cleaned[key] = sanitized
        return cleaned
    if isinstance(value, list):
        cleaned = []
        for item in value:
            if isinstance(item, str) and re.search(r"\bf1\b", item, flags=re.IGNORECASE):
                continue
            sanitized = strip_f1_context(item)
            if sanitized is not None:
                cleaned.append(sanitized)
        return cleaned
    if isinstance(value, str) and re.search(r"\bf1\b", value, flags=re.IGNORECASE):
        clauses = [clause.strip() for clause in value.split(";")
                   if not re.search(r"\bf1\b", clause, flags=re.IGNORECASE)]
        return "; ".join(clauses) or None
    return value


def intent_output_schema() -> dict[str, Any]:
    string_fields = [
        "decision", "primary_dimension", "target_component", "mechanism_key",
        "observed_prior_limitation", "proposed_mechanism",
        "planned_tool_control_flow_changes", "expected_behavioral_change",
        "fallback_or_bounding_rule", "novelty_claim",
    ]
    properties: dict[str, Any] = {field: {"type": "string"} for field in string_fields}
    properties["decision"] = {"type": "string", "enum": ["change"]}
    properties["mechanism_key"] = {"type": "string", "maxLength": 80,
                                   "pattern": "^[a-z][a-z0-9_]{2,79}$"}
    properties["validation_expectations"] = {"type": "array", "items": {"type": "string"}, "minItems": 1}
    properties["potential_regressions"] = {"type": "array", "items": {"type": "string"}}
    properties["parent_selection"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["materialization_base_node_id", "parents", "synthesis_strategy", "selection_rationale"],
        "properties": {
            "materialization_base_node_id": {"type": "string"},
            "parents": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["node_id", "role", "use"],
                    "properties": {
                        "node_id": {"type": "string"},
                        "role": {"type": "string", "enum": sorted(PARENT_ROLES)},
                        "use": {"type": "string"},
                    },
                },
            },
            "synthesis_strategy": {"type": "string"},
            "selection_rationale": {"type": "string"},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [*INTENT_FIELDS, "parent_selection"],
        "properties": properties,
    }


def review_output_schema() -> dict[str, Any]:
    link_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "evidence", "interpretation"],
        "properties": {
            "status": {"type": "string", "enum": sorted(CAUSAL_LINK_STATUSES)},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "interpretation": {"type": "string"},
        },
    }
    properties: dict[str, Any] = {
        "outcome_label": {"type": "string", "enum": sorted(OUTCOME_LABELS)},
        "source_reuse_recommendation": {"type": "string", "enum": sorted(SOURCE_REUSE_RECOMMENDATIONS)},
        "intent_realization": {"type": "string"},
        "activation_evidence": {"type": "array", "items": {"type": "string"}},
        "behavioral_effect": {"type": "string"},
        "task_effect": {"type": "string"},
        "short_review": {"type": "string", "maxLength": 1200},
        "failure_mechanism_key": {"type": ["string", "null"]},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "relations_to_prior": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["node_id", "relation", "reason"],
                "properties": {
                    "node_id": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "enum": ["continues", "repairs", "refines", "contradicts", "supersedes", "independent"],
                    },
                    "reason": {"type": "string"},
                },
            },
        },
        "causal_diagnosis": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "links", "failure_boundary", "falsified_claims", "unsupported_claims",
                "excluded_equivalence_classes", "open_discriminators",
            ],
            "properties": {
                "links": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(CAUSAL_LINKS),
                    "properties": {link: link_schema for link in CAUSAL_LINKS},
                },
                "failure_boundary": {"type": "string", "enum": sorted(CAUSAL_BOUNDARIES)},
                "falsified_claims": {"type": "array", "items": {"type": "string"}},
                "unsupported_claims": {"type": "array", "items": {"type": "string"}},
                "excluded_equivalence_classes": {"type": "array", "items": {"type": "string"}},
                "open_discriminators": {"type": "array", "items": {"type": "string"}},
            },
        },
        "detailed_analysis": {"type": "string"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": [*REVIEW_FIELDS, "detailed_analysis"],
        "properties": properties,
    }


def hypothesis_pool_output_schema() -> dict[str, Any]:
    intent_schema = intent_output_schema()
    intent_schema = {
        key: value for key, value in intent_schema.items() if key != "$schema"
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["hypotheses"],
        "properties": {
            "hypotheses": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "hypothesis_id", "causal_hypothesis", "discriminating_prediction", "intent",
                    ],
                    "properties": {
                        "hypothesis_id": {"type": "string", "pattern": "^h[1-9][0-9]{0,2}$"},
                        "causal_hypothesis": {"type": "string"},
                        "discriminating_prediction": {"type": "string"},
                        "intent": intent_schema,
                    },
                },
            },
        },
    }


def intent_selection_output_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["selected_hypothesis_id", "comparative_assessment", "selection_rationale"],
        "properties": {
            "selected_hypothesis_id": {"type": "string", "pattern": "^h[1-9][0-9]{0,2}$"},
            "comparative_assessment": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "hypothesis_id", "decision", "evidence_fit", "discriminating_value",
                        "implementation_risk", "reason",
                    ],
                    "properties": {
                        "hypothesis_id": {"type": "string", "pattern": "^h[1-9][0-9]{0,2}$"},
                        "decision": {"type": "string", "enum": ["selected", "rejected"]},
                        "evidence_fit": {"type": "string"},
                        "discriminating_value": {"type": "string"},
                        "implementation_risk": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
            "selection_rationale": {"type": "string"},
        },
    }


def validate_intent(value: dict[str, Any]) -> list[str]:
    errors = [f"missing {field}" for field in INTENT_FIELDS if field not in value]
    for field in INTENT_FIELDS:
        if field in {"validation_expectations", "potential_regressions"}:
            continue
        if field in value and not str(value[field]).strip():
            errors.append(f"empty {field}")
    if value.get("decision") != "change":
        errors.append("decision must be change")
    if not MECHANISM_KEY_RE.fullmatch(str(value.get("mechanism_key") or "")):
        errors.append("mechanism_key must be a lowercase snake_case identifier")
    expectations = value.get("validation_expectations")
    if not isinstance(expectations, list) or not expectations or not all(isinstance(item, str) and item.strip() for item in expectations):
        errors.append("validation_expectations must be a nonempty string list")
    regressions = value.get("potential_regressions")
    if not isinstance(regressions, list) or not all(isinstance(item, str) for item in regressions):
        errors.append("potential_regressions must be a string list")
    selection = value.get("parent_selection")
    if not isinstance(selection, dict):
        errors.append("parent_selection must be an object")
        return errors
    parents = selection.get("parents")
    base = selection.get("materialization_base_node_id")
    if not isinstance(parents, list) or not parents:
        errors.append("parent_selection.parents must be nonempty")
        return errors
    ids: list[str] = []
    code_bases = 0
    for edge in parents:
        if not isinstance(edge, dict):
            errors.append("parent_selection contains a malformed edge")
            continue
        node_id = str(edge.get("node_id") or "")
        role = edge.get("role")
        if not node_id or role not in PARENT_ROLES or not str(edge.get("use") or "").strip():
            errors.append("each selected parent needs node_id, valid role, and nonempty use")
        ids.append(node_id)
        code_bases += role == "code_base"
    if len(ids) != len(set(ids)):
        errors.append("selected parent node IDs must be unique")
    if base not in ids:
        errors.append("materialization base must be included in parents")
    if code_bases != 1 or not any(edge.get("node_id") == base and edge.get("role") == "code_base" for edge in parents if isinstance(edge, dict)):
        errors.append("exactly one code_base parent must match materialization_base_node_id")
    if not str(selection.get("synthesis_strategy") or "").strip() or not str(selection.get("selection_rationale") or "").strip():
        errors.append("parent selection needs synthesis_strategy and selection_rationale")
    return errors


def validate_review(value: dict[str, Any], known_node_ids: set[str]) -> list[str]:
    errors = [f"missing {field}" for field in REVIEW_FIELDS if field not in value]
    if value.get("outcome_label") not in OUTCOME_LABELS:
        errors.append("invalid outcome_label")
    if value.get("source_reuse_recommendation") not in SOURCE_REUSE_RECOMMENDATIONS:
        errors.append("invalid source_reuse_recommendation")
    if not str(value.get("short_review") or "").strip():
        errors.append("short_review must be nonempty")
    if len(str(value.get("short_review") or "")) > 1200:
        errors.append("short_review exceeds 1200 characters")
    diagnosis = value.get("causal_diagnosis")
    if not isinstance(diagnosis, dict):
        errors.append("causal_diagnosis must be an object")
    else:
        links = diagnosis.get("links")
        if not isinstance(links, dict) or set(links) != set(CAUSAL_LINKS):
            errors.append("causal_diagnosis.links must contain exactly the seven causal links")
        else:
            for link_name, link in links.items():
                if not isinstance(link, dict) or link.get("status") not in CAUSAL_LINK_STATUSES:
                    errors.append(f"invalid causal status for {link_name}")
                    continue
                evidence = link.get("evidence")
                if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
                    errors.append(f"causal evidence for {link_name} must be a string list")
                if not str(link.get("interpretation") or "").strip():
                    errors.append(f"causal interpretation for {link_name} must be nonempty")
        if diagnosis.get("failure_boundary") not in CAUSAL_BOUNDARIES:
            errors.append("invalid causal failure_boundary")
        for field in (
            "falsified_claims", "unsupported_claims", "excluded_equivalence_classes", "open_discriminators",
        ):
            items = diagnosis.get(field)
            if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                errors.append(f"causal_diagnosis.{field} must be a string list")
    for relation in value.get("relations_to_prior", []):
        if not isinstance(relation, dict) or relation.get("node_id") not in known_node_ids:
            errors.append("relations_to_prior references an unknown node")
    return errors


def validate_hypothesis_pool(value: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list) or not 3 <= len(hypotheses) <= 5:
        return ["hypotheses must contain between 3 and 5 items"]
    errors: list[str] = []
    hypothesis_ids: list[str] = []
    mechanism_keys: list[str] = []
    known_nodes = {item.get("node_id") for item in snapshot.get("selectable_parents", [])}
    required_nodes = set(snapshot.get("selection_policy", {}).get("human_required_parent_nodes", []))
    for index, item in enumerate(hypotheses, start=1):
        if not isinstance(item, dict):
            errors.append(f"hypothesis {index} must be an object")
            continue
        hypothesis_id = str(item.get("hypothesis_id") or "")
        if not HYPOTHESIS_ID_RE.fullmatch(hypothesis_id):
            errors.append(f"hypothesis {index} has invalid hypothesis_id")
        hypothesis_ids.append(hypothesis_id)
        for field in ("causal_hypothesis", "discriminating_prediction"):
            if not str(item.get(field) or "").strip():
                errors.append(f"hypothesis {hypothesis_id or index} has empty {field}")
        intent = item.get("intent")
        if not isinstance(intent, dict):
            errors.append(f"hypothesis {hypothesis_id or index} has no intent object")
            continue
        errors.extend(f"hypothesis {hypothesis_id or index}: {error}" for error in validate_intent(intent))
        mechanism_keys.append(str(intent.get("mechanism_key") or ""))
        parents = intent.get("parent_selection", {}).get("parents", [])
        selected = {edge.get("node_id") for edge in parents if isinstance(edge, dict)}
        unknown = selected - known_nodes
        if unknown:
            errors.append(f"hypothesis {hypothesis_id or index} selects unknown parents: {sorted(unknown)}")
        if not required_nodes.issubset(selected):
            errors.append(f"hypothesis {hypothesis_id or index} omits required parent nodes")
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        errors.append("hypothesis IDs must be unique")
    if len(mechanism_keys) != len(set(mechanism_keys)):
        errors.append("competing hypotheses must use distinct mechanism keys")
    return errors


def validate_intent_selection(value: dict[str, Any], pool: dict[str, Any]) -> list[str]:
    hypotheses = pool.get("hypotheses", [])
    pool_ids = [item.get("hypothesis_id") for item in hypotheses if isinstance(item, dict)]
    selected_id = value.get("selected_hypothesis_id")
    errors: list[str] = []
    if selected_id not in pool_ids:
        errors.append("selected_hypothesis_id is not in the sealed hypothesis pool")
    assessments = value.get("comparative_assessment")
    if not isinstance(assessments, list):
        return [*errors, "comparative_assessment must be a list"]
    assessed_ids = [item.get("hypothesis_id") for item in assessments if isinstance(item, dict)]
    if len(assessments) != len(pool_ids) or sorted(assessed_ids) != sorted(pool_ids):
        errors.append("comparative_assessment must cover every hypothesis exactly once")
    selected_assessments = [
        item for item in assessments if isinstance(item, dict) and item.get("decision") == "selected"
    ]
    if len(selected_assessments) != 1 or selected_assessments[0].get("hypothesis_id") != selected_id:
        errors.append("exactly the chosen hypothesis must be marked selected")
    for item in assessments:
        if not isinstance(item, dict):
            errors.append("comparative_assessment contains a malformed item")
            continue
        if item.get("decision") not in {"selected", "rejected"}:
            errors.append("comparative_assessment contains an invalid decision")
        for field in ("evidence_fit", "discriminating_value", "implementation_risk", "reason"):
            if not str(item.get(field) or "").strip():
                errors.append(f"comparative_assessment has empty {field}")
    if not str(value.get("selection_rationale") or "").strip():
        errors.append("selection_rationale must be nonempty")
    return errors


def init_campaign(args: argparse.Namespace) -> int:
    campaign_root = args.campaign_root.resolve()
    if campaign_root.exists() and any(campaign_root.iterdir()):
        raise SystemExit(f"Campaign root is not empty: {campaign_root}")
    campaign_root.mkdir(parents=True, exist_ok=True)
    source_root = args.source_root.resolve()
    batch = read_json(args.evolution_batch.resolve())
    query_ids = batch.get("query_ids")
    if not isinstance(query_ids, list) or not query_ids:
        raise SystemExit("Evolution batch must contain a nonempty query_ids list")
    parent_hash = source_tree_hash(source_root)
    campaign = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": args.campaign_id,
        "created_at": utc_now(),
        "source_root": str(source_root),
        "initial_parent_source_tree_sha256": parent_hash,
        "evolution_batch": str(args.evolution_batch.resolve()),
        "evolution_batch_sha256": sha256_file(args.evolution_batch.resolve()),
        "query_ids": query_ids,
        "max_generations": args.max_generations,
        "max_agent_iterations": args.max_agent_iterations,
        "meta_agent": {
            "codex": args.codex,
            "profile": args.meta_profile,
            "model": args.meta_model,
            "wall_clock_timeout_seconds": None,
        },
        "protocol_notes": [
            "One sealed intent and one candidate per generation.",
            "The meta-agent independently selects one or more graph parents for every intent.",
            "Exactly one selected parent supplies the materialized source tree; other parents supply mechanisms or evidence.",
            "A review recommendation annotates a node but never binds the next parent selection.",
            "The meta-agent has no wall-clock deadline.",
            "DAB tasks retain a bounded interaction-iteration count.",
            "Detailed reviews are immutable artifacts linked from compact roadmap nodes.",
        ],
    }
    state = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": args.campaign_id,
        "stage": "ready_for_intent",
        "next_generation": 1,
        "updated_at": utc_now(),
    }
    campaign_path, state_path, roadmap_path = campaign_paths(campaign_root)
    write_json(campaign_path, campaign)
    write_json(state_path, state)
    roadmap_path.touch(exist_ok=False)
    root = materialize_root_node(campaign_root, source_root, args.parent_result.resolve() if args.parent_result else None)
    print(json.dumps({"status": "initialized", "campaign_root": str(campaign_root), "parent_hash": parent_hash}, indent=2))
    return 0


def build_intent_prompt(snapshot: dict[str, Any]) -> str:
    prompt = """You are the hypothesis-generation Meta agent for a data-agent harness evolution
campaign. Read the entire compact evolution graph and produce 3 to 5 competing, complete intents.
Do not choose a winner, rank the proposals, or imply that one should be selected. A separate Meta
invocation will compare the sealed pool.

Each proposal must state a distinct causal hypothesis and a prediction that discriminates it from
the alternatives. Seek materially different mechanisms or workflow designs, not cosmetic threshold,
wording, or post-tool-check variants of one idea. There is deliberately no fixed taxonomy of
intervention scales or mechanism families: invent the most useful alternatives supported by the
evidence. A local change is allowed when warranted, but the pool as a whole must not collapse to
near-duplicate local repairs.

Every proposed intent must independently select one or more parent nodes. Exactly one must have role `code_base`
and must equal `materialization_base_node_id`; its frozen source tree will be copied as
the concrete implementation base. Other selected nodes may contribute a mechanism, complementary
capability, or failure evidence. Do not blindly merge repositories: explain how selected evidence
would be synthesized.
Honor any human_required_parent_nodes in selection_policy by including those nodes; you still
independently choose their roles, all additional parents, and exactly one materialization base.
Use only the compact results and graph cards supplied below. Archival detail links are
provenance only: do not open them or load per-query feedback, raw traces, patches, or
detailed historical reviews. Missing activation evidence is unknown, not proof of inactivity.
Treat prior review explanations as hypotheses, not independent root-cause audits. An LLM
BadRequestError termination is an observed failure, not proof that infrastructure rather than
candidate context or behavior caused it; do not assume a causal attribution without evidence.

Prioritize reusable data-agent capabilities that can improve multiple DAB tasks. Do not propose
query-specific answer logic, ground-truth access, validator changes, or a purely descriptive log.
If recent generations keep refining one mechanism family without demonstrated behavioral effect,
include at least one materially different cross-task hypothesis in the pool. A proposal that stays
on that path must explain why you continue it despite the evidence, while plausible alternatives
remain represented; a new mechanism_key alone does not establish novelty.

Use these historical behavior dimensions only as optional lenses for generating hypotheses:
`state_externalization` (where intermediate state lives), `control_topology` (execution and
replanning flow), `processing_granularity` (unit of work), `uncertainty_representation` (how
unresolved choices are retained), `evidence_composition` (how evidence paths are combined), and
`implementation_locus` (which active layer changes behavior). They are not an exhaustive menu,
an enum, or a requirement to rotate dimensions. You may combine lenses or propose a new
`primary_dimension` outside this list when the compact evidence supports it. Each intent must name a
concrete, testable mechanism grounded in an observed limitation. A dimension name is a hypothesis,
not an observed property or a performance claim.

Avoid repeating a mechanism_key already present in mechanism_index unless the new intent explicitly
repairs or refines it and selects the relevant prior nodes. Failed and inconclusive nodes may be useful
parents when their failure evidence informs a repair, but justify that choice. Review source-reuse
recommendations are evidence only and are not binding. Every intent must describe a real change on
the active execution path, an observable activation signal, a bounded fallback, expected behavior,
and possible regressions. Return JSON matching the supplied hypothesis-pool schema and nothing else.

# Compact result and evolution graph

```json
""" + json.dumps({
        "result": snapshot.get("latest_result"),
        "graph": {key: value for key, value in snapshot.items() if key != "latest_result"},
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    if snapshot.get("safe_detail_access"):
        prompt = prompt.replace("Use only the compact results and graph cards supplied below.",
                                "Use the compact results and graph cards first, plus explicitly indexed safe details when needed.")
    return prompt + detail_context.access_prompt(snapshot)


def build_selection_prompt(snapshot: dict[str, Any], pool: dict[str, Any]) -> str:
    evidence = {
        "hypothesis_pool": pool,
        "result": snapshot.get("latest_result"),
        "graph": {key: value for key, value in snapshot.items() if key != "latest_result"},
    }
    prompt = """You are the independent selection Meta agent for a data-agent harness evolution
campaign. A different invocation generated the sealed hypothesis pool below. Compare every proposal
against the same compact evidence and select exactly one. You may not edit, merge, or invent an
intent; your selected_hypothesis_id must identify one proposal verbatim.

Assess evidence fit, whether the stated prediction would distinguish the causal explanation, likely
opportunity and reach on the observed workload, implementation and regression risk, and whether the
proposal merely repeats a recently activated no-gain pattern. These are comparative considerations,
not a fixed scoring formula or intervention taxonomy. Novelty alone is not sufficient, and ease of
implementation alone is not sufficient. Give a substantive rejection reason for every unselected
proposal so the full competition remains auditable. Do not inspect archival links, raw traces,
per-query answers, validator targets, patches, or held-out tasks. Return JSON matching the selection
schema and nothing else.

# Sealed competition and compact evidence

```json
""" + json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    return prompt


def next_meta_session(campaign_root: Path, generation: int, phase: str) -> Path:
    """Keep every invoked attempt intact; an uninvoked prepared session may be reused."""
    if phase not in {"intent", "review", "diagnosis", "hypotheses", "selection"}:
        raise ValueError("Unsupported Meta session phase")
    root = generation_dir(campaign_root, generation) / "meta_agent"
    attempt = 1
    while True:
        name = phase if attempt == 1 else f"{phase}_attempt_{attempt:03d}"
        session = root / name
        invoked = any((session / marker).exists() for marker in (
            "invocation.json", "codex.stdout", "codex.stderr",
            "intent_response.json", "review_response.json", "hypothesis_pool.json",
            "selection_response.json", "diagnosis_response.json", "request_prompt.md",
        ))
        if not invoked:
            return session
        attempt += 1


def explicit_response_contract(prompt: str, schema: dict[str, Any]) -> str:
    """Expose the complete structural contract even when a provider ignores CLI metadata."""
    return prompt + "\n\n# Mandatory response structure\n\n" + (
        "Return exactly one JSON object and no surrounding prose. Include EVERY required field "
        "in the JSON schema below, not just a summary or recommendation. Independently choose "
        "all judgments and enum values from the supplied evidence; no judgment is prescribed "
        "by this formatting contract. Do not invent measurements. Where evidence is unavailable, "
        "state that explicitly and use empty arrays or null only where the schema allows them.\n\n"
    ) + "```json\n" + json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"


def prepare_intent_context(campaign_root: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Prepare stage two: a pool of competing intents (legacy name kept for callers)."""
    campaign, state = load_campaign(campaign_root)
    if state["stage"] != "ready_for_intent":
        raise SystemExit(f"Campaign is not ready for an intent: {state['stage']}")
    generation = int(state["next_generation"])
    if int(campaign["max_generations"]) > 0 and generation > int(campaign["max_generations"]):
        raise SystemExit("Campaign reached max_generations")
    parents = selectable_parent_descriptors(campaign_root)
    unavailable = [node_id for node_id, item in parents.items() if not item.get("source_available")]
    if unavailable:
        raise SystemExit("Selectable graph parents have missing source trees: " + ", ".join(unavailable))
    snapshot = build_snapshot(campaign_root)
    materialize_safe_details(campaign_root, snapshot)
    session = next_meta_session(campaign_root, generation, "hypotheses")
    session.mkdir(parents=True, exist_ok=True)
    write_json(session / "roadmap_snapshot.json", snapshot)
    write_json(session / "output_schema.json", hypothesis_pool_output_schema())
    prompt = build_intent_prompt(snapshot) + (
        "\nReturn exactly three fully specified, causally distinct hypotheses. "
        "Keep each explanatory free-text field to at most two sentences, while preserving "
        "every required schema field and all implementation safety boundaries.\n"
    )
    (session / "prompt.md").write_text(prompt, encoding="utf-8")
    return session, snapshot, state


def prepare_selection_context(
    campaign_root: Path, snapshot: dict[str, Any], pool: dict[str, Any],
) -> Path:
    _, state = load_campaign(campaign_root)
    if state["stage"] != "ready_for_intent":
        raise SystemExit(f"Campaign is not ready for intent selection: {state['stage']}")
    generation = int(state["next_generation"])
    session = next_meta_session(campaign_root, generation, "selection")
    session.mkdir(parents=True, exist_ok=True)
    write_json(session / "roadmap_snapshot.json", snapshot)
    write_json(session / "sealed_hypothesis_pool.json", pool)
    write_json(session / "output_schema.json", intent_selection_output_schema())
    (session / "prompt.md").write_text(build_selection_prompt(snapshot, pool), encoding="utf-8")
    return session


def invoke_codex_json(
    *,
    campaign: dict[str, Any],
    session: Path,
    prompt: str,
    schema_path: Path,
    output_name: str,
) -> dict[str, Any]:
    schema = read_json(schema_path)
    prompt = explicit_response_contract(prompt, schema)
    require_new(session / "request_prompt.md")
    (session / "request_prompt.md").write_text(prompt, encoding="utf-8")
    meta = campaign["meta_agent"]
    command = [resolve_codex(str(meta.get("codex") or "codex")), "--no-daemon", "-C", str(session)]
    if meta.get("model"):
        command.extend(["--model", str(meta["model"])])
    if meta.get("profile"):
        command.extend(["--profile", str(meta["profile"])])
    output_path = session / output_name
    command.extend([
        "exec", "--sandbox", "read-only", "-c", 'approval_policy="on-request"',
        "-c", 'approvals_reviewer="auto_review"', "--json",
        "--skip-git-repo-check", "--output-schema", str(schema_path),
        "--output-last-message", str(output_path), "-",
    ])
    environment = meta_environment(meta.get("profile"))
    write_json(session / "invocation.json", {
        "status": "running", "started_at": utc_now(),
        "started_without_wall_clock_deadline": True,
        "model": meta.get("model"), "profile": meta.get("profile"),
        "output": str(output_path),
    })
    process = run_logged_command(
        command,
        cwd=session,
        prompt=prompt,
        stdout_path=session / "codex.stdout",
        stderr_path=session / "codex.stderr",
        env=environment,
        timeout=None,
    )
    write_json(session / "invocation.json", {
        "status": "completed" if process.returncode == 0 else "failed",
        "started_without_wall_clock_deadline": True,
        "exit_code": process.returncode,
        "model": meta.get("model"),
        "profile": meta.get("profile"),
        "output": str(output_path),
    })
    if process.returncode != 0:
        raise SystemExit(f"Meta-agent failed with exit code {process.returncode}; see {session / 'codex.stderr'}")
    response = read_json(output_path)
    if not isinstance(response, dict):
        raise SystemExit(f"Meta-agent response is not a JSON object; evidence retained in {session}")
    missing = [field for field in schema.get("required", []) if field not in response]
    if missing:
        raise SystemExit(f"Meta-agent response omitted required fields {missing}; evidence retained in {session}")
    return response


def seal_intent(
    campaign_root: Path,
    raw_intent: dict[str, Any],
    snapshot: dict[str, Any] | None = None,
    competition_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    campaign, state = load_campaign(campaign_root)
    generation = int(state["next_generation"])
    if state["stage"] != "ready_for_intent":
        raise SystemExit(f"Cannot seal intent from stage {state['stage']}")
    snapshot = snapshot or build_snapshot(campaign_root)
    errors = validate_intent(raw_intent)
    if errors:
        raise SystemExit("Invalid intent: " + "; ".join(errors))
    known_nodes = {ROOT_NODE_ID, *[record["node_id"] for record in load_roadmap(campaign_root)],
                   *[record["node_id"] for record in load_repair_branches(campaign_root)]}
    selection = raw_intent["parent_selection"]
    selected_ids = [edge["node_id"] for edge in selection["parents"]]
    required_ids = snapshot.get("selection_policy", {}).get("human_required_parent_nodes", [])
    if any(node_id not in selected_ids for node_id in required_ids):
        raise SystemExit("Intent must include the human-requested graph parent; role/base remain Meta-selected")
    unknown = sorted(set(selected_ids) - known_nodes)
    if unknown:
        raise SystemExit("Intent selects unknown graph parents: " + ", ".join(unknown))
    base = resolve_materialization_parent(campaign_root, selection["materialization_base_node_id"])
    intent = dict(raw_intent)
    intent.update({
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "generation": generation,
        "code_parent_hash": base["source_tree_sha256"],
        "code_parent_node_id": base["node_id"],
        "selected_parent_node_ids": selected_ids,
        "prior_node_ids": [node_id for node_id in selected_ids if node_id != ROOT_NODE_ID],
        "information_parent_snapshot_hash": snapshot["snapshot_sha256"],
        "sealed_at": utc_now(),
    })
    if competition_binding is not None:
        intent["competition_binding"] = competition_binding
    intent["canonical_json_sha256"] = canonical_hash(intent)
    path = generation_dir(campaign_root, generation) / "sealed_intent.json"
    require_new(path)
    write_json(path, intent)
    state.update({"stage": "intent_sealed", "active_intent": str(path), "updated_at": utc_now()})
    write_json(campaign_root / "campaign_state.json", state)
    return intent


def invoke_intent(args: argparse.Namespace) -> int:
    campaign_root = args.campaign_root.resolve()
    campaign, _ = load_campaign(campaign_root)
    session, snapshot, _ = prepare_intent_context(campaign_root)
    if args.prepare_only:
        print(json.dumps({"status": "hypothesis_context_prepared", "session": str(session)}, indent=2))
        return 0
    pool = invoke_codex_json(
        campaign=campaign,
        session=session,
        prompt=(session / "prompt.md").read_text(encoding="utf-8"),
        schema_path=session / "output_schema.json",
        output_name="hypothesis_pool.json",
    )
    pool_errors = validate_hypothesis_pool(pool, snapshot)
    if pool_errors:
        raise SystemExit("Invalid hypothesis pool: " + "; ".join(pool_errors))
    selection_session = prepare_selection_context(campaign_root, snapshot, pool)
    selection = invoke_codex_json(
        campaign=campaign,
        session=selection_session,
        prompt=(selection_session / "prompt.md").read_text(encoding="utf-8"),
        schema_path=selection_session / "output_schema.json",
        output_name="selection_response.json",
    )
    selection_errors = validate_intent_selection(selection, pool)
    if selection_errors:
        raise SystemExit("Invalid intent selection: " + "; ".join(selection_errors))
    selected_id = selection["selected_hypothesis_id"]
    selected = next(item for item in pool["hypotheses"] if item["hypothesis_id"] == selected_id)
    assessments = {item["hypothesis_id"]: item for item in selection["comparative_assessment"]}
    alternatives = [{
        "hypothesis_id": item["hypothesis_id"],
        "mechanism_key": item["intent"]["mechanism_key"],
        "decision": assessments[item["hypothesis_id"]]["decision"],
        "reason": assessments[item["hypothesis_id"]]["reason"],
    } for item in pool["hypotheses"]]
    competition_binding = {
        "protocol": META_PROTOCOL_VERSION,
        "selected_hypothesis_id": selected_id,
        "selected_proposal_sha256": canonical_hash(selected),
        "hypothesis_pool_sha256": sha256_file(session / "hypothesis_pool.json"),
        "selection_sha256": sha256_file(selection_session / "selection_response.json"),
        "hypothesis_pool_path": str((session / "hypothesis_pool.json").resolve()),
        "selection_path": str((selection_session / "selection_response.json").resolve()),
        "selection_rationale": selection["selection_rationale"],
        "alternatives": alternatives,
    }
    intent = seal_intent(campaign_root, selected["intent"], snapshot, competition_binding)
    print(json.dumps({
        "status": "intent_sealed_after_competition",
        "generation": intent["generation"],
        "selected_hypothesis_id": selected_id,
        "hypothesis_count": len(pool["hypotheses"]),
        "intent_sha256": intent["canonical_json_sha256"],
    }, indent=2))
    return 0


def build_selected_parent_evidence(campaign_root: Path, intent: dict[str, Any]) -> dict[str, Any]:
    """Selected compact cards only; never automatically expand historical artifacts."""
    descriptors = selectable_parent_descriptors(campaign_root)
    records = {record["node_id"]: record for record in
               load_roadmap(campaign_root) + load_repair_branches(campaign_root)}
    selected: list[dict[str, Any]] = []
    for edge in intent["parent_selection"]["parents"]:
        node_id = edge["node_id"]
        descriptor = descriptors[node_id]
        item: dict[str, Any] = {"selection": edge, "descriptor": compact_parent_descriptor(descriptor)}
        record = records.get(node_id)
        if record:
            item["roadmap_node"] = compact_graph_node(record)
        selected.append(item)
    snapshot = build_snapshot(campaign_root)
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "context_policy": "compact_result_graph_v1",
        "generation": intent["generation"],
        "materialization_base_node_id": intent["parent_selection"]["materialization_base_node_id"],
        "synthesis_strategy": intent["parent_selection"]["synthesis_strategy"],
        "parents": selected,
        "execution_environment": snapshot.get("execution_environment", {}),
    }
    if snapshot.get("safe_detail_access"):
        selected_ids = {item["selection"]["node_id"] for item in selected}
        evidence["context_policy"] = snapshot["context_policy"]
        evidence["safe_detail_access"] = {**snapshot["safe_detail_access"], "nodes": [
            item for item in snapshot["safe_detail_access"]["nodes"] if item["node_id"] in selected_ids]}
    return strip_f1_context(evidence)


def record_candidate(args: argparse.Namespace) -> int:
    campaign_root = args.campaign_root.resolve()
    _, state = load_campaign(campaign_root)
    if state["stage"] != "intent_sealed":
        raise SystemExit(f"Cannot record candidate from stage {state['stage']}")
    generation = int(state["next_generation"])
    workspace = args.workspace.resolve()
    admission = read_json(workspace / "candidate_admission.json")
    manifest = read_json(workspace / "workspace_manifest.json")
    intent = read_json(Path(state["active_intent"]))
    if admission.get("status") != "source_preflight_passed":
        raise SystemExit("Candidate did not pass source preflight")
    if manifest.get("intent_canonical_sha256") != intent["canonical_json_sha256"]:
        raise SystemExit("Candidate workspace is not bound to the active intent")
    if manifest.get("parent_source_sha256") != intent["code_parent_hash"]:
        raise SystemExit("Candidate workspace is not bound to the selected materialization parent")
    candidate_repo = workspace / "repo"
    candidate_ref = {
        "schema_version": SCHEMA_VERSION,
        "generation": generation,
        "workspace": str(workspace),
        "repo": str(candidate_repo),
        "candidate_patch": str(workspace / "candidate.patch"),
        "patch_sha256": admission["patch_sha256"],
        "source_tree_sha256": source_tree_hash(candidate_repo),
        "changed_files": admission["changed_files"],
        "implementation_files": admission["implementation_files"],
        "claim_to_source_valid": admission["claim_to_source_valid"],
        "recorded_at": utc_now(),
    }
    path = generation_dir(campaign_root, generation) / "candidate_ref.json"
    require_new(path)
    write_json(path, candidate_ref)
    state.update({
        "stage": "candidate_admitted",
        "active_candidate_ref": str(path),
        "updated_at": utc_now(),
    })
    write_json(campaign_root / "campaign_state.json", state)
    print(json.dumps({"status": "candidate_admitted", "candidate_ref": str(path)}, indent=2))
    return 0


def record_candidate_revision(args: argparse.Namespace) -> int:
    """Append a pre-evaluation source revision without rewriting its predecessor."""
    campaign_root = args.campaign_root.resolve()
    _, state = load_campaign(campaign_root)
    if state["stage"] != "candidate_admitted":
        raise SystemExit(f"Cannot revise candidate from stage {state['stage']}")
    if not str(args.reason or "").strip():
        raise SystemExit("Candidate revision requires a concrete admission reason")
    generation = int(state["next_generation"])
    intent = read_json(Path(state["active_intent"]))
    predecessor_path = Path(state["active_candidate_ref"])
    predecessor = read_json(predecessor_path)
    if source_tree_hash(Path(predecessor["repo"])) != predecessor["source_tree_sha256"]:
        raise SystemExit("Previously recorded candidate source changed")
    if sha256_file(Path(predecessor["candidate_patch"])) != predecessor["patch_sha256"]:
        raise SystemExit("Previously recorded candidate patch changed")

    workspace = args.workspace.resolve()
    manifest = read_json(workspace / "workspace_manifest.json")
    admission_path = workspace / "candidate_admission.json"
    admission = read_json(admission_path)
    if admission.get("status") != "source_preflight_passed":
        raise SystemExit("Revised candidate did not pass source preflight")
    if manifest.get("intent_canonical_sha256") != intent["canonical_json_sha256"]:
        raise SystemExit("Revised candidate is not bound to the sealed intent")
    if manifest.get("parent_source_sha256") != intent["code_parent_hash"]:
        raise SystemExit("Revised candidate is not bound to the selected materialization parent")
    if sha256_file(workspace / "candidate.patch") != admission["patch_sha256"]:
        raise SystemExit("Revised candidate patch changed after source preflight")
    candidate_repo = workspace / "repo"
    revised_tree = source_tree_hash(candidate_repo)
    if revised_tree == predecessor["source_tree_sha256"]:
        raise SystemExit("Revised candidate source is identical to its predecessor")
    revision = 1
    generation_root = generation_dir(campaign_root, generation)
    while (generation_root / f"candidate_ref_revision_{revision:03d}.json").exists():
        revision += 1
    path = generation_root / f"candidate_ref_revision_{revision:03d}.json"
    candidate_ref = {
        "schema_version": SCHEMA_VERSION,
        "generation": generation,
        "revision": revision,
        "revision_reason": str(args.reason).strip(),
        "revises_candidate_ref": str(predecessor_path),
        "revises_candidate_ref_sha256": sha256_file(predecessor_path),
        "source_preflight_path": str(admission_path),
        "source_preflight_sha256": sha256_file(admission_path),
        "workspace": str(workspace),
        "repo": str(candidate_repo),
        "candidate_patch": str(workspace / "candidate.patch"),
        "patch_sha256": admission["patch_sha256"],
        "source_tree_sha256": revised_tree,
        "changed_files": admission["changed_files"],
        "implementation_files": admission["implementation_files"],
        "claim_to_source_valid": admission["claim_to_source_valid"],
        "recorded_at": utc_now(),
    }
    require_new(path)
    write_json(path, candidate_ref)
    state.update({"active_candidate_ref": str(path), "updated_at": utc_now()})
    write_json(campaign_root / "campaign_state.json", state)
    print(json.dumps({"status": "candidate_revision_admitted", "candidate_ref": str(path)}, indent=2))
    return 0


def invoke_candidate(args: argparse.Namespace) -> int:
    """Prepare and run the coding meta-agent with no wall-clock deadline."""
    campaign_root = args.campaign_root.resolve()
    campaign, state = load_campaign(campaign_root)
    if state["stage"] != "intent_sealed":
        raise SystemExit(f"Cannot generate candidate from stage {state['stage']}")
    generation = int(state["next_generation"])
    intent = read_json(Path(state["active_intent"]))
    base = resolve_materialization_parent(campaign_root, intent["code_parent_node_id"])
    evidence_path = generation_dir(campaign_root, generation) / "selected_parent_evidence.json"
    if not evidence_path.exists():
        evidence = build_selected_parent_evidence(campaign_root, intent)
        materialize_safe_details(campaign_root, evidence)
        write_json(evidence_path, evidence)
    workspace = (
        args.workspace.resolve()
        if args.workspace
        else generation_dir(campaign_root, generation) / "candidate_workspace"
    )
    if not workspace.exists():
        frozen_upstream = Path(load_root_node(campaign_root)["source_root"]) / "external/DataAgentBench_official/common_scaffold/DataAgent.py"
        candidate_workspace.prepare(argparse.Namespace(
            source_root=Path(base["source_root"]),
            output=workspace,
            intent=Path(state["active_intent"]),
            parent_source=None,
            parent_context=evidence_path,
            upstream_source=frozen_upstream if frozen_upstream.is_file() else None,
            mechanism_contract=args.mechanism_contract.resolve() if args.mechanism_contract else None,
        ))
    if args.prepare_only:
        print(json.dumps({"status": "candidate_workspace_prepared", "workspace": str(workspace)}, indent=2))
        return 0
    meta = campaign["meta_agent"]
    result = candidate_workspace.generate(argparse.Namespace(
        workspace=workspace,
        codex=args.codex or meta.get("codex") or "codex",
        model=args.model or meta.get("model"),
        profile=args.profile or meta.get("profile"),
        python=args.python,
        timeout=0,
        max_repairs=args.max_repairs,
    ))
    if result != 0:
        raise SystemExit(f"Candidate generation did not pass source admission; see {workspace}")
    return record_candidate(argparse.Namespace(campaign_root=campaign_root, workspace=workspace))


def batch_query_ids(summary: dict[str, Any]) -> list[str]:
    batch = summary.get("batch") if isinstance(summary.get("batch"), dict) else {}
    values = batch.get("query_ids")
    return [str(value) for value in values] if isinstance(values, list) else []


def compact_result(summary: dict[str, Any]) -> dict[str, Any]:
    rows = summary.get("per_query_feedback") if isinstance(summary.get("per_query_feedback"), list) else []
    return {
        "query_count": len(rows),
        "strict_pass_count": sum(row.get("strict_match_passed") is True for row in rows if isinstance(row, dict)),
        "strict_evaluated_count": sum(isinstance(row.get("strict_match_passed"), bool) for row in rows if isinstance(row, dict)),
        "final_answer_nonempty_count": sum(row.get("final_answer_nonempty") is True for row in rows if isinstance(row, dict)),
        "run_error_count": sum(bool(row.get("run_error")) for row in rows if isinstance(row, dict)),
        "nonzero_exit_count": sum(isinstance(row.get("run_exit_code"), int) and row["run_exit_code"] != 0 for row in rows if isinstance(row, dict)),
        "provider_error_count": sum(provider_failure(row) for row in rows if isinstance(row, dict)),
    }


def expected_query_timeout(row: dict[str, Any]) -> bool:
    """Recognize runner-owned wall timeouts as valid failed evaluations."""
    return (
        row.get("run_exit_code") == 124
        and isinstance(row.get("run_error"), str)
        and row["run_error"].startswith("query_wall_timeout_")
        and row.get("terminate_reason") == row.get("run_error")
    )


def aggregate_diagnostics(summary: dict[str, Any]) -> dict[str, Any]:
    """Batch-wide measurements only: no task IDs, paths, observations or code."""
    rows = [row for row in summary.get("per_query_feedback", []) if isinstance(row, dict)]
    result: dict[str, Any] = {}
    for field in ("llm_call_count", "tool_call_count"):
        values = [row[field] for row in rows if isinstance(row.get(field), int)
                  and not isinstance(row[field], bool)]
        result[field] = {"observed_rows": len(values), "total": sum(values),
                         "maximum": max(values) if values else None}
    for field in ("terminate_reason", "selected_stage", "selected_problem_type"):
        counts = Counter(short_text(row.get(field), 80) for row in rows if row.get(field))
        result[field + "_counts"] = dict(counts.most_common(8))
        if len(counts) > 8:
            result[field + "_counts"]["other"] = sum(counts.values()) - sum(value for _, value in counts.most_common(8))
    return result


def intent_result_binding(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_sha256": intent.get("canonical_json_sha256") or intent.get("intent_sha256"),
        "mechanism_key": intent.get("mechanism_key"),
        "proposed_mechanism": short_text(intent.get("proposed_mechanism"), 600),
    }


def candidate_result_binding(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in (
        "generation", "patch_sha256", "source_tree_sha256", "claim_to_source_valid",
    )}


def compact_evaluation_binding(value: dict[str, Any]) -> dict[str, Any]:
    """Only bounded regime metadata; never row mappings or task identifiers."""
    view = {key: value[key] for key in (
        "result_type", "homogeneous_runtime", "human_accepted_mixed", "comparability",
        "repair_policy", "input_policy",
    ) if key in value and (value[key] is None or isinstance(value[key], (str, bool, int)))}
    view["regimes"] = [{key: regime[key] for key in (
        "name", "row_count", "source_sha256", "upstream_runtime_sha256", "input_policy",
        "repair_policy", "workers",
    ) if key in regime} for regime in value.get("regimes", [])[:8] if isinstance(regime, dict)]
    return view


def visible_result(result: dict[str, Any], intent: dict[str, Any] | None = None,
                   candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    """A safe view even when an immutable historical result contains full rows."""
    view = {
        "generation": result.get("generation"),
        "summary": compact_metrics(result.get("summary", {})),
        "parent_summary": compact_metrics(result.get("parent_summary", {})),
        "strict_pass_delta": result.get("strict_pass_delta"),
        "intent": intent_result_binding(intent or result.get("intent_binding", {})),
        "candidate": candidate_result_binding(candidate or result.get("candidate", {})),
        "activation_evidence_status": "not_supplied_in_compact_result",
        "evaluation_binding": compact_evaluation_binding(result.get("evaluation_binding", {})),
    }
    # Fresh summaries can be projected without exposing their individual rows.
    diagnostics = aggregate_diagnostics(result) if "per_query_feedback" in result else result.get("diagnostics", {})
    view["diagnostics"] = {key: diagnostics[key] for key in (
        "llm_call_count", "tool_call_count", "terminate_reason_counts",
        "selected_stage_counts", "selected_problem_type_counts",
    ) if key in diagnostics}
    if "mechanism_evidence" in result:
        view["mechanism_evidence"] = result["mechanism_evidence"]
        view["activation_evidence_status"] = "measured_in_bound_terminal_audit"
    if view["evaluation_binding"].get("homogeneous_runtime") is False:
        view["strict_pass_delta"] = None
        view["parent_comparison_status"] = "not_causally_comparable_mixed_runtime"
    if "causal strict delta suppressed" in view["evaluation_binding"].get("comparability", ""):
        view["strict_pass_delta"] = None
        view["parent_comparison_status"] = "not_causally_comparable_unmatched_control"
    parent_path = result.get("parent_summary_path")
    parent_invalid = False
    if parent_path and Path(parent_path).is_file():
        parent_rows = read_json(Path(parent_path)).get("per_query_feedback", [])
        parent_invalid = any(
            isinstance(row, dict) and not expected_query_timeout(row)
            and (row.get("run_error") or row.get("run_exit_code", 0) != 0)
            for row in parent_rows
        )
    if view["parent_summary"].get("provider_error_count", 0) or parent_invalid:
        view["strict_pass_delta"] = None
        view["parent_comparison_status"] = "infrastructure_invalid_parent_reference_not_performance_baseline"
    return view


def verified_mechanism_evidence(card_path: Path, audit_path: Path, summary_path: Path,
                                intent_path: Path) -> dict[str, Any]:
    """Fail closed unless the supplied bounded card matches immutable inputs."""
    card_path, audit_path = card_path.resolve(), audit_path.resolve()
    mechanism = read_json(intent_path).get("mechanism_key")
    builder = (build_gen001_mechanism_evidence_card if mechanism == "evidence_grounded_answer_gate_with_bounded_requery"
               else build_gen002_mechanism_evidence_card if mechanism == "pre_dispatch_tool_call_dedup_and_failure_signature_memoization"
               else build_gen003_mechanism_evidence_card if mechanism == "tool_error_observation_triggered_class_scoped_repair"
               else build_gen004_mechanism_evidence_card if mechanism == "externalized_observation_ledger_with_supersession_and_compact_replay"
               else build_gen005_mechanism_evidence_card if mechanism == "trajectory_information_gain_stall_bounding_with_fact_ledger"
               else build_gen006_mechanism_evidence_card if mechanism == "protocol_safe_directive_channel_with_in_observation_delivery"
               else build_gen007_mechanism_evidence_card if mechanism == "wallclock_budget_governor_with_forced_evidence_commitment"
               else build_gen008_mechanism_evidence_card if mechanism == "cost_normalized_divergence_commitment_trigger"
               else build_mechanism_evidence_card_v3 if mechanism == "delivered_repeat_failure_steering"
               else build_mechanism_evidence_card_v2 if mechanism == "failure_triggered_obligation_steering"
               else build_gen009_shape_evidence_card if mechanism == "bounded_preflight_source_shape_card"
               else build_gen010_grain_evidence_card if mechanism == "declared_grain_executed_keyform_conformance_observation"
               else build_gen011_divergence_evidence_card if mechanism == "executed_evidence_divergence_reconciliation_note"
               else build_gen012_obligation_evidence_card if mechanism == "referent_scoped_dispatch_admission_obligation"
               else build_gen013_grounding_evidence_card if mechanism == "bounded_runtime_referent_grounding_prefetch"
               else build_gen014_recovery_evidence_card if mechanism == "runtime_owned_bounded_readonly_failure_recovery"
               else build_gen015_handoff_evidence_card if mechanism == "two_phase_frozen_evidence_handoff"
               else build_gen016_digest_evidence_card if mechanism == "tool_result_digest_replacement_with_expansion_handles"
               else build_gen017_referent_evidence_card if mechanism == "predispatch_runtime_referent_materialization"
               else build_gen018_tool_call_repair_evidence_card if mechanism == "executor_owned_repair_reexecution_for_tool_failures"
               else build_gen019_empirical_repair_evidence_card if mechanism == "empirical_failure_signature_mining_with_verified_repair"
               else build_mechanism_evidence_card_v1)
    if mechanism in {"evidence_grounded_answer_gate_with_bounded_requery",
                     "pre_dispatch_tool_call_dedup_and_failure_signature_memoization",
                     "tool_error_observation_triggered_class_scoped_repair",
                     "externalized_observation_ledger_with_supersession_and_compact_replay",
                     "trajectory_information_gain_stall_bounding_with_fact_ledger",
                     "protocol_safe_directive_channel_with_in_observation_delivery",
                     "wallclock_budget_governor_with_forced_evidence_commitment",
                     "cost_normalized_divergence_commitment_trigger"}:
        generation_root = audit_path.parent.parent
        launch_manifest_path = (generation_root / "evaluation" / "divergence_r2" / "launch_manifest.json"
                                if mechanism == "cost_normalized_divergence_commitment_trigger"
                                else generation_root / "evaluation" / "launch_manifest.json")
        candidate_ref_name = ("candidate_ref_revision_002.json"
                              if mechanism == "cost_normalized_divergence_commitment_trigger"
                              else "candidate_ref_revision_001.json" if mechanism in {
                                  "pre_dispatch_tool_call_dedup_and_failure_signature_memoization",
                                  "tool_error_observation_triggered_class_scoped_repair",
                                  "externalized_observation_ledger_with_supersession_and_compact_replay",
                                  "trajectory_information_gain_stall_bounding_with_fact_ledger",
                                  "protocol_safe_directive_channel_with_in_observation_delivery",
                                  "wallclock_budget_governor_with_forced_evidence_commitment",
                              } else "candidate_ref.json")
        expected = builder(
            audit_path, summary_path, intent_path,
            generation_root / candidate_ref_name,
            launch_manifest_path,
        )
    else:
        expected = builder(audit_path, summary_path, intent_path)
    actual = read_json(card_path)
    if actual != expected:
        raise SystemExit("Mechanism evidence card differs from its terminal audit/summary/intent")
    return expected


def record_result(args: argparse.Namespace) -> int:
    campaign_root = args.campaign_root.resolve()
    campaign, state = load_campaign(campaign_root)
    if state["stage"] not in {"candidate_admitted", "evaluation_running"}:
        raise SystemExit(f"Cannot record result from stage {state['stage']}")
    if state["stage"] == "evaluation_running":
        audit_path = getattr(args, "mechanism_terminal_audit", None)
        if not audit_path or not getattr(args, "mechanism_evidence_card", None):
            raise SystemExit("Running evaluation requires a bound natural-end terminal audit before result recording")
        terminal = read_json(audit_path.resolve())
        if not all(terminal.get(key) is True for key in ("complete", "natural_end", "hashes_verified")):
            raise SystemExit("Evaluation has not passed its natural-end terminal audit")
    generation = int(state["next_generation"])
    summary_path = args.batch_summary.resolve()
    summary = read_json(summary_path)
    if batch_query_ids(summary) != [str(value) for value in campaign["query_ids"]]:
        raise SystemExit("Batch summary query IDs do not match the frozen evolution batch")
    invalid_provider_rows = [row for row in summary.get("per_query_feedback", [])
                             if isinstance(row, dict) and provider_failure(row)]
    if invalid_provider_rows:
        raise SystemExit(f"Refusing formal result: {len(invalid_provider_rows)} provider/transport failures require infrastructure retry")
    rows = summary.get("per_query_feedback", [])
    if [row.get("query_id") for row in rows] != campaign["query_ids"]:
        raise SystemExit("Result rows/order must exactly match the frozen batch")
    if summary.get("audit_only") or summary.get("formal_result_eligible") is False:
        raise SystemExit("Audit-only/ineligible summary cannot be recorded")
    invalid_rows = [
        row for row in rows
        if not expected_query_timeout(row)
        and (row.get("run_error") or row.get("run_exit_code", 0) != 0)
    ]
    if invalid_rows:
        raise SystemExit("Result contains infrastructure-invalid rows")
    binding = compact_evaluation_binding(summary.get("evaluation_binding", {}))
    if binding.get("homogeneous_runtime") is False and not binding.get("human_accepted_mixed"):
        raise SystemExit("Mixed runtime evidence requires explicit human acceptance")
    result = {
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "generation": generation,
        "batch_summary_path": str(summary_path),
        "batch_summary_sha256": sha256_file(summary_path),
        "candidate_ref": state["active_candidate_ref"],
        "candidate": candidate_result_binding(read_json(Path(state["active_candidate_ref"]))),
        "summary": compact_result(summary),
        "diagnostics": aggregate_diagnostics(summary),
        "context_policy": "compact_result_graph_v1",
        "evaluation_binding": binding,
        "recorded_at": utc_now(),
    }
    intent = read_json(Path(state["active_intent"]))
    card_path = getattr(args, "mechanism_evidence_card", None)
    audit_path = getattr(args, "mechanism_terminal_audit", None)
    if bool(card_path) != bool(audit_path):
        raise SystemExit("Mechanism evidence card and terminal audit must be supplied together")
    if card_path:
        result["mechanism_evidence"] = verified_mechanism_evidence(
            card_path, audit_path, summary_path, Path(state["active_intent"]),
        )
        result["mechanism_evidence_path"] = str(card_path.resolve())
        # Gen1's runner summary predates the compact evaluation-binding field;
        # carry the independently bound regime card into the formal result.
        if isinstance(result["mechanism_evidence"].get("evaluation_binding"), dict):
            result["evaluation_binding"] = compact_evaluation_binding(
                result["mechanism_evidence"]["evaluation_binding"]
            )
    result["intent_binding"] = intent_result_binding(intent)
    base = selectable_parent_descriptors(campaign_root)[intent["code_parent_node_id"]]
    parent_result_path = args.parent_summary.resolve() if args.parent_summary else (
        Path(base["result_path"]) if base.get("result_path") else None
    )
    if parent_result_path and parent_result_path.is_file():
        parent_summary = read_json(parent_result_path)
        if batch_query_ids(parent_summary) == batch_query_ids(summary):
            parent_compact = compact_result(parent_summary)
            result["parent_summary_path"] = str(parent_result_path)
            result["parent_summary"] = parent_compact
            result["strict_pass_delta"] = result["summary"]["strict_pass_count"] - parent_compact["strict_pass_count"]
    if "causal strict delta suppressed" in result["evaluation_binding"].get("comparability", ""):
        result["strict_pass_delta"] = None
        result["parent_comparison_status"] = "not_causally_comparable_unmatched_control"
    path = generation_dir(campaign_root, generation) / "result.json"
    require_new(path)
    write_json(path, result)
    state.update({"stage": "result_recorded", "active_result": str(path), "updated_at": utc_now()})
    write_json(campaign_root / "campaign_state.json", state)
    print(json.dumps({"status": "result_recorded", "result": str(path), "summary": result["summary"]}, indent=2))
    return 0


def build_review_prompt(intent: dict[str, Any], candidate: dict[str, Any], result: dict[str, Any], snapshot: dict[str, Any]) -> str:
    evidence = {
        "result": visible_result(result, intent, candidate),
        "graph": {key: value for key, value in snapshot.items() if key != "latest_result"},
    }
    prompt = """You are the diagnosis Meta agent reviewing one completed generation of a data-agent
harness evolution campaign. Produce a fact-and-constraint diagnosis only. Do not propose a next
intent, recommend a patch, prescribe a workflow, or choose future parents; later independent stages
will generate and select competing intents.

Determine whether the sealed mechanism was implemented, integrated into the real execution path,
activated, behaviorally consequential, and associated with task improvement. Do not equate source
presence with activation, or activation with accuracy gain. Use `inconclusive` when evidence is
insufficient. Your only evidence is the compact result and brief graph below. The result contains
minimal intent/candidate bindings, not source or per-query evidence. Do not open archival links,
read historical result files, retrieve patches or raw traces, or expand per-query feedback.
Absent activation measurements mean unknown, not zero activations or failed integration. Do not
manufacture causal attribution from aggregate accuracy or infer integration from source admission.
If the compact result includes bound `mechanism_evidence`, distinguish measured zero from missing
measurement, name the exact counter and coverage in `activation_evidence`, and explain any missing
opportunity denominator. Treat a zero intervention counter as no observed intervention; do not
attribute an accuracy change to an intervention that did not fire. Put the key limitation in
`short_review` so the brief Graph card does not erase it. This is aggregate evidence, not a
license to inspect task rows or raw traces.
When evaluation_binding marks heterogeneous runtime/input regimes, the merged metrics are
human-accepted descriptive evidence only. Do not attribute gains to the sealed candidate or
concurrency, and do not treat the infrastructure repair as a Meta-selected improvement.
Give a nonbinding `source_reuse_recommendation`: `eligible_as_base` when this source is
a sound future materialization base, `evidence_only` when its observations are useful but its source
should not normally be reused, or `avoid` when both reuse and evidentiary reliance are unsafe. This
recommendation does not select the next generation's parents; the next intent meta-agent will inspect
the whole graph and decide independently.

The historical six behavior dimensions are optional review lenses: `state_externalization`,
`control_topology`, `processing_granularity`, `uncertainty_representation`,
`evidence_composition`, and `implementation_locus`. Use them only where the bound evidence
supports a concrete mechanism observation; combine them or identify a new dimension if more
apt. Do not force a classification, infer effects from a dimension label, or constrain the next
intent to these six directions.

Complete the standardized causal chain in `causal_diagnosis`: opportunity -> integration ->
activation -> delivery -> model_uptake -> downstream_behavior -> task_effect. For every link choose
exactly one status: `positive` for affirmative measured evidence, `measured_zero` only for an explicit
zero with adequate coverage, `unknown` when the necessary measurement is absent, or `confounded`
when a measurement exists but cannot isolate the link. Do not turn an unknown into a zero. Identify
the earliest defensible `failure_boundary`, or use `undetermined`/`no_observed_failure`. Record claims
actually falsified by evidence separately from unsupported claims. `excluded_equivalence_classes`
must describe only classes of explanations or repeat interventions ruled out by evidence; it must
not suggest their replacement. `open_discriminators` must state unresolved observations that would
separate competing explanations, not preferred fixes.

Write a concise `short_review` for the roadmap and a more specific `detailed_analysis`. Evidence
references must point to paths or facts present below. Return JSON matching the supplied schema.

# Generation evidence

```json
""" + json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    if snapshot.get("safe_detail_access"):
        prompt = prompt.replace("Your only evidence is the compact result and brief graph below.",
                                "Use the compact result and brief graph first; indexed safe historical details may clarify related prior mechanisms.")
    return prompt + detail_context.access_prompt(snapshot)


def prepare_review_context(campaign_root: Path) -> tuple[Path, dict[str, Any]]:
    campaign, state = load_campaign(campaign_root)
    if state["stage"] != "result_recorded":
        raise SystemExit(f"Campaign is not ready for review: {state['stage']}")
    generation = int(state["next_generation"])
    intent = read_json(Path(state["active_intent"]))
    candidate = read_json(Path(state["active_candidate_ref"]))
    result = read_json(Path(state["active_result"]))
    snapshot = build_snapshot(campaign_root)
    materialize_safe_details(campaign_root, snapshot)
    session = next_meta_session(campaign_root, generation, "diagnosis")
    session.mkdir(parents=True, exist_ok=True)
    write_json(session / "output_schema.json", review_output_schema())
    prompt = build_review_prompt(intent, candidate, result, snapshot)
    (session / "prompt.md").write_text(prompt, encoding="utf-8")
    return session, campaign


def review_candidate_changed_files(candidate: dict[str, Any]) -> list[str]:
    if "changed_files" in candidate:
        return candidate["changed_files"]
    if candidate.get("schema_version") != "dab_versioned_engineering_candidate_ref_v1":
        raise SystemExit("Candidate reference has no changed_files")
    patch = Path(candidate["candidate_patch"])
    if sha256_file(patch) != candidate["patch_sha256"]:
        raise SystemExit("Engineering revision patch hash changed")
    original = Path(candidate["original_ref"])
    if sha256_file(original) != candidate["original_ref_sha256"]:
        raise SystemExit("Engineering revision original reference changed")
    # Derive metadata from this revision's bound patch, not its obsolete original.
    stats = subprocess.run(
        ["git", "apply", "--numstat", "-z", str(patch.resolve())],
        cwd=Path(candidate["repo"]), capture_output=True, check=False,
    )
    if stats.returncode:
        raise SystemExit("Cannot inspect bound engineering revision patch")
    entries = iter(stats.stdout.decode("utf-8").split("\0"))
    paths = set()
    for entry in entries:
        if not entry:
            continue
        _, _, path = entry.split("\t", 2)
        if path:
            paths.add(path)
        else:
            # Git's -z rename form supplies both old and new paths separately.
            paths.update((next(entries), next(entries)))
    if not paths:
        raise SystemExit("Engineering revision patch has no changed files")
    return sorted(paths)


def preserve_review_artifact(path: Path, detailed_review: dict[str, Any]) -> None:
    if path.exists():
        existing = read_json(path)
        # A crash may have persisted the immutable review before the Graph append.
        # Resume only the identical diagnosis and bindings; keep its original bytes.
        expected = {key: value for key, value in detailed_review.items() if key != "reviewed_at"}
        actual = {key: value for key, value in existing.items() if key != "reviewed_at"}
        if actual != expected or not existing.get("reviewed_at"):
            raise SystemExit("Existing detailed review differs; refusing to overwrite or append")
        return
    write_json(path, detailed_review)


def append_review(campaign_root: Path, review: dict[str, Any]) -> dict[str, Any]:
    campaign, state = load_campaign(campaign_root)
    if state["stage"] != "result_recorded":
        raise SystemExit(f"Cannot append review from stage {state['stage']}")
    records = load_roadmap(campaign_root)
    known_node_ids = {ROOT_NODE_ID, *[record["node_id"] for record in records]}
    errors = validate_review(review, known_node_ids)
    if errors:
        raise SystemExit("Invalid review: " + "; ".join(errors))
    generation = int(state["next_generation"])
    if len(records) != generation - 1 or not verify_roadmap(campaign_root)["ok"]:
        raise SystemExit("Cannot append to noncontiguous or invalid Graph")
    intent_path = Path(state["active_intent"])
    candidate_path = Path(state["active_candidate_ref"])
    result_path = Path(state["active_result"])
    intent = read_json(intent_path)
    candidate = read_json(candidate_path)
    result = read_json(result_path)
    changed_files = review_candidate_changed_files(candidate)
    detailed_review = {
        **review,
        "schema_version": SCHEMA_VERSION,
        "campaign_id": campaign["campaign_id"],
        "generation": generation,
        "intent_sha256": intent["canonical_json_sha256"],
        "candidate_patch_sha256": candidate["patch_sha256"],
        "result_sha256": sha256_file(result_path),
        "reviewed_at": utc_now(),
    }
    review_path = campaign_root / "details" / f"review_gen_{generation:03d}.json"
    node_id = f"gen_{generation:03d}_{intent['mechanism_key']}"
    record = {
        "schema_version": SCHEMA_VERSION,
        "node_id": node_id,
        "generation": generation,
        "code_parent_node_id": intent.get("code_parent_node_id"),
        "materialization_base_node_id": intent["parent_selection"]["materialization_base_node_id"],
        "parent_edges": intent["parent_selection"]["parents"],
        "information_parent_snapshot_hash": intent["information_parent_snapshot_hash"],
        "intent": {
            "mechanism_key": intent["mechanism_key"],
            "primary_dimension": intent["primary_dimension"],
            "target_component": intent["target_component"],
            "proposed_mechanism": intent["proposed_mechanism"],
            "expected_behavioral_change": intent["expected_behavioral_change"],
            "novelty_claim": intent["novelty_claim"],
            **({"competition_binding": intent["competition_binding"]}
               if "competition_binding" in intent else {}),
        },
        "candidate": {
            "patch_sha256": candidate["patch_sha256"],
            "source_tree_sha256": candidate["source_tree_sha256"],
            "changed_files": changed_files,
        },
        "result": {
            **result["summary"],
            "strict_pass_delta": visible_result(result).get("strict_pass_delta"),
        },
        "evaluation_binding": result.get("evaluation_binding", {}),
        **({"mechanism_evidence": result["mechanism_evidence"]}
           if "mechanism_evidence" in result else {}),
        "review": {
            "outcome_label": review["outcome_label"],
            "source_reuse_recommendation": review["source_reuse_recommendation"],
            "short_review": review["short_review"],
            "failure_mechanism_key": review.get("failure_mechanism_key"),
            "relations_to_prior": review["relations_to_prior"],
            "causal_diagnosis": review["causal_diagnosis"],
        },
        "detail_links": {
            "sealed_intent": str(intent_path),
            "candidate_ref": str(candidate_path),
            "evaluation_result": str(result_path),
            "detailed_review": str(review_path),
            "batch_summary": result["batch_summary_path"],
            **({"mechanism_evidence": result["mechanism_evidence_path"]}
               if "mechanism_evidence_path" in result else {}),
            **({
                "hypothesis_pool": intent["competition_binding"]["hypothesis_pool_path"],
                "intent_selection": intent["competition_binding"]["selection_path"],
            } if "competition_binding" in intent else {}),
        },
        "previous_record_sha256": records[-1]["record_sha256"] if records else None,
        "appended_at": utc_now(),
    }
    record["record_sha256"] = record_hash(record)
    preserve_review_artifact(review_path, detailed_review)
    _, _, roadmap_path = campaign_paths(campaign_root)
    with roadmap_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(record) + "\n")
    state.update({
        "stage": "ready_for_intent",
        "next_generation": generation + 1,
        "last_completed_node_id": node_id,
        "updated_at": utc_now(),
    })
    for key in ("active_intent", "active_candidate_ref", "active_result"):
        state.pop(key, None)
    write_json(campaign_root / "campaign_state.json", state)
    verification = verify_roadmap(campaign_root)
    if not verification["ok"]:
        raise RuntimeError("Roadmap failed verification immediately after append")
    return record


def invoke_review(args: argparse.Namespace) -> int:
    campaign_root = args.campaign_root.resolve()
    session, campaign = prepare_review_context(campaign_root)
    if args.prepare_only:
        print(json.dumps({"status": "review_context_prepared", "session": str(session)}, indent=2))
        return 0
    review = invoke_codex_json(
        campaign=campaign,
        session=session,
        prompt=(session / "prompt.md").read_text(encoding="utf-8"),
        schema_path=session / "output_schema.json",
        output_name="diagnosis_response.json",
    )
    record = append_review(campaign_root, review)
    print(json.dumps({"status": "roadmap_node_appended", "node_id": record["node_id"], "record_sha256": record["record_sha256"]}, indent=2))
    return 0


def migrate_graph_v2(args: argparse.Namespace) -> int:
    """Migrate a quiescent v1 campaign without rewriting immutable roadmap lines."""
    campaign_root = args.campaign_root.resolve()
    campaign, state = load_campaign(campaign_root)
    if state.get("stage") != "ready_for_intent":
        raise SystemExit("Migration requires a quiescent campaign at ready_for_intent")
    if root_node_path(campaign_root).exists():
        raise SystemExit("Campaign already has a graph root")
    source_root = args.root_source.resolve()
    actual_hash = source_tree_hash(source_root)
    expected_hash = campaign.get("initial_parent_source_tree_sha256")
    if actual_hash != expected_hash:
        raise SystemExit(f"Root source hash mismatch: expected {expected_hash}, got {actual_hash}")
    result_path = args.root_result.resolve() if args.root_result else (
        Path(state["current_parent_result_path"]).resolve() if state.get("current_parent_result_path") else None
    )
    root = materialize_root_node(campaign_root, source_root, result_path)
    campaign["schema_version"] = SCHEMA_VERSION
    campaign["max_generations"] = max(int(campaign.get("max_generations") or 0), int(args.max_generations))
    campaign["graph_parent_selection"] = {
        "selector": "meta_agent",
        "mode": "multi_parent",
        "materialization_base_count": 1,
        "review_recommendations_are_nonbinding": True,
    }
    notes = list(campaign.get("protocol_notes") or [])
    for note in (
        "The meta-agent independently selects one or more graph parents for every intent.",
        "Exactly one selected parent supplies the materialized source tree; other parents supply mechanisms or evidence.",
        "A review recommendation annotates a node but never binds the next parent selection.",
    ):
        if note not in notes:
            notes.append(note)
    campaign["protocol_notes"] = notes
    state["schema_version"] = SCHEMA_VERSION
    state["parent_selection_mode"] = "meta_agent_graph_native"
    state["updated_at"] = utc_now()
    write_json(campaign_root / "campaign.json", campaign)
    write_json(campaign_root / "campaign_state.json", state)
    verification = verify_roadmap(campaign_root)
    if not verification["ok"]:
        raise RuntimeError("Roadmap failed verification after migration: " + "; ".join(verification["errors"]))
    print(json.dumps({
        "status": "migrated_graph_v2",
        "root": root,
        "next_generation": state["next_generation"],
        "max_generations": campaign["max_generations"],
        "roadmap": verification,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--campaign-root", type=Path, required=True)
    init.add_argument("--campaign-id", required=True)
    init.add_argument("--evolution-batch", type=Path, required=True)
    init.add_argument("--source-root", type=Path, default=ROOT)
    init.add_argument("--parent-result", type=Path)
    init.add_argument("--max-generations", type=int, default=6)
    init.add_argument("--max-agent-iterations", type=int, default=20)
    init.add_argument("--codex", default="codex")
    init.add_argument("--meta-profile", default="active-research-api")
    init.add_argument("--meta-model", default="glm-5.3-flash")

    intent = sub.add_parser("invoke-intent")
    intent.add_argument("--campaign-root", type=Path, required=True)
    intent.add_argument("--prepare-only", action="store_true")

    seal = sub.add_parser("seal-intent")
    seal.add_argument("--campaign-root", type=Path, required=True)
    seal.add_argument("--input", type=Path, required=True)

    candidate = sub.add_parser("record-candidate")
    candidate.add_argument("--campaign-root", type=Path, required=True)
    candidate.add_argument("--workspace", type=Path, required=True)

    candidate_revision = sub.add_parser("record-candidate-revision")
    candidate_revision.add_argument("--campaign-root", type=Path, required=True)
    candidate_revision.add_argument("--workspace", type=Path, required=True)
    candidate_revision.add_argument("--reason", required=True)

    invoke_candidate_parser = sub.add_parser("invoke-candidate")
    invoke_candidate_parser.add_argument("--campaign-root", type=Path, required=True)
    invoke_candidate_parser.add_argument("--workspace", type=Path)
    invoke_candidate_parser.add_argument("--mechanism-contract", type=Path)
    invoke_candidate_parser.add_argument("--codex")
    invoke_candidate_parser.add_argument("--model")
    invoke_candidate_parser.add_argument("--profile")
    invoke_candidate_parser.add_argument("--python", type=Path)
    invoke_candidate_parser.add_argument("--max-repairs", type=int, default=1)
    invoke_candidate_parser.add_argument("--prepare-only", action="store_true")

    result = sub.add_parser("record-result")
    result.add_argument("--campaign-root", type=Path, required=True)
    result.add_argument("--batch-summary", type=Path, required=True)
    result.add_argument("--parent-summary", type=Path)
    result.add_argument("--mechanism-evidence-card", type=Path)
    result.add_argument("--mechanism-terminal-audit", type=Path)

    review = sub.add_parser("invoke-review")
    review.add_argument("--campaign-root", type=Path, required=True)
    review.add_argument("--prepare-only", action="store_true")

    append = sub.add_parser("append-review")
    append.add_argument("--campaign-root", type=Path, required=True)
    append.add_argument("--input", type=Path, required=True)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--campaign-root", type=Path, required=True)
    snapshot.add_argument("--output", type=Path)

    detail = sub.add_parser("read-meta-detail")
    detail.add_argument("--campaign-root", type=Path, required=True)
    detail.add_argument("--node-id", required=True)
    detail.add_argument("--expected-sha256", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--campaign-root", type=Path, required=True)

    migrate = sub.add_parser("migrate-graph-v2")
    migrate.add_argument("--campaign-root", type=Path, required=True)
    migrate.add_argument("--root-source", type=Path, required=True)
    migrate.add_argument("--root-result", type=Path)
    migrate.add_argument("--max-generations", type=int, default=7)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        return init_campaign(args)
    if args.command == "invoke-intent":
        return invoke_intent(args)
    if args.command == "seal-intent":
        value = seal_intent(args.campaign_root.resolve(), read_json(args.input.resolve()))
        print(json.dumps({"status": "intent_sealed", "intent_sha256": value["canonical_json_sha256"]}, indent=2))
        return 0
    if args.command == "record-candidate":
        return record_candidate(args)
    if args.command == "record-candidate-revision":
        return record_candidate_revision(args)
    if args.command == "invoke-candidate":
        return invoke_candidate(args)
    if args.command == "record-result":
        return record_result(args)
    if args.command == "invoke-review":
        return invoke_review(args)
    if args.command == "append-review":
        value = append_review(args.campaign_root.resolve(), read_json(args.input.resolve()))
        print(json.dumps({"status": "roadmap_node_appended", "node_id": value["node_id"]}, indent=2))
        return 0
    if args.command == "migrate-graph-v2":
        return migrate_graph_v2(args)
    if args.command == "snapshot":
        value = build_snapshot(args.campaign_root.resolve())
        if args.output:
            write_json(args.output.resolve(), value)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    if args.command == "read-meta-detail":
        root = args.campaign_root.resolve()
        snapshot = build_snapshot(root)
        entries = snapshot.get("safe_detail_access", {}).get("nodes", [])
        entry = next((item for item in entries if item["node_id"] == args.node_id), None)
        if not entry or entry.get("status") != "available" or entry["sha256"] != args.expected_sha256:
            raise SystemExit("Safe detail unavailable or not bound to the requested snapshot")
        campaign, _ = load_campaign(root)
        record = next(item for item in load_roadmap(root) if item["node_id"] == args.node_id)
        value = detail_context.build_detail(root, campaign, record, compact_metrics(record.get("result", {})),
                                           compact_evaluation_binding(record.get("evaluation_binding", {})))
        raw = detail_context.encoded(value)
        if detail_context.digest(raw) != args.expected_sha256:
            raise SystemExit("Safe detail checksum mismatch")
        # Pure read: no file generation, model calls, SSH, or stage mutation.
        print(raw.decode("utf-8"), end="")
        return 0
    value = verify_roadmap(args.campaign_root.resolve())
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
