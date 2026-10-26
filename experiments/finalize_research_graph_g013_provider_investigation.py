#!/usr/bin/env python3
"""Verify and append the bounded G13 synthetic provider-boundary finding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.research_graph_memory import _artifact, build_research_memory, validate_research_memory


BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g013_provider_boundary_investigation_002"
SCOPED = WORK / "scoped_source"
PREVIOUS = BASE / "research_graph_memory_v14.json"
META = BASE / "g013_research_meta_post_interface_002/final_raw.txt"
FIRST_FINDING = BASE / "g013_interface_investigation_001/scoped_source/BOUNDED_FINDINGS.md"
PRIOR_FAILURE = BASE / "g013_provider_boundary_investigation_001/failure_receipt.json"
BINDING = WORK / "input_binding.json"
RECEIPT = WORK / "provider_boundary_receipt.json"
RAW = ROOT / ".g013_provider_boundary_scratch_002/raw_provider_response.json"
OUT = BASE / "research_graph_memory_v15.json"
EXPECTED = {
    PREVIOUS: "ecdec2bbe36dc83ecb6cd5242cd5344829a03febe5f4570b1e48e480766eed22",
    META: "10ea715d6c05a7c0c5fd1b489ec5933e4a274c6765e473c1a36bce21fc783f39",
    FIRST_FINDING: "745fe68e7d62bd590e89681bee8e47065bdc0430aab6c0a836ebde207b9bc7f6",
    PRIOR_FAILURE: "4501f1c5b97c240824f969d06931e73092ad332cc4efdb05e8afac89a46b6220",
    BINDING: "f7d7c5549036ecb40d11c51cf25a6a880e45d721fb2d05c27808a49968a0c0a3",
    RECEIPT: "1eb66dcabf19bfad3802a54095bf480e0ea546fe6694a65f3015795cca8d0963",
    RAW: "cdd35184ffbc0581501c2f0911d0f193516916994e52cfaf38aefbae4bd0c033",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def write_same_or_new(path: Path, value: object) -> None:
    content = json_text(value)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Refusing to overwrite differing artifact: {path}")
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def load_probe():
    path = SCOPED / "probe.py"
    spec = importlib.util.spec_from_file_location("g013_provider_probe_finalize", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Provider probe cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    sys.path.insert(0, str(SCOPED))
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if any(not path.is_file() or digest(path) != expected for path, expected in EXPECTED.items()):
        raise RuntimeError("G13 provider-boundary verification input differs")
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    validate_research_memory(previous, root=ROOT)
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    prior_failure = json.loads(PRIOR_FAILURE.read_text(encoding="utf-8"))
    if binding.get("maximum_provider_calls") != 1 or binding.get("cumulative_provider_request_cap") != 2:
        raise RuntimeError("Provider call cap differs")
    if prior_failure.get("provider_call_count") != 1 or prior_failure.get("model_response_received") is not False:
        raise RuntimeError("Prior failed attempt differs")
    required_true = (
        "production_tool_schema_accepted",
        "actual_response_boundary_inspected",
        "carrier_accepted",
        "opaque_tokens_exact",
        "all_fault_cases_explicit_unknown",
        "enabled_disabled_inert_outside_carrier",
        "aggregate_only",
    )
    if receipt.get("status") != "passed" or any(receipt.get(key) is not True for key in required_true):
        raise RuntimeError("Provider-boundary receipt did not pass")
    if receipt.get("provider_call_count") != 1 or receipt.get("mechanism_initiated_tool_call_count") != 0:
        raise RuntimeError("Provider-boundary call count differs")
    if any(receipt.get(key) is not False for key in (
        "forced_answer", "scoring_mutation", "wall_timeout_extension", "benchmark_accessed",
        "database_accessed", "formal_experiment_created", "candidate_parent_selected",
        "raw_provider_response_exported", "semantic_coverage_claim",
    )):
        raise RuntimeError("Provider-boundary claim boundary differs")

    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_probe.py", "--disable-warnings"],
        cwd=SCOPED,
        capture_output=True,
        text=True,
        check=False,
    )
    if test.returncode or "12 passed" not in test.stdout:
        raise RuntimeError(f"Independent replay failed: {test.stdout}\n{test.stderr}")

    probe = load_probe()
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    req, obs = probe.synthetic_tokens(digest(BINDING))
    message = raw["choices"][0]["message"]
    replay = probe.inspect_boundary(
        message,
        enabled=True,
        expected_requirement=req,
        expected_observation=obs,
    )
    if replay.get("accepted") is not True or replay.get("opaque_tokens_exact") is not True:
        raise RuntimeError("Independent raw response replay failed")
    raw_text = RAW.read_text(encoding="utf-8")
    credential_pattern = re.compile(
        r"(?i)(?:api[_-]?key|authorization|cookie|password|private[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{16,}"
    )
    privacy = {
        "credential_value_hits": len(credential_pattern.findall(raw_text)),
        "sql_statement_hits": len(re.findall(r"(?i)\b(?:select|insert|update|delete)\b", raw_text)),
        "benchmark_path_hits": len(re.findall(r"(?i)(?:DataAgentBench|benchmark[s]?[/\\])", raw_text)),
        "task_identifier_hits": len(re.findall(r"(?i)(?:task[_-]?id|query[_-]?id)\s*[:=]", raw_text)),
    }
    if any(privacy.values()):
        raise RuntimeError("Independent raw response privacy scan failed")

    findings = {
        "schema_version": "g013_provider_boundary_findings_v1",
        "status": "verified_synthetic_provider_boundary_formal_endpoints_untested",
        "evidence_class": "interface_research_not_benchmark_evidence",
        "selected_target_id": "research_target:g013:002",
        "mechanism_id": "mech_requirement_observation_coverage",
        "verified": [
            "the source-generated production self-observation tool schema was accepted by DeepSeek",
            "one synthetic response reached the source-grounded choices[0].message.tool_calls boundary",
            "the real provider copied both opaque tokens exactly into one strict carrier",
            "missing, malformed, truncated, and provider-rejected fixtures all remained explicit unknown",
            "enabled and disabled paths were inert for tool dispatch, answer forcing, scoring, and wall time",
            "the research export stayed aggregate-only and the isolated raw synthetic response passed privacy scans",
        ],
        "unknown": [
            "formal real-model row authorship rate across benchmark tasks",
            "formal real-model action compliance after a structural next-action view",
            "semantic requirement completeness, relevance, support, correctness, or task truth",
            "task-bearing production no-leak behavior and benchmark benefit",
            "production runtime attachment and code parent selection",
        ],
        "contradicted": [],
        "corrected_interface_fact": (
            "DeepSeek thinking mode rejects forced function tool_choice; the production-compatible automatic "
            "tool-selection request was accepted in the preserved second attempt."
        ),
        "provider_request_count_total": 2,
        "accepted_provider_round_trip_count": 1,
        "formal_endpoint_status": {
            "real_model_authorship": "untested",
            "real_model_action_compliance": "untested",
        },
        "claim_boundary": {
            "formal_candidate": False,
            "formal_experiment": False,
            "benchmark_evidence": False,
            "semantic_coverage_proven": False,
            "causal_benefit_proven": False,
        },
    }
    findings_path = WORK / "interface_findings.json"
    write_same_or_new(findings_path, findings)
    manifest = {
        "schema_version": "g013_provider_boundary_manifest_v1",
        "status": findings["status"],
        "evidence_class": findings["evidence_class"],
        "input_binding_sha256": digest(BINDING),
        "provider_boundary_receipt_sha256": digest(RECEIPT),
        "prior_failed_attempt_receipt_sha256": digest(PRIOR_FAILURE),
        "isolated_raw_response_sha256": digest(RAW),
        "isolated_raw_response_exported": False,
        "tests": "12 passed independently",
        "provider_request_count_total": 2,
        "accepted_provider_round_trip_count": 1,
        "privacy_scan": privacy,
        "source_hashes": binding["source_binding"],
        "formal_experiment_created": False,
        "formal_candidate_created": False,
        "benchmark_run": False,
        "database_accessed": False,
        "score_claim": False,
    }
    manifest_path = WORK / "investigation_manifest.json"
    write_same_or_new(manifest_path, manifest)
    verification = {
        "schema_version": "g013_provider_boundary_independent_verification_v1",
        "status": "passed",
        "evidence_class": findings["evidence_class"],
        "input_binding_sha256": digest(BINDING),
        "receipt_sha256": digest(RECEIPT),
        "findings_sha256": digest(findings_path),
        "manifest_sha256": digest(manifest_path),
        "isolated_raw_response_sha256_match": digest(RAW) == receipt["raw_provider_response_sha256"],
        "independent_response_replay": "accepted_exact_opaque_tokens",
        "independent_tests": "12 passed",
        "privacy_scan": privacy,
        "research_export_contains_raw_provider_response": False,
        "formal_endpoint_status": findings["formal_endpoint_status"],
    }
    verification_path = WORK / "independent_verification.json"
    write_same_or_new(verification_path, verification)

    incubation = previous["research_incubation_layer"]
    known = {node["id"] for node in incubation["nodes"]}
    investigation_id = "interface_investigation:g013:002"
    finding_id = "interface_finding:g013:002"
    if {investigation_id, finding_id} & known:
        raise RuntimeError("G13 provider-boundary incubation IDs already exist")
    investigation_node = {
        "id": investigation_id,
        "kind": "interface_investigation",
        "evidence_class": findings["evidence_class"],
        "scope": "synthetic_real_provider_production_response_boundary",
        "performed_by": "codex_bounded_provider_boundary_investigation",
        "status": "completed_independently_replayed",
        "test_summary": "12_passed_independently",
        "provider_request_count_total": 2,
        "accepted_provider_round_trip_count": 1,
        "artifacts": [_artifact(BINDING, ROOT), _artifact(RECEIPT, ROOT), _artifact(PRIOR_FAILURE, ROOT)],
    }
    finding_node = {
        "id": finding_id,
        "kind": "interface_finding",
        "evidence_class": findings["evidence_class"],
        "status": findings["status"],
        "statement": (
            "A source-grounded production tool schema and real DeepSeek response boundary accepted one "
            "synthetic opaque carrier with exact token copying and fail-closed structural faults; formal "
            "authorship, action compliance, semantic coverage, and task-bearing behavior remain untested."
        ),
        "verified": findings["verified"],
        "unknown": findings["unknown"],
        "contradicted": findings["contradicted"],
        "claim_boundary": findings["claim_boundary"],
        "artifacts": [
            _artifact(findings_path, ROOT),
            _artifact(manifest_path, ROOT),
            _artifact(verification_path, ROOT),
        ],
    }
    nodes = [*incubation["nodes"], investigation_node, finding_node]
    edges = [
        *incubation["edges"],
        {"source": investigation_id, "relation": "investigates", "target": "research_target:g013:002"},
        {"source": finding_id, "relation": "derived_from", "target": investigation_id},
    ]
    refs = previous["formal_evolution_layer"]["generation_refs"]
    paths = {row["generation"]: ROOT / row["graph"]["path"] for row in refs}
    hashes = {row["generation"]: row["graph"]["sha256"] for row in refs}
    memory = build_research_memory(
        root=ROOT,
        formal_graph_paths=paths,
        formal_graph_hashes=hashes,
        incubation_nodes=nodes,
        incubation_edges=edges,
        cross_layer_edges=previous["cross_layer_edges"],
    )
    validate_research_memory(memory, root=ROOT)
    write_same_or_new(OUT, memory)
    print(json.dumps({
        "status": verification["status"],
        "provider_request_count_total": 2,
        "accepted_provider_round_trip_count": 1,
        "findings_sha256": digest(findings_path),
        "manifest_sha256": digest(manifest_path),
        "verification_sha256": digest(verification_path),
        "memory_sha256": digest(OUT),
        "next": "post_interface_research_meta",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
