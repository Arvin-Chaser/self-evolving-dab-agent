"""Request and admit one constrained replacement workspace plan for G14.

The prior plan is retained as evidence. This pass may only create a separate
synthetic test target; the root G14 smoke test remains a read-only reference.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.curated_coding_workspace_meta_adapter import (
    IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION,
    build_workspace_inputs_from_meta_plan,
)
from experiments.dab_meta_runtime import meta_environment, run_logged_command
from experiments.dab_meta_standalone_runtime_v1 import CODEX


OUT = ROOT / "experiments/g014_restart_interface_candidate_001"
HANDOFF = OUT / "local_handoff.json"
RECEIPT = OUT / "prepare_receipt.json"
PLAN_PATH = OUT / "implementation_meta_plan_repair001.json"
VALIDATION_PATH = OUT / "implementation_meta_plan_repair001_validation.json"
ROOT_REGRESSION_TEST = "tests/test_research_graph_role_scoped_wiring.py"
SYNTHETIC_TEST = "tests/test_g014_restart_competing_hypothesis.py"
WIRING_MODULE = "experiments/research_graph_role_scoped_wiring.py"

CATALOG = [
    WIRING_MODULE,
    ROOT_REGRESSION_TEST,
    "experiments/research_graph_interface_contract.py",
]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")


def validate_g14_plan(plan: dict, handoff: dict, receipt: dict) -> None:
    """Bind the generic contract to this candidate's immutable regression test."""
    _contract, request = build_workspace_inputs_from_meta_plan(
        plan,
        local_handoff=handoff,
        contract_id="contract:g014:restart:interface:repair001",
        task_id="task:g014:restart:interface:001",
        task_ref="taskref:g014:restart:interface:001",
        measurement_plan_id="measurement:g014:restart:interface:001",
        measurement_plan_ref="measure:g014:restart:interface:001",
        expected_packet_sha256=receipt["packet_sha256"],
        expected_source_binding=handoff["source_binding"],
        expected_handoff_sha256=receipt["handoff_sha256"],
        protected_writable_target_paths=[ROOT_REGRESSION_TEST],
    )
    selections = {
        (item["source_relative_path"], item["target_path"], item["category"])
        for item in request["selection"]
    }
    required = {
        (WIRING_MODULE, f"coding_workspace/candidate/{WIRING_MODULE}", "candidate_implementation"),
        (ROOT_REGRESSION_TEST, f"coding_workspace/readonly/{ROOT_REGRESSION_TEST}", "test_documents"),
        (ROOT_REGRESSION_TEST, f"coding_workspace/candidate/{SYNTHETIC_TEST}", "candidate_tests"),
        ("experiments/research_graph_interface_contract.py", "coding_workspace/readonly/experiments/research_graph_interface_contract.py", "source_documents"),
    }
    if not required <= selections:
        raise ValueError("Replacement plan does not provide the required scoped implementation and test layout")


def main() -> int:
    if PLAN_PATH.exists() or VALIDATION_PATH.exists():
        raise RuntimeError("Replacement Implementation Meta attempt already exists")
    handoff = json.loads(HANDOFF.read_text(encoding="utf-8"))
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    refs = sorted([*handoff["local_view"]["node_ids"], *handoff["local_view"]["edge_ids"]])
    prompt = f'''Return exactly one JSON object matching `{IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION}` with keys schema_version, plan_id, coding_task, graph_refs, files. Each file has source_relative_path, category, target_relative_path, reason, graph_refs.

You are Implementation Meta for a no-task, provider-free G14 interface candidate. The target studies competing hypotheses and a bounded discriminating observation. Select an import-closed workspace plan from this catalog: {json.dumps(CATALOG)}.

Hard workspace layout:
- `{WIRING_MODULE}` must be `candidate_implementation` targeted to itself.
- `{ROOT_REGRESSION_TEST}` must be `test_documents` targeted to itself. It is read-only reference coverage and must not be replaced, weakened, renamed, or selected as a writable target.
- A separate `candidate_tests` selection must seed `{SYNTHETIC_TEST}` from `{ROOT_REGRESSION_TEST}`. The Coding Agent may replace only this new synthetic test copy with no-task coverage.
- `experiments/research_graph_interface_contract.py` must be `source_documents` targeted to itself.
- Do not select any file outside this catalog. Do not use providers, databases, servers, task data, answers, or formal evaluation. Do not claim benchmark benefit.

The Coding Agent will run only the new synthetic test. The controller alone will later run the unchanged real G14 regression from the root repository.

Allowed local Graph refs: {json.dumps(refs)}
Local handoff: {json.dumps(handoff['graph_slice'], sort_keys=True)}
'''
    (OUT / "implementation_meta_repair001_prompt.md").write_text(prompt, encoding="utf-8", newline="\n")
    command = [
        str(CODEX), "--profile", "deepseek-standalone-dab", "--model", "deepseek-flash",
        "--sandbox", "workspace-write", "-a", "never", "exec", "--skip-git-repo-check",
        "--output-last-message", str(OUT / "implementation_meta_repair001_final.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=OUT, prompt=prompt,
        stdout_path=OUT / "implementation_meta_repair001.stdout",
        stderr_path=OUT / "implementation_meta_repair001.stderr",
        env=meta_environment("deepseek-standalone-dab"), timeout=300,
    )
    if result.returncode:
        write_json(VALIDATION_PATH, {"status": "provider_failed", "provider_called": True, "exit_code": result.returncode})
        return result.returncode
    raw = (OUT / "implementation_meta_repair001_final.txt").read_text(encoding="utf-8").strip()
    plan = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    write_json(PLAN_PATH, plan)
    try:
        validate_g14_plan(plan, handoff, receipt)
    except (TypeError, ValueError) as exc:
        write_json(VALIDATION_PATH, {"status": "rejected", "reason": str(exc), "provider_called": True})
        return 2
    write_json(VALIDATION_PATH, {"status": "accepted", "provider_called": True, "plan_id": plan["plan_id"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
