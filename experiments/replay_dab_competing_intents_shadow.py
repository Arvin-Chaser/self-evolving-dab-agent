#!/usr/bin/env python3
"""Run the causal-diagnosis and competing-intent protocol without mutating a campaign.

The replay reads an already appended generation's compact result and graph, then
stores all new Meta outputs under an isolated shadow directory. It neither
appends a roadmap node nor seals, admits, or evaluates a candidate.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import dab_roadmap_protocol as protocol


def require_new_directory(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"Shadow replay destination already exists: {path}")
    path.mkdir(parents=True)


def write_manifest(path: Path, value: dict[str, Any]) -> None:
    protocol.require_new(path)
    protocol.write_json(path, value)


def run(args: argparse.Namespace) -> int:
    campaign_root = args.campaign_root.resolve()
    campaign, _ = protocol.load_campaign(campaign_root)
    records = protocol.load_roadmap(campaign_root)
    record = next((item for item in records if item.get("generation") == args.generation), None)
    if record is None:
        raise SystemExit(f"No appended generation {args.generation} in {campaign_root}")

    generation_dir = protocol.generation_dir(campaign_root, args.generation)
    intent_path = generation_dir / "sealed_intent.json"
    candidate_path = Path(record["detail_links"]["candidate_ref"])
    result_path = generation_dir / "result.json"
    for path in (intent_path, candidate_path, result_path):
        if not path.is_file():
            raise SystemExit(f"Required replay input is unavailable: {path}")

    output = args.output.resolve()
    require_new_directory(output)
    intent = protocol.read_json(intent_path)
    candidate = protocol.read_json(candidate_path)
    result = protocol.read_json(result_path)
    snapshot = protocol.build_snapshot(campaign_root)
    input_binding = {
        "mode": "shadow_replay_no_campaign_mutation_v1",
        "campaign_root": str(campaign_root),
        "source_generation": args.generation,
        "input_artifacts": {
            "sealed_intent": str(intent_path),
            "sealed_intent_sha256": protocol.sha256_file(intent_path),
            "candidate_ref": str(candidate_path),
            "candidate_ref_sha256": protocol.sha256_file(candidate_path),
            "result": str(result_path),
            "result_sha256": protocol.sha256_file(result_path),
            "roadmap_head_sha256": snapshot["roadmap_head_sha256"],
        },
        "context_boundary": {
            "uses": "compact result, compact graph, and bound aggregate mechanism evidence only",
            "excludes": "per-query traces, answer content, validator targets, F1, and held-out queries",
        },
    }
    protocol.write_json(output / "input_binding.json", input_binding)

    diagnosis_session = output / "diagnosis"
    diagnosis_session.mkdir()
    diagnosis_prompt = protocol.build_review_prompt(intent, candidate, result, snapshot)
    protocol.write_json(diagnosis_session / "output_schema.json", protocol.review_output_schema())
    (diagnosis_session / "prompt.md").write_text(diagnosis_prompt, encoding="utf-8")
    if args.prepare_only:
        print({"status": "shadow_replay_prepared", "output": str(output)})
        return 0
    if args.resume_diagnosis_from:
        prior = args.resume_diagnosis_from.resolve()
        prior_binding = protocol.read_json(prior / "input_binding.json")
        if prior_binding["input_artifacts"] != input_binding["input_artifacts"]:
            raise SystemExit("Cannot reuse diagnosis: shadow input hashes have changed")
        diagnosis = protocol.read_json(prior / "diagnosis.json")
        protocol.write_json(diagnosis_session / "resume_source.json", {
            "source": str(prior / "diagnosis.json"),
            "sha256": protocol.sha256_file(prior / "diagnosis.json"),
        })
    else:
        diagnosis = protocol.invoke_codex_json(
            campaign=campaign,
            session=diagnosis_session,
            prompt=diagnosis_prompt,
            schema_path=diagnosis_session / "output_schema.json",
            output_name="diagnosis_response.json",
        )
    diagnosis_errors = protocol.validate_review(
        diagnosis,
        {protocol.ROOT_NODE_ID, *[item["node_id"] for item in records]},
    )
    if diagnosis_errors:
        raise SystemExit("Invalid shadow diagnosis: " + "; ".join(diagnosis_errors))
    write_manifest(output / "diagnosis.json", diagnosis)

    hypothesis_snapshot = deepcopy(snapshot)
    hypothesis_snapshot["shadow_replay"] = {
        "source_generation": args.generation,
        "source_node_id": record["node_id"],
        "causal_diagnosis": diagnosis["causal_diagnosis"],
        "outcome_label": diagnosis["outcome_label"],
        "short_review": diagnosis["short_review"],
    }
    hypothesis_snapshot["snapshot_sha256"] = protocol.sha256_text(
        protocol.canonical_json({key: value for key, value in hypothesis_snapshot.items()
                                 if key != "snapshot_sha256"})
    )
    hypothesis_session = output / "hypotheses"
    hypothesis_session.mkdir()
    hypothesis_prompt = protocol.build_intent_prompt(hypothesis_snapshot)
    if args.resume_diagnosis_from:
        hypothesis_prompt += "\nFor this shadow replay, return exactly three concise, fully specified hypotheses. Keep each explanatory free-text field to at most two sentences; preserve every required schema field.\n"
    protocol.write_json(hypothesis_session / "roadmap_snapshot.json", hypothesis_snapshot)
    protocol.write_json(hypothesis_session / "output_schema.json", protocol.hypothesis_pool_output_schema())
    (hypothesis_session / "prompt.md").write_text(hypothesis_prompt, encoding="utf-8")
    pool = protocol.invoke_codex_json(
        campaign=campaign,
        session=hypothesis_session,
        prompt=hypothesis_prompt,
        schema_path=hypothesis_session / "output_schema.json",
        output_name="hypothesis_pool.json",
    )
    pool_errors = protocol.validate_hypothesis_pool(pool, hypothesis_snapshot)
    if pool_errors:
        raise SystemExit("Invalid shadow hypothesis pool: " + "; ".join(pool_errors))
    write_manifest(output / "hypothesis_pool.json", pool)

    selection_session = output / "selection"
    selection_session.mkdir()
    selection_prompt = protocol.build_selection_prompt(hypothesis_snapshot, pool)
    protocol.write_json(selection_session / "roadmap_snapshot.json", hypothesis_snapshot)
    protocol.write_json(selection_session / "sealed_hypothesis_pool.json", pool)
    protocol.write_json(selection_session / "output_schema.json", protocol.intent_selection_output_schema())
    (selection_session / "prompt.md").write_text(selection_prompt, encoding="utf-8")
    selection = protocol.invoke_codex_json(
        campaign=campaign,
        session=selection_session,
        prompt=selection_prompt,
        schema_path=selection_session / "output_schema.json",
        output_name="selection_response.json",
    )
    selection_errors = protocol.validate_intent_selection(selection, pool)
    if selection_errors:
        raise SystemExit("Invalid shadow intent selection: " + "; ".join(selection_errors))
    write_manifest(output / "selection.json", selection)

    selected = next(item for item in pool["hypotheses"]
                    if item["hypothesis_id"] == selection["selected_hypothesis_id"])
    manifest = {
        **input_binding,
        "diagnosis_sha256": protocol.sha256_file(output / "diagnosis.json"),
        "hypothesis_pool_sha256": protocol.sha256_file(output / "hypothesis_pool.json"),
        "selection_sha256": protocol.sha256_file(output / "selection.json"),
        "selected_hypothesis_id": selected["hypothesis_id"],
        "selected_mechanism_key": selected["intent"]["mechanism_key"],
        "selected_intent": selected["intent"],
    }
    write_manifest(output / "shadow_replay_manifest.json", manifest)
    print({
        "status": "shadow_replay_complete",
        "output": str(output),
        "selected_hypothesis_id": selected["hypothesis_id"],
        "selected_mechanism_key": selected["intent"]["mechanism_key"],
    })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--generation", type=int, default=13)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--resume-diagnosis-from", type=Path)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
