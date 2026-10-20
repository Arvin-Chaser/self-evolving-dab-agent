#!/usr/bin/env python3
"""Build a bounded, source-bound execution-interface card for a selected DAB base.

The card contains AST-derived call/return/message facts and tool argument types,
not source excerpts, historical patches, task rows, answers, or traces.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments import dab_roadmap_protocol as protocol


SCHEMA = "dab_meta_interface_card_v1"
HANDLERS = {"_handle_tool_call", "_handle_tool_call_with_recovery", "_handle_content",
            "append_suppressed_tool_response"}
STOCK_TOOLS = ("ListDBTool", "QueryDBTool", "ExecTool", "ReturnAnswerTool")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(path: Path) -> ast.Module:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing or symlinked bound source: {path}")
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def attr_chain(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return attr_chain(node.value) + "." + node.attr
    return ""


def direct_handler_facts(function: ast.FunctionDef) -> dict[str, Any]:
    calls: dict[str, list[int]] = {}
    returns = []
    role_tool_appends = []
    # ast.walk would include returns/calls of classes defined inside a handler
    # (for example a tool-call proxy's model_dump). Those are not handler facts.
    def own_body_nodes():
        pending = list(function.body)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            yield node
            pending.extend(ast.iter_child_nodes(node))

    for node in own_body_nodes():
        if isinstance(node, ast.Call):
            name = attr_chain(node.func)
            if name in {"self.messages.append", "self.append_suppressed_tool_response",
                        "super()._handle_tool_call", "super()._handle_content"}:
                calls.setdefault(name, []).append(node.lineno)
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "_handle_tool_call", "_handle_content"} and isinstance(node.func.value, ast.Call) \
                    and isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == "super":
                calls.setdefault("super()." + node.func.attr, []).append(node.lineno)
            if name == "self.messages.append" and node.args and isinstance(node.args[0], ast.Dict):
                mapping = {k.value: v for k, v in zip(node.args[0].keys, node.args[0].values)
                           if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                role = mapping.get("role")
                if isinstance(role, ast.Constant) and role.value == "tool":
                    role_tool_appends.append(node.lineno)
        elif isinstance(node, ast.Return):
            returns.append({"line": node.lineno, "has_value": node.value is not None})
    return {"defined_at_line": function.lineno,
            "parameters": [arg.arg for arg in function.args.args],
            "calls": {key: sorted(set(value)) for key, value in sorted(calls.items())},
            "role_tool_message_append_lines": sorted(set(role_tool_appends)),
            "return_statements": sorted(returns, key=lambda item: item["line"])}


def handler_cards(tree: ast.Module, names: set[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            result.setdefault(node.name, []).append(direct_handler_facts(node))
    return result


def literal_key(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def dict_value(node: ast.Dict, key: str) -> ast.AST | None:
    for k, v in zip(node.keys, node.values):
        if literal_key(k) == key:
            return v
    return None


def schema_properties(function: ast.FunctionDef) -> dict[str, Any]:
    candidates = [node for node in ast.walk(function) if isinstance(node, ast.Dict)
                  and isinstance(dict_value(node, "properties"), ast.Dict)]
    if len(candidates) != 1:
        raise ValueError(f"Expected one literal properties mapping in get_spec at {function.lineno}")
    parameters = candidates[0]
    fields_node = dict_value(parameters, "properties")
    assert isinstance(fields_node, ast.Dict)
    fields: dict[str, str] = {}
    for key_node, field_node in zip(fields_node.keys, fields_node.values):
        name = literal_key(key_node)
        if not name or not isinstance(field_node, ast.Dict):
            raise ValueError("Nonliteral tool argument mapping")
        field_type = literal_key(dict_value(field_node, "type"))
        if not field_type:
            raise ValueError("Nonliteral tool argument type")
        fields[name] = field_type
    required_node = dict_value(parameters, "required")
    if not isinstance(required_node, (ast.List, ast.Tuple)):
        raise ValueError("Nonliteral required arguments")
    required = [literal_key(item) for item in required_node.elts]
    if any(item is None for item in required):
        raise ValueError("Nonliteral required argument")
    return {"properties": fields, "required": required}


def tool_card(path: Path) -> dict[str, Any]:
    tree = parse(path)
    methods = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == "get_spec"]
    if len(methods) != 1:
        raise ValueError(f"Expected one get_spec: {path}")
    return {"source_sha256": digest(path), "get_spec_line": methods[0].lineno,
            "argument_schema": schema_properties(methods[0])}


def runner_tool_specs(tree: ast.Module) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "get_spec":
            continue
        try:
            value: dict[str, Any] = {"argument_schema": schema_properties(node)}
        except ValueError:
            value = {"argument_schema": "not_literal_in_source; inspect bound override before relying on it"}
        result[str(node.lineno)] = value
    return result


def journal_dispatch_card(path: Path) -> dict[str, Any]:
    tree = parse(path)
    journal = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "Journal"]
    if len(journal) != 1:
        raise ValueError("Expected one bound checkpoint Journal class")
    dispatch = [node for node in journal[0].body
                if isinstance(node, ast.FunctionDef) and node.name == "dispatch"]
    if len(dispatch) != 1:
        raise ValueError("Expected one Journal.dispatch")
    handler_calls = []
    cursor_advances = []
    for node in ast.walk(dispatch[0]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "_handle_tool_call":
            handler_calls.append(node.lineno)
        if isinstance(node, ast.AugAssign) and attr_chain(node.target) == "self.cursor":
            cursor_advances.append(node.lineno)
    if not handler_calls or not cursor_advances:
        raise ValueError("Tool dispatch or durable cursor advance not observable")
    return {"relative_path": "experiments/dab_runtime_repair_v1.py",
            "source_sha256": digest(path), "dispatch_line": dispatch[0].lineno,
            "tool_handler_call_lines": sorted(handler_calls),
            "cursor_advance_lines": sorted(cursor_advances),
            "scope": "current hash-bound overlay implementation, not part of the frozen candidate base"}


def build(campaign_root: Path, base_node_id: str) -> dict[str, Any]:
    base = protocol.resolve_materialization_parent(campaign_root, base_node_id)
    repo = Path(base["source_root"])
    runner_path = repo / "experiments" / "run_dab_tool_agent.py"
    root = protocol.load_root_node(campaign_root)
    upstream_root = Path(root["source_root"]) / "external" / "DataAgentBench_official" / "common_scaffold"
    upstream_path = upstream_root / "DataAgent.py"
    runner_tree = parse(runner_path)
    runner = handler_cards(runner_tree, HANDLERS)
    upstream = handler_cards(parse(upstream_path), {"_handle_tool_call", "_handle_content"})
    if len(upstream.get("_handle_tool_call", [])) != 1 or not runner.get("_handle_tool_call"):
        raise ValueError("Required handler topology not statically observable")
    upstream_call = upstream["_handle_tool_call"][0]
    if not upstream_call["role_tool_message_append_lines"]:
        raise ValueError("Original tool-message append not statically observed")
    # The campaign's frozen root snapshots DataAgent.py but not the four stock
    # tool modules. Bind each live stock spec by its exact source hash instead
    # of silently inventing a schema or claiming it came from that snapshot.
    tool_root = upstream_root / "tools"
    tool_origin = "campaign_root_snapshot"
    if not tool_root.is_dir():
        tool_root = Path(__file__).resolve().parents[1] / "external" / "DataAgentBench_official" / "common_scaffold" / "tools"
        tool_origin = "current_workspace_official_scaffold_hash_bound"
    stock = {name: tool_card(tool_root / f"{name}.py") for name in STOCK_TOOLS}
    journal = journal_dispatch_card(Path(__file__).resolve().parents[1] / "experiments" / "dab_runtime_repair_v1.py")
    cards = {
        "schema": SCHEMA, "base_node_id": base_node_id,
        "base_source_tree_sha256": base["source_tree_sha256"],
        "runner": {"relative_path": "experiments/run_dab_tool_agent.py",
                   "source_sha256": digest(runner_path), "handlers": runner,
                   "declared_tool_spec_overrides": runner_tool_specs(runner_tree)},
        "upstream": {"relative_path": "external/DataAgentBench_official/common_scaffold/DataAgent.py",
                     "source_sha256": digest(upstream_path), "handlers": upstream},
        "stock_tool_specs": stock,
        "stock_tool_spec_origin": tool_origin,
        "current_overlay_journal": journal,
        "derived_contract": {
            "upstream_tool_result_transport": "appends a role=tool message to self.messages; handler has no result-object return contract",
            "selected_base_has_suppressed_tool_message_path": bool(runner.get("append_suppressed_tool_response")
                and any(item["calls"].get("self.append_suppressed_tool_response")
                        for group in runner.values() for item in group)),
            "base_wrapper_may_return_values": any(
                entry["has_value"] for item in runner.get("_handle_tool_call", [])
                for entry in item["return_statements"]),
            "separate_advisory_tool_message_risk": (
                "Upstream appends a role=tool response for each handled call and the current overlay advances "
                "one durable cursor position per handler invocation. A second role=tool message for the same "
                "call ID changes the native conversation shape; do not assume it is accepted without a "
                "separate protocol compatibility proof."
            ),
        },
        "scope": "Static source interface facts only; no task rows, answers, raw traces, source excerpts, or historical patches",
        "generator_source_sha256": digest(Path(__file__)),
    }
    cards["canonical_json_sha256"] = protocol.canonical_hash(cards)
    return cards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--base-node-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    card = build(args.campaign_root.resolve(), args.base_node_id)
    protocol.require_new(args.output)
    protocol.write_json(args.output, card)
    print(json.dumps({"card": str(args.output), "sha256": digest(args.output),
                      "base_node_id": card["base_node_id"]}, indent=2))


if __name__ == "__main__":
    main()
