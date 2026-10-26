#!/usr/bin/env python3
"""Bounded synthetic runtime probe for the frozen G13 revision-5 candidate."""

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
    "task": "G013_ADMISSION_SYNTHETIC_TASK_7319",
    "answer": "G013_ADMISSION_SYNTHETIC_ANSWER_7319",
    "result": "G013_ADMISSION_SYNTHETIC_RESULT_7319",
}
EXPECTED_UPSTREAM = {
    "common_scaffold/DataAgent.py": "ea64b4e2b54ca32545c006d9d2aa77ad3d788ecf337b50c898b268631b24f80a",
    "common_scaffold/prompts/prompt_builder.py": "f06a44319ea1cbd74723c152c3278b00b3ed658895f1463b943fba0e5801da4c",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_sha(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
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
                                    "arguments": json.dumps(arguments, separators=(",", ":")),
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("enabled", "disabled", "provider"))
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Refusing to overwrite probe scratch")
    args.output.mkdir(parents=True)
    repo = args.repo.resolve()
    upstream_root = args.upstream.resolve()
    for relative, expected in EXPECTED_UPSTREAM.items():
        if sha(upstream_root / relative) != expected:
            raise RuntimeError("Frozen upstream binding differs")

    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(upstream_root))
    from common_scaffold import DataAgent as upstream
    from openai.types.chat import ChatCompletion
    from experiments import run_dab_tool_agent as runner
    from experiments.g013_requirement_coverage import (
        ACTION_VOCABULARY,
        CONTENT_BLIND_MARKER,
        RequirementCoverageRuntime,
    )

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
                    "tool": self.name,
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
        self.logger = logging.getLogger("g013_admission_probe")
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
                    "Synthetic no-benchmark runtime boundary check. No database is connected. "
                    "Use automatic tool selection only. Structural coverage is not semantic truth."
                ),
            },
            {
                "role": "user",
                "content": (
                    SENTINELS["task"]
                    + " Work one phase per model turn. First call query_db once with harmless "
                    "synthetic arguments. After its result, call record_self_observation exactly "
                    "once with a strict g013_requirement_coverage_record_v1 JSON in freeform. "
                    "Use revision 1 and exactly two rows: one observed/current/none row that copies "
                    "the actual visible var_<tool_call_id> key exactly as observation_token, and one "
                    "uncovered/unknown/none row with null observation_token. Choose bounded opaque "
                    "requirement tokens yourself. Do not answer before receiving the structural view. "
                    "After the view, take at most one action of its structural class."
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
        g013_requirement_coverage=enabled,
        g013_sidecar_path=args.output / "g013_requirement_coverage_sidecar.jsonl",
        g004_journal_path=args.output / "g004.jsonl",
        g005_sidecar_path=args.output / "g005.jsonl",
        g006_sidecar_path=args.output / "g006.jsonl",
        g007_sidecar_path=args.output / "g007.jsonl",
        llm_retries=1,
        llm_retry_sleep=0,
        llm_timeout=90,
    )
    cls = runner.import_upstream_data_agent(upstream_root, options)
    agent = cls()

    programmed_record = {
        "schema": "g013_requirement_coverage_record_v1",
        "revision": 1,
        "rows": [
            {
                "requirement_token": "req_seen_7319",
                "observation_token": "var_fixture_prior_7319",
                "coverage_state": "observed",
                "freshness": "current",
                "fault": "none",
            },
            {
                "requirement_token": "req_gap_7319",
                "observation_token": None,
                "coverage_state": "uncovered",
                "freshness": "unknown",
                "fault": "none",
            },
        ],
    }
    sequence = [
        completion_response(
            ChatCompletion,
            "fixture_prior_7319",
            "query_db",
            {"db_name": "synthetic", "query": "bounded synthetic observation"},
        ),
        completion_response(
            ChatCompletion,
            "fixture_record_7319",
            "record_self_observation",
            {"freeform": json.dumps(programmed_record, separators=(",", ":"))},
        ),
        completion_response(
            ChatCompletion,
            "fixture_followup_7319",
            "query_db",
            {"db_name": "synthetic", "query": "bounded structural followup"},
        ),
        completion_response(
            ChatCompletion,
            "fixture_terminal_7319",
            "return_answer",
            {"answer": SENTINELS["answer"]},
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
        messages = kwargs.get("messages", [])
        view_count = sum(
            isinstance(message, dict)
            and message.get("role") == "user"
            and isinstance(message.get("content"), str)
            and message["content"].startswith("G013_REQUIREMENT_COVERAGE_V1 ")
            for message in messages
        )
        request_meta.append(
            {
                "ordinal": ordinal,
                "automatic_tool_selection": "tool_choice" not in kwargs,
                "view_count": view_count,
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

    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    start = time.monotonic()
    max_turns = 5 if live else 4
    for _ in range(max_turns):
        message = agent.call_llm()
        if message is None:
            break
        agent.handle_reponse(message)
        runtime = getattr(agent, "_g013_requirement_coverage", None)
        summary = runtime.task_summary() if runtime is not None else {}
        if agent.final_result is not None:
            break
        # Programmed controls must consume the same fixed response sequence.
        # A live probe may stop once the registered behavioral endpoint is seen.
        if live and sum(summary.get("action_consistency_counts", {}).values()) > 0:
            break
        if live and dispatches and int(summary.get("accepted_record_count", 0)) == 0:
            agent.messages.append(
                {
                    "role": "user",
                    "content": (
                        "Continue the required next phase only. If query_db already returned a "
                        "visible var_ key, call record_self_observation now with the exact strict "
                        "two-row G13 carrier described earlier; do not answer."
                    ),
                }
            )
    elapsed = time.monotonic() - start

    runtime = getattr(agent, "_g013_requirement_coverage", None)
    if runtime is not None:
        runtime.write_task_summary()
    summary = runtime.task_summary() if runtime is not None else {
        "enabled": False,
        "accepted_record_count": 0,
        "exact_token_copy_rows": 0,
        "directive_delivered_count": 0,
        "action_consistency_counts": {state: 0 for state in ("consistent", "contradictory", "unknown")},
        "mechanism_initiated_tool_call_count": 0,
        "forced_tool_call_count": 0,
        "forced_answer_count": 0,
        "scoring_mutation_count": 0,
        "timeout_extension_count": 0,
    }

    active_rows = runtime.engine.rows() if runtime is not None else ()
    sensitive_tokens = [
        token
        for row in active_rows
        for token in (row.requirement_token, row.observation_token)
        if isinstance(token, str)
    ]
    raw_surfaces: dict[str, Any] = {}
    persisted_sensitive_hits = 0
    persisted_reasoning_field_hits = 0
    for name in (
        "llm_calls.jsonl",
        "tool_calls.jsonl",
        "agent_self_observations.jsonl",
        "g013_requirement_coverage_sidecar.jsonl",
    ):
        path = args.output / name
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        hits = sum(text.count(token) for token in sensitive_tokens)
        persisted_sensitive_hits += hits
        reasoning_hits = text.count('"reasoning_content"')
        persisted_reasoning_field_hits += reasoning_hits
        raw_surfaces[name] = {
            "exists": path.is_file(),
            "sha256": sha(path) if path.is_file() else None,
            "sensitive_token_hit_count": hits,
            "reasoning_content_field_hit_count": reasoning_hits,
            "contains_general_synthetic_context": any(value in text for value in SENTINELS.values()),
            "isolated_scratch_only": True,
            "copied_to_research_artifact": False,
        }
    final_state = agent.to_dict()
    final_path = args.output / "final_agent.json"
    write_new(final_path, final_state)
    final_text = final_path.read_text(encoding="utf-8", errors="replace")
    final_sensitive_hits = sum(final_text.count(token) for token in sensitive_tokens)
    persisted_sensitive_hits += final_sensitive_hits
    final_reasoning_hits = final_text.count('"reasoning_content"')
    persisted_reasoning_field_hits += final_reasoning_hits
    raw_surfaces["final_agent.json"] = {
        "exists": True,
        "sha256": sha(final_path),
        "sensitive_token_hit_count": final_sensitive_hits,
        "reasoning_content_field_hit_count": final_reasoning_hits,
        "contains_general_synthetic_context": any(value in final_text for value in SENTINELS.values()),
        "isolated_scratch_only": True,
        "copied_to_research_artifact": False,
    }

    # Exercise the four fail-closed cases independently of the accepted live state.
    fault_runtime = RequirementCoverageRuntime(enabled=True, remaining_seconds_fn=lambda: 900)
    # A genuinely missing carrier has no argument value. An empty object is a
    # separate malformed fixture and must not be relabeled to satisfy the gate.
    fault_runtime.observe_response_boundary(
        [
            SimpleNamespace(
                function=SimpleNamespace(
                    name="record_self_observation",
                    arguments=None,
                )
            )
        ]
    )
    fault_runtime.observe_response_boundary(
        [
            SimpleNamespace(
                function=SimpleNamespace(
                    name="record_self_observation",
                    arguments="{}",
                )
            )
        ]
    )
    fault_runtime.observe_response_boundary(
        [SimpleNamespace(function=SimpleNamespace(name="record_self_observation", arguments="not-json"))]
    )
    fault_runtime.observe_response_boundary(
        [SimpleNamespace(function=SimpleNamespace(name="record_self_observation", arguments='{\"freeform\":\"unterminated'))]
    )
    fault_runtime.observe_provider_rejection()
    fault_summary = fault_runtime.task_summary()
    rejection_counts = fault_summary["rejection_reason_counts"]
    fault_closed = all(
        int(rejection_counts.get(name, 0)) >= 1
        for name in ("missing", "malformed", "truncated", "provider_rejected")
    )

    consistent_count = int(summary.get("action_consistency_counts", {}).get("consistent", 0))
    structural_pass = bool(
        live
        and int(summary.get("accepted_record_count", 0)) >= 1
        and int(summary.get("exact_token_copy_rows", 0)) >= 1
        and int(summary.get("directive_delivered_count", 0)) == 1
        and consistent_count >= 1
        and all(item["automatic_tool_selection"] for item in request_meta)
    )
    prohibited_zero = all(
        int(summary.get(name, 0)) == 0
        for name in (
            "mechanism_initiated_tool_call_count",
            "forced_tool_call_count",
            "forced_answer_count",
            "scoring_mutation_count",
            "timeout_extension_count",
        )
    )
    privacy_pass = (
        persisted_sensitive_hits == 0
        and persisted_reasoning_field_hits == 0
    )
    status = (
        "passed"
        if structural_pass and prohibited_zero and privacy_pass and fault_closed
        else ("control_complete" if not live else "blocked")
    )
    non_carrier_dispatches = [row for row in dispatches if row.get("tool") != "record_self_observation"]
    result = {
        "schema_version": "g013_no_task_runtime_probe_v1",
        "status": status,
        "mode": args.mode,
        "synthetic_only": True,
        "benchmark_accessed": False,
        "database_accessed": False,
        "formal_evaluation_started": False,
        "provider_call_count": len(request_meta) if live else 0,
        "provider_call_cap": 5,
        "automatic_tool_selection_only": all(item["automatic_tool_selection"] for item in request_meta),
        "production_call_llm_used": True,
        "production_handle_reponse_used": True,
        "production_response_boundary_used": True,
        "real_model_authored_carrier_accepted": bool(live and int(summary.get("accepted_record_count", 0)) >= 1),
        "exact_visible_opaque_token_copy_count": int(summary.get("exact_token_copy_rows", 0)),
        "directive_delivered_count": int(summary.get("directive_delivered_count", 0)),
        "provider_request_with_view_count": sum(item["view_count"] > 0 for item in request_meta),
        "action_consistency_counts": summary.get("action_consistency_counts", {}),
        "selected_action_counts": summary.get("selected_action_counts", {}),
        "coverage_counts": summary.get("coverage_counts", {}),
        "freshness_counts": summary.get("freshness_counts", {}),
        "fault_counts": summary.get("fault_counts", {}),
        "fault_fixtures_fail_closed": fault_closed,
        "fault_fixture_rejection_counts": {
            name: int(rejection_counts.get(name, 0))
            for name in ("missing", "malformed", "truncated", "provider_rejected")
        },
        "non_carrier_dispatch_count": len(non_carrier_dispatches),
        "non_carrier_dispatch_sha256": value_sha(non_carrier_dispatches),
        "termination": agent.terminate_reason,
        "final_result_sha256": value_sha(agent.final_result),
        "llm_call_count": agent.llm_call_count,
        "persisted_sensitive_token_hit_count": persisted_sensitive_hits,
        "persisted_reasoning_content_field_hit_count": persisted_reasoning_field_hits,
        "raw_log_surfaces": raw_surfaces,
        "content_blind_marker_present": any(
            CONTENT_BLIND_MARKER in (args.output / name).read_text(encoding="utf-8", errors="replace")
            for name in ("llm_calls.jsonl", "tool_calls.jsonl", "agent_self_observations.jsonl", "final_agent.json")
            if (args.output / name).is_file()
        ),
        "mechanism_initiated_tool_call_count": int(summary.get("mechanism_initiated_tool_call_count", 0)),
        "forced_tool_call_count": int(summary.get("forced_tool_call_count", 0)),
        "forced_answer_count": int(summary.get("forced_answer_count", 0)),
        "scoring_mutation_count": int(summary.get("scoring_mutation_count", 0)),
        "timeout_extension_count": int(summary.get("timeout_extension_count", 0)),
        "action_cap_per_turn": summary.get("action_cap_per_turn"),
        "views_per_turn_cap": summary.get("views_per_turn_cap"),
        "views_per_task_cap": summary.get("views_per_task_cap"),
        "deadline_guard_seconds": summary.get("deadline_guard_seconds"),
        "elapsed_seconds": elapsed,
        "request_durations_seconds": durations,
        "timing_measurements_only": True,
        "strict_timing_equivalence_claimed": False,
        "probe_sha256": sha(Path(__file__)),
        "research_export_read_raw_logs": False,
        "raw_scratch_exported": False,
        "claim_limit": "No-task runtime admission only; no semantic, benchmark, or causal claim",
    }
    encoded = json.dumps(result, sort_keys=True)
    if any(value in encoded for value in SENTINELS.values()) or any(token in encoded for token in sensitive_tokens):
        raise RuntimeError("Probe receipt contains prohibited synthetic content")
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
        print(json.dumps({"status": "probe_error", "error_class": type(exc).__name__, "frames": frames}))
        raise SystemExit(1)
