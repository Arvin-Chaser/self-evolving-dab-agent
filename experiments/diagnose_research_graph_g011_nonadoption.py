#!/usr/bin/env python3
"""Read-only aggregate of frozen G11 structural summaries for adoption diagnosis."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/research_graph_baseline_20261016")
RUN = BASE / "g011_solution_loop_revision001/evaluation/g011_structural_plan_evidence_ledger_nohint_56_v1"


def main() -> None:
    summaries = list((RUN / "runs").glob("*/g011_plan_evidence_summary.json"))
    counts = Counter()
    for path in summaries:
        row = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "record_count", "accepted_record_count", "rejected_record_count",
            "guidance_message_count", "guidance_binding_count",
            "guidance_suppressed_no_state_count",
            "guidance_suppressed_cap_count", "guidance_suppressed_deadline_count",
            "guidance_suppressed_duplicate_count",
            "redacted_plan_record_observation_count",
            "extra_model_turn_count", "extra_tool_dispatch_count",
            "mechanism_initiated_tool_call_count",
        ):
            value = row.get(key)
            if type(value) is not int or value < 0:
                raise RuntimeError(f"G11 summary field invalid: {key}")
            counts[key] += value
            counts[f"tasks_with_{key}"] += value > 0
    print(json.dumps({"summary_count": len(summaries), "aggregates": dict(counts)}, sort_keys=True))


if __name__ == "__main__":
    main()
