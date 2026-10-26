#!/usr/bin/env python3
"""Bind G3 Meta to the actual, answer-blind G2 trace interface."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from experiments.intent_candidate_workspace import source_tree_hash
from experiments.run_research_graph_g001_meta_v2 import sha, write_new


BASE = Path(__file__).resolve().parents[1] / "experiments/research_graph_baseline_20261016"
PARENT = BASE / "g002_candidate_001/repo"
SOURCE = PARENT / "experiments/run_dab_tool_agent.py"
OUT = BASE / "g003_g002_interface_card_v1.json"
EXPECTED_TREE = "87eaf0f67c9bb237d8a7d6083441fe66abe903418721d589e32d2c9c403e1208"
EXPECTED_SOURCE = "31d1b3fdbb21f6313b5e8f0a1ca2eacd6096ac2922cfe5abacec5218cdd1a66a"
EXPECTED_START = {
    "event_type", "tool_call_index", "tool_name", "event_time", "args",
    "validated_args", "raw_tool_call",
}
EXPECTED_END = {
    "event_type", "tool_call_index", "tool_name", "event_time", "duration",
    "success", "result", "raw_tool_call",
}


def trace_event_fields(source: str) -> dict[str, list[str]]:
    tree = ast.parse(source)
    function = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "build_full_execution_trace"), None)
    if function is None:
        raise RuntimeError("G2 full-trace builder is absent")
    events: dict[str, list[str]] = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        pairs = [(key.value, value.value if isinstance(value, ast.Constant) else None)
                 for key, value in zip(node.keys, node.values)
                 if isinstance(key, ast.Constant) and isinstance(key.value, str)]
        kind = next((value for key, value in pairs if key == "event_type"), None)
        if kind in {"tool_call_start", "tool_call_end"}:
            if kind in events:
                raise RuntimeError("G2 trace event dictionary is ambiguous")
            events[kind] = sorted(key for key, _ in pairs)
    if (set(events.get("tool_call_start", [])) != EXPECTED_START or
            set(events.get("tool_call_end", [])) != EXPECTED_END):
        raise RuntimeError("G2 tool-event schema differs from reviewed interface")
    return events


def build_card() -> dict:
    if source_tree_hash(PARENT) != EXPECTED_TREE or sha(SOURCE) != EXPECTED_SOURCE:
        raise RuntimeError("G2 parent source hash differs")
    events = trace_event_fields(SOURCE.read_text(encoding="utf-8"))
    return {
        "schema_version": "g003_g002_source_interface_answer_blind_v1",
        "source_tree_sha256": EXPECTED_TREE,
        "agent_source_sha256": EXPECTED_SOURCE,
        "tool_event_fields": events,
        "structure_only_fields": ["event_type", "tool_call_index", "tool_name",
                                  "event_time", "duration", "success"],
        "local_content_fields_not_for_meta": ["args", "validated_args", "result",
                                              "raw_tool_call"],
        "existing_task_obligation_binding_fields": [],
        "supported_derivations": [
            "Within one task, local canonical hashes of tool name and arguments can test exact repeated calls without exporting arguments or hashes.",
            "Within one task, local result hashes can test exact repetition or novelty, but novelty does not establish task relevance or correctness.",
        ],
        "unsupported_inferences": [
            "No source field maps a tool event or result to a task-specific obligation ID or schema binding key.",
            "Tool-event success and result-digest novelty do not establish that a task obligation was satisfied.",
            "A freeform agent subgoal or completion claim is not an independent obligation-binding key.",
        ],
        "meta_input_boundary": "Only source schema and hash-bound structural capabilities; no task IDs, questions, messages, tool arguments/results, answers, hints, validators, or held-out data.",
    }


def main() -> None:
    write_new(OUT, build_card())
    print(json.dumps({"status": "prepared", "card_sha256": sha(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
