#!/usr/bin/env python3
"""No-benchmark G12 runtime probes using the real upstream dispatch/log code.

Run in a fresh process for each mode. The only replaced execution is agent
initialization and the synthetic database tool; no database or evaluator runs.
"""

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


SENTINELS = {
    "task": "G012_SYNTHETIC_TASK_SENTINEL_8712",
    "answer": "G012_SYNTHETIC_ANSWER_SENTINEL_8712",
    "result": "G012_SYNTHETIC_RESULT_SENTINEL_8712",
    "plan": "G012_SYNTHETIC_PLAN_SENTINEL_8712",
    "step": "G012_SYNTHETIC_STEP_SENTINEL_8712",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--upstream", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=["enabled", "disabled", "transport_enabled", "transport_disabled", "provider"])
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Refusing to overwrite probe output")
    args.output.mkdir(parents=True)
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(args.upstream.resolve()))
    from common_scaffold import DataAgent as upstream
    from openai.types.chat import ChatCompletion
    from experiments import run_dab_tool_agent as runner
    from experiments.g012_interface_contract import AUTHORING_POLICY_RENDERED, parse_directive
    from experiments.g012_runtime_gap_action import read_sidecar, write_g012_task_summary

    binding = json.loads((repo.parent / "assembly.json").read_text()) if (repo.parent / "assembly.json").exists() else None
    expected = {
        "common_scaffold/DataAgent.py": "ea64b4e2b54ca32545c006d9d2aa77ad3d788ecf337b50c898b268631b24f80a",
        "common_scaffold/prompts/prompt_builder.py": "f06a44319ea1cbd74723c152c3278b00b3ed658895f1463b943fba0e5801da4c",
    }
    if any(sha(args.upstream / name) != digest for name, digest in expected.items()):
        raise RuntimeError("Real upstream source binding differs")
    enabled = args.mode not in {"disabled", "transport_disabled"}
    live = args.mode == "provider"
    transport_failure = args.mode.startswith("transport_")
    os.environ["DAB_TASK_DEADLINE_MONOTONIC"] = str(time.monotonic() + 1200)
    os.environ["DAB_ANONYMOUS_TASK_INDEX"] = "0"
    dispatches = []
    requests = []
    durations = []

    class SyntheticQueryTool:
        name = "query_db"

        def __init__(self):
            template = upstream.QueryDBTool.__new__(upstream.QueryDBTool)
            template.name = self.name
            self.spec = template.get_spec()

        def get_spec(self):
            return copy.deepcopy(self.spec)

        def to_dict(self):
            return {"name": self.name, "synthetic_no_database": True}

        def exec(self, arguments):
            dispatches.append({"tool": self.name, "arguments": copy.deepcopy(arguments)})
            return {"success": True, "result": [{"synthetic_value": SENTINELS["result"]}]}

        def clean_up(self):
            pass

    # Keep run/call_llm/handle_reponse/_handle_tool_call/to_dict untouched.
    # Replace only initialization to avoid opening any benchmark or database.
    def synthetic_init(self):
        self.root_dir = args.output
        self.query_dir = args.output / "no_benchmark_directory"
        self.file_storage_dir = args.output / "file_storage"
        self.file_storage_dir.mkdir()
        self.llm_log_path = args.output / "llm_calls.jsonl"
        self.tool_log_path = args.output / "tool_calls.jsonl"
        self.validation_log_path = args.output / "validation_not_used.jsonl"
        self.logger = logging.getLogger("g012_synthetic_probe")
        self.logger.disabled = True
        self.final_result = None
        self.terminate_reason = None
        self.result_storage = {}
        self.llm_call_count = 0
        self.max_iterations = 8
        self.deployment_name = "deepseek-flash"
        self.messages = [
            {"role": "system", "content": "Synthetic no-benchmark interface check. " + (AUTHORING_POLICY_RENDERED if live else "")},
            {"role": "user", "content": SENTINELS["task"] + (
                " First call query_db once using db_name=synthetic and query=SELECT 1. "
                "After its result, call record_self_observation to author a plan using the declared policy. "
                "Make two step positions: the first references the actual visible prior storage key, "
                "the second has an empty refs list. Choose your own plan and step IDs. "
                "Do not invent a reference or emit the record before seeing the tool result. "
                "After any structural directive, take the indicated next action and then finish."
                if live else " synthetic fixture")},
        ]
        self.tools = {
            "query_db": SyntheticQueryTool(),
            "return_answer": upstream.ReturnAnswerTool(self.tool_log_path, "return_answer"),
        }

    upstream.DataAgent.__init__ = synthetic_init
    options = SimpleNamespace(
        deployment_name="deepseek-flash", openai_compatible_base_url=None,
        disable_evolved_helper_tools=True, disable_self_observation_tool=False,
        self_observation_tool_name="record_self_observation",
        enable_g011_plan_evidence_ledger=True, enable_g012_uncertainty_gap_action=enabled,
        g011_sidecar_path=args.output / "g011_plan_evidence.jsonl",
        g012_sidecar_path=args.output / "g012_uncertainty_gap_action.jsonl",
        g005_sidecar_path=args.output / "g005_provenance.jsonl",
        g006_sidecar_path=args.output / "g006_tool_class.jsonl",
        g007_sidecar_path=args.output / "g007_last_pre_exec.jsonl",
        llm_retries=1, llm_retry_sleep=0, llm_timeout=90,
    )
    cls = runner.import_upstream_data_agent(args.upstream, options)
    agent = cls()
    record = {
        "schema": "g011_plan_record_v1", "plan_id": SENTINELS["plan"],
        "revision": 1, "supersedes": None,
        "steps": [{"step_id": SENTINELS["step"], "refs": ["var_fixture_prior_8712"]}],
    }
    carrier = "G011_PLAN_RECORD_V1 " + json.dumps(record)

    def response(call_id, name, arguments):
        return ChatCompletion.model_validate({
            "id": "synthetic-completion", "object": "chat.completion", "created": 0,
            "model": "deepseek-flash", "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {
                    "name": name, "arguments": json.dumps(arguments),
                }}],
            }}],
        })

    sequence = [
        response("fixture_prior_8712", "query_db", {"db_name": "synthetic", "query": "SELECT 1"}),
        response("fixture_record_8712", "record_self_observation", {"freeform": carrier}),
        response("fixture_terminal_8712", "return_answer", {"answer": SENTINELS["answer"]}),
    ]
    provider = None
    if live:
        from openai import OpenAI
        from adapters.deepseek_client_v1 import install_client
        credential = sys.stdin.readline().strip()
        if not credential or any(c.isspace() for c in credential):
            raise RuntimeError("Missing or malformed credential")
        provider = install_client(OpenAI(api_key=credential, base_url="https://api.deepseek.com/v1", max_retries=0, timeout=90))
        del credential

    def create(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        start = time.monotonic()
        try:
            if transport_failure:
                raise ConnectionError("synthetic_transport_failure")
            if provider is not None:
                if len(requests) > 4:
                    raise RuntimeError("No-task provider call cap reached")
                return provider.chat.completions.create(**kwargs)
            return sequence.pop(0)
        finally:
            durations.append(time.monotonic() - start)

    agent.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    start = time.monotonic()
    if live:
        # Three live turns exercise acquisition, real-model authorship and
        # delivery at a later call_llm boundary. Do not force a final answer.
        for _ in range(3):
            message = agent.call_llm()
            agent.handle_reponse(message)
            if agent.final_result is not None:
                break
        with (args.output / "final_agent.json").open("x", encoding="utf-8") as stream:
            json.dump(agent.to_dict(), stream)
    else:
        agent.run()
    elapsed = time.monotonic() - start
    if enabled:
        write_g012_task_summary(agent)
    adapter = getattr(agent, "_g011_plan_evidence_adapter", None)
    ledger = adapter.ledger if adapter is not None else None
    if adapter is not None and adapter.recorder is not None:
        adapter.recorder.write_task_summary(ledger, getattr(agent, "_g011_plan_evidence_state", {}))
    active = ledger.active_assessment() if ledger is not None else None
    sidecar = read_sidecar(options.g012_sidecar_path) if enabled else {}
    summary = sidecar.get("summary") or {}
    surfaces = {}
    for name in ("llm_calls.jsonl", "final_agent.json", "tool_calls.jsonl", "agent_self_observations.jsonl"):
        path = args.output / name
        raw = path.read_text(encoding="utf-8") if path.is_file() else ""
        surfaces[name] = {
            "exists": path.is_file(), "sha256": sha(path) if path.is_file() else None,
            "sentinel_presence": {key: value in raw for key, value in SENTINELS.items()},
            "record_prefix_present": "G011_PLAN_RECORD_V1" in raw,
        }
    structural_raw = json.dumps(sidecar.get("rows", [])) + json.dumps(summary)
    structural_clean = not any(s in structural_raw for s in SENTINELS.values())
    directive_count = sum(
        len([m for m in request["messages"] if m.get("role") == "user" and isinstance(m.get("content"), str)
             and m["content"].startswith("Structural check only: ")])
        for request in requests
    )
    for request in requests:
        for message in request["messages"]:
            if isinstance(message.get("content"), str) and message["content"].startswith("Structural check only: "):
                parse_directive(message["content"])
    result = {
        "schema_version": "g012_no_task_runtime_probe_v1", "mode": args.mode,
        "synthetic_only": True, "benchmark_accessed": False, "database_accessed": False,
        "evaluation_run": False, "provider_call_count": len(requests) if live else 0,
        "upstream_data_agent_sha256": sha(args.upstream / "common_scaffold/DataAgent.py"),
        "probe_sha256": sha(Path(__file__)),
        "production_runner_wrappers_used": True, "constructor_replaced_with_synthetic_fixture": True,
        "llm_call_count": agent.llm_call_count, "termination": agent.terminate_reason,
        "final_result_is_synthetic_answer": agent.final_result == SENTINELS["answer"],
        "final_result_is_empty": agent.final_result == "",
        "dispatch_count": len(dispatches),
        "carrier_absent_from_query_dispatch": all("self_observation" not in row["arguments"] for row in dispatches),
        "active_record_present": active is not None,
        "active_unique_ref_count": sum(item.status == "unique" for item in active.ref_statuses) if active else 0,
        "g012_summary": summary,
        "g012_sidecar_violations": sidecar.get("violations", []),
        "g012_exports_synthetic_content_absent": structural_clean,
        "directive_observed_at_provider_boundary_count": directive_count,
        "raw_log_surfaces": surfaces,
        "elapsed_seconds": elapsed, "request_durations_seconds": durations,
        "timing_equivalence_proven": False,
        "scoring_code_executed": False,
        "claim_limit": "No-task interface feasibility only; explicitly instructed authoring is not autonomous benchmark adoption or semantic correctness",
    }
    # Persist only anonymous structural metadata outside the synthetic scratch logs.
    with (args.output / "probe_result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Provider exceptions may contain request details. Never print them.
        import traceback
        frames = [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                  for frame in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps({"status": "probe_error", "error_class": type(exc).__name__, "frames": frames}))
        raise SystemExit(1)
