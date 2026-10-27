"""Run one bounded Implementation Meta file-selection pass for restarted G14."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.dab_meta_runtime import meta_environment, run_logged_command
from experiments.dab_meta_standalone_runtime_v1 import CODEX
from experiments.curated_coding_workspace_meta_adapter import IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION

OUT = ROOT / "experiments/g014_restart_interface_candidate_001"
HANDOFF = OUT / "local_handoff.json"
CATALOG = [
    "experiments/research_graph_role_scoped_wiring.py",
    "tests/test_research_graph_role_scoped_wiring.py",
    "experiments/research_graph_interface_contract.py",
    "experiments/curated_coding_workspace_contract.py",
    "experiments/curated_coding_workspace_meta_adapter.py",
    "experiments/curated_coding_workspace_materializer.py",
]

def main() -> int:
    if (OUT / "implementation_meta_plan.json").exists():
        raise RuntimeError("Implementation Meta plan already exists")
    handoff = json.loads(HANDOFF.read_text(encoding="utf-8"))
    refs = sorted([*handoff["local_view"]["node_ids"], *handoff["local_view"]["edge_ids"]])
    prompt = f'''Return exactly one JSON object matching `{IMPLEMENTATION_META_WORKSPACE_PLAN_SCHEMA_VERSION}` with keys schema_version, plan_id, coding_task, graph_refs, files. Each file has source_relative_path, category, target_relative_path, reason, graph_refs.\n\nYou are Implementation Meta for a no-task, provider-free G14 interface candidate. The active target studies competing hypotheses and a bounded discriminating observation. Select the smallest import-closed plan from this catalog for an isolated prototype and focused tests. The coding task must not claim benchmark benefit or use providers, databases, servers, tasks, answers, or formal evaluation. Use candidate_implementation only for the wiring module, candidate_tests only for its test, and source_documents otherwise. Select only needed files.\n\nAllowed local Graph refs: {json.dumps(refs)}\nLocal handoff: {json.dumps(handoff['graph_slice'], sort_keys=True)}\nCatalog: {json.dumps(CATALOG)}\n'''
    (OUT / "implementation_meta_prompt.md").write_text(prompt, encoding="utf-8", newline="\n")
    command = [str(CODEX), "--profile", "deepseek-standalone-dab", "--model", "deepseek-flash", "--sandbox", "workspace-write", "-a", "never", "exec", "--skip-git-repo-check", "--output-last-message", str(OUT / "implementation_meta_final.txt"), "-"]
    result = run_logged_command(command, cwd=OUT, prompt=prompt, stdout_path=OUT / "implementation_meta.stdout", stderr_path=OUT / "implementation_meta.stderr", env=meta_environment("deepseek-standalone-dab"), timeout=300)
    if result.returncode:
        raise RuntimeError("Implementation Meta failed; attempt retained")
    raw = (OUT / "implementation_meta_final.txt").read_text(encoding="utf-8").strip()
    plan = json.loads(raw[raw.find("{"):raw.rfind("}")+1])
    (OUT / "implementation_meta_plan.json").write_text(json.dumps(plan, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    return 0
if __name__ == "__main__": raise SystemExit(main())
