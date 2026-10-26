#!/usr/bin/env python3
"""Run and finalize the bounded G13 no-benchmark runtime admission."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.intent_candidate_workspace import source_paths, source_tree_hash


BASE = ROOT / "experiments/research_graph_baseline_20261016"
IMPLEMENTATION = BASE / "g013_formal_implementation_006"
CHILD = IMPLEMENTATION / "candidate_patch"
PARENT = BASE / "g007_candidate_002/repo"
CONTRACT = BASE / "g013_formal_research_contract.json"
MANIFEST = CHILD / "implementation_manifest.json"
SOURCE_REVIEW = IMPLEMENTATION / "source_review_004.json"
PROBE = ROOT / "experiments/probe_research_graph_g013_admission_attempt005.py"
UPSTREAM = ROOT / "external/DataAgentBench_official"
OUTPUT = BASE / "g013_admission_005"
REMOTE_PROBE_NAME = "probe_research_graph_g013_admission_attempt005.py"
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
REMOTE_PYTHON = "/srv/text2sql/.venv/bin/python"

PARENT_HASH = "572b8c92f4aaa3834e36a7899d667123eb548d0a6f1675a243cc07a9974244ac"
CHILD_HASH = "e966e07211bae0d8ddea96af8d88143b47af40db40567161d2d8391abfc7591c"
CONTRACT_HASH = "5c60ad036745f2219582d1e0a9e6ef10ce82920461537702df3ed691121d917c"
MANIFEST_HASH = "0c939b2afd6c51163e9b1702052f882fd9e5f0651234ab20e2cf0c9b9d0e9ff2"
SOURCE_REVIEW_HASH = "235b54b132fb8eb44020a0f5f5fa47834712b0cd37101a4d616f0cb94177d4a0"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True)
        stream.write("\n")


def checked(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("Bounded remote command failed")
    return completed


def remote_python(code: str, *, timeout: int = 60) -> Any:
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    command = f'{REMOTE_PYTHON} -B -c "exec(__import__(\'base64\').b64decode(\'{encoded}\'))"'
    return json.loads(checked(SSH + [command], timeout=timeout).stdout)


def prepare_remote(remote: str, scratch: Path) -> dict[str, Any]:
    if not remote.startswith(
        "/srv/text2sql/evolution_runtime/research_graph_baseline_20261016/g013_admission_"
    ) or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/" for character in remote):
        raise RuntimeError("Remote synthetic scratch boundary differs")
    checked(SSH + [f"test ! -e {remote} && mkdir -p {remote}/repo"], timeout=30)
    archive = scratch / "frozen_child_source.tar.gz"
    manifest_path = scratch / "child_files.json"
    rows = []
    with tarfile.open(archive, "w:gz") as bundle:
        for path in source_paths(CHILD):
            relative = path.relative_to(CHILD).as_posix()
            bundle.add(path, arcname=relative, recursive=False)
            rows.append({"path": relative, "sha256": sha(path)})
    write_new(manifest_path, rows)
    checked(SCP + [str(archive), f"root@100.83.10.33:{remote}/source.tar.gz"], timeout=120)
    checked(SCP + [str(manifest_path), f"root@100.83.10.33:{remote}/child_files.json"], timeout=60)
    checked(SCP + [str(PROBE), f"root@100.83.10.33:{remote}/{REMOTE_PROBE_NAME}"], timeout=60)
    checked(SSH + [f"tar -xzf {remote}/source.tar.gz -C {remote}/repo"], timeout=60)
    code = f"""
