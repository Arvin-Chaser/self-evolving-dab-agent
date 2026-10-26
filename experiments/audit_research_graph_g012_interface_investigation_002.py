#!/usr/bin/env python3
"""Verify G12's second exploratory interface finding without task data."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g012_interface_investigation_002"
SCOPED = WORK / "scoped_source"
MANIFEST = SCOPED / "exploratory_implementation_manifest.json"
OUTPUT = WORK / "independent_verification.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    binding = json.loads((WORK / "input_binding.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (manifest.get("selected_target_id") != "research_target:g012:002"
            or manifest.get("status") != "feasible_bounded"
            or manifest.get("not_formal_candidate") is not True):
        raise RuntimeError("G12 second exploratory claim differs")
    for key in ("formal_experiment_created", "benchmark_run", "evidence_extractor_created",
                "launch_claim", "score_claim", "provider_call", "network_request"):
        if manifest.get(key) is not False:
            raise RuntimeError(f"G12 exploratory boundary differs: {key}")
    if manifest["reference_hashes"] != binding["scoped_reference_sha256"]:
        raise RuntimeError("G12 scoped reference manifest differs")
    if any(digest(SCOPED / "reference" / path) != sha
           for path, sha in binding["scoped_reference_sha256"].items()):
        raise RuntimeError("G12 scoped reference hash differs")
    prior = manifest["input_binding"]["prior_artifacts_present_and_verified"]
    if any(digest(SCOPED / path) != sha for path, sha in prior.items()):
        raise RuntimeError("G12 prior scoped artifact hash differs")
    if any(digest(BASE / path) != sha for path, sha in binding["input_sha256"].items()):
        raise RuntimeError("G12 frozen input hash differs")
    outputs = manifest["output_hashes"]
    if any(digest(SCOPED / path) != sha for path, sha in outputs.items()):
        raise RuntimeError("G12 second output hash differs")
    observed = {
        path.relative_to(SCOPED).as_posix()
        for path in SCOPED.rglob("*")
        if path.is_file() and not any(part in {"__pycache__", ".pytest_cache"} for part in path.parts)
    }
    allowed = {"exploratory_implementation_manifest.json", *outputs}
    allowed.update("reference/" + path for path in binding["scoped_reference_sha256"])
    allowed.update(prior)
    if observed != allowed:
        raise RuntimeError(f"Unexpected second investigation file set: {sorted(observed ^ allowed)}")
    test = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_g012_action_interface.py", "--disable-warnings"],
        cwd=SCOPED, capture_output=True, text=True, check=False,
    )
    if test.returncode or "41 passed" not in test.stdout:
        raise RuntimeError("G12 independent action-interface tests failed")
    sensitivity = manifest["no_task_tests"]["sensitivity_case"]
    if (sensitivity.get("classification") != "conditional_interface_demonstration_only_not_real_model_compliance"
            or sensitivity.get("structured_steps_differ_across_states") is not True
            or sensitivity.get("generic_steps_equal_across_states") is not True):
        raise RuntimeError("G12 sensitivity claim differs")
    report = {
        "schema_version": "g012_interface_002_independent_verification_v1",
        "status": "verified_conditional_action_interface_real_model_unknown",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": "research_target:g012:002",
        "manifest_sha256": digest(MANIFEST),
        "findings_sha256": digest(SCOPED / "BOUNDED_FINDINGS.md"),
        "input_binding_sha256": digest(WORK / "input_binding.json"),
        "reference_hashes_match": True,
        "prior_hashes_match": True,
        "output_hashes_match": True,
        "scoped_file_set_match": True,
        "independent_no_task_tests": "41 passed",
        "established": [
            "The synthetic structured view exposes selected structural action, status, and opaque target at the reviewed call_llm message boundary.",
            "A same-state generic guidance control does not carry those selected fields.",
            "A programmed synthetic policy distinguishes absent and unknown states through the structured view; this is conditional interface sensitivity only.",
            "Freshness and instrumentation categories remain structural and do not promote semantic support or omitted-obligation claims.",
        ],
        "open_gaps": [
            "A programmed synthetic policy is not evidence that a real model will author records or select a different next action.",
            "No provider call, live carrier acceptance, response-boundary acceptance, or real-model compliance check was performed.",
            "Obligations remain model-authored; a structural inventory cannot detect omitted semantic obligations.",
            "The existing raw-context log surface still needs separate no-leak admission review.",
            "The prototype's latest_attempt directive source and target-token mapping are not formal runtime contracts.",
        ],
        "claim_boundary": {
            "formal_candidate": False,
            "benchmark_evidence": False,
            "semantic_support_proven": False,
            "real_model_gap_directed_action_proven": False,
            "strict_benefit_proven": False,
        },
    }
    content = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("G12 second independent verification already differs")
    OUTPUT.write_text(content, encoding="utf-8")
    print(json.dumps({"status": report["status"], "sha256": digest(OUTPUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
