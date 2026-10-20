"""Model-free preparation and validated research-memory updates.

These commands write isolated research artifacts. They neither seal production
intents nor modify campaign state, candidate admission or benchmark execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments import dab_research_route as route
from experiments import dab_roadmap_protocol as protocol


def _clip(value: object, string_limit: int = 700, list_limit: int = 8,
          key_limit: int = 14, depth: int = 0) -> object:
    """Keep a bounded, auditable briefing while retaining the full signed snapshot."""
    if depth > 4:
        raw = protocol.canonical_json(value)
        return {"truncated": True, "sha256": route.digest(value), "characters": len(raw)}
    if isinstance(value, str):
        if len(value) <= string_limit:
            return value
        return value[:string_limit] + " [truncated; sha256=" + route.digest(value) + "]"
    if isinstance(value, list):
        values = [_clip(item, string_limit, list_limit, key_limit, depth + 1)
                  for item in value[:list_limit]]
        if len(value) > list_limit:
            values.append({"truncated_items": len(value) - list_limit,
                           "sha256": route.digest(value)})
        return values
    if isinstance(value, dict):
        keys = sorted(value)[:key_limit]
        result = {key: _clip(value[key], string_limit, list_limit, key_limit, depth + 1)
                  for key in keys}
        if len(value) > key_limit:
            result["_truncated_keys"] = {"count": len(value) - key_limit,
                                         "sha256": route.digest(value)}
        return result
    return value


def _brief(node: dict) -> dict:
    """Expose measurements and interpretations separately in a bounded retrieval item."""
    content = node.get("content", {})
    kind = node["kind"]
    if kind == "evidence":
        observations = content.get("observations", {})
        selected = {"summary": observations.get("summary"),
                    "mechanism_measurements": observations.get("mechanism_measurements"),
                    "diagnostics": observations.get("diagnostics"),
                    "row_examples": observations.get("row_examples"),
                    "reviewer_interpretation": content.get("reviewer_interpretation")}
        rendered = _clip(selected, string_limit=900, list_limit=8, key_limit=16)
    else:
        rendered = _clip(content, string_limit=900, list_limit=8, key_limit=16)
    value = {"id": node["id"], "kind": kind, "generation": node["generation"],
             "content": rendered}
    for key in ("state", "scope", "question_origin", "origin_reason", "evidence_ids"):
        if key in node:
            value[key] = _clip(node[key])
    if node.get("latest_assessment"):
        value["latest_assessment"] = _clip(node["latest_assessment"],
                                            string_limit=500, list_limit=6, key_limit=16)
    # The underlying snapshot retains archive locations; a prompt only needs a
    # stable source digest and pointer to cite a reported measurement.
    if kind == "evidence":
        value["provenance"] = [{key: ref[key] for key in ("sha256", "json_pointer")}
                               for ref in node.get("provenance", [])]
        value["metric_index"] = _metric_index(node)
    return value


def _metric_index(node: dict, limit: int = 48) -> list[dict]:
    """Expose exact pointers for counters that a planner can bind to evidence."""
    metrics = []
    def visit(value: object, pointer: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                escaped = key.replace("~", "~0").replace("/", "~1")
                visit(item, pointer + "/" + escaped)
        elif type(value) is int:
            metrics.append({"pointer": pointer, "value": value})
    visit(node["content"].get("observations", {}), "/content/observations")
    metrics.sort(key=lambda item: (0 if any(word in item["pointer"].lower() for word in
                         ("opportunity", "activat", "coverage", "denominator", "rows")) else 1,
                                   item["pointer"]))
    return metrics[:limit]


def _retrieval_ids(view: dict, recent_generations: int = 4) -> list[str]:
    """Deterministically retrieve recent experiments and their immediate lineage."""
    floor = max(1, view["through_generation"] - recent_generations + 1)
    chosen = {node["id"] for node in view["nodes"] if node["generation"] >= floor}
    for item in route.research_agenda(view):
        chosen.add(item["source_id"])
        chosen.update(item["evidence_ids"])
    # A recent experiment may depend on an older code or research ancestor.
    seeds = set(chosen)
    for edge in view["edges"]:
        if edge["source"] in seeds and edge["relation"] in {
                "code_base", "motivated_by", "refines", "depends_on", "explains", "tests", "observes"}:
            chosen.add(edge["target"])
        if edge["target"] in seeds and edge["relation"] in {"supports", "challenges", "alternative_to"}:
            chosen.add(edge["source"])
    return [node["id"] for node in view["nodes"] if node["id"] in chosen]


def contexts(view: dict) -> dict[str, dict]:
    route.verify_snapshot(view)
    common = {"snapshot_sha256": view["snapshot_sha256"],
              "through_generation": view["through_generation"],
              "limits": view["limits"], "research_agenda": route.research_agenda(view)}
    # Flat and route arms expose exactly the same node contents/provenance.
    # Only relation structure and its navigation instruction differ.
    ids = _retrieval_ids(view)
    node_by_id = {node["id"]: node for node in view["nodes"]}
    nodes = [_brief(node_by_id[node_id]) for node_id in ids]
    generations = {node["generation"] for node in nodes}
    compact = [{"candidate_node_id": node["node_id"], "historical_card": node}
               for node in view["compact_nodes"] if node.get("generation") in generations]
    bases = [base for base in view["code_bases"]
             if base["node_id"] == protocol.ROOT_NODE_ID or base.get("generation") in generations]
    briefing = {"retrieval_policy": "active research agenda plus four latest completed generations and one-hop lineage",
                "retrieved_node_ids": ids, "omitted_node_count": len(view["nodes"]) - len(nodes),
                "available_evidence_ids": [node["id"] for node in nodes if node["kind"] == "evidence"]}
    common = {**common, **briefing, "code_bases": bases}
    relations = [edge for edge in view["edges"] if edge["source"] in ids and edge["target"] in ids]
    return {"compact": {**common, "arm": "compact", "history": compact},
            "flat": {**common, "arm": "flat", "history": nodes},
            "route": {**common, "arm": "route", "history": nodes, "relations": relations}}


def prepare(root: Path, through: int, out: Path, previous: dict | None = None,
            review_hypothesis_ids: list[str] | None = None) -> dict:
    if out.exists():
        raise ValueError("Preparation requires a fresh output directory")
    view = (route.advance_history(root, previous, through) if previous is not None
            else route.history(root, through))
    out.mkdir(parents=True)
    route.new_json(out / "snapshot.json", view)
    route.new_json(out / "decision_schema.json", route.decision_schema())
    route.new_json(out / "navigation_schema.json", route.navigation_schema())
    route.new_json(out / "review_schema.json", route.update_schema())
    route.new_json(out / "research_agenda.json", route.research_agenda(view))
    for arm, context in contexts(view).items():
        route.new_json(out / f"{arm}_context.json", context)
        with (out / f"{arm}_prompt.txt").open("x", encoding="utf-8") as stream:
            stream.write(route.decision_prompt(context))
    with (out / "navigation_prompt.txt").open("x", encoding="utf-8") as stream:
        stream.write(route.navigation_prompt(contexts(view)["route"]))
    review_dir = out / "review_batches"
    review_dir.mkdir()
    hypothesis_ids = review_hypothesis_ids or [
        node["id"] for node in view["nodes"] if node["kind"] == "hypothesis"]
    # Keep direct counterexamples visible while avoiding a single giant review request.
    for index, start in enumerate(range(0, len(hypothesis_ids), 2), 1):
        ids = hypothesis_ids[start:start + 2]
        route.new_json(review_dir / f"review_{index:02d}_context.json", route.review_context(view, ids))
        with (review_dir / f"review_{index:02d}_prompt.txt").open("x", encoding="utf-8") as stream:
            stream.write(route.review_prompt(view, ids))
    receipt = {"schema": route.SCHEMA, "through_generation": through,
               "snapshot_sha256": view["snapshot_sha256"],
               "files": {str(p.relative_to(out)).replace("\\", "/"): protocol.sha256_file(p)
                         for p in out.rglob("*") if p.is_file()},
               "campaign_changed": False, "candidate_started": False}
    route.new_json(out / "preparation.json", receipt)
    return receipt


def prepare_handoff(root: Path, view: dict, plan: dict, out: Path) -> dict:
    """Translate a validated research choice into the existing source-bound stage."""
    from experiments import dab_meta_interface_card_v1 as cards
    from experiments import dab_meta_interface_bound_intent_v1 as bound
    route.validate_navigation(plan, view)
    decision = plan["decision"]
    if decision["decision"] != "implement":
        raise ValueError("Diagnostic/probe decisions do not authorize candidate implementation")
    _, state = protocol.load_campaign(root)
    verification = protocol.verify_roadmap(root)
    if (state["stage"] != "ready_for_intent" or state.get("active_candidate_ref")
            or not verification["ok"] or verification["head_record_sha256"] != view["historical_head"]
            or int(state["next_generation"]) != view["through_generation"] + 1):
        raise ValueError("Research decision is not at the current ready-for-intent boundary")
    if out.exists():
        raise ValueError("Handoff requires a fresh directory")
    base = protocol.resolve_materialization_parent(root, decision["code_parent"])
    card = cards.build(root, base["node_id"])
    out.mkdir(parents=True)
    route.new_json(out / "research_snapshot.json", view)
    route.new_json(out / "research_navigation.json", plan)
    route.new_json(out / "research_decision.json", decision)
    route.new_json(out / "interface_card.json", card)
    route.new_json(out / "output_schema.json", bound.bound_schema(card))
    prompt = (
        "Finalize one reusable harness intent from the selected research experiment below. "
        "Preserve the selected code base and do not invent tool arguments or dispatch paths. "
        "Bind interface_binding to the source card. Preserve the research question, measured "
        "opportunity, observable prediction, falsification condition and negative control in "
        "validation_expectations. Use research parents as evidence, never blindly merge code. "
        "Translate their historical experiment IDs to candidate node IDs in parent_selection. "
        "Exactly one code_base must equal the selected code_parent. This preparation does not "
        "seal an intent, launch a candidate or resume a paused campaign.\n" +
        protocol.canonical_json({"research_decision": decision, "interface_card": card,
                                 "research_navigation": plan,
                                 "research_history": contexts(view)["route"]}))
    with (out / "prompt.txt").open("x", encoding="utf-8") as stream:
        stream.write(prompt)
    receipt = {"snapshot_sha256": view["snapshot_sha256"],
               "decision_sha256": route.digest(decision), "code_parent": base["node_id"],
               "navigation_sha256": route.digest(plan),
               "source_tree_sha256": base["source_tree_sha256"],
               "roadmap_head": verification["head_record_sha256"],
               "generation": state["next_generation"], "production_intent_sealed": False}
    route.new_json(out / "handoff.json", receipt)
    return receipt


def seal_handoff(root: Path, session: Path, response: dict) -> dict:
    """Explicit live handoff; production admission and evaluation remain downstream."""
    from experiments import dab_meta_interface_card_v1 as cards
    from experiments import dab_meta_interface_bound_intent_v1 as bound
    view = protocol.read_json(session / "research_snapshot.json")
    decision = protocol.read_json(session / "research_decision.json")
    plan = protocol.read_json(session / "research_navigation.json")
    binding = protocol.read_json(session / "handoff.json")
    route.validate_navigation(plan, view)
    if (plan["decision"] != decision or route.digest(plan) != binding["navigation_sha256"]
            or decision["decision"] != "implement" or route.digest(decision) != binding["decision_sha256"]):
        raise ValueError("Handoff decision changed")
    _, state = protocol.load_campaign(root)
    head = protocol.verify_roadmap(root)
    if (not head["ok"] or head["head_record_sha256"] != binding["roadmap_head"]
            or state["next_generation"] != binding["generation"]
            or state["stage"] != "ready_for_intent" or state.get("active_candidate_ref")):
        raise ValueError("Live Graph/state changed since research handoff")
    card = protocol.read_json(session / "interface_card.json")
    if cards.build(root, decision["code_parent"]) != card:
        raise ValueError("Selected source interface changed")
    errors = bound.validate_bound_response(response, card)
    if errors:
        raise ValueError("Source-bound intent invalid: " + "; ".join(errors))
    response = {**response, "research_binding": binding}
    return protocol.seal_intent(root, response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--campaign-root", type=Path, required=True)
    prep.add_argument("--through-generation", type=int, required=True)
    prep.add_argument("--output", type=Path, required=True)
    prep.add_argument("--previous-snapshot", type=Path,
                      help="Carry the reviewed research state forward to this roadmap boundary")
    prep.add_argument("--review-hypothesis-ids", nargs="+",
                      help="Generate review briefs only for these hypothesis IDs")
    read = sub.add_parser("retrieve")
    read.add_argument("--snapshot", type=Path, required=True)
    read.add_argument("--ids", nargs="+", required=True)
    validate = sub.add_parser("validate-decision")
    validate.add_argument("--snapshot", type=Path, required=True)
    validate.add_argument("--response", type=Path, required=True)
    navigation = sub.add_parser("validate-navigation")
    navigation.add_argument("--snapshot", type=Path, required=True)
    navigation.add_argument("--response", type=Path, required=True)
    probe = sub.add_parser("import-probe")
    probe.add_argument("--campaign-root", type=Path, required=True)
    probe.add_argument("--snapshot", type=Path, required=True)
    probe.add_argument("--record", type=Path, required=True)
    probe.add_argument("--events", type=Path, required=True)
    probe.add_argument("--output", type=Path, required=True)
    update = sub.add_parser("apply-review")
    update.add_argument("--snapshot", type=Path, required=True)
    update.add_argument("--update", type=Path, required=True)
    update.add_argument("--events", type=Path, required=True)
    update.add_argument("--output", type=Path, required=True)
    handoff = sub.add_parser("prepare-handoff")
    handoff.add_argument("--campaign-root", type=Path, required=True)
    handoff.add_argument("--snapshot", type=Path, required=True)
    handoff.add_argument("--plan", type=Path, required=True)
    handoff.add_argument("--output", type=Path, required=True)
    seal = sub.add_parser("seal-handoff")
    seal.add_argument("--campaign-root", type=Path, required=True)
    seal.add_argument("--session", type=Path, required=True)
    seal.add_argument("--response", type=Path, required=True)
    normalize = sub.add_parser("normalize-model-json")
    normalize.add_argument("--input", type=Path, required=True)
    normalize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        previous = protocol.read_json(args.previous_snapshot) if args.previous_snapshot else None
        value = prepare(args.campaign_root.resolve(), args.through_generation,
                        args.output.resolve(), previous, args.review_hypothesis_ids)
    elif args.command == "retrieve":
        value = route.retrieve(protocol.read_json(args.snapshot), args.ids)
    elif args.command == "validate-decision":
        route.validate_decision(protocol.read_json(args.response), protocol.read_json(args.snapshot))
        value = {"valid": True, "production_intent_sealed": False}
    elif args.command == "validate-navigation":
        route.validate_navigation(protocol.read_json(args.response), protocol.read_json(args.snapshot))
        value = {"valid": True, "production_intent_sealed": False}
    elif args.command == "import-probe":
        if args.output.exists():
            raise ValueError("Probe import must write a new immutable snapshot")
        snapshot = route.append_probe(args.events, protocol.read_json(args.snapshot),
                                      args.campaign_root.resolve(), protocol.read_json(args.record))
        route.new_json(args.output, snapshot)
        value = {"snapshot_sha256": snapshot["snapshot_sha256"],
                 "events": str(args.events), "production_intent_sealed": False}
    elif args.command == "prepare-handoff":
        value = prepare_handoff(args.campaign_root.resolve(), protocol.read_json(args.snapshot),
                                protocol.read_json(args.plan), args.output.resolve())
    elif args.command == "seal-handoff":
        value = seal_handoff(args.campaign_root.resolve(), args.session.resolve(),
                             protocol.read_json(args.response))
    elif args.command == "normalize-model-json":
        if args.output.exists():
            raise ValueError("Normalized response output must be fresh")
        value = route.parse_model_json(args.input.read_text(encoding="utf-8"))
        route.new_json(args.output, value)
    else:
        if args.output.exists():
            raise ValueError("Review must write a new immutable snapshot")
        value = route.append_update(args.events, protocol.read_json(args.snapshot),
                                    protocol.read_json(args.update))
        route.new_json(args.output, value)
        value = {"snapshot_sha256": value["snapshot_sha256"], "events": str(args.events)}
    print(json.dumps(value, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
