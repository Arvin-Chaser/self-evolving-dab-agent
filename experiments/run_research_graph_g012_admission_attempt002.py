#!/usr/bin/env python3
"""Run the bounded G12 attempt002 controls and live provider probe remotely."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.intent_candidate_workspace import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
SOURCE = BASE / "g012_admission_001"
OUTPUT = BASE / "g012_admission_005"
PROBE = ROOT / "experiments/probe_research_graph_g012_admission_attempt002.py"
REMOTE_PROBE_NAME = "probe_research_graph_g012_admission_attempt005.py"
CONTRACT = BASE / "g012_formal_implementation_002/context/research_contract.json"
SSH = [
    "ssh",
    "-i",
    "C:/Users/34934/.ssh/codex_ct104",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
    "root@100.83.10.33",
]
SCP = [
    "scp",
    "-i",
    "C:/Users/34934/.ssh/codex_ct104",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=15",
]
PYTHON = "/srv/text2sql/.venv/bin/python"
UPSTREAM = "/srv/text2sql/external/DataAgentBench_official"
PARENT_HASH = "7a08559bad85ac3de94bc897759cc0f41aeb3260816a3e0ff21989687fae24ac"
CHILD_HASH = "47dbf42636bbaa234c5f58256a37821a2ac891d29b34fcce13fe350207e7e344"
CONTRACT_HASH = "67086825a82f1bd3bcc34297c85410ced236c965085c2ec94723bfc567c0b190"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def checked(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError("Bounded remote command failed")
    return result


def remote_python(code: str, *, timeout: int = 60) -> Any:
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    command = f"{PYTHON} -B -c \"exec(__import__('base64').b64decode('{encoded}'))\""
    result = checked(SSH + [command], timeout=timeout)
    return json.loads(result.stdout)


def remote_read_text(path: str) -> str:
    if not path.startswith(
        "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g012_admission_"
    ):
        raise RuntimeError("Remote read escaped the synthetic scratch boundary")
    if Path(path).name not in {
        "probe_result.json",
        "g012_uncertainty_gap_action.jsonl",
        "g012_uncertainty_gap_action_summary.json",
    }:
        raise RuntimeError("Remote read is not an allow-listed structural artifact")
    result = checked(SSH + [f"/bin/cat {path}"], timeout=30)
    return result.stdout


def remote_file_exists(path: str) -> bool:
    if not path.startswith(
        "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g012_admission_"
    ):
        raise RuntimeError("Remote existence check escaped the synthetic scratch boundary")
    result = subprocess.run(SSH + [f"test -f {path}"], capture_output=True, text=True, timeout=30)
    return result.returncode == 0


def run_probe(remote: str, label: str, mode: str, credential: str | None) -> dict[str, Any]:
    output = f"{remote}/{label}_{mode}"
    command = (
        f"cd {remote} && {PYTHON} -B {REMOTE_PROBE_NAME} "
        f"--repo {remote}/repo --upstream {UPSTREAM} --output {output} --mode {mode}"
    )
    completed = subprocess.run(
        SSH + [command],
        input=(credential + "\n") if credential is not None else None,
        capture_output=True,
        text=True,
        timeout=480,
    )
    lines = completed.stdout.strip().splitlines()
    try:
        result = json.loads(lines[-1]) if lines else {"status": "no_probe_output"}
    except ValueError:
        result = {"status": "invalid_probe_output"}
    if completed.returncode:
        return {
            "exit_code": completed.returncode,
            "result": result,
        }
    persisted = json.loads(remote_read_text(f"{output}/probe_result.json"))
    if persisted != result:
        raise RuntimeError("Probe stdout and persisted receipt differ")
    return {"exit_code": 0, "result": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--label", default="attempt005")
    args = parser.parse_args()
    remote = args.remote_root
    if not remote.startswith(
        "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g012_admission_"
    ) or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/" for character in remote):
        raise RuntimeError("Remote scratch directory boundary differs")
    if not args.label.isalnum():
        raise RuntimeError("Label must be alphanumeric")
    if OUTPUT.exists():
        raise RuntimeError("Refusing to overwrite g012_admission_005")

    parent_hash = source_tree_hash(SOURCE / "parent_control")
    child_hash = source_tree_hash(SOURCE / "repo")
    contract_hash = sha(CONTRACT)
    if (parent_hash, child_hash, contract_hash) != (PARENT_HASH, CHILD_HASH, CONTRACT_HASH):
        raise RuntimeError("Frozen source or research contract hash differs")
    assembly = json.loads((SOURCE / "assembly.json").read_text(encoding="utf-8"))
    if assembly.get("parent_tree_sha256") != PARENT_HASH or assembly.get("candidate_tree_sha256") != CHILD_HASH:
        raise RuntimeError("Assembly binding differs")

    remote_probe = f"{remote}/{REMOTE_PROBE_NAME}"
    checked(SSH + [f"test -d {remote}/repo && test -f {remote}/child_files.json && test ! -e {remote_probe}"], timeout=30)
    checked(SCP + [str(PROBE), f"root@100.83.10.33:{remote_probe}"], timeout=60)
    verification_code = f"""
