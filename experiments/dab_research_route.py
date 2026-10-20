"""Evidence-indexed research memory, separate from the immutable candidate roadmap.

Historical imports retain reviewer interpretations as interpretations. Only an
explicit, evidence-citing assessment changes a hypothesis state. Cutoff views
are built before any replay prediction is dispatched.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from experiments import dab_roadmap_protocol as protocol

SCHEMA = "dab_research_route_v1"
KINDS = {"problem", "hypothesis", "experiment", "evidence"}
RELATIONS = {"explains", "tests", "observes", "supports", "challenges", "depends_on",
             "refines", "alternative_to", "motivated_by", "code_base"}
STATES = {"unassessed", "open", "supported_in_scope", "challenged_in_scope",
          "mixed", "inconclusive", "retired"}
CAUSAL_CHAIN_FIELDS = ("opportunity", "reachability", "behavior", "target_failure", "task_effect")
VALIDITY_FIELDS = ("confounding",)
ASSESSMENT_STATES = {"supported", "challenged", "mixed", "unknown", "not_applicable"}
QUESTION_ORIGINS = {"unexplained_failure", "contradicted_prediction",
                    "missing_opportunity", "competing_explanation", "residual_failure"}
PRIORITY_POLICY = "exclude_blocked_then_impact_discrimination_evidence_cost_novelty"
PROBE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_]{2,79}")


def digest(value: Any) -> str:
    return hashlib.sha256(protocol.canonical_json(value).encode("utf-8")).hexdigest()


def new_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, indent=2)
        stream.write("\n")


def parse_model_json(text: str) -> dict:
    """Accept exactly one JSON response, optionally wrapped in one json fence."""
    value = text.strip()
    if value.startswith("```json"):
        if not value.endswith("```"):
            raise ValueError("Model response has an unterminated JSON fence")
        value = value[len("```json"):].strip()
        value = value[:-3].rstrip()
    if "```" in value:
        raise ValueError("Model response contains unexpected fenced content")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Model response must be a JSON object")
    return parsed


def project(value: Any) -> Any:
    """Drop retired metrics and archive paths; evidence is fetched through IDs."""
    value = protocol.strip_f1_context(value)
    if isinstance(value, dict):
        return {k: project(v) for k, v in value.items()
                if not any(marker in k.lower() for marker in
                           ("path", "detail_links", "evidence_refs", "answer_quality",
                            "ground_truth", "expected_answer", "response_text"))
                and k not in {"final_answer", "answer", "output"}}
    if isinstance(value, list):
        return [project(v) for v in value]
    return value


def artifact(root: Path, path: Path, pointer: str, value: Any) -> dict:
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_relative_to(root.resolve()):
        raise ValueError("Historical evidence must reside inside the campaign")
    return {"artifact": path.relative_to(root).as_posix(), "sha256": protocol.sha256_file(path),
            "json_pointer": pointer, "value": project(value)}


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def row_view(summary: dict, allowed: set[str]) -> dict:
    rows = summary.get("per_query_feedback", [])
    if not isinstance(rows, list):
        raise ValueError("Invalid historical rows")
    if any(row.get("query_id") not in allowed for row in rows):
        raise ValueError("Historical rows contain queries outside the evolution split")
    # Deterministic stratified examples, with coverage reported before sampling.
    def bucket(row: dict) -> str:
        if row.get("terminate_reason") == "query_wall_timeout_1200s":
            return "timeout"
        return {True: "strict_pass", False: "strict_fail", None: "unscored"}.get(
            row.get("strict_match_passed"), "unscored")
    counts: dict[str, int] = {}
    for row in rows:
        key = bucket(row)
        counts[key] = counts.get(key, 0) + 1
    samples = []
    for name in ("timeout", "strict_fail", "strict_pass", "unscored"):
        group = [row for row in rows if bucket(row) == name]
        group.sort(key=lambda r: (-int(r.get("tool_call_count") or 0), r["query_id"]))
        for row in group[:2]:
            samples.append({"stratum": name, **{k: row.get(k) for k in (
                "query_id", "status", "terminate_reason", "tool_call_count", "llm_call_count",
                "selected_stage", "selected_problem_type", "strict_match_passed")}})
    return {"coverage": counts, "total_rows": len(rows), "samples": samples,
            "selection": "up to two highest-tool-count rows in each outcome stratum",
            "limits": "Outcome labels do not attribute cause. Timeout telemetry may be absent. "
                      "Samples are not raw traces or a population estimate."}


def history(root: Path, through: int) -> dict:
    """Reconstruct only nodes <= through, never today's active campaign result."""
    root = root.resolve()
    verification = protocol.verify_roadmap(root)
    if not verification["ok"]:
        raise ValueError("Invalid historical roadmap")
    records = protocol.load_roadmap(root)
    if not 0 <= through <= len(records):
        raise ValueError("Cutoff is outside the completed roadmap")
    selected = records[:through]
    campaign = protocol.read_json(root / "campaign.json")
    cutoff_time = selected[-1]["appended_at"] if selected else None
    nodes, edges, sources, compact = [], [], [], []
    omissions = []
    for record in selected:
        generation = record["generation"]
        record_cutoff_time = record["appended_at"]
        directory = root / "generations" / f"gen_{generation:03d}"
        intent_path, result_path = directory / "sealed_intent.json", directory / "result.json"
        intent, result = protocol.read_json(intent_path), protocol.read_json(result_path)
        if (result.get("recorded_at") and _time(result["recorded_at"]) > _time(record_cutoff_time)):
            raise ValueError("Result was recorded after the cutoff")
        base = record["node_id"]
        ids = {kind: f"{kind}:{base}" for kind in KINDS}
        problem = project(intent.get("observed_prior_limitation", ""))
        hypothesis = {key: project(intent.get(key)) for key in (
            "mechanism_key", "primary_dimension", "proposed_mechanism",
            "expected_behavioral_change", "validation_expectations",
            "fallback_or_bounding_rule", "potential_regressions", "novelty_claim")}
        review_path = root / "details" / f"review_gen_{generation:03d}.json"
        review = protocol.read_json(review_path) if review_path.is_file() else record["review"]
        if (review.get("reviewed_at")
                and _time(review["reviewed_at"]) > _time(record_cutoff_time)):
            review = record["review"]
            omissions.append(f"generation {generation}: later detailed review omitted")
        observations = {"summary": protocol.compact_metrics(record["result"]),
                        "diagnostics": project(result.get("diagnostics", {})),
                        "mechanism_measurements": project(record.get("mechanism_evidence", {})),
                        "evaluation_binding": project(record.get("evaluation_binding", {}))}
        interpretation = {key: project(review.get(key)) for key in (
            "intent_realization", "activation_evidence", "behavioral_effect", "task_effect",
            "detailed_analysis", "failure_mechanism_key", "causal_diagnosis",
            "outcome_label", "source_reuse_recommendation")}
        provenance = [artifact(root, intent_path, "/", hypothesis),
                      artifact(root, result_path, "/diagnostics", observations["diagnostics"])]
        summary_path = Path(record.get("detail_links", {}).get("batch_summary", ""))
        if summary_path.is_file() and summary_path.resolve().is_relative_to(root.resolve()):
            summary = protocol.read_json(summary_path)
            if summary.get("created_at") and _time(summary["created_at"]) > _time(record_cutoff_time):
                raise ValueError("Row summary was created after the cutoff")
            observations["row_examples"] = row_view(summary, set(campaign["query_ids"]))
            provenance.append(artifact(root, summary_path, "/per_query_feedback", observations["row_examples"]))
        else:
            omissions.append(f"generation {generation}: local row summary unavailable")
        if review_path.is_file() and review == protocol.read_json(review_path):
            provenance.append(artifact(root, review_path, "/", interpretation))
        nodes.extend([
            {"id": ids["problem"], "kind": "problem", "generation": generation,
             "content": {"reported_limitation": problem, "status": "historical_proposal_not_audited_cause"}},
            {"id": ids["hypothesis"], "kind": "hypothesis", "generation": generation,
             "content": hypothesis, "state": "unassessed", "scope": "internal evolution batch"},
            {"id": ids["experiment"], "kind": "experiment", "generation": generation,
             "content": {"candidate_node_id": base, "candidate": record.get("candidate"),
                         "planned_changes": project(intent.get("planned_tool_control_flow_changes")),
                         "code_parent": record.get("code_parent_node_id")}},
            {"id": ids["evidence"], "kind": "evidence", "generation": generation,
             "content": {"observations": observations, "reviewer_interpretation": interpretation},
             "provenance": provenance},
        ])
        edges.extend([
            {"source": ids["hypothesis"], "target": ids["problem"], "relation": "explains"},
            {"source": ids["experiment"], "target": ids["hypothesis"], "relation": "tests"},
            {"source": ids["evidence"], "target": ids["experiment"], "relation": "observes"},
        ])
        for parent in record.get("parent_edges", []):
            if parent["node_id"] != protocol.ROOT_NODE_ID:
                edges.append({"source": ids["experiment"], "target": f"experiment:{parent['node_id']}",
                              "relation": "code_base" if parent["role"] == "code_base" else "motivated_by",
                              "historical_role": parent["role"]})
        compact.append(project(protocol.compact_graph_node(record)))
        ref_path = Path(record.get("detail_links", {}).get("candidate_ref", ""))
        ref = protocol.read_json(ref_path) if ref_path.is_file() else {}
        repo = Path(ref.get("repo", "")) if ref else None
        available = bool(repo and repo.is_dir())
        if available:
            available = protocol.source_tree_hash(repo) == record["candidate"]["source_tree_sha256"]
        sources.append({"node_id": base, "source_available_now": available,
                        "source_tree_sha256": record["candidate"]["source_tree_sha256"],
                        "reuse_annotation": review.get("source_reuse_recommendation"),
                        "generation": generation})
    root_node = protocol.load_root_node(root)
    root_repo = Path(root_node["source_root"])
    sources.insert(0, {"node_id": protocol.ROOT_NODE_ID, "generation": 0,
                      "source_tree_sha256": root_node["source_tree_sha256"],
                      "source_available_now": root_repo.is_dir() and
                      protocol.source_tree_hash(root_repo) == root_node["source_tree_sha256"],
                      "reuse_annotation": "baseline"})
    view = {"schema": SCHEMA, "campaign_id": campaign["campaign_id"],
            "through_generation": through, "historical_cutoff_time": cutoff_time,
            "historical_head": selected[-1]["record_sha256"] if selected else None,
            "nodes": nodes, "edges": edges, "compact_nodes": compact,
            "code_bases": sources, "omissions": omissions,
            "limits": ["Imported hypothesis states are unassessed; reviewer explanations are hypotheses.",
                       "Source availability is verified now, not reconstructed historical availability.",
                       "Reconstructed views use versioned archived records, not a bit-exact historic prompt.",
                       "No held-out queries, answer contents, retired metric or raw archive paths are exposed."]}
    view["snapshot_sha256"] = digest(view)
    return view


