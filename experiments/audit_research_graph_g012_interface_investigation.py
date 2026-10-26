#!/usr/bin/env python3
"""Independently verify G12's no-task interface investigation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g012_interface_investigation_001"
SCOPED = WORK / "scoped_source"
MANIFEST = SCOPED / "exploratory_implementation_manifest.json"
OUTPUT = WORK / "independent_verification.json"
PARENT = BASE / "g011_solution_loop_candidate_003/repo"
PARENT_SHA = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    binding = json.loads((WORK / "input_binding.json").read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if source_tree_hash(PARENT) != PARENT_SHA:
        raise RuntimeError("Frozen G11 parent tree differs")
    if manifest.get("status") != "feasible_bounded" or manifest.get("not_formal_candidate") is not True:
        raise RuntimeError("Exploratory manifest claim differs")
    if any(manifest.get(key) is not False for key in (
        "formal_experiment_created", "benchmark_run", "evidence_extractor_created",
        "launch_claim", "score_claim",
    )):
        raise RuntimeError("Exploratory/formal boundary differs")
    if any(manifest["input_binding"][key] != binding[key] for key in (
        "parent_tree_sha256", "research_sha256", "research_memory_sha256",
        "capability_sha256", "g011_evidence_sha256", "prior_implementation_sha256",
    )):
        raise RuntimeError("Input binding differs")
    references = binding["scoped_reference_sha256"]
    if manifest["reference_hashes"] != references:
        raise RuntimeError("Reference manifest differs")
    if any(sha256(SCOPED / "reference" / path) != digest for path, digest in references.items()):
        raise RuntimeError("Scoped reference hash differs")
    outputs = manifest["output_hashes"]
    if any(sha256(SCOPED / path) != digest for path, digest in outputs.items()):
        raise RuntimeError("Output hash differs")
    observed = {
        path.relative_to(SCOPED).as_posix()
        for path in SCOPED.rglob("*")
        if path.is_file() and not any(part in {"__pycache__", ".pytest_cache"} for part in path.parts)
    }
    allowed = {"exploratory_implementation_manifest.json", *outputs}
    allowed.update("reference/" + path for path in references)
    if observed != allowed:
        raise RuntimeError(f"Unexpected scoped file set: {sorted(observed ^ allowed)}")
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_g012_uncertainty_interface.py", "--disable-warnings"],
        cwd=SCOPED, capture_output=True, text=True, check=False,
    )
    if test.returncode or "26 passed" not in test.stdout:
        raise RuntimeError("Independent no-task test replay failed")
    report = {
        "schema_version": "g012_interface_independent_verification_v1",
        "status": "artifacts_verified_bounded_substrate_action_gap_open",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": "research_target:g012:001",
        "input_binding_sha256": sha256(WORK / "input_binding.json"),
        "implementation_manifest_sha256": sha256(MANIFEST),
        "findings_sha256": sha256(SCOPED / "BOUNDED_FINDINGS.md"),
        "reference_hashes_match": True,
        "output_hashes_match": True,
        "scoped_file_set_match": True,
        "independent_no_task_tests": "26 passed",
        "established": [
            "A model-facing freeform record carrier and fixed authoring policy exist in the frozen source.",
            "The reviewed ledger distinguishes structural provenance and uncertainty states without semantic promotion.",
            "A synthetic unresolved state changes an internal directive and whether fixed guidance is present.",
            "The fixture preserves tool dispatch and result behavior in its status-sensitivity comparison.",
        ],
        "open_gaps": [
            "The fixed model-facing guidance is generic and does not expose the selected action, target, or status.",
            "The synthetic fixture does not show a model selecting a different next action in response to a gap.",
            "Real provider acceptance, model-authored record adoption, and model compliance remain untested.",
            "Obligations are model-authored; omitted obligations and semantic support are not independently detected.",
            "The existing raw-context log surface requires separate no-leak review before formal admission.",
        ],
        "claim_boundary": {
            "formal_candidate": False,
            "benchmark_evidence": False,
            "semantic_support_proven": False,
            "gap_directed_model_action_proven": False,
            "strict_benefit_proven": False,
        },
    }
    content = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") != content:
        raise RuntimeError("Independent verification already exists with different content")
    OUTPUT.write_text(content, encoding="utf-8")
    print(json.dumps({"status": report["status"], "sha256": sha256(OUTPUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