import hashlib,json
from pathlib import Path
root=Path({remote!r})
rows=json.loads((root/'child_files.json').read_text())
bad=[row['path'] for row in rows if hashlib.sha256((root/'repo'/row['path']).read_bytes()).hexdigest()!=row['sha256']]
probe=root/{REMOTE_PROBE_NAME!r}
print(json.dumps({{'status':'verified_hash_bound_synthetic_scratch','file_count':len(rows),'mismatch_count':len(bad),'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest()}}))
"""
    remote_verification = remote_python(verification_code)
    if remote_verification.get("mismatch_count") != 0 or remote_verification.get("probe_sha256") != sha(PROBE):
        raise RuntimeError("Remote frozen source or probe verification failed")

    OUTPUT.mkdir(parents=True)
    baseline = {
        "schema_version": "g012_admission_attempt002_baseline_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_tree_sha256": parent_hash,
        "child_tree_sha256": child_hash,
        "research_contract_sha256": contract_hash,
        "assembly_sha256": sha(SOURCE / "assembly.json"),
        "source_admission_sha256": sha(SOURCE / "source_admission.json"),
        "prior_provider_receipt_sha256": sha(SOURCE / "remote_live001_provider.json"),
        "probe_sha256": sha(PROBE),
        "driver_sha256": sha(Path(__file__)),
        "remote_source_verification": remote_verification,
        "benchmark_accessed": False,
        "database_accessed": False,
        "formal_evaluation_started": False,
    }
    write_new(OUTPUT / "baseline_verification.json", baseline)

    results: dict[str, Any] = {}
    for mode in ("enabled", "disabled"):
        receipt = run_probe(remote, args.label, mode, None)
        results[mode] = receipt
        write_new(OUTPUT / f"control_{mode}_probe_result.json", receipt)
        if receipt["exit_code"]:
            raise RuntimeError("Programmed control probe failed")
    enabled = results["enabled"]["result"]
    disabled = results["disabled"]["result"]
    control = {
        "schema_version": "g012_attempt002_enabled_disabled_control_v1",
        "dispatch_count_equal": enabled.get("dispatch_count") == disabled.get("dispatch_count"),
        "dispatch_arguments_and_results_equal": enabled.get("dispatch_payload_sha256") == disabled.get("dispatch_payload_sha256"),
        "termination_equal": enabled.get("termination") == disabled.get("termination"),
        "final_result_equal": enabled.get("final_result_sha256") == disabled.get("final_result_sha256"),
        "llm_call_count_equal": enabled.get("llm_call_count") == disabled.get("llm_call_count"),
        "enabled_mechanism_initiated_tool_call_count": enabled.get("mechanism_initiated_tool_call_count"),
        "disabled_mechanism_initiated_tool_call_count": disabled.get("mechanism_initiated_tool_call_count"),
        "scoring_code_executed": bool(enabled.get("scoring_code_executed") or disabled.get("scoring_code_executed")),
        "forced_answer": bool(enabled.get("forced_answer") or disabled.get("forced_answer")),
        "wall_timeout_extension_allowed": bool(enabled.get("wall_timeout_extension_allowed") or disabled.get("wall_timeout_extension_allowed")),
        "enabled_elapsed_seconds": enabled.get("elapsed_seconds"),
        "disabled_elapsed_seconds": disabled.get("elapsed_seconds"),
        "timing_measurements_only": True,
        "strict_timing_equivalence_claimed": False,
    }
    control["passed"] = all(
        control[key]
        for key in (
            "dispatch_count_equal",
            "dispatch_arguments_and_results_equal",
            "termination_equal",
            "final_result_equal",
            "llm_call_count_equal",
        )
    ) and all(
        not control[key]
        for key in (
            "enabled_mechanism_initiated_tool_call_count",
            "disabled_mechanism_initiated_tool_call_count",
            "scoring_code_executed",
            "forced_answer",
            "wall_timeout_extension_allowed",
        )
    )
    write_new(OUTPUT / "enabled_disabled_control.json", control)

    from experiments.dab_api_routing import active_route, read_explicit_key

    route = active_route()
    if route is None or route.get("provider") != "deepseek_official" or route.get("model") != "deepseek-flash":
        raise RuntimeError("Explicit approved DeepSeek route is unavailable")
    credential = read_explicit_key(route)
    provider_receipt = run_probe(remote, args.label, "provider", credential)
    credential = ""
    results["provider"] = provider_receipt
    write_new(OUTPUT / "provider_probe_result.json", provider_receipt)

    provider_dir = f"{remote}/{args.label}_provider"
    copied = []
    for remote_name, local_name in (
        ("g012_uncertainty_gap_action.jsonl", "provider_g012_uncertainty_gap_action.jsonl"),
        ("g012_uncertainty_gap_action_summary.json", "provider_g012_uncertainty_gap_action_summary.json"),
    ):
        remote_path = f"{provider_dir}/{remote_name}"
        if not remote_file_exists(remote_path):
            continue
        text = remote_read_text(remote_path)
        local_path = OUTPUT / local_name
        with local_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        copied.append({"name": local_name, "sha256": sha(local_path)})

    provider_result = provider_receipt.get("result", {})
    privacy_scan = {
        "schema_version": "g012_attempt002_privacy_scan_v1",
        "sidecar_violations": provider_result.get("g012_sidecar_violations", []),
        "structural_sentinel_presence": provider_result.get("g012_structural_sentinel_presence", {}),
        "structural_exports_clean": provider_result.get("g012_structural_exports_clean", False),
        "probe_receipt_synthetic_prefix_present": "G012_ATTEMPT002_SYNTHETIC_" in json.dumps(provider_receipt),
        "probe_receipt_record_prefix_present": "G011_PLAN_RECORD_V1" in json.dumps(provider_receipt),
        "probe_receipt_raw_ref_prefix_present": "var_" in json.dumps(provider_receipt),
        "base_raw_logs_isolated": all(
            row.get("isolated_base_raw_log") and not row.get("copied_to_research_artifact")
            for row in provider_result.get("raw_log_surfaces", {}).values()
        ),
        "base_raw_logs_contain_synthetic_context": any(
            row.get("contains_synthetic_context")
            for row in provider_result.get("raw_log_surfaces", {}).values()
        ),
        "research_export_read_raw_logs": provider_result.get("research_export_read_raw_logs"),
        "copied_structural_artifacts": copied,
    }
    privacy_scan["passed"] = bool(
        not privacy_scan["sidecar_violations"]
        and privacy_scan["structural_exports_clean"]
        and not privacy_scan["probe_receipt_synthetic_prefix_present"]
        and not privacy_scan["probe_receipt_record_prefix_present"]
        and not privacy_scan["probe_receipt_raw_ref_prefix_present"]
        and privacy_scan["base_raw_logs_isolated"]
        and privacy_scan["research_export_read_raw_logs"] is False
    )
    write_new(OUTPUT / "privacy_scan.json", privacy_scan)

    final_parent_hash = source_tree_hash(SOURCE / "parent_control")
    final_child_hash = source_tree_hash(SOURCE / "repo")
    final_contract_hash = sha(CONTRACT)
    frozen_unchanged = (final_parent_hash, final_child_hash, final_contract_hash) == (
        PARENT_HASH,
        CHILD_HASH,
        CONTRACT_HASH,
    )
    provider_passed = provider_receipt.get("exit_code") == 0 and provider_result.get("status") == "passed"
    final_status = "passed" if provider_passed and control["passed"] and privacy_scan["passed"] and frozen_unchanged else (
        "blocked" if provider_result.get("status") == "blocked" or not control["passed"] or not privacy_scan["passed"] or not frozen_unchanged else "untested"
    )
    attempt_result = {
        "schema_version": "g012_admission_attempt002_result_v1",
        "status": final_status,
        "artifact_directory": str(OUTPUT.resolve()),
        "parent_tree_sha256": final_parent_hash,
        "child_tree_sha256": final_child_hash,
        "research_contract_sha256": final_contract_hash,
        "frozen_sources_unchanged": frozen_unchanged,
        "probe_sha256": sha(PROBE),
        "driver_sha256": sha(Path(__file__)),
        "provider_call_count": provider_result.get("provider_call_count"),
        "record_attempt_count": provider_result.get("record_attempt_count"),
        "accepted_record_count": provider_result.get("accepted_record_count"),
        "active_unique_ref_count": provider_result.get("active_unique_ref_count"),
        "directive_count": provider_result.get("directive_observed_at_provider_boundary_count"),
        "directive_fields": provider_result.get("directive_fields"),
        "next_action_classification": provider_result.get("next_action_classification"),
        "next_action_structural_class": provider_result.get("next_action_structural_class"),
        "enabled_disabled_control_passed": control["passed"],
        "privacy_scan_passed": privacy_scan["passed"],
        "mechanism_initiated_tool_call_count": provider_result.get("mechanism_initiated_tool_call_count"),
        "benchmark_accessed": False,
        "database_accessed": False,
        "formal_evaluation_started": False,
        "launch_claim_created": False,
        "formal_graph_modified": False,
        "frozen_candidate_modified": False,
    }
    write_new(OUTPUT / "attempt_result.json", attempt_result)
    if final_status == "passed":
        admission = dict(attempt_result)
        admission["schema_version"] = "g012_runtime_admission_result_v1"
        write_new(OUTPUT / "admission_result.json", admission)
    write_new(
        OUTPUT / "remote_attempt002.json",
        {
            "schema_version": "g012_remote_admission_receipt_attempt002_v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "remote_synthetic_scratch": remote,
            "results": results,
            "probe_sha256": sha(PROBE),
            "driver_sha256": sha(Path(__file__)),
            "copied_base_raw_logs": False,
            "benchmark_accessed": False,
            "database_accessed": False,
            "formal_evaluation_started": False,
        },
    )
    print(json.dumps(attempt_result, sort_keys=True))


if __name__ == "__main__":
    main()