def verify_snapshot(view: dict) -> None:
    payload = {k: v for k, v in view.items() if k != "snapshot_sha256"}
    if digest(payload) != view.get("snapshot_sha256"):
        raise ValueError("Research snapshot changed")


def advance_history(root: Path, previous: dict, through: int) -> dict:
    """Carry reviewed hypotheses into the next immutable roadmap boundary."""
    verify_snapshot(previous)
    old_cutoff = previous["through_generation"]
    if through < old_cutoff:
        raise ValueError("Research history cannot move backward")
    old_import = history(root, old_cutoff)
    if previous.get("historical_head") != old_import["historical_head"]:
        raise ValueError("Research snapshot belongs to a different roadmap head")
    imported = {node["id"]: node for node in old_import["nodes"]}
    carried = {node["id"]: node for node in previous["nodes"]}
    if len(carried) != len(previous["nodes"]) or not set(imported).issubset(carried):
        raise ValueError("Research snapshot lost or duplicated imported nodes")
    mutable = {"state", "scope", "latest_assessment"}
    for node_id, original in imported.items():
        current = carried[node_id]
        if ({k: v for k, v in current.items() if k not in mutable} !=
                {k: v for k, v in original.items() if k not in mutable}):
            raise ValueError("Imported research evidence or hypothesis content changed")
    if previous["edges"][:len(old_import["edges"])] != old_import["edges"]:
        raise ValueError("Imported research relations changed")
    if previous["compact_nodes"] != old_import["compact_nodes"]:
        raise ValueError("Historical compact cards changed")
    if through == old_cutoff:
        return copy.deepcopy(previous)
    fresh = history(root, through)
    fresh_ids = {node["id"] for node in fresh["nodes"]}
    additions = [copy.deepcopy(node) for node in previous["nodes"] if node["id"] not in imported]
    if any(node["id"] in fresh_ids for node in additions):
        raise ValueError("Research node conflicts with a newly imported experiment")
    for node in fresh["nodes"]:
        if node["id"] in imported:
            for key in mutable:
                if key in carried[node["id"]]:
                    node[key] = copy.deepcopy(carried[node["id"]][key])
    fresh["nodes"].extend(additions)
    fresh["edges"].extend(copy.deepcopy(previous["edges"][len(old_import["edges"]):]))
    fresh["snapshot_sha256"] = digest({k: v for k, v in fresh.items() if k != "snapshot_sha256"})
    return fresh


