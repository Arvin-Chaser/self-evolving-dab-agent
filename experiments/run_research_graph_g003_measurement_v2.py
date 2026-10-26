#!/usr/bin/env python3
"""One bounded G3 measurement-spec correction without altering prior Meta output."""

from experiments.run_research_graph_g003_measurement import BASE, research


if __name__ == "__main__":
    research(
        directory=BASE / "g003_research_meta_006",
        stage="g003_measurement_research_v2",
        extra_instruction=(
            "Schema clarification: uncertainty_fact_ids may contain ONLY fact-card "
            "IDs whose kind is uncertainty; timeout_trace_gap is an observation, "
            "not an uncertainty. code_parent must equal EXACTLY one eligible alias "
            "(g001_deadline_reserve or g002_lifecycle_stage), with no hash or "
            "description appended. If repeated_result_digest is logged, it must "
            "be only a boolean repeated/not-repeated flag, never a digest string. "
            "Do not claim an obligation can be matched to a tool result unless "
            "the permitted runtime inputs actually contain a deterministic "
            "binding key; ambiguous matches are UNKNOWN. Do not use an unpaired "
            "strict-score change as hypothesis falsification. This is one "
            "independent correction; do not assume spec readiness."
        ),
    )
