"""Cutoff-bound, no-tool DeepSeek pilot of historical research decisions.

The initial pilot measures decision outputs, not hypothetical candidate scores.
No response repairs, transport retries, production state writes or evaluations.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import random
import time
import urllib.request
from pathlib import Path

from experiments import dab_research_route as route
from experiments import dab_roadmap_protocol as protocol
from experiments import run_dab_research_workflow as workflow


def prepare(root: Path, out: Path, targets: list[int], seed: int = 56,
            input_chars: int = 260000, output_tokens: int = 16384) -> dict:
    if out.exists():
        raise ValueError("Replay requires a new directory; no overwritten predictions")
    if not targets or len(set(targets)) != len(targets) or min(targets) < 2:
        raise ValueError("Replay targets must be unique generations >= 2")
    before = {name: protocol.sha256_file(root / name) for name in (
        "campaign_state.json", "roadmap.jsonl", "campaign.json")}
    out.mkdir(parents=True)
    cases = []
    for target in targets:
        case = out / f"before_gen_{target:03d}"
        workflow.prepare(root, target - 1, case)
        for arm in ("compact", "flat", "route"):
            session = case / arm
            session.mkdir()
            prompt = (case / f"{arm}_prompt.txt").read_text(encoding="utf-8")
            schema = route.decision_schema()
            prompt += "\nReturn one JSON object matching this schema:\n" + protocol.canonical_json(schema)
            if len(prompt) > input_chars:
                raise ValueError("Replay input exceeds the common budget; never silently truncate")
            with (session / "request.txt").open("x", encoding="utf-8") as stream:
                stream.write(prompt)
            cases.append({"target_generation": target, "arm": arm,
                          "session": session.relative_to(out).as_posix(),
                          "input_chars": len(prompt), "request_sha256": protocol.sha256_file(session / "request.txt"),
                          "snapshot_sha256": protocol.read_json(case / "snapshot.json")["snapshot_sha256"]})
    random.Random(seed).shuffle(cases)
    manifest = {"schema": route.SCHEMA, "mode": "retrospective_no_tool_decision_pilot",
                "model": "deepseek-flash", "provider": "deepseek_official", "thinking": "enabled",
                "reasoning_effort": "high", "output_token_cap": output_tokens,
                "input_character_cap": input_chars, "seed": seed, "cases": cases,
                "campaign_root": str(root), "campaign_bindings": before,
                "flat_route_evidence_equal": True, "tools": [], "automatic_retries": 0,
                "limitations": ["One response per arm and cutoff; exploratory, not significance evidence.",
                                "Equal caps, unequal actual prompt lengths; input usage is reported.",
                                "Direct native chat calls, not the deployed tool-enabled Meta CLI.",
                                "Method was designed after observing these failures; retrospective selection bias.",
                                "No prediction of unevaluated candidate benchmark scores.",
                                "Historical imports do not reconstruct deleted Gen8 sources or its intent."]}
    route.new_json(out / "manifest.json", manifest)
    return manifest


def _request(prompt: str, output_tokens: int) -> dict:
    from experiments import dab_api_routing as routing
    from adapters.deepseek_client_v1 import request_options
    bound = protocol.read_json(protocol.ROOT / "configs/dab_deepseek_standalone_route_v2.json")
    # No CLI executable is used here. Bind the direct chat provider separately;
    # leave the production CLI runtime validation and its stale receipt intact.
    expected = {"provider": "deepseek_official", "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-flash", "api_key_env": "DEEPSEEK_API_KEY",
                "api_key_file": "C:/Users/34934/.config/dab/deepseek_api_key.txt"}
    if any(bound.get(key) != value for key, value in expected.items()):
        raise ValueError("Replay provider binding differs")
    options = request_options({"model": bound["model"], "messages": [
        {"role": "system", "content": "You are a data-agent harness research planner. Return JSON only."},
        {"role": "user", "content": prompt}], "response_format": {"type": "json_object"},
        "max_tokens": output_tokens})
    options.update(options.pop("extra_body"))
    request = urllib.request.Request(bound["base_url"] + "/chat/completions",
        data=json.dumps(options, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + routing.read_explicit_key(bound),
                 "Content-Type": "application/json"}, method="POST")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Replay provider redirect rejected")
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=600) as response:
        return json.load(response)


def run_case(out: Path, case: dict, manifest: dict) -> dict:
    session = out / case["session"]
    request_path = session / "request.txt"
    if protocol.sha256_file(request_path) != case["request_sha256"]:
        raise ValueError("Replay request changed")
    route.new_json(session / "dispatch.json", {"started_at": protocol.utc_now(),
                   "request_sha256": case["request_sha256"], "automatic_retry": False})
    started = time.monotonic()
    try:
        response = _request(request_path.read_text(encoding="utf-8"), manifest["output_token_cap"])
        route.new_json(session / "provider_response.json", response)
        answer = json.loads(response["choices"][0]["message"]["content"])
        route.new_json(session / "decision.json", answer)
        view = protocol.read_json(session.parent / "snapshot.json")
        route.validate_decision(answer, view)
        receipt = {**case, "status": "valid_decision", "decision": answer["decision"],
                   "code_parent": answer["code_parent"], "selected_option_id": answer["selected_option_id"],
                   "usage": response.get("usage"), "provider_model": response.get("model"),
                   "finish_reason": response["choices"][0].get("finish_reason"),
                   "decision_sha256": protocol.sha256_file(session / "decision.json")}
    except Exception as exc:
        receipt = {**case, "status": "failed", "failure_class": type(exc).__name__,
                   "automatic_retry": False}
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
    route.new_json(session / "receipt.json", receipt)
    return receipt


def run(out: Path, workers: int = 3) -> dict:
    manifest = protocol.read_json(out / "manifest.json")
    root = Path(manifest["campaign_root"])
    for name, expected in manifest["campaign_bindings"].items():
        if protocol.sha256_file(root / name) != expected:
            raise ValueError("Campaign changed since replay preparation")
    if any((out / case["session"] / "dispatch.json").exists() for case in manifest["cases"]):
        raise ValueError("A replay dispatch exists; do not repeat an ambiguous or completed run")
    # This marker freezes the complete set of prompts before any paid request.
    route.new_json(out / "dispatch_manifest.json", {"manifest_sha256": protocol.sha256_file(out / "manifest.json"),
                   "started_at": protocol.utc_now(), "workers": workers})
    receipts = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_case, out, case, manifest) for case in manifest["cases"]]
        for future in as_completed(futures):
            receipt = future.result()
            receipts.append(receipt)
            print(json.dumps({k: receipt[k] for k in ("target_generation", "arm", "status", "elapsed_seconds")}), flush=True)
    unchanged = all(protocol.sha256_file(root / name) == expected
                    for name, expected in manifest["campaign_bindings"].items())
    report = {"cases": receipts, "valid_decisions": sum(r["status"] == "valid_decision" for r in receipts),
              "campaign_unchanged": unchanged, "candidate_or_evaluation_started": False,
              "comparative_effectiveness": "not_established; inspect decisions and run independent replications"}
    route.new_json(out / "pilot_results.json", report)
    return report


def reveal(root: Path, out: Path) -> dict:
    """Outcome files become available only after every prediction has a receipt."""
    manifest = protocol.read_json(out / "manifest.json")
    if not all((out / case["session"] / "receipt.json").is_file() for case in manifest["cases"]):
        raise ValueError("Cannot reveal outcomes before all predictions are frozen")
    outcomes = []
    records = {record["generation"]: record for record in protocol.load_roadmap(root)}
    for target in sorted({case["target_generation"] for case in manifest["cases"]}):
        if target in records:
            record = records[target]
            outcomes.append({"generation": target, "mechanism": record["intent"]["mechanism_key"],
                             "historical_observations": route.project(record.get("mechanism_evidence", {})),
                             "reviewer_interpretation": route.project(record["review"])})
        else:
            outcomes.append({"generation": target, "status": "unavailable_in_roadmap",
                             "reason": "No archived node; deleted intent/candidate are not reconstructed."})
    value = {"revealed_at": protocol.utc_now(), "outcomes": outcomes,
             "scope": "Compare anticipation of historical risks, not unevaluated counterfactual scores."}
    route.new_json(out / "revealed_outcomes.json", value)
    return value


def audit(out: Path) -> dict:
    """Compute descriptive replay metrics without repairing rejected decisions."""
    manifest = protocol.read_json(out / "manifest.json")
    pilot = protocol.read_json(out / "pilot_results.json")
    if not (out / "revealed_outcomes.json").is_file():
        raise ValueError("Reveal historical outcomes before auditing the replay")
    rows = []
    for case in manifest["cases"]:
        session = out / case["session"]
        receipt = protocol.read_json(session / "receipt.json")
        response = protocol.read_json(session / "provider_response.json")
        content = response["choices"][0]["message"].get("content", "")
        parsed = None
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            pass
        selected = None
        if parsed and isinstance(parsed.get("options"), list):
            selected = next((option for option in parsed["options"]
                             if option.get("id") == parsed.get("selected_option_id")), None)
        experiment = parsed.get("experiment", {}) if parsed else {}
        search = protocol.canonical_json({"selected": selected, "experiment": experiment,
                                          "reason": parsed.get("selection_reason") if parsed else None}).lower()
        rows.append({"target_generation": case["target_generation"], "arm": case["arm"],
                     "contract_valid": receipt["status"] == "valid_decision",
                     "decision": parsed.get("decision") if parsed else None,
                     "selected_option_id": parsed.get("selected_option_id") if parsed else None,
                     "premature_implementation": bool(parsed and parsed.get("decision") == "implement"),
                     "matched_control_language": any(term in search for term in
                                                     ("matched", "paired", "control arm", "arm a")),
                     "opportunity_measurement_language": any(term in search for term in
                         ("opportunity", "denominator", "activation", "first satisfiable")),
                     "prompt_tokens": response.get("usage", {}).get("prompt_tokens"),
                     "completion_tokens": response.get("usage", {}).get("completion_tokens"),
                     "finish_reason": response["choices"][0].get("finish_reason")})
    arms = {}
    for arm in ("compact", "flat", "route"):
        group = [row for row in rows if row["arm"] == arm]
        arms[arm] = {"cases": len(group), "contract_valid": sum(row["contract_valid"] for row in group),
                     "implement_decisions": sum(row["premature_implementation"] for row in group),
                     "matched_control_language": sum(row["matched_control_language"] for row in group),
                     "opportunity_measurement_language": sum(row["opportunity_measurement_language"] for row in group),
                     "prompt_tokens": sum(row["prompt_tokens"] or 0 for row in group),
                     "completion_tokens": sum(row["completion_tokens"] or 0 for row in group)}
    current = {name: protocol.sha256_file(Path(manifest["campaign_root"]) / name)
               for name in manifest["campaign_bindings"]}
    report = {"schema": route.SCHEMA, "replay": out.name, "cases": rows, "by_arm": arms,
              "overall": {"cases": len(rows),
                          "contract_valid": sum(row["contract_valid"] for row in rows),
                          "implement_decisions": sum(row["premature_implementation"] for row in rows)},
              "campaign_unchanged": current == manifest["campaign_bindings"]
                                    == {name: protocol.sha256_file(Path(manifest["campaign_root"]) / name)
                                        for name in manifest["campaign_bindings"]},
              "candidate_or_evaluation_started": pilot["candidate_or_evaluation_started"],
              "interpretation_limits": [
                  "String matches describe decision form; they are not a blinded quality judgment.",
                  "One sample per arm and cutoff cannot establish route superiority.",
                  "Retrospective cutoffs were selected after the historical campaign.",
                  "A rejected response remains rejected even when its JSON can be inspected.",
                  "Historical alignment does not estimate counterfactual benchmark gain."]}
    route.new_json(out / "audit.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--targets", type=int, nargs="+", default=[2, 7, 8])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run-once", action="store_true")
    mode.add_argument("--reveal", action="store_true")
    mode.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.prepare_only:
        value = prepare(args.campaign_root.resolve(), args.output.resolve(), args.targets)
    elif args.run_once:
        value = run(args.output.resolve())
    elif args.reveal:
        value = reveal(args.campaign_root.resolve(), args.output.resolve())
    else:
        value = audit(args.output.resolve())
    print(json.dumps(value, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