def research_agenda(view: dict, limit: int = 12) -> list[dict]:
    """Surface evidence gaps and reviewer questions without asserting a new cause."""
    verify_snapshot(view)
    agenda: list[dict] = []
    for node in reversed(view["nodes"]):
        if node["kind"] in {"problem", "hypothesis"} and node.get("question_origin"):
            agenda.append({"origin": node["question_origin"], "source_id": node["id"],
                           "evidence_ids": node["evidence_ids"],
                           "question": node["content"]["statement"],
                           "status": node.get("state", "open")})
        if node["kind"] == "hypothesis" and node.get("latest_assessment"):
            assessment = node["latest_assessment"]
            for question in assessment.get("remaining_questions", [])[:2]:
                agenda.append({"origin": "competing_explanation", "source_id": node["id"],
                               "evidence_ids": assessment["evidence_ids"],
                               "question": question, "status": node["state"]})
            chain = assessment.get("causal_chain", {})
            # Legacy snapshots remain readable, but all new reviews use causal_chain.
            if not chain and "axes" in assessment:
                chain = {name: assessment["axes"][name] for name in CAUSAL_CHAIN_FIELDS
                         if name in assessment["axes"]}
            for link_name, link in chain.items():
                status = link["status"]
                if status == "unknown":
                    origin = "missing_opportunity" if link_name == "opportunity" else "unexplained_failure"
                    question = f"What measurement resolves unknown {link_name} for this hypothesis?"
                elif status == "challenged":
                    origin = "contradicted_prediction"
                    question = f"What alternative explains the challenged {link_name} link?"
                elif status == "mixed":
                    origin = "competing_explanation"
                    question = f"Which condition separates the mixed {link_name} evidence?"
                else:
                    continue
                agenda.append({"origin": origin, "source_id": node["id"],
                               "evidence_ids": link["evidence_ids"], "question": question,
                               "status": node["state"]})
            for facet in assessment.get("facets", []):
                if facet["status"] in {"unknown", "challenged", "mixed"}:
                    agenda.append({"origin": "competing_explanation" if facet["status"] == "mixed"
                                   else "unexplained_failure", "source_id": node["id"],
                                   "evidence_ids": facet["evidence_ids"],
                                   "question": f"What evidence resolves the {facet['name']} diagnostic facet?",
                                   "status": node["state"]})
        elif node["kind"] == "evidence":
            measurements = node["content"].get("observations", {}).get("mechanism_measurements", {})
            for statement in measurements.get("evidence_limits", [])[:3]:
                lowered = statement.lower()
                origin = ("missing_opportunity" if any(word in lowered for word in
                          ("telemetry", "opportunity", "denominator", "unmeasured"))
                          else "contradicted_prediction" if any(word in lowered for word in
                          ("exceed", "failed", "never", "zero")) else "residual_failure")
                agenda.append({"origin": origin, "source_id": node["id"],
                               "evidence_ids": [node["id"]], "question": statement,
                               "status": "archived_limit_not_new_fact"})
        if len(agenda) >= limit:
            break
    return agenda[:limit]


def retrieve(view: dict, ids: list[str]) -> dict:
    verify_snapshot(view)
    indexed = {node["id"]: node for node in view["nodes"]}
    if not ids or any(node_id not in indexed for node_id in ids):
        raise ValueError("Unknown or empty research evidence selection")
    return {"snapshot_sha256": view["snapshot_sha256"], "nodes": [indexed[key] for key in ids],
            "edges": [edge for edge in view["edges"] if edge["source"] in ids or edge["target"] in ids]}


def _resolve_node_id(ref: str, nodes: dict[str, dict], aliases: dict[str, str]) -> str:
    """Resolve a historic candidate alias without treating it as measured evidence."""
    resolved = aliases.get(ref, ref)
    if resolved not in nodes:
        raise ValueError("Research reference is unavailable at the cutoff")
    return resolved


def _citations(refs: Any, nodes: dict, cutoff: int) -> None:
    if not isinstance(refs, list) or not refs:
        raise ValueError("Every judgment needs evidence references")
    for ref in refs:
        node = nodes.get(ref)
        if node is None or node["kind"] != "evidence" or node["generation"] > cutoff:
            raise ValueError("Citation is not available evidence at the cutoff")


