#!/usr/bin/env python3
"""Finalize and append the bounded G13 no-task interface investigation."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from experiments.research_graph_memory import (
    _artifact,
    build_research_memory,
    validate_research_memory,
)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g013_interface_investigation_001"
SCOPED = WORK / "scoped_source"
RESEARCH = BASE / "g013_research_meta_solution_loop_004/final_raw.txt"
PREVIOUS = BASE / "research_graph_memory_v12.json"
OUT = BASE / "research_graph_memory_v13.json"
RESEARCH_SHA = "6609b286be192258ab0cb3ccace712139896cd80534be74d9bc71a1576bed071"
PREVIOUS_SHA = "80eda89e3664128d092d7374cbb2a0f74e040c3d37bbbd77a531f31b158de544"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_same_or_new(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.write_text(content, encoding="utf-8")


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def main() -> None:
    if digest(RESEARCH) != RESEARCH_SHA or digest(PREVIOUS) != PREVIOUS_SHA:
        raise RuntimeError("G13 investigation input binding differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    target = research.get("research_target")
    if not isinstance(target, dict) or target.get("state") != "interface_investigation":
        raise RuntimeError("G13 target state differs")
    if target.get("mechanism_id") != "mech_requirement_observation_coverage":
        raise RuntimeError("G13 mechanism differs")
    if research["mechanism_ranking"][0]["mechanism_id"] != target["mechanism_id"]:
        raise RuntimeError("G13 target is not rank one")
    selected = [
        row for row in research["mechanism_candidates"]
        if row["mechanism_id"] == target["mechanism_id"]
    ]
    if len(selected) != 1:
        raise RuntimeError("G13 selected candidate differs")

    source_files = {
        "prototype/__init__.py": SCOPED / "prototype/__init__.py",
        "prototype/requirement_coverage.py": SCOPED / "prototype/requirement_coverage.py",
        "prototype/run_no_task_fixture.py": SCOPED / "prototype/run_no_task_fixture.py",
        "prototype/no_task_fixture_output.json": SCOPED / "prototype/no_task_fixture_output.json",
        "tests/test_g013_requirement_coverage.py": SCOPED / "tests/test_g013_requirement_coverage.py",
    }
    if not all(path.is_file() for path in source_files.values()):
        raise RuntimeError("G13 scoped source is incomplete")

    binding = {
        "schema_version": "g013_interface_investigation_input_v1",
        "status": "exploratory_not_formal_candidate",
        "selected_target_id": "research_target:g013:001",
        "research_meta_output_sha256": RESEARCH_SHA,
        "research_memory_sha256": PREVIOUS_SHA,
        "mechanism_id": target["mechanism_id"],
        "scope": "synthetic_no_task_structural_interface_only",
        "excluded": [
            "benchmark tasks", "answers", "hints", "validators", "database access",
            "raw task messages", "tool arguments", "tool results", "provider transcript",
            "credentials", "formal experiment", "code parent selection", "benchmark launch",
            "invalid manual g013 implementation",
        ],
    }
    binding_path = WORK / "input_binding.json"
    write_same_or_new(binding_path, json_text(binding))

    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_g013_requirement_coverage.py", "--disable-warnings"],
        cwd=SCOPED,
        capture_output=True,
        text=True,
        check=False,
    )
    if test.returncode or "49 passed" not in test.stdout:
        raise RuntimeError(f"G13 no-task replay failed: {test.stdout}\n{test.stderr}")

    findings = "# G13 bounded interface findings\n\n"
    findings += "Status: bounded structural interface verified; real-model behavior unknown.\n\n"
    findings += "## Verified\n\n"
    findings += "- A strict bounded JSON carrier accepts opaque requirement and visible-observation tokens without storing requirement text.\n"
    findings += "- Deterministic transitions cover uncovered, observed, ambiguous, failed, unavailable, unknown, current, stale, duplicate, and later-observation cases.\n"
    findings += "- Missing, truncated, or malformed instrumentation always preserves unknown and is never reclassified as genuine evidence absence.\n"
    findings += "- A structural model-facing view changes across unresolved, stale, resolved, and instrumentation-loss states and exposes only action, opaque target, state, freshness, and reason.\n"
    findings += "- Disabled mode, the one-action cap, and the 180-second deadline guard are inert; the prototype does not dispatch tools, force an answer, score, or extend wall time.\n"
    findings += "- Structural summaries are aggregate-only and exclude requirement IDs, observation IDs, semantic support, correctness, and task content.\n\n"
    findings += "## Unknown\n\n"
    findings += "- No provider call was made. Real-model row authorship, opaque-reference copying, carrier acceptance at the production response boundary, and bounded action compliance remain untested.\n"
    findings += "- The prototype is not attached to a production runtime carrier, and no code parent has been selected.\n"
    findings += "- Requirement rows are model-authored; omitted semantic requirements and semantic coverage cannot be inferred.\n"
    findings += "- Programmed state sensitivity is conditional interface evidence, not evidence of real-model behavior or benchmark benefit.\n"
    findings += "- Existing raw-context logs require a separate admission audit before any task-bearing use.\n\n"
    findings += "## Contradicted\n\n"
    findings += "- None within this bounded investigation.\n\n"
    findings += "Next workflow step: return this finding to Research Meta. Do not enter Implementation Meta directly.\n"
    findings_path = SCOPED / "BOUNDED_FINDINGS.md"
    write_same_or_new(findings_path, findings)

    outputs = {name: digest(path) for name, path in source_files.items()}
    outputs["BOUNDED_FINDINGS.md"] = digest(findings_path)
    manifest = {
        "schema_version": "g013_interface_investigation_manifest_v1",
        "status": "bounded_structural_interface_verified_real_model_unknown",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": "research_target:g013:001",
        "mechanism_id": target["mechanism_id"],
        "input_binding_sha256": digest(binding_path),
        "test_summary": "49 passed independently",
        "verified": [
            "strict opaque carrier and row validation",
            "coverage, freshness, revision, duplicate, and fault transitions",
            "instrumentation loss separated from evidence absence",
            "conditional structural next-action view",
            "disabled, action-cap, and deadline-guard inertness",
            "aggregate-only structural export boundary",
        ],
        "unknown": [
            "real-model authorship and opaque-reference copying",
            "provider and production response-boundary acceptance",
            "real-model action compliance",
            "production runtime carrier and code parent",
            "omitted semantic requirements and semantic coverage",
            "raw-context log admission",
        ],
        "contradicted": [],
        "output_hashes": outputs,
        "formal_experiment_created": False,
        "formal_candidate_created": False,
        "benchmark_run": False,
        "database_accessed": False,
        "provider_called": False,
        "launch_claim": False,
        "score_claim": False,
        "not_formal_candidate": True,
    }
    manifest_path = SCOPED / "exploratory_implementation_manifest.json"
    write_same_or_new(manifest_path, json_text(manifest))

    scanned_paths = [*source_files.values(), findings_path, binding_path, manifest_path]
    credential_pattern = re.compile(
        r"(?i)(?:api[_-]?key|authorization|cookie|password|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{16,}"
    )
    credential_hits = sum(
        len(credential_pattern.findall(path.read_text(encoding="utf-8"))) for path in scanned_paths
    )
    if credential_hits:
        raise RuntimeError("Sensitive-value scan failed")
    verification = {
        "schema_version": "g013_interface_independent_verification_v1",
        "status": "verified_bounded_structural_interface_real_model_unknown",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": "research_target:g013:001",
        "input_binding_sha256": digest(binding_path),
        "implementation_manifest_sha256": digest(manifest_path),
        "findings_sha256": digest(findings_path),
        "output_hashes_match": all(digest(SCOPED / path) == value for path, value in outputs.items()),
        "independent_no_task_tests": "49 passed",
        "sensitive_value_hits": credential_hits,
        "provider_called": False,
        "real_model_authorship_status": "unknown",
        "real_model_compliance_status": "unknown",
        "claim_boundary": {
            "formal_candidate": False,
            "benchmark_evidence": False,
            "semantic_coverage_proven": False,
            "real_model_behavior_proven": False,
            "strict_benefit_proven": False,
        },
    }
    verification_path = WORK / "independent_verification.json"
    write_same_or_new(verification_path, json_text(verification))

    incubation = previous["research_incubation_layer"]
    known_ids = {node["id"] for node in incubation["nodes"]}
    target_id = "research_target:g013:001"
    investigation_id = "interface_investigation:g013:001"
    finding_id = "interface_finding:g013:001"
    if {target_id, investigation_id, finding_id} & known_ids:
        raise RuntimeError("G13 incubation IDs already exist")
    target_node = {
        "id": target_id,
        "kind": "research_target",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "state": "interface_investigation",
        "mechanism_id": target["mechanism_id"],
        "statement": target["problem"],
        "hypothesis": target["hypothesis"],
        "status": "selected_for_no_task_interface_investigation",
        "primary_lens": target["primary_lens"],
        "related_lenses": target["related_lenses"],
        "de_risk_questions": target["de_risk_questions"],
        "no_task_checks": target["no_task_checks"],
        "interface_gaps": target["interface_gaps"],
        "limitations": research.get("limitations", []),
        "artifacts": [_artifact(RESEARCH, ROOT)],
    }
    investigation_node = {
        "id": investigation_id,
        "kind": "interface_investigation",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "scope": "synthetic_no_task_requirement_coverage_interface",
        "performed_by": "codex_bounded_interface_investigation",
        "status": "completed_independently_replayed",
        "test_summary": "49_passed_independently",
        "artifacts": [
            _artifact(binding_path, ROOT),
            _artifact(manifest_path, ROOT),
            _artifact(verification_path, ROOT),
        ],
    }
    finding_node = {
        "id": finding_id,
        "kind": "interface_finding",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "status": "bounded_structural_interface_verified_real_model_unknown",
        "statement": (
            "An opaque structural requirement-coverage carrier, deterministic fault-aware state "
            "transitions, and bounded action view work in no-task fixtures; provider acceptance, "
            "real-model authorship, and real-model action compliance remain unknown."
        ),
        "verified": manifest["verified"],
        "unknown": manifest["unknown"],
        "contradicted": manifest["contradicted"],
        "claim_boundary": verification["claim_boundary"],
        "artifacts": [
            _artifact(manifest_path, ROOT),
            _artifact(findings_path, ROOT),
            _artifact(verification_path, ROOT),
        ],
    }
    edges = [*incubation["edges"]]
    edges.extend(
        {"source": target_id, "relation": "informed_by", "target": ref}
        for ref in selected[0]["incubation_refs"]
    )
    edges.extend([
        {"source": investigation_id, "relation": "investigates", "target": target_id},
        {"source": finding_id, "relation": "derived_from", "target": investigation_id},
    ])
    cross_edges = [*previous["cross_layer_edges"]]
    generations = sorted({int(fact_id[1:4]) for fact_id in selected[0]["fact_ids"]})
    cross_edges.extend(
        {"source": target_id, "relation": "motivated_by", "target": f"evidence:g{generation:03d}"}
        for generation in generations
    )
    refs = previous["formal_evolution_layer"]["generation_refs"]
    graph_paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    graph_hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=graph_paths,
        formal_graph_hashes=graph_hashes,
        incubation_nodes=[*incubation["nodes"], target_node, investigation_node, finding_node],
        incubation_edges=edges,
        cross_layer_edges=cross_edges,
    )
    validate_research_memory(memory, root=ROOT)
    write_same_or_new(OUT, json_text(memory))
    print(json.dumps({
        "status": verification["status"],
        "tests": verification["independent_no_task_tests"],
        "manifest_sha256": digest(manifest_path),
        "verification_sha256": digest(verification_path),
        "memory_sha256": digest(OUT),
        "memory_path": str(OUT),
        "next": "post_interface_research_meta",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
