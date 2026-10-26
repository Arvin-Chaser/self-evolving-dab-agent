#!/usr/bin/env python3
"""Resume G13 Implementation Meta after independent privacy review failed."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g013_formal_implementation_002"
CHILD = WORK / "candidate_patch"
CONTRACT = WORK / "context/research_contract.json"
REVIEW = WORK / "source_review_001.json"
MANIFEST = CHILD / "implementation_manifest.json"
OUT = BASE / "g013_formal_implementation_meta_003"
CONTRACT_SHA = "5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c"
REVIEW_SHA = "2b9411fde038a72b4afd3b7d11520ee954a4e754457231d9d3479124986fa8ee"
MANIFEST_SHA = "40064be4fe97655224807c47b8123ffea8e4fca7e7a09ec4e33f6e176970e944"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G13 implementation revision 003 already exists")
    if (
        digest(CONTRACT) != CONTRACT_SHA
        or digest(REVIEW) != REVIEW_SHA
        or digest(MANIFEST) != MANIFEST_SHA
    ):
        raise RuntimeError("G13 implementation revision input differs")
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    if review.get("status") != "failed_fixable_privacy_contract_violation":
        raise RuntimeError("G13 independent source review differs")
    OUT.mkdir(exist_ok=False)
    shutil.copy2(MANIFEST, OUT / "implementation_manifest_before_revision.json")
    prompt = (
        "You are continuing the SAME formal G13 Implementation Meta candidate after an independent "
        "source review rejected source-level admission. Work only in candidate_patch/. Do not access "
        "the invalid g013_formal_implementation_001 directory, parent repository, network, provider, "
        "database, benchmark, task content, answers, hints, validators, raw real logs, or credentials. "
        "Do not reopen Research selection or change the frozen contract.\n\n"
        "The independent review found a critical but fixable privacy-contract violation: the current "
        "G13 record_self_observation path still persists the full strict carrier through the inherited "
        "SelfObservationTool._exec into agent_self_observations.jsonl; configurable_call_llm writes the "
        "raw provider tool-call arguments to llm_calls.jsonl; and the upstream response path retains raw "
        "tool-call arguments in messages that can reach later logs/final state. The earlier privacy test "
        "did not cover those producer surfaces. The frozen contract prohibits persistence/export of raw "
        "G13 requirement or observation tokens.\n\n"
        "Repair the implementation without changing the mechanism: preserve transient parsing at the "
        "actual choices[0].message.tool_calls boundary, exact binding, and structural view, but ensure "
        "the carrier and raw G13 tokens are replaced by a fixed content-blind marker before every file "
        "persistence boundary and do not enter agent_self_observations.jsonl, tool_calls.jsonl, "
        "llm_calls.jsonl, final_agent.json, normalized copies, analyzer output, evidence packs, or G13 "
        "sidecars. Do not redact or alter unrelated parent task/tool content beyond the G13 carrier. "
        "The record tool must remain model-authored, never forced, must not initiate another tool call, "
        "and its sanitized acknowledgement must preserve normal loop structure. Disabled mode must remain "
        "unmodified G7 behavior. If this cannot be done at real source-grounded producer boundaries, write "
        "BLOCKED.md rather than claim readiness.\n\n"
        "Add focused synthetic end-to-end tests that construct a provider-shaped record call with unique "
        "requirement/observation sentinels, execute the real installed wrapper/fake upstream persistence "
        "path, materialize every relevant synthetic log/final surface, and assert zero sentinel hits while "
        "the aggregate counters still prove accepted authorship/exact token binding. Also rerun all focused "
        "G13 tests, inherited G4-G7 tests, full local tests, py_compile, and disabled controls. Update "
        "implementation_manifest.json in place with revised hashes, the failed review SHA, exact producer "
        "boundaries fixed, complete commands/results, and honest claim boundaries. Admission remains false; "
        "no provider/runtime/benchmark/formal run is allowed.\n\nIndependent review:\n"
        + json.dumps(review, sort_keys=True, ensure_ascii=True)
        + "\n\nFrozen contract:\n"
        + CONTRACT.read_text(encoding="utf-8")
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab", "--model", "deepseek-flash",
        "exec", "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
        "--skip-git-repo-check", "--json", "--output-last-message", str(OUT / "final_raw.txt"), "-",
    ]
    result = run_logged_command(
        command,
        cwd=WORK,
        prompt=prompt,
        stdout_path=OUT / "events.jsonl",
        stderr_path=OUT / "stderr.log",
        env=meta_environment("deepseek-standalone-dab"),
        timeout=None,
    )
    print(json.dumps({"returncode": result.returncode, "output_dir": str(OUT)}, sort_keys=True))
    if result.returncode:
        raise RuntimeError("G13 Implementation Meta privacy revision failed; attempt retained")


if __name__ == "__main__":
    main()