def apply_update(view: dict, update: dict) -> dict:
    """Validate the entire update before applying any state changes."""
    verify_snapshot(view)
    validate_schema(update, update_schema())
    if update.get("snapshot_sha256") != view["snapshot_sha256"]:
        raise ValueError("Update refers to a stale snapshot")
    nodes = {node["id"]: copy.deepcopy(node) for node in view["nodes"]}
    cutoff = view["through_generation"]
    added = update.get("new_nodes", [])
    for node in added:
        if node.get("kind") not in {"problem", "hypothesis", "evidence", "experiment"}:
            raise ValueError("Invalid research node kind")
        if not node.get("id") or node["id"] in nodes or not isinstance(node.get("content"), dict):
            raise ValueError("Duplicate/invalid research node")
        if node.get("generation") != cutoff:
            raise ValueError("New node must bind the current evidence boundary")
        if node["kind"] == "evidence":
            raise ValueError("New measured evidence requires an archived experiment import")
        _citations(node.get("evidence_ids"), nodes, cutoff)
        if node.get("question_origin") not in QUESTION_ORIGINS or not node.get("origin_reason"):
            raise ValueError("New research node must explain where its question came from")
        node = copy.deepcopy(node)
        if node["kind"] == "hypothesis":
            node["state"] = "open"
        nodes[node["id"]] = node
    seen = set()
    for assessment in update.get("assessments", []):
        node = nodes.get(assessment.get("hypothesis_id"))
        if node is None or node["kind"] != "hypothesis" or node["id"] in seen:
            raise ValueError("Invalid or duplicate hypothesis assessment")
        seen.add(node["id"])
        if assessment.get("state") not in STATES or not assessment.get("scope"):
            raise ValueError("Assessment must state a valid state and its scope")
        _citations(assessment.get("evidence_ids"), nodes, cutoff)
        chain = assessment.get("causal_chain", {})
        validity = assessment.get("validity", {})
        if set(chain) != set(CAUSAL_CHAIN_FIELDS):
            raise ValueError("Review must address the complete causal chain")
        if set(validity) != set(VALIDITY_FIELDS):
            raise ValueError("Review must address causal validity")
        judgments = list(chain.values()) + list(validity.values())
        facets = assessment.get("facets", [])
        facet_names = [facet.get("name", "").strip().casefold() for facet in facets]
        if any(not name for name in facet_names) or len(facet_names) != len(set(facet_names)):
            raise ValueError("Diagnostic facet names must be non-empty and unique")
        judgments.extend(facets)
        for judgment in judgments:
            if judgment.get("status") not in ASSESSMENT_STATES or not judgment.get("reason"):
                raise ValueError("Invalid causal or diagnostic assessment")
            _citations(judgment.get("evidence_ids"), nodes, cutoff)
        if not isinstance(assessment.get("remaining_questions"), list):
            raise ValueError("Review must retain remaining questions")
        node.update({"state": assessment["state"], "scope": assessment["scope"],
                     "latest_assessment": copy.deepcopy(assessment)})
    edges = copy.deepcopy(view["edges"])
    for edge in update.get("new_edges", []):
        if edge.get("source") not in nodes or edge.get("target") not in nodes or edge.get("relation") not in RELATIONS:
            raise ValueError("Invalid research edge")
        source_kind, target_kind = nodes[edge["source"]]["kind"], nodes[edge["target"]]["kind"]
        allowed = {"explains": ("hypothesis", "problem"),
                   "tests": ("experiment", "hypothesis"),
                   "observes": ("evidence", "experiment"),
                   "supports": ("evidence", "hypothesis"),
                   "challenges": ("evidence", "hypothesis"),
                   "alternative_to": ("hypothesis", "hypothesis"),
                   "refines": ("hypothesis", "hypothesis"),
                   "code_base": ("experiment", "experiment")}
        if edge["relation"] in allowed and (source_kind, target_kind) != allowed[edge["relation"]]:
            raise ValueError("Research relation connects incompatible node kinds")
        _citations(edge.get("evidence_ids"), nodes, cutoff)
        edges.append(copy.deepcopy(edge))
    for node in added:
        relation = {"problem": "explains", "hypothesis": "explains", "experiment": "tests"}[node["kind"]]
        if not any(edge["relation"] == relation and
                   (edge["target"] == node["id"] if node["kind"] == "problem"
                    else edge["source"] == node["id"])
                   for edge in update.get("new_edges", [])):
            raise ValueError("New research node needs a typed hypothesis/experiment link")
    result = {k: copy.deepcopy(v) for k, v in view.items() if k != "snapshot_sha256"}
    result["nodes"], result["edges"] = list(nodes.values()), edges
    result["snapshot_sha256"] = digest(result)
    return result


def _append_snapshot_event(log: Path, view: dict, next_view: dict,
                           event_type: str, payload: dict) -> dict:
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    previous = None
    for event in events:
        payload = {k: v for k, v in event.items() if k != "event_sha256"}
        if event.get("previous_sha256") != previous or event.get("event_sha256") != digest(payload):
            raise ValueError("Research event chain is invalid")
        previous = event["event_sha256"]
    if events and events[-1]["result_snapshot_sha256"] != view["snapshot_sha256"]:
        raise ValueError("Research update forks the recorded snapshot")
    event = {"schema": SCHEMA, "event_type": event_type, "previous_sha256": previous,
             event_type: payload,
             "input_snapshot_sha256": view["snapshot_sha256"],
             "result_snapshot_sha256": next_view["snapshot_sha256"]}
    event["event_sha256"] = digest(event)
    log.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive lock rejects concurrent writers instead of interleaving events.
    lock = log.with_suffix(".lock")
    try:
        with lock.open("x", encoding="utf-8"):
            fresh = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
            if fresh != events:
                raise ValueError("Research event log changed before append")
            with log.open("a", encoding="utf-8") as stream:
                stream.write(protocol.canonical_json(event) + "\n")
    finally:
        lock.unlink(missing_ok=True)
    return next_view


def append_update(log: Path, view: dict, update: dict) -> dict:
    return _append_snapshot_event(log, view, apply_update(view, update), "review_update", update)


