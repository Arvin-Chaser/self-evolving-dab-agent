#!/usr/bin/env python3
"""Bind G3 research to both post-run trace fields and live tool dispatch."""

from __future__ import annotations

import ast
import json

from experiments.build_research_graph_g003_interface_card import (
    BASE, EXPECTED_SOURCE, EXPECTED_TREE, PARENT, SOURCE, trace_event_fields,
)
from experiments.intent_candidate_workspace import source_tree_hash
from experiments.run_research_graph_g001_meta_v2 import sha, write_new


UPSTREAM = PARENT / "external/DataAgentBench_official/common_scaffold/DataAgent.py"
EXPECTED_UPSTREAM = "ea64b4e2b54ca32545c006d9d2aa77ad3d788ecf337b50c898b268631b24f80a"
OUT = BASE / "g003_g002_runtime_interface_card_v3.json"


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    matches = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Reviewed source must have one {name} function")
    return matches[0]


def verify_lifecycle(agent_source: str, upstream_source: str) -> None:
    agent = ast.parse(agent_source)
    upstream = ast.parse(upstream_source)
    trace = ast.unparse(_function(agent, "build_full_execution_trace"))
    normalize = ast.unparse(_function(agent, "normalize_run_artifacts"))
    adapter = ast.unparse(_function(agent, "install_self_observation_tool"))
    dispatch = ast.unparse(_function(upstream, "_handle_tool_call"))
    required = (
        (trace, 'read_jsonl(upstream_run_dir / \'tool_calls.jsonl\')'),
        (trace, "'validated_args': row.get('val_args')"),
        (normalize, "build_full_execution_trace(upstream_run_dir)"),
        (normalize, "append_jsonl(normalized_dir / 'full_execution_trace.jsonl'"),
        (adapter, "super()._handle_tool_call(tool_call)"),
        (dispatch, "json.loads(tool_call.function.arguments)"),
        (dispatch, "tool_args['env'] = self.result_storage.copy()"),
        (dispatch, "self.tools[tool_name].exec(tool_args)"),
        (dispatch, "self.final_result = tool_args['answer']"),
    )
    if any(fragment not in body for body, fragment in required):
        raise RuntimeError("G2 trace or live-dispatch lifecycle differs")
    if "validated_args" in dispatch or "val_args" in dispatch:
        raise RuntimeError("G2 pre-dispatch argument availability changed")


def build_card() -> dict:
    if (source_tree_hash(PARENT) != EXPECTED_TREE or
            sha(SOURCE) != EXPECTED_SOURCE or
            sha(UPSTREAM) != EXPECTED_UPSTREAM):
        raise RuntimeError("G2 parent or source hash differs")
    agent_source = SOURCE.read_text(encoding="utf-8")
    upstream_source = UPSTREAM.read_text(encoding="utf-8")
    verify_lifecycle(agent_source, upstream_source)
    return {
        "schema_version": "g003_g002_runtime_interface_answer_blind_v3",
        "source_tree_sha256": EXPECTED_TREE,
        "agent_source_sha256": EXPECTED_SOURCE,
        "upstream_dispatch_source_sha256": EXPECTED_UPSTREAM,
        "tool_event_fields": trace_event_fields(agent_source),
        "trace_event_lifecycle": {
            "tool_call_start": "post_run_normalization_from_tool_calls_jsonl",
            "tool_call_end": "post_run_normalization_from_tool_calls_jsonl",
            "validated_args": "post_execution_tool_log_val_args_not_pre_dispatch",
            "tool_call_index": "post_run_enumeration_not_pre_dispatch",
            "event_time": "post_execution_tool_log_timestamp_not_pre_dispatch",
            "trace_events_are_live_hooks": False,
        },
        "live_tool_dispatch": {
            "hook": "DataAgentWithSelfObservation._handle_tool_call",
            "delegated_hook": "DataAgent._handle_tool_call",
            "before_exec_fields": ["tool_name", "raw_arguments", "parsed_tool_args"],
            "before_exec_validated_args_available": False,
            "before_exec_tool_call_index_available": False,
            "parsed_tool_args_match_executed_args_verified": False,
            "execution_call": "self.tools[tool_name].exec(tool_args)",
            "execute_python_injects_result_storage_env": True,
            "return_answer_sets_final_result_only_after_successful_exec": True,
            "blocking_response_contract_verified": False,
            "safe_to_suppress_repeated_calls_verified": False,
        },
        "existing_task_obligation_binding_fields": [],
        "available_read_only_derivations": [
            "Exact within-task call repetition can be counted from hash-verified completed G2 traces without a new formal child.",
            "Result equality or novelty does not establish task relevance or correctness.",
        ],
        "unsupported_runtime_claims": [
            "A post-run tool_call_start trace record is not a live dispatch hook.",
            "validated_args and post-run tool_call_index cannot be required by a pre-exec guard without a separately verified implementation.",
            "A blocked call has no pre-verified replacement tool-message, retry, terminal, or result-storage contract.",
            "Exact duplicate calls may be legitimate after state changes; suppression is not certified safe.",
        ],
        "meta_input_boundary": "Source schema and lifecycle only; no task IDs, questions, messages, tool arguments/results, answers, hints, validators, or held-out data.",
    }


def main() -> None:
    write_new(OUT, build_card())
    print(json.dumps({"status": "prepared", "card_sha256": sha(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