import hashlib,json
from pathlib import Path
root=Path({remote!r})
rows=json.loads((root/'child_files.json').read_text())
bad=[row['path'] for row in rows if hashlib.sha256((root/'repo'/row['path']).read_bytes()).hexdigest()!=row['sha256']]
probe=root/{REMOTE_PROBE_NAME!r}
print(json.dumps({{'file_count':len(rows),'mismatch_count':len(bad),'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest()}}))
"""
    verification = remote_python(code)
    if verification.get("mismatch_count") != 0 or verification.get("probe_sha256") != sha(PROBE):
        raise RuntimeError("Remote frozen source verification failed")
    return verification


def run_probe(mode: str, remote: str, credential: str | None) -> dict[str, Any]:
    output = f"{remote}/{mode}"
    command = (
        f"cd {remote} && {REMOTE_PYTHON} -B {REMOTE_PROBE_NAME} "
        f"--repo {remote}/repo --upstream /srv/text2sql/external/DataAgentBench_official "
        f"--output {output} --mode {mode}"
    )
    completed = subprocess.run(
        SSH + [command],
        input=(credential + "\n") if credential is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1]) if lines else {"status": "no_probe_output"}
    except json.JSONDecodeError:
        result = {"status": "invalid_probe_output"}
    receipt = {
        "exit_code": completed.returncode,
        "result": result,
        "stderr_sha256": hashlib.sha256(completed.stderr.encode("utf-8")).hexdigest(),
    }
    if completed.returncode == 0:
        persisted_text = checked(SSH + [f"/bin/cat {output}/probe_result.json"], timeout=30).stdout
        persisted = json.loads(persisted_text)
        if persisted != result:
            raise RuntimeError("Probe stdout and persisted receipt differ")
    return receipt


def pytest_result(repo: Path, args: list[str], basetemp: str, timeout: int = 600) -> dict[str, Any]:
    # Every generated path stays outside the frozen candidate tree. Avoid a
    # custom PYTHONPYCACHEPREFIX because nested compile tests manage their own
    # temporary source trees and must not share pytest's removable basetemp.
    temp_root = Path(tempfile.mkdtemp(prefix=f"{basetemp}_"))
    pytest_base = temp_root / "pytest_base"
    env = os.environ.copy()
    env.update(
        {
            "TMP": str(temp_root),
            "TEMP": str(temp_root),
            "TMPDIR": str(temp_root),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.pop("PYTHONPYCACHEPREFIX", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            *args,
            "-q",
            "-p",
            "no:cacheprovider",
            f"--basetemp={pytest_base}",
            "--tb=short",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    text = "\n".join((completed.stdout + "\n" + completed.stderr).splitlines())
    summary_lines = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"\b(?:passed|failed|deselected|error)s?\b", line, re.IGNORECASE)
    ]
    failed_nodeids = sorted(
        {
            line.split(" - ", 1)[0].removeprefix("FAILED ").strip()
            for line in text.splitlines()
            if line.startswith("FAILED ")
        }
    )
    return {
        "exit_code": completed.returncode,
        "summary": summary_lines[-1] if summary_lines else "no pytest summary",
        "failed_nodeids": failed_nodeids,
        "failed_nodeid_count": len(failed_nodeids),
        "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "external_temp_root_sha256": hashlib.sha256(
            str(temp_root).encode("utf-8")
        ).hexdigest(),
        "temporary_roots_outside_candidate": not temp_root.is_relative_to(repo.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--remote-root", required=True)
    args = parser.parse_args()
    scratch = args.scratch.resolve()
    if OUTPUT.exists() or scratch.exists():
        raise RuntimeError("Refusing to overwrite admission artifact or scratch")
    scratch.mkdir(parents=True)
    remote_verification = prepare_remote(args.remote_root, scratch)

    bindings = {
        "parent_tree_sha256": source_tree_hash(PARENT),
        "child_tree_sha256": source_tree_hash(CHILD),
        "research_contract_sha256": sha(CONTRACT),
        "implementation_manifest_sha256": sha(MANIFEST),
        "source_review_sha256": sha(SOURCE_REVIEW),
    }
    expected = {
        "parent_tree_sha256": PARENT_HASH,
        "child_tree_sha256": CHILD_HASH,
        "research_contract_sha256": CONTRACT_HASH,
        "implementation_manifest_sha256": MANIFEST_HASH,
        "source_review_sha256": SOURCE_REVIEW_HASH,
    }
    if bindings != expected:
        raise RuntimeError("Frozen G13 admission binding differs")
    source_review = json.loads(SOURCE_REVIEW.read_text(encoding="utf-8"))
    if source_review.get("review_status") != "passed_source_contract_and_privacy_ready_for_new_runtime_admission":
        raise RuntimeError("Independent source review is not admission-eligible")

    OUTPUT.mkdir(parents=True)
    baseline = {
        "schema_version": "g013_runtime_admission_binding_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        **bindings,
        "probe_sha256": sha(PROBE),
        "driver_sha256": sha(Path(__file__)),
        "synthetic_only": True,
        "provider_call_cap": 5,
        "benchmark_accessed": False,
        "database_accessed": False,
        "formal_evaluation_started": False,
        "raw_scratch_exported": False,
        "remote_source_verification": remote_verification,
    }
    write_new(OUTPUT / "input_binding.json", baseline)

    controls: dict[str, Any] = {}
    for mode in ("enabled", "disabled"):
        controls[mode] = run_probe(mode, args.remote_root, None)
        write_new(OUTPUT / f"control_{mode}.json", controls[mode])
        if controls[mode]["exit_code"] != 0:
            raise RuntimeError(f"Programmed {mode} control failed")

    enabled = controls["enabled"]["result"]
    disabled = controls["disabled"]["result"]
    control = {
        "schema_version": "g013_enabled_disabled_control_v1",
        "non_carrier_dispatch_count_equal": enabled.get("non_carrier_dispatch_count") == disabled.get("non_carrier_dispatch_count"),
        "non_carrier_dispatch_equal": enabled.get("non_carrier_dispatch_sha256") == disabled.get("non_carrier_dispatch_sha256"),
        "termination_equal": enabled.get("termination") == disabled.get("termination"),
        "final_result_equal": enabled.get("final_result_sha256") == disabled.get("final_result_sha256"),
        "llm_call_count_equal": enabled.get("llm_call_count") == disabled.get("llm_call_count"),
        "enabled_mechanism_initiated_tool_call_count": enabled.get("mechanism_initiated_tool_call_count"),
        "disabled_mechanism_initiated_tool_call_count": disabled.get("mechanism_initiated_tool_call_count"),
        "forced_tool_call_count": max(int(enabled.get("forced_tool_call_count", 0)), int(disabled.get("forced_tool_call_count", 0))),
        "forced_answer_count": max(int(enabled.get("forced_answer_count", 0)), int(disabled.get("forced_answer_count", 0))),
        "scoring_mutation_count": max(int(enabled.get("scoring_mutation_count", 0)), int(disabled.get("scoring_mutation_count", 0))),
        "timeout_extension_count": max(int(enabled.get("timeout_extension_count", 0)), int(disabled.get("timeout_extension_count", 0))),
        "timing_measurements_only": True,
        "strict_timing_equivalence_claimed": False,
    }
    control["passed"] = all(
        control[name]
        for name in (
            "non_carrier_dispatch_count_equal",
            "non_carrier_dispatch_equal",
            "termination_equal",
            "final_result_equal",
            "llm_call_count_equal",
        )
    ) and all(
        int(control[name] or 0) == 0
        for name in (
            "enabled_mechanism_initiated_tool_call_count",
            "disabled_mechanism_initiated_tool_call_count",
            "forced_tool_call_count",
            "forced_answer_count",
            "scoring_mutation_count",
            "timeout_extension_count",
        )
    )
    write_new(OUTPUT / "enabled_disabled_control.json", control)

    from experiments.dab_api_routing import active_route, read_explicit_key

    route = active_route()
    if route is None or route.get("provider") != "deepseek_official" or route.get("model") != "deepseek-flash":
        raise RuntimeError("Explicit approved DeepSeek route is unavailable")
    credential = read_explicit_key(route)
    provider = run_probe("provider", args.remote_root, credential)
    credential = ""
    write_new(OUTPUT / "provider_probe_result.json", provider)

    focused_args = [
        "tests/test_g013_requirement_coverage.py",
        "tests/test_g007_evidence_extractor.py",
        "tests/test_g007_interface_contract.py",
        "tests/test_g007_last_pre_exec_sidecar.py",
    ]
    tests = {
        "candidate_focused_g13_g7": pytest_result(CHILD, focused_args, "g013_admission_focused"),
        "candidate_full": pytest_result(CHILD, ["tests"], "g013_admission_candidate_full"),
        "parent_full": pytest_result(PARENT, ["tests"], "g013_admission_parent_full"),
    }
    candidate_summary = tests["candidate_full"]["summary"]
    parent_summary = tests["parent_full"]["summary"]
    inherited_failure_match = (
        tests["candidate_full"]["exit_code"] == 1
        and tests["parent_full"]["exit_code"] == 1
        and "5 failed" in candidate_summary
        and "5 failed" in parent_summary
        and "216 passed" in candidate_summary
        and "153 passed" in parent_summary
        and tests["candidate_full"]["failed_nodeids"]
        == tests["parent_full"]["failed_nodeids"]
        and tests["candidate_full"]["failed_nodeid_count"] == 5
        and tests["candidate_full"]["temporary_roots_outside_candidate"]
        and tests["parent_full"]["temporary_roots_outside_candidate"]
    )
    tests["new_failure_count"] = 0 if inherited_failure_match else None
    tests["inherited_failure_match"] = inherited_failure_match
    write_new(OUTPUT / "test_results.json", tests)

    provider_result = provider.get("result", {})
    privacy = {
        "schema_version": "g013_runtime_admission_privacy_v1",
        "persisted_sensitive_token_hit_count": provider_result.get("persisted_sensitive_token_hit_count"),
        "persisted_reasoning_content_field_hit_count": provider_result.get("persisted_reasoning_content_field_hit_count"),
        "raw_surfaces_isolated": all(
            row.get("isolated_scratch_only") and not row.get("copied_to_research_artifact")
            for row in provider_result.get("raw_log_surfaces", {}).values()
        ),
        "raw_surfaces_contain_general_synthetic_context": any(
            row.get("contains_general_synthetic_context")
            for row in provider_result.get("raw_log_surfaces", {}).values()
        ),
        "content_blind_marker_present": provider_result.get("content_blind_marker_present"),
        "research_export_read_raw_logs": provider_result.get("research_export_read_raw_logs"),
        "raw_scratch_exported": provider_result.get("raw_scratch_exported"),
    }
    privacy["passed"] = bool(
        privacy["persisted_sensitive_token_hit_count"] == 0
        and privacy["persisted_reasoning_content_field_hit_count"] == 0
        and privacy["raw_surfaces_isolated"]
        and privacy["content_blind_marker_present"]
        and privacy["research_export_read_raw_logs"] is False
        and privacy["raw_scratch_exported"] is False
    )
    write_new(OUTPUT / "privacy_scan.json", privacy)

    final_bindings = {
        "parent_tree_sha256": source_tree_hash(PARENT),
        "child_tree_sha256": source_tree_hash(CHILD),
        "research_contract_sha256": sha(CONTRACT),
        "implementation_manifest_sha256": sha(MANIFEST),
        "source_review_sha256": sha(SOURCE_REVIEW),
    }
    frozen_unchanged = final_bindings == expected
    tests_pass = bool(
        tests["candidate_focused_g13_g7"]["exit_code"] == 0
        and inherited_failure_match
    )
    provider_pass = provider.get("exit_code") == 0 and provider_result.get("status") == "passed"
    passed = provider_pass and control["passed"] and privacy["passed"] and tests_pass and frozen_unchanged
    result = {
        "schema_version": "g013_runtime_admission_result_v1",
        "status": "passed" if passed else "blocked",
        "artifact_directory": str(OUTPUT.resolve()),
        **final_bindings,
        "frozen_sources_unchanged": frozen_unchanged,
        "probe_sha256": sha(PROBE),
        "driver_sha256": sha(Path(__file__)),
        "provider_call_count": provider_result.get("provider_call_count"),
        "automatic_tool_selection_only": provider_result.get("automatic_tool_selection_only"),
        "real_model_authored_carrier_accepted": provider_result.get("real_model_authored_carrier_accepted"),
        "exact_visible_opaque_token_copy_count": provider_result.get("exact_visible_opaque_token_copy_count"),
        "directive_delivered_count": provider_result.get("directive_delivered_count"),
        "action_consistency_counts": provider_result.get("action_consistency_counts"),
        "selected_action_counts": provider_result.get("selected_action_counts"),
        "fault_fixtures_fail_closed": provider_result.get("fault_fixtures_fail_closed"),
        "enabled_disabled_control_passed": control["passed"],
        "privacy_scan_passed": privacy["passed"],
        "focused_tests": tests["candidate_focused_g13_g7"]["summary"],
        "candidate_full_tests": candidate_summary,
        "parent_full_tests": parent_summary,
        "new_failure_count": tests["new_failure_count"],
        "mechanism_initiated_tool_call_count": provider_result.get("mechanism_initiated_tool_call_count"),
        "forced_tool_call_count": provider_result.get("forced_tool_call_count"),
        "forced_answer_count": provider_result.get("forced_answer_count"),
        "scoring_mutation_count": provider_result.get("scoring_mutation_count"),
        "timeout_extension_count": provider_result.get("timeout_extension_count"),
        "benchmark_accessed": False,
        "database_accessed": False,
        "formal_evaluation_started": False,
        "launch_claim_created": False,
        "formal_graph_modified": False,
        "frozen_candidate_modified": False,
        "strict_timing_equivalence_claimed": False,
        "semantic_or_causal_claim": False,
    }
    write_new(OUTPUT / "admission_result.json", result)
    manifest = {
        "schema_version": "g013_runtime_admission_manifest_v1",
        "status": result["status"],
        "files": [
            {"name": path.name, "sha256": sha(path)}
            for path in sorted(OUTPUT.iterdir(), key=lambda item: item.name)
            if path.is_file()
        ],
        "raw_scratch_path_sha256": hashlib.sha256(args.remote_root.encode("utf-8")).hexdigest(),
        "raw_scratch_copied": False,
        "provider_call_count": provider_result.get("provider_call_count"),
        "benchmark_accessed": False,
        "database_accessed": False,
        "formal_evaluation_started": False,
    }
    write_new(OUTPUT / "admission_manifest.json", manifest)
    print(json.dumps(result, sort_keys=True))
    if not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