def probe_schema() -> dict:
    def obj(properties: dict) -> dict:
        return {"type": "object", "additionalProperties": False,
                "properties": properties, "required": list(properties)}
    text = {"type": "string", "minLength": 1, "maxLength": 900}
    refs = {"type": "array", "minItems": 1, "maxItems": 8, "items": text}
    measurement = obj({"name": text, "json_pointer": text})
    source = obj({"path": text, "sha256": text,
                  "measurements": {"type": "array", "minItems": 1, "maxItems": 32,
                                   "items": measurement}})
    design = obj({"question": text, "intervention": text, "observable_prediction": text,
                  "negative_control": text, "falsification_condition": text,
                  "resource_budget": text, "scope": text})
    return obj({"snapshot_sha256": text, "probe_id": text, "generation": {"type": "integer"},
                "hypothesis_ids": refs, "design": design,
                "artifacts": {"type": "array", "minItems": 1, "maxItems": 8,
                              "items": source}})


def _json_pointer(value: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must be absolute")
    current = value
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise ValueError("JSON pointer does not resolve")
    return current


def import_probe(view: dict, campaign_root: Path, record: dict) -> dict:
    """Import measured probe counters from hash-bound campaign artifacts."""
    verify_snapshot(view)
    validate_schema(record, probe_schema())
    if record["snapshot_sha256"] != view["snapshot_sha256"]:
        raise ValueError("Probe was designed against a different research snapshot")
    if record["generation"] != view["through_generation"] or not PROBE_ID_RE.fullmatch(record["probe_id"]):
        raise ValueError("Probe ID or generation is invalid")
    nodes = {node["id"]: node for node in view["nodes"]}
    for hypothesis_id in record["hypothesis_ids"]:
        if nodes.get(hypothesis_id, {}).get("kind") != "hypothesis":
            raise ValueError("Probe tests an unavailable hypothesis")
    experiment_id, evidence_id = f"experiment:{record['probe_id']}", f"evidence:{record['probe_id']}"
    if experiment_id in nodes or evidence_id in nodes:
        raise ValueError("Probe already exists")
    root = campaign_root.resolve()
    measurements, provenance = {}, []
    for source in record["artifacts"]:
        relative = Path(source["path"])
        candidate = root / relative
        path = candidate.resolve()
        if (relative.is_absolute() or candidate.is_symlink() or
                not path.is_relative_to(root) or not path.is_file()):
            raise ValueError("Probe artifact must be a regular campaign file")
        if protocol.sha256_file(path) != source["sha256"]:
            raise ValueError("Probe artifact hash differs")
        payload = protocol.read_json(path)
        for item in source["measurements"]:
            if item["name"] in measurements:
                raise ValueError("Probe measurement names must be unique")
            measured = _json_pointer(payload, item["json_pointer"])
            if (type(measured) not in (int, float, bool) or
                    isinstance(measured, float) and not math.isfinite(measured)):
                raise ValueError("Probe evidence accepts only finite scalar measurements")
            measurements[item["name"]] = measured
            provenance.append(artifact(root, path, item["json_pointer"], measured))
    result = {k: copy.deepcopy(v) for k, v in view.items() if k != "snapshot_sha256"}
    result["nodes"].extend([
        {"id": experiment_id, "kind": "experiment", "generation": record["generation"],
         "content": {"probe_id": record["probe_id"], **copy.deepcopy(record["design"])}},
        {"id": evidence_id, "kind": "evidence", "generation": record["generation"],
         "content": {"observations": {"probe_measurements": measurements,
                                       "scope": record["design"]["scope"]}},
         "provenance": provenance},
    ])
    result["edges"].extend(
        [{"source": experiment_id, "target": hypothesis_id, "relation": "tests"}
         for hypothesis_id in record["hypothesis_ids"]] +
        [{"source": evidence_id, "target": experiment_id, "relation": "observes"}])
    result["snapshot_sha256"] = digest(result)
    return result


def append_probe(log: Path, view: dict, campaign_root: Path, record: dict) -> dict:
    next_view = import_probe(view, campaign_root, record)
    return _append_snapshot_event(log, view, next_view, "probe_import", record)


def decision_schema() -> dict:
    def obj(properties: dict) -> dict:
        return {"type": "object", "additionalProperties": False,
                "properties": properties, "required": list(properties)}
    text = {"type": "string", "minLength": 1, "maxLength": 900}
    texts = {"type": "array", "maxItems": 8, "items": text}
    refs = {"type": "array", "minItems": 1, "maxItems": 8, "items": text}
    read_refs = {"type": "array", "minItems": 1, "maxItems": 32, "items": text}
    option = obj({"id": text, "question": text, "hypothesis": text,
                  "evidence_ids": refs, "context_ids": refs,
                  "competing_explanation": text,
                  "opportunity_status": {"type": "string", "enum": ["measured", "unknown", "absent"]},
                  "scope_and_coverage": text, "discriminating_observation": text,
                  "falsification_condition": text, "expected_task_value": text})
    parent = obj({"node_id": text, "role": {"type": "string", "enum": [
        "hypothesis", "mechanism_donor", "failure_evidence", "complementary_evidence"]}, "use": text})
    return obj({"snapshot_sha256": text, "options": {"type": "array", "minItems": 2,
        "maxItems": 3, "items": option}, "selected_option_id": text,
        "decision": {"type": "string", "enum": ["diagnose", "probe", "implement", "stop"]},
        "selection_reason": text, "research_parents": {"type": "array", "maxItems": 6, "items": parent},
        "code_parent": {"type": ["string", "null"]}, "code_parent_reason": text,
        "experiment": obj({"design": text, "observable_prediction": text, "negative_control": text,
                           "opportunity_gate": text, "resource_budget": text}),
        "read_node_ids": read_refs, "unresolved_questions": texts})


def navigation_schema() -> dict:
    """A research choice with an explicit comparison of all candidate questions."""
    def obj(properties: dict) -> dict:
        return {"type": "object", "additionalProperties": False,
                "properties": properties, "required": list(properties)}
    text = {"type": "string", "minLength": 1, "maxLength": 900}
    refs = {"type": "array", "minItems": 1, "maxItems": 8, "items": text}
    measurement = obj({"evidence_id": text, "count_pointer": text,
                       "count": {"type": "integer"}, "coverage_pointer": text,
                       "coverage": {"type": "integer"}})
    assessment = obj({"option_id": text,
                      "question_origin": {"type": "string", "enum": sorted(QUESTION_ORIGINS)},
                      "source_node_ids": refs, "origin_evidence_ids": refs,
                      "impact": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
                      "evidence_strength": {"type": "string", "enum": ["measured", "mixed", "unknown"]},
                      "discrimination": {"type": "string", "enum": ["strong", "partial", "weak"]},
                      "cost": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
                      "novelty": {"type": "string", "enum": ["new", "extends", "repeated"]},
                      "readiness": {"type": "string", "enum": ["implement_ready", "probe_first",
                                                          "diagnose_first", "blocked"]},
                      "opportunity_measurement": {"type": ["object", "null"],
                                                   **{k: v for k, v in measurement.items() if k != "type"}},
                      "rank_reason": text})
    return obj({"snapshot_sha256": text, "decision": decision_schema(),
                "priority_order": {"type": "array", "minItems": 2, "maxItems": 3, "items": text},
                "option_assessments": {"type": "array", "minItems": 2, "maxItems": 3,
                                       "items": assessment},
                "selection_rule": {"type": "string", "enum": [PRIORITY_POLICY]},
                "stop_condition": text})


def _priority(item: dict) -> tuple:
    if item["readiness"] == "blocked":
        return (-1, -1, -1, -1, -1)
    impact = {"high": 3, "medium": 2, "unknown": 1, "low": 0}
    discrimination = {"strong": 2, "partial": 1, "weak": 0}
    evidence = {"measured": 2, "mixed": 1, "unknown": 0}
    cost = {"low": 3, "medium": 2, "unknown": 1, "high": 0}
    novelty = {"new": 2, "extends": 1, "repeated": 0}
    return (impact[item["impact"]], discrimination[item["discrimination"]],
            evidence[item["evidence_strength"]], cost[item["cost"]], novelty[item["novelty"]])


def _pointer(value: dict, pointer: str) -> Any:
    if not pointer.startswith("/content/observations/"):
        raise ValueError("Opportunity must cite a measured observation")
    return _json_pointer(value, pointer)


def validate_navigation(plan: dict, view: dict) -> None:
    validate_schema(plan, navigation_schema())
    verify_snapshot(view)
    if plan["snapshot_sha256"] != view["snapshot_sha256"]:
        raise ValueError("Navigation is bound to a different snapshot")
    decision = plan["decision"]
    validate_decision(decision, view)
    option_ids = {option["id"] for option in decision["options"]}
    order = plan["priority_order"]
    assessments = plan["option_assessments"]
    if (len(order) != len(option_ids) or set(order) != option_ids or
            len(assessments) != len(option_ids) or
            {item["option_id"] for item in assessments} != option_ids or
            order[0] != decision["selected_option_id"]):
        raise ValueError("Priority order must rank each option exactly once, selected first")
    nodes = {node["id"]: node for node in view["nodes"]}
    aliases = {base["node_id"]: f"experiment:{base['node_id']}" for base in view["code_bases"]
               if base["node_id"] != protocol.ROOT_NODE_ID}
    read = {_resolve_node_id(ref, nodes, aliases) for ref in decision["read_node_ids"]}
    selected = next(item for item in assessments if item["option_id"] == order[0])
    for item in assessments:
        _citations(item["origin_evidence_ids"], nodes, view["through_generation"])
        source = {_resolve_node_id(ref, nodes, aliases) for ref in item["source_node_ids"]}
        if not source.issubset(read) or not set(item["origin_evidence_ids"]).issubset(read):
            raise ValueError("Question origin cites material outside the reported reading")
        measurement = item["opportunity_measurement"]
        if measurement is None:
            continue
        evidence_id = measurement["evidence_id"]
        _citations([evidence_id], nodes, view["through_generation"])
        if evidence_id not in item["origin_evidence_ids"]:
            raise ValueError("Opportunity evidence must support the option's origin")
        count = _pointer(nodes[evidence_id], measurement["count_pointer"])
        coverage = _pointer(nodes[evidence_id], measurement["coverage_pointer"])
        if (type(count) is not int or type(coverage) is not int or
                (count, coverage) != (measurement["count"], measurement["coverage"]) or
                count < 0 or coverage < count or coverage == 0):
            raise ValueError("Opportunity count or denominator does not match the evidence")
    by_id = {item["option_id"]: item for item in assessments}
    expected_order = sorted(option_ids)
    expected_order.sort(key=lambda item_id: _priority(by_id[item_id]), reverse=True)
    if order != expected_order:
        raise ValueError("Priority order does not follow the recorded selection policy")
    if decision["decision"] == "implement":
        measurement = selected["opportunity_measurement"]
        if (selected["readiness"] != "implement_ready" or measurement is None or
                measurement["count"] == 0):
            raise ValueError("Implementation requires a positive measured opportunity")
    elif decision["decision"] == "stop" and selected["readiness"] != "blocked":
        raise ValueError("A stop decision needs an explicit blocking condition")


def update_schema() -> dict:
    def obj(properties: dict) -> dict:
        return {"type": "object", "additionalProperties": False,
                "properties": properties, "required": list(properties)}
    text = {"type": "string", "minLength": 1}
    refs = {"type": "array", "minItems": 1, "items": text}
    judgment = obj({"status": {"type": "string", "enum": sorted(ASSESSMENT_STATES)},
                    "reason": text, "evidence_ids": refs})
    facet = obj({"name": text, "status": {"type": "string", "enum": sorted(ASSESSMENT_STATES)},
                 "reason": text, "evidence_ids": refs})
    assessment = obj({"hypothesis_id": text, "state": {"type": "string", "enum": sorted(STATES)},
                      "scope": text, "evidence_ids": refs,
                      "causal_chain": obj({name: judgment for name in CAUSAL_CHAIN_FIELDS}),
                      "validity": obj({name: judgment for name in VALIDITY_FIELDS}),
                      "facets": {"type": "array", "maxItems": 24, "items": facet},
                      "remaining_questions": {"type": "array", "items": text}})
    node = obj({"id": text, "kind": {"type": "string", "enum": ["problem", "hypothesis", "experiment"]},
                "generation": {"type": "integer"}, "content": obj({"statement": text,
                    "prediction": text, "falsification_condition": text, "scope": text}),
                "evidence_ids": refs,
                "question_origin": {"type": "string", "enum": sorted(QUESTION_ORIGINS)},
                "origin_reason": text})
    edge = obj({"source": text, "target": text, "relation": {"type": "string", "enum": sorted(RELATIONS)},
                "evidence_ids": refs, "reason": text})
    return obj({"snapshot_sha256": text, "assessments": {"type": "array", "items": assessment},
                "new_nodes": {"type": "array", "items": node},
                "new_edges": {"type": "array", "items": edge}})


def validate_decision(value: dict, view: dict) -> None:
    validate_schema(value, decision_schema())
    verify_snapshot(view)
    if value["snapshot_sha256"] != view["snapshot_sha256"]:
        raise ValueError("Decision snapshot binding differs")
    nodes = {node["id"]: node for node in view["nodes"]}
    aliases = {base["node_id"]: f"experiment:{base['node_id']}" for base in view["code_bases"]
               if base["node_id"] != protocol.ROOT_NODE_ID}
    options = value["options"]
    option_ids = [option["id"] for option in options]
    if len(set(option_ids)) != len(option_ids) or value["selected_option_id"] not in option_ids:
        raise ValueError("Invalid competing option selection")
    for option in options:
        _citations(option["evidence_ids"], nodes, view["through_generation"])
        for ref in option["context_ids"]:
            _resolve_node_id(ref, nodes, aliases)
    read = {_resolve_node_id(ref, nodes, aliases) for ref in value["read_node_ids"]}
    factual = {ref for option in options for ref in option["evidence_ids"]}
    contextual = {_resolve_node_id(ref, nodes, aliases)
                  for option in options for ref in option["context_ids"]}
    if not factual.issubset(read) or not contextual.issubset(read):
        raise ValueError("Proposal cites material it did not report reading")
    seen_parents = set()
    for parent in value["research_parents"]:
        resolved = aliases.get(parent["node_id"], parent["node_id"])
        if resolved not in nodes or resolved in seen_parents:
            raise ValueError("Research parent is unavailable or repeated at the cutoff")
        seen_parents.add(resolved)
    if value["decision"] == "implement":
        selected = next(option for option in options if option["id"] == value["selected_option_id"])
        if selected["opportunity_status"] != "measured":
            raise ValueError("Implementation requires measured opportunity; choose a probe first")
    if value["code_parent"] is not None:
        bases = {base["node_id"]: base for base in view["code_bases"]}
        if not bases.get(value["code_parent"], {}).get("source_available_now"):
            raise ValueError("Code parent has no verified frozen source")
    elif value["decision"] == "implement":
        raise ValueError("Implementation requires exactly one verified code base")


def validate_schema(value: Any, schema: dict, path: str = "response") -> None:
    """Validate the restricted schema dialect used by research responses."""
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    matches = {"object": isinstance(value, dict), "array": isinstance(value, list),
               "string": isinstance(value, str), "null": value is None,
               "integer": type(value) is int, "boolean": type(value) is bool}
    if types and not any(matches.get(kind, False) for kind in types):
        raise ValueError(f"{path}: wrong type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: invalid enum")
    if isinstance(value, str) and len(value.strip()) < schema.get("minLength", 0):
        raise ValueError(f"{path}: empty text")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError(f"{path}: missing fields")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"{path}: extra fields")
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], path + "." + key)
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")):
            raise ValueError(f"{path}: invalid item count")
        for index, item in enumerate(value):
            validate_schema(item, schema.get("items", {}), f"{path}[{index}]")


