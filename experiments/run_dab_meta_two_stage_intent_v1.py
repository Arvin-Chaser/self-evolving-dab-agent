#!/usr/bin/env python3
"""One command for graph selection, source-bound interface card, and final Meta intent.

No intent is sealed here. Every dispatch is unique and durable; a failed or
ambiguous stage stops the command without automatically replaying that stage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments import dab_meta_interface_bound_intent_v1 as bound
from experiments import dab_meta_interface_card_v1 as cards
from experiments import dab_native_meta_audit_v4
from experiments import dab_roadmap_protocol as protocol


def run_once(campaign_root: Path) -> dict:
    campaign, state = protocol.load_campaign(campaign_root)
    if state["stage"] != "ready_for_intent" or state.get("active_candidate_ref"):
        raise RuntimeError("Graph selection must begin at ready_for_intent with no candidate")
    generation = int(state["next_generation"])
    if generation > int(campaign["max_generations"]):
        raise RuntimeError("Generation ceiling reached")
    if campaign["meta_agent"].get("model") != "deepseek-flash" or campaign["meta_agent"].get("profile") != "deepseek-standalone-dab":
        raise RuntimeError("Strict native Meta audit binding differs from configured route")
    snapshot = protocol.build_snapshot(campaign_root)
    protocol.materialize_safe_details(campaign_root, snapshot)
    provisional = protocol.next_meta_session(campaign_root, generation, "intent")
    provisional.mkdir(parents=True, exist_ok=False)
    protocol.write_json(provisional / "roadmap_snapshot.json", snapshot)
    protocol.write_json(provisional / "output_schema.json", protocol.intent_output_schema())
    (provisional / "prompt.md").write_text(protocol.build_intent_prompt(snapshot), encoding="utf-8")
    selected = protocol.invoke_codex_json(
        campaign=campaign, session=provisional,
        prompt=(provisional / "prompt.md").read_text(encoding="utf-8"),
        schema_path=provisional / "output_schema.json", output_name="intent_response.json")
    native = dab_native_meta_audit_v4.verify(
        provisional, provisional / "codex.stdout", provisional / "codex.stderr",
        bound.HOME, "read-only")
    protocol.write_json(provisional / "native_audit_v4.json", native)
    errors = protocol.validate_intent(selected)
    if errors:
        raise RuntimeError("Provisional graph selection invalid: " + "; ".join(errors))
    base_id = selected["parent_selection"]["materialization_base_node_id"]
    card = cards.build(campaign_root, base_id)
    card_path = provisional / "selected_base_interface_card.json"
    protocol.require_new(card_path)
    protocol.write_json(card_path, card)
    final = bound.prepare(campaign_root, provisional, card_path)
    completed = bound.run_once(campaign_root, provisional, card_path, final)
    completed.update({"provisional_session": str(provisional),
                      "selected_base_interface_card": str(card_path),
                      "intent_sealed": False, "automatic_replay": False})
    return completed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--run-once", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(run_once(args.campaign_root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
