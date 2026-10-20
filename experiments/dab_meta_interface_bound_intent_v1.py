#!/usr/bin/env python3
"""Complete a graph-selected Meta intent against a bound execution-interface card.

This is a separate, versioned second stage. It never seals an intent or launches a
candidate/evaluation. One CLI invocation is one model dispatch; retries are manual.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments import dab_meta_interface_card_v1 as card_builder
from experiments import dab_native_meta_audit_v4
from experiments import dab_roadmap_protocol as protocol


HOME = Path(r"C:\Users\34934\source\text2sql\configs\deepseek_meta_standalone_v2")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound_schema(card: dict) -> dict:
    schema = protocol.intent_output_schema()
    schema["required"] = [*schema["required"], "interface_binding"]
    schema["properties"]["interface_binding"] = {
        "type": "object", "additionalProperties": False,
        "required": ["card_canonical_sha256", "base_node_id", "base_source_tree_sha256",
                     "runner_source_sha256", "upstream_source_sha256", "overlay_journal_source_sha256",
                     "inherited_suppression_present", "tool_result_transport",
                     "inherited_suppression_treatment", "inherited_suppression_plan",
                     "tool_message_shape", "tool_message_attachment_plan",
                     "tool_message_cardinality_plan"],
        "properties": {
            "card_canonical_sha256": {"type": "string", "const": card["canonical_json_sha256"]},
            "base_node_id": {"type": "string", "const": card["base_node_id"]},
            "base_source_tree_sha256": {"type": "string", "const": card["base_source_tree_sha256"]},
            "runner_source_sha256": {"type": "string", "const": card["runner"]["source_sha256"]},
            "upstream_source_sha256": {"type": "string", "const": card["upstream"]["source_sha256"]},
            "overlay_journal_source_sha256": {"type": "string", "const": card["current_overlay_journal"]["source_sha256"]},
            "inherited_suppression_present": {"type": "boolean", "const": card["derived_contract"]
                                               ["selected_base_has_suppressed_tool_message_path"]},
            "tool_result_transport": {"type": "string", "const": card["derived_contract"]
                                      ["upstream_tool_result_transport"]},
            "inherited_suppression_treatment": {"type": "string", "enum": ["preserve_as_is", "remove_or_disable_with_tests"]},
            "inherited_suppression_plan": {"type": "string", "minLength": 1},
            "tool_message_shape": {"type": "string", "enum": ["modify_existing_tool_message", "no_tool_message_change"]},
            "tool_message_attachment_plan": {"type": "string", "minLength": 1},
            "tool_message_cardinality_plan": {"type": "string", "minLength": 1},
        },
    }
    return schema


def validate_bound_response(response: dict, card: dict) -> list[str]:
    errors = protocol.validate_intent(response)
    selection = response.get("parent_selection")
    if not isinstance(selection, dict) or selection.get("materialization_base_node_id") != card["base_node_id"]:
        errors.append("Final intent changed the selected code base without a new interface card")
    binding = response.get("interface_binding")
    if not isinstance(binding, dict):
        return [*errors, "Missing interface_binding"]
    expected = {
        "card_canonical_sha256": card["canonical_json_sha256"],
        "base_node_id": card["base_node_id"],
        "base_source_tree_sha256": card["base_source_tree_sha256"],
        "runner_source_sha256": card["runner"]["source_sha256"],
        "upstream_source_sha256": card["upstream"]["source_sha256"],
        "overlay_journal_source_sha256": card["current_overlay_journal"]["source_sha256"],
        "inherited_suppression_present": card["derived_contract"]
                                         ["selected_base_has_suppressed_tool_message_path"],
        "tool_result_transport": card["derived_contract"]["upstream_tool_result_transport"],
    }
    for key, value in expected.items():
        if binding.get(key) != value:
            errors.append(f"Incorrect interface binding: {key}")
    for key in ("inherited_suppression_plan", "tool_message_attachment_plan",
                "tool_message_cardinality_plan"):
        if not isinstance(binding.get(key), str) or not binding[key].strip():
            errors.append(f"Missing concrete {key}")
    if binding.get("inherited_suppression_treatment") not in ("preserve_as_is", "remove_or_disable_with_tests"):
        errors.append("Missing explicit inherited suppression treatment")
    if binding.get("tool_message_shape") not in ("modify_existing_tool_message", "no_tool_message_change"):
        errors.append("Unverified extra tool-message shape is not admissible")
    return errors


def preconditions(campaign_root: Path, provisional: Path, card_path: Path) -> tuple[dict, dict, dict]:
    campaign, state = protocol.load_campaign(campaign_root)
    if (state["stage"] not in {"ready_for_intent", "intent_sealed"}
            or state.get("active_candidate_ref") or state.get("execution_status") not in (None, "paused_by_user")):
        raise RuntimeError("Interface-bound intent requires unadmitted candidate state")
    if campaign["meta_agent"].get("model") != "deepseek-flash" or campaign["meta_agent"].get("profile") != "deepseek-standalone-dab":
        raise RuntimeError("Native audit binding is not configured for this Meta runtime")
    selected = protocol.read_json(provisional / "intent_response.json")
    if protocol.validate_intent(selected):
        raise RuntimeError("Provisional graph selection is invalid")
    audit_path = provisional / "native_audit_v4.json"
    if not audit_path.is_file():
        raise RuntimeError("Provisional graph selection lacks strict native audit")
    native = protocol.read_json(audit_path)
    if (native.get("model") != "deepseek-flash"
            or native.get("model_provider") != "dab_deepseek_standalone"
            or native.get("completed_turn_count") != 1
            or native.get("approved_prefix_count") != 0
            or native.get("events_sha256") != sha(provisional / "codex.stdout")
            or native.get("stderr_sha256") != sha(provisional / "codex.stderr")):
        raise RuntimeError("Provisional native audit no longer binds its session logs")
    snapshot = protocol.read_json(provisional / "roadmap_snapshot.json")
    fresh = protocol.build_snapshot(campaign_root)
    if snapshot["snapshot_sha256"] != fresh["snapshot_sha256"]:
        raise RuntimeError("Graph/result snapshot changed since provisional selection")
    card = protocol.read_json(card_path)
    if card_builder.build(campaign_root, card["base_node_id"]) != card:
        raise RuntimeError("Interface card no longer matches the selected frozen sources")
    if selected["parent_selection"]["materialization_base_node_id"] != card["base_node_id"]:
        raise RuntimeError("Provisional selection and interface card bind different bases")
    return campaign, selected, card


def prepare(campaign_root: Path, provisional: Path, card_path: Path) -> Path:
    _, selected, card = preconditions(campaign_root, provisional, card_path)
    session = protocol.next_meta_session(campaign_root, int(protocol.load_campaign(campaign_root)[1]["next_generation"]), "intent")
    session.mkdir(parents=True, exist_ok=False)
    snapshot = protocol.read_json(provisional / "roadmap_snapshot.json")
    protocol.write_json(session / "roadmap_snapshot.json", snapshot)
    protocol.write_json(session / "output_schema.json", bound_schema(card))
    protocol.write_json(session / "provisional_selection_binding.json", {
        "response_sha256": sha(provisional / "intent_response.json"),
        "native_audit_sha256": sha(provisional / "native_audit_v4.json"),
        "materialization_base_node_id": card["base_node_id"],
        "interface_card_exact_bytes_sha256": sha(card_path),
        "interface_card_canonical_sha256": card["canonical_json_sha256"],
    })
    protocol.write_json(session / "interface_card.json", card)
    prompt = protocol.build_intent_prompt(snapshot)
    prompt += "\n# Selected-base interface completion stage\n\n"
    prompt += (
        "Your previous independent graph stage selected the code base below. This stage is to finalize "
        "a concrete intent for THAT base, not to invent an interface or silently select another base. "
        "You may revise or abandon the provisional mechanism. If no safe, reachable intent is possible "
        "for this base, explain the incompatibility rather than claiming a nonexistent return or dispatch path. "
        "State explicitly how inherited suppression paths are treated and where any tool-message "
        "change is attached. Address the one-cursor-advance-per-call versus a second role=tool message: "
        "without a separate protocol proof, preserve one role=tool response per call by modifying the "
        "existing message or not changing it; a second tool message is not an admissible assumption. "
        "Treat AST facts as source facts, "
        "not as proof of runtime activation. "
        "No query rows, answers, raw traces, or historical patches are provided.\n\n"
    )
    prompt += "```json\n" + json.dumps({
        "provisional_mechanism_key": selected["mechanism_key"],
        "selected_materialization_base": card["base_node_id"],
        "selected_base_interface_card": card,
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n```\n"
    (session / "prompt.md").write_text(prompt, encoding="utf-8")
    return session


def run_once(campaign_root: Path, provisional: Path, card_path: Path, session: Path) -> dict:
    campaign, _, card = preconditions(campaign_root, provisional, card_path)
    binding = protocol.read_json(session / "provisional_selection_binding.json")
    if (binding["response_sha256"] != sha(provisional / "intent_response.json")
            or binding["interface_card_exact_bytes_sha256"] != sha(card_path)
            or protocol.read_json(session / "interface_card.json") != card
            or (session / "request_prompt.md").exists()):
        raise RuntimeError("Prepared session changed or already dispatched; no automatic replay")
    response = protocol.invoke_codex_json(
        campaign=campaign, session=session,
        prompt=(session / "prompt.md").read_text(encoding="utf-8"),
        schema_path=session / "output_schema.json", output_name="intent_response.json",
    )
    audit = dab_native_meta_audit_v4.verify(
        session, session / "codex.stdout", session / "codex.stderr", HOME, "read-only")
    protocol.write_json(session / "native_audit_v4.json", audit)
    errors = validate_bound_response(response, card)
    if errors:
        raise RuntimeError("Interface-bound response failed deterministic validation: " + "; ".join(errors))
    return {"session": str(session), "response_sha256": sha(session / "intent_response.json"),
            "native_audit_passed": True, "interface_binding_passed": True,
            "mechanism_key": response["mechanism_key"], "base_node_id": card["base_node_id"],
            "intent_sealed": False, "candidate_or_evaluation_started": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--provisional-session", type=Path, required=True)
    parser.add_argument("--interface-card", type=Path, required=True)
    parser.add_argument("--session", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run-once", action="store_true")
    args = parser.parse_args()
    campaign_root = args.campaign_root.resolve()
    provisional = args.provisional_session.resolve()
    card_path = args.interface_card.resolve()
    if args.prepare_only:
        result = {"prepared_session": str(prepare(campaign_root, provisional, card_path))}
    else:
        if args.session is None:
            parser.error("--run-once requires --session")
        result = run_once(campaign_root, provisional, card_path, args.session.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