def review_context(view: dict, hypothesis_ids: list[str] | None = None) -> dict:
    """Return the direct evidence neighbourhood needed to audit hypotheses."""
    verify_snapshot(view)
    indexed = {node["id"]: node for node in view["nodes"]}
    available = [node["id"] for node in view["nodes"] if node["kind"] == "hypothesis"]
    selected = hypothesis_ids or available
    if not selected or len(set(selected)) != len(selected) or any(
            node_id not in indexed or indexed[node_id]["kind"] != "hypothesis"
            for node_id in selected):
        raise ValueError("Review selection must name unique available hypotheses")
    chosen = set(selected)
    for edge in view["edges"]:
        if edge["source"] in chosen or edge["target"] in chosen:
            chosen.add(edge["source"])
            chosen.add(edge["target"])
    experiments = {node_id for node_id in chosen if indexed[node_id]["kind"] == "experiment"}
    for edge in view["edges"]:
        if edge["target"] in experiments and indexed[edge["source"]]["kind"] == "evidence":
            chosen.add(edge["source"])
    def clip(value: Any, depth: int = 0) -> Any:
        """Bound review prose without dropping a signed source from the snapshot."""
        if depth > 4:
            return {"truncated": True, "sha256": digest(value)}
        if isinstance(value, str):
            return value if len(value) <= 1600 else value[:1600] + " [truncated; sha256=" + digest(value) + "]"
        if isinstance(value, list):
            values = [clip(item, depth + 1) for item in value[:12]]
            if len(value) > 12:
                values.append({"truncated_items": len(value) - 12, "sha256": digest(value)})
            return values
        if isinstance(value, dict):
            keys = list(value)
            result = {key: clip(value[key], depth + 1) for key in keys[:30]}
            if len(keys) > 30:
                result["_truncated_keys"] = {"count": len(keys) - 30, "sha256": digest(value)}
            return result
        return value

    def brief(node: dict) -> dict:
        result = {key: copy.deepcopy(node[key]) for key in ("id", "kind", "generation")}
        if node["kind"] == "evidence":
            observations = node.get("content", {}).get("observations", {})
            result["content"] = {"observations": clip({
                "summary": observations.get("summary"),
                "mechanism_measurements": observations.get("mechanism_measurements"),
                "diagnostics": observations.get("diagnostics"),
                "row_examples": observations.get("row_examples"),
                "probe_measurements": observations.get("probe_measurements"),
                "reviewer_interpretation": node.get("content", {}).get("reviewer_interpretation"),
            })}
            result["provenance"] = [{key: ref[key] for key in ("sha256", "json_pointer")}
                                    for ref in node.get("provenance", [])]
        else:
            result["content"] = clip(node.get("content", {}))
        for key in ("state", "scope", "latest_assessment", "question_origin", "origin_reason", "evidence_ids"):
            if key in node:
                result[key] = clip(node[key])
        return result

    nodes = [brief(node) for node in view["nodes"] if node["id"] in chosen]
    edges = [edge for edge in view["edges"]
             if edge["source"] in chosen and edge["target"] in chosen]
    return {"snapshot_sha256": view["snapshot_sha256"],
            "through_generation": view["through_generation"],
            "review_hypothesis_ids": selected, "nodes": nodes, "edges": edges,
            "limits": view["limits"]}


