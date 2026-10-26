#!/usr/bin/env python3
"""Bounded G12 directive/action probe with no benchmark or database access."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SENTINELS = {
    "task": "G012_ATTEMPT002_SYNTHETIC_TASK_6129",
    "answer": "G012_ATTEMPT002_SYNTHETIC_ANSWER_6129",
    "result": "G012_ATTEMPT002_SYNTHETIC_RESULT_6129",
    "plan": "G012_ATTEMPT002_SYNTHETIC_PLAN_6129",
    "step": "G012_ATTEMPT002_SYNTHETIC_STEP_6129",
}
DIRECTIVE_PREFIX = "Structural check only: action="
EXPECTED_UPSTREAM = {
    "common_scaffold/DataAgent.py": "ea64b4e2b54ca32545c006d9d2aa77ad3d788ecf337b50c898b268631b24f80a",
    "common_scaffold/prompts/prompt_builder.py": "f06a44319ea1cbd74723c152c3278b00b3ed658895f1463b943fba0e5801da4c",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_sha(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def completion_response(chat_completion: Any, call_id: str, name: str, arguments: dict[str, Any]) -> Any:
    return chat_completion.model_validate(
        {
            "id": "synthetic-completion",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )


def completion_multi_response(chat_completion: Any, calls: list[tuple[str, str, dict[str, Any]]]) -> Any:
    return chat_completion.model_validate(
        {
            "id": "synthetic-completion",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                            for call_id, name, arguments in calls
                        ],
                    },
                }
            ],
        }
    )


def directive_fields_from_row(row: dict[str, Any]) -> dict[str, str]:
    status = row.get("target_status")
    return {
        "action": str(row.get("action_code")),
        "reason": str(row.get("action_reason")),
        "record_status": str(row.get("record_status")),
        "target_scope": str(row.get("target_scope")),
        "target": str(row.get("target_token")),
        "target_status": "none" if status is None else str(status),
        "category": str(row.get("category")),
        "freshness": str(row.get("freshness")),
    }


def classify_behavior(summary: dict[str, Any]) -> str:
    if int(summary.get("contradicted_action_count", 0)):
        return "contradicted"
    if int(summary.get("consistent_action_count", 0)):
        return "consistent"
    if int(summary.get("unknown_action_count", 0)):
        return "unknown"
    return "untested"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=["enabled", "disabled", "provider"])
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Refusing to overwrite probe output")
    args.output.mkdir(parents=True)
    repo = args.repo.resolve()
    upstream_root = args.upstream.resolve()
    for relative, expected in EXPECTED_UPSTREAM.items():
        if sha(upstream_root / relative) != expected:
            raise RuntimeError("Real upstream source binding differs")

    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(upstream_root))
    from common_scaffold import DataAgent as upstream
    from openai.types.chat import ChatCompletion
    from experiments import run_dab_tool_agent as runner
    from experiments.g012_interface_contract import (
        AUTHORING_POLICY_RENDERED,
        parse_directive,
        render_directive,
    )
    from experiments.g012_runtime_gap_action import read_sidecar, write_g012_task_summary

    enabled = args.mode != "disabled"
    live = args.mode == "provider"
    os.environ["DAB_TASK_DEADLINE_MONOTONIC"] = str(time.monotonic() + 1200)
    os.environ["DAB_ANONYMOUS_TASK_INDEX"] = "0"
    dispatches: list[dict[str, Any]] = []
    request_meta: list[dict[str, Any]] = []
    durations: list[float] = []

    class SyntheticQueryTool:
        name = "query_db"

        def __init__(self) -> None:
            template = upstream.QueryDBTool.__new__(upstream.QueryDBTool)
            template.name = self.name
            self.spec = template.get_spec()

        def get_spec(self) -> dict[str, Any]:
            return copy.deepcopy(self.spec)

        def to_dict(self) -> dict[str, Any]:
            return {"name": self.name, "synthetic_no_database": True}

        def exec(self, arguments: dict[str, Any]) -> dict[str, Any]:
            result = {"success": True, "result": [{"synthetic_value": SENTINELS["result"]}]}
            dispatches.append(
                {
                    "arguments": copy.deepcopy(arguments),
                    "result": copy.deepcopy(result),
                }
            )
            return result

        def clean_up(self) -> None:
            return None

    def synthetic_init(self: Any) -> None:
        self.root_dir = args.output
        self.query_dir = args.output / "no_benchmark_directory"
        self.file_storage_dir = args.output / "file_storage"
        self.file_storage_dir.mkdir()
        self.llm_log_path = args.output / "llm_calls.jsonl"
        self.tool_log_path = args.output / "tool_calls.jsonl"
        self.validation_log_path = args.output / "validation_not_used.jsonl"
        self.logger = logging.getLogger("g012_attempt002_probe")
        self.logger.disabled = True
        self.final_result = None
        self.terminate_reason = None
        self.result_storage = {}
        self.llm_call_count = 0
        self.max_iterations = 8
        self.deployment_name = "deepseek-flash"
        self.messages = [
            {
                "role": "system",
                "content": (
                    "Synthetic no-benchmark runtime boundary check. No database is connected.\n\n"
                    + AUTHORING_POLICY_RENDERED
                ),
            },
            {
                "role": "user",
                "content": (
                    SENTINELS["task"]
                    + " Follow these phases exactly, one model turn at a time. Phase 1: call "
                    "query_db once with harmless "
                    "synthetic arguments of your choice so that a real visible var_<tool_call_id> "
                    "storage key is returned. Phase 2: use record_self_observation and the "
                    "declared policy to author a valid plan record. It must copy that actual visible "
                    "storage key into one step and include a second step with an empty refs list, "
                    "using plan and step identifiers of your choice. Do not invent the storage key "
                    "and do not record before seeing it. Do not call return_answer before the record "
                    "is accepted and a structural directive is received. Phase 3: after that "
                    "directive, take at most one action of its structural class; then you may finish."
                ),
            },
        ]
        self.tools = {
            "query_db": SyntheticQueryTool(),
            "return_answer": upstream.ReturnAnswerTool(self.tool_log_path, "return_answer"),
        }

    upstream.DataAgent.__init__ = synthetic_init
    options = SimpleNamespace(
        deployment_name="deepseek-flash",
        openai_compatible_base_url=None,
        disable_evolved_helper_tools=True,
        disable_self_observation_tool=False,
        self_observation_tool_name="record_self_observation",
        enable_g011_plan_evidence_ledger=True,
        enable_g012_uncertainty_gap_action=enabled,
        g011_sidecar_path=args.output / "g011_plan_evidence.jsonl",
        g012_sidecar_path=args.output / "g012_uncertainty_gap_action.jsonl",
        g005_sidecar_path=args.output / "g005_provenance.jsonl",
        g006_sidecar_path=args.output / "g006_tool_class.jsonl",
        g007_sidecar_path=args.output / "g007_last_pre_exec.jsonl",
        llm_retries=1,
        llm_retry_sleep=0,
        llm_timeout=90,
    )
    cls = runner.import_upstream_data_agent(upstream_root, options)
    agent = cls()

    record = {
        "schema": "g011_plan_record_v1",
        "plan_id": SENTINELS["plan"],
        "revision": 1,
        "supersedes": None,
        "steps": [
            {"step_id": SENTINELS["step"] + "_1", "refs": ["var_fixture_prior_6129"]},
            {"step_id": SENTINELS["step"] + "_2", "refs": []},
        ],
    }
    carrier = "G011_PLAN_RECORD_V1 " + json.dumps(record)
    sequence = [
        completion_response(
            ChatCompletion,
            "fixture_prior_6129",
            "query_db",
            {"db_name": "synthetic", "query": "SELECT synthetic_fixture"},
        ),
        completion_response(
            ChatCompletion,
            "fixture_record_6129",
            "record_self_observation",
            {"freeform": carrier},
        ),
        completion_multi_response(
            ChatCompletion,
            [
                (
                    "fixture_acquire_6129",
                    "query_db",
                    {"db_name": "synthetic", "query": "SELECT bounded_followup"},
                ),
                (
                    "fixture_terminal_6129",
                    "return_answer",
                    {"answer": SENTINELS["answer"]},
                ),
            ],
        ),
    ]

    provider = None
    if live:
        from openai import OpenAI
        from adapters.deepseek_client_v1 import install_client

        credential = sys.stdin.readline().strip()
        if not credential or any(character.isspace() for character in credential):
            raise RuntimeError("Missing or malformed credential")
        provider = install_client(
            OpenAI(
                api_key=credential,
                base_url="https://api.deepseek.com/v1",
                max_retries=0,
                timeout=90,
            )
        )
        del credential

    def create(**kwargs: Any) -> Any:
        ordinal = len(request_meta) + 1
        directive_texts = [
            message["content"]
            for message in kwargs.get("messages", [])
            if isinstance(message, dict)
            and message.get("role") == "user"
            and isinstance(message.get("content"), str)
            and message["content"].startswith(DIRECTIVE_PREFIX)
        ]
        parsed = []
        for text in directive_texts:
            parsed.append(parse_directive(text))
        request_meta.append(
            {
                "provider_call_ordinal": ordinal,
                "directive_count": len(directive_texts),
                "directive_texts": directive_texts,
                "parsed": parsed,
            }
        )
        start = time.monotonic()
        try:
            if provider is not None:
                if ordinal > 5:
                    raise RuntimeError("No-task provider call cap reached")
                return provider.chat.completions.create(**kwargs)
            if not sequence:
                raise RuntimeError("Programmed control response sequence exhausted")
            return sequence.pop(0)
        finally:
            durations.append(time.monotonic() - start)

    agent.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    start = time.monotonic()
    if live:
        for _ in range(5):
            message = agent.call_llm()
            if message is None:
                break
            agent.handle_reponse(message)
            state = getattr(agent, "_g012_gap_action_state", {})
            summary_state = state if isinstance(state, dict) else {}
            measurements = summary_state.get("measurements", [])
            if agent.final_result is not None:
                break
            if any(
                item.get("measurement_status") in {"consistent", "contradicted"}
                for item in measurements
                if isinstance(item, dict)
            ):
                break
            g011 = getattr(agent, "_g011_plan_evidence_adapter", None)
            active_record = g011.ledger.active_assessment() if g011 is not None else None
            if dispatches and active_record is None:
                agent.messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue phase 2 now: call record_self_observation with one valid "
                            "G011_PLAN_RECORD_V1 record. Copy the actual visible prior storage key, "
                            "include a second step with an empty refs list, choose all other record "
                            "arguments yourself, and do not return an answer yet."
                        ),
                    }
                )
        write_new(args.output / "final_agent.json", agent.to_dict())
    else:
        agent.run()
    elapsed = time.monotonic() - start

    if enabled:
        write_g012_task_summary(agent)
    g011_adapter = getattr(agent, "_g011_plan_evidence_adapter", None)
    ledger = g011_adapter.ledger if g011_adapter is not None else None
    if g011_adapter is not None and g011_adapter.recorder is not None:
        g011_adapter.recorder.write_task_summary(
            ledger, getattr(agent, "_g011_plan_evidence_state", {})
        )
    active = ledger.active_assessment() if ledger is not None else None
    sidecar = read_sidecar(options.g012_sidecar_path) if enabled else {
        "rows": [],
        "summary": None,
        "violations": [],
    }
    rows = sidecar.get("rows", [])
    summary = sidecar.get("summary") or {}
    directive_rows = [row for row in rows if row.get("event_phase") == "directive"]
    outcome_rows = [row for row in rows if row.get("event_phase") == "action_outcome"]
    boundary_directives = [
        (item["provider_call_ordinal"], text, parsed)
        for item in request_meta
        for text, parsed in zip(item["directive_texts"], item["parsed"])
    ]
    boundary_parsed = boundary_directives[0][2] if len(boundary_directives) == 1 else None
    sidecar_fields = (
        directive_fields_from_row(directive_rows[0]) if len(directive_rows) == 1 else None
    )
    runtime_messages = list(
        getattr(getattr(agent, "_g012_gap_action_adapter", None), "guidance_messages", ())
    )
    exact_runtime_match = bool(
        len(boundary_directives) == 1
        and len(runtime_messages) == 1
        and boundary_directives[0][1] == runtime_messages[0]
    )
    rerendered_match = False
    if boundary_parsed is not None:
        render_view = dict(boundary_parsed)
        render_view["target_token"] = render_view.pop("target")
        render_view["target_status"] = (
            None if render_view["target_status"] == "none" else render_view["target_status"]
        )
        rerendered_match = render_directive(render_view) == boundary_directives[0][1]

    structural_paths = [
        options.g012_sidecar_path,
        options.g012_sidecar_path.with_name("g012_uncertainty_gap_action_summary.json"),
    ]
    structural_text = "\n".join(
        path.read_text(encoding="utf-8") for path in structural_paths if path.is_file()
    )
    sentinel_scan = {key: value in structural_text for key, value in SENTINELS.items()}
    raw_logs: dict[str, Any] = {}
    for name in ("llm_calls.jsonl", "final_agent.json", "tool_calls.jsonl", "agent_self_observations.jsonl"):
        path = args.output / name
        raw = path.read_text(encoding="utf-8") if path.is_file() else ""
        raw_logs[name] = {
            "exists": path.is_file(),
            "sha256": sha(path) if path.is_file() else None,
            "contains_synthetic_context": any(value in raw for value in SENTINELS.values()),
            "isolated_base_raw_log": True,
            "copied_to_research_artifact": False,
        }

    summary_behavior = classify_behavior(summary)
    outcome = outcome_rows[0] if outcome_rows else {}
    directive_fields = boundary_parsed if boundary_parsed is not None else None
    directive_count = len(boundary_directives)
    fields_match = bool(directive_fields is not None and directive_fields == sidecar_fields)
    structural_clean = not any(sentinel_scan.values())
    adoption_ok = bool(
        active is not None
        and int(summary.get("accepted_record_count", 0)) >= 1
        and int(summary.get("adoption_visible_ref_count", 0)) >= 1
    )
    directive_ok = bool(
        directive_count == 1
        and len(directive_rows) == 1
        and fields_match
        and exact_runtime_match
        and rerendered_match
    )
    safety_ok = bool(
        structural_clean
        and not sidecar.get("violations", [])
        and int(summary.get("mechanism_initiated_tool_call_count", 0)) == 0
    )
    if live and adoption_ok and directive_ok and safety_ok and summary_behavior == "consistent":
        probe_status = "passed"
    elif live and (
        summary_behavior == "contradicted"
        or (directive_count and not directive_ok)
        or not safety_ok
    ):
        probe_status = "blocked"
    elif live:
        probe_status = "untested"
    else:
        probe_status = "control_complete"

    result = {
        "schema_version": "g012_no_task_runtime_probe_attempt002_v1",
        "status": probe_status,
        "mode": args.mode,
        "synthetic_only": True,
        "benchmark_accessed": False,
        "database_accessed": False,
        "evaluation_run": False,
        "provider_call_count": len(request_meta) if live else 0,
        "provider_tool_schema_accepted": bool(live and request_meta),
        "upstream_data_agent_sha256": sha(upstream_root / "common_scaffold/DataAgent.py"),
        "probe_sha256": sha(Path(__file__)),
        "production_call_llm_used": True,
        "production_handle_reponse_used": True,
        "production_handle_tool_call_used": True,
        "constructor_replaced_with_synthetic_fixture": True,
        "llm_call_count": agent.llm_call_count,
        "termination": agent.terminate_reason,
        "final_result_sha256": value_sha(agent.final_result),
        "dispatch_count": len(dispatches),
        "dispatch_payload_sha256": value_sha(dispatches),
        "record_attempt_count": int(summary.get("record_attempt_count", 0)),
        "accepted_record_count": int(summary.get("accepted_record_count", 0)),
        "active_record_present": active is not None,
        "active_unique_ref_count": (
            sum(item.status == "unique" for item in active.ref_statuses) if active else 0
        ),
        "directive_observed_at_provider_boundary_count": directive_count,
        "directive_provider_call_ordinal": (
            boundary_directives[0][0] if len(boundary_directives) == 1 else None
        ),
        "directive_strict_parse_passed": boundary_parsed is not None,
        "directive_exact_runtime_text_match": exact_runtime_match,
        "directive_exact_rerender_match": rerendered_match,
        "directive_sidecar_fields_match": fields_match,
        "directive_fields": directive_fields,
        "next_action_classification": summary_behavior,
        "next_action_structural_class": outcome.get("measured_action_class", "none"),
        "next_action_terminal_observed": bool(outcome.get("terminal_observed", False)),
        "g012_summary": summary,
        "g012_sidecar_violations": sidecar.get("violations", []),
        "g012_structural_sentinel_presence": sentinel_scan,
        "g012_structural_exports_clean": structural_clean,
        "mechanism_initiated_tool_call_count": int(
            summary.get("mechanism_initiated_tool_call_count", 0)
        ),
        "raw_log_surfaces": raw_logs,
        "elapsed_seconds": elapsed,
        "request_durations_seconds": durations,
        "timing_measurements_only": True,
        "strict_timing_equivalence_claimed": False,
        "scoring_code_executed": False,
        "wall_timeout_extension_allowed": False,
        "forced_answer": False,
        "forced_tool_dispatch": False,
        "research_export_read_raw_logs": False,
        "claim_limit": "No-task structural runtime admission only; no semantic or benchmark claim",
    }
    encoded_result = json.dumps(result, sort_keys=True)
    if any(value in encoded_result for value in SENTINELS.values()):
        raise RuntimeError("Probe receipt contains synthetic content")
    write_new(args.output / "probe_result.json", result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        frames = [
            {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(exc.__traceback__)
        ]
        print(
            json.dumps(
                {
                    "status": "probe_error",
                    "error_class": type(exc).__name__,
                    "frames": frames,
                }
            )
        )
        raise SystemExit(1)
