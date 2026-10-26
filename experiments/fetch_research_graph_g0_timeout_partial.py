#!/usr/bin/env python3
"""Persist the bounded G0 timeout-log extraction as a new local sidecar."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "experiments/collect_research_graph_g0_timeout_partial.py"
OUTPUT = ROOT / "experiments/research_graph_baseline_20261016/g000_timeout_partial_v1.json"
SSH = ["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "IdentitiesOnly=yes",
       "-o", "BatchMode=yes", "root@100.83.10.33",
       "df -hT /srv/text2sql; /srv/text2sql/.venv/bin/python -"]


def validate_payload(payload: dict) -> None:
    allowed_top = {"schema_version", "source_summary_sha256", "timeout_case_count",
                   "cases", "scope", "limitations"}
    allowed_case = {"anonymous_timeout_index", "llm_record_count", "llm_response_present_count",
                    "llm_error_present_count", "tool_record_count", "tool_calls_by_name",
                    "tool_failures_by_name", "recorded_llm_duration_sec",
                    "recorded_tool_duration_sec", "observed_event_span_sec",
                    "torn_tail_bytes", "source_hashes"}
    cases = payload.get("cases")
    if (set(payload) != allowed_top
            or payload.get("schema_version") != "dab_g0_timeout_partial_answer_blind_v1"
            or payload.get("timeout_case_count") != 6
            or not isinstance(cases, list) or len(cases) != 6
            or [case.get("anonymous_timeout_index") for case in cases] != list(range(1, 7))):
        raise RuntimeError("Timeout extraction failed top-level contract checks")
    for case in cases:
        if (set(case) != allowed_case
                or set(case["source_hashes"]) != {"llm_calls_sha256", "tool_calls_sha256"}
                or set(case["torn_tail_bytes"]) != {"llm", "tool"}
                or not 0 <= case["observed_event_span_sec"] <= 1200):
            raise RuntimeError("Timeout extraction contains an unapproved field or value")


def main() -> None:
    if OUTPUT.exists():
        raise RuntimeError("Timeout sidecar already exists; refusing overwrite")
    proc = subprocess.run(SSH, input=COLLECTOR.read_text(encoding="utf-8"), text=True,
                          encoding="utf-8", capture_output=True, timeout=180, check=False)
    lines = proc.stdout.splitlines()
    if proc.returncode or not lines or not lines[0].startswith("Filesystem"):
        raise RuntimeError(f"Remote extraction or disk precheck failed: exit {proc.returncode}")
    payload = json.loads(lines[-1])
    validate_payload(payload)
    cases = payload["cases"]
    with OUTPUT.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(json.dumps({"status": "written", "timeout_cases": 6,
                      "llm_records": [case["llm_record_count"] for case in cases],
                      "tool_records": [case["tool_record_count"] for case in cases]}, sort_keys=True))


if __name__ == "__main__":
    main()