def review_prompt(view: dict, hypothesis_ids: list[str] | None = None) -> str:
    context = review_context(view, hypothesis_ids)
    return ("Review hypotheses using evidence IDs. Separate recorded measurements from historical "
            "reviewer explanations. Assess the required causal chain independently: opportunity "
            "(does the target condition occur), reachability (can the mechanism intercept it), "
            "behavior (did the intervention change execution), target_failure (did that change the "
            "intended failure), and task_effect (did task outcome improve). Assess confounding as the "
            "required validity check. Add open-named diagnostic facets only when the evidence makes "
            "them useful, for example timing, cost, regressions, state_consistency or tool_semantics; "
            "do not fill a predefined checklist or invent unsupported facets. Every chain link, "
            "validity judgment and facet must cite evidence. "
            "Use unknown where telemetry is missing. State scope, evidence IDs, remaining questions "
            "and counterexamples. Do not infer causal task gain from an unpaired score. "
            "New problems and hypotheses must arise from unexplained residuals, contradicted "
            "predictions, missing opportunity, or competing explanations, each with cited evidence "
            "and a typed link. New nodes describe questions available at THIS evidence boundary: their "
            "generation must equal through_generation, not a proposed future candidate generation. "
            "Relations are type constrained: hypothesis --explains--> problem; experiment --tests--> "
            "hypothesis; evidence --observes--> experiment; evidence --supports/challenges--> hypothesis; "
            "hypothesis --alternative_to/refines--> hypothesis; experiment --code_base--> experiment. "
            "Every new problem needs an incoming hypothesis --explains--> problem edge; every new "
            "hypothesis needs an outgoing explains edge to a problem, unless it instead refines an "
            "existing hypothesis and also explains an existing or new problem. Do not create an evidence "
            "edge to a problem: cite the evidence on its explaining hypothesis/edge instead. Return assessments for "
            "every and only the supplied review_hypothesis_ids, "
            "bound to snapshot_sha256, plus any justified new_nodes/new_edges.\n" +
            protocol.canonical_json(context) + "\nResponse schema:\n" + protocol.canonical_json(update_schema()))


def decision_prompt(context: dict) -> str:
    guidance = ""
    if context["arm"] == "route":
        guidance = ("Use the problem/hypothesis/experiment/evidence links to distinguish disputed "
                    "premises from implementation failures. Choose the research question before the "
                    "code base. Consult counterevidence and dependencies; explain what new observation "
                    "would change the route. Imported hypotheses are unassessed.\n")
    return ("Conduct one retrospective research decision at the supplied cutoff. Use ONLY this "
            "context, with no external tools or prior knowledge of later generations. Return exactly "
            "the supplied JSON schema, with no extra keys. Be concise: prefer exactly two competing "
            "options and keep every text field under 900 characters. Each option must put factual "
            "measurements only in evidence_ids (IDs beginning evidence:) and may put problem/hypothesis/"
            "experiment context in context_ids. read_node_ids must include every cited ID. Cite the "
            "retrieved IDs only; it may list up to 32 accumulated IDs even though each individual option "
            "uses at most eight. Report unknown opportunity honestly, and select diagnose/probe/implement/"
            "stop. Select research parents separately from at most one verified code parent; never use "
            "root_baseline as a research parent. Describe an experiment that distinguishes explanations, "
            "a falsification condition and a negative control. No query-specific answer logic. Do not "
            "assume a tool interface beyond supplied source facts. Scores are descriptive. Historical "
            "candidate IDs resolve to experiment nodes only for research_parents and read_node_ids. "
            "The output is a research decision, not a sealed intent or launch authorization.\n" +
            guidance + protocol.canonical_json(context))


def navigation_prompt(context: dict) -> str:
    return ("Choose the next research step from this evidence-bound route. Start with the "
            "research_agenda, but propose at least two genuinely competing questions. For each "
            "option identify its question origin, evidence strength, likely scope of impact, "
            "discriminating power, cost, novelty and readiness. Rank every option and say why "
            "lower choices can wait. Use selection_rule exactly '" + PRIORITY_POLICY + "': exclude "
            "blocked options, then rank lexicographically by impact, discrimination, evidence "
            "strength, lower cost and novelty; break a complete tie by ascending option ID. If "
            "implementation is chosen, cite an exact positive activation "
            "count and coverage denominator from an evidence node using JSON pointers under "
            "/content/observations/. Unknown or zero opportunity calls for diagnosis or a probe. "
            "Treat reviewer interpretations as hypotheses; do not infer causal gain from an "
            "unpaired score. Pick a research parent for reasons, and one verified code parent "
            "only when implementation needs source. Return exactly the schema below.\nContext:\n" +
            protocol.canonical_json(context) + "\nSchema:\n" +
            protocol.canonical_json(navigation_schema()))
