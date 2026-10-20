#!/usr/bin/env python3
"""Run one same-spec G11 Implementation Meta repair after mechanical admission."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from experiments.assemble_research_graph_g004_candidate import source_tree_hash
from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g011_solution_loop_formal_implementation_001"
CANDIDATE = WORK / "candidate"
CONTEXT = WORK / "context"
PRIOR_MANIFEST = WORK / "implementation_manifest.json"
RESEARCH = BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt"
OUT = BASE / "g011_solution_loop_formal_implementation_meta_003"

PRIOR_CANDIDATE_SHA256 = "54b00d2ef02acc937921c3276239876d4ed195b8988fb17d10d12680ac464e1a"
PRIOR_MANIFEST_SHA256 = "c9cb355a8c7c84b3ed3c160ea7dc0dfaff0ab1371e9a3db296aabd342b290ef8"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G11 formal Implementation repair already exists")
    if (
        source_tree_hash(CANDIDATE) != PRIOR_CANDIDATE_SHA256
        or sha(PRIOR_MANIFEST) != PRIOR_MANIFEST_SHA256
        or sha(RESEARCH) != RESEARCH_SHA256
    ):
        raise RuntimeError("G11 repair input binding differs")
    revised_contract = CONTEXT / "research_contract_revision_004.json"
    if revised_contract.exists():
        if sha(revised_contract) != RESEARCH_SHA256:
            raise RuntimeError("G11 revised Research context differs")
    else:
        shutil.copy2(RESEARCH, revised_contract)
    binding = {
        "schema_version": "g011_solution_loop_formal_repair_input_v1",
        "repair_attempt": 1,
        "candidate_tree_sha256_before_repair": PRIOR_CANDIDATE_SHA256,
        "prior_implementation_manifest_sha256": PRIOR_MANIFEST_SHA256,
        "revised_research_sha256": RESEARCH_SHA256,
        "mechanical_findings": [
            {
                "id": "F1",
                "status": "repaired_by_research_revision_004",
                "finding": "Revision 003 named undeclared nested self_observation.plan_record, while the implementation selected declared self_observation.freeform.",
                "required_action": "Bind all source and tests to Revision 004, which freezes self_observation.freeform and explicitly rejects nested plan_record.",
            },
            {
                "id": "F2",
                "status": "implementation_repair_required",
                "finding": "Seven G11 tests fail after assembly because g011_interface_contract defaults to an incubation context directory that is not part of the deployable candidate.",
                "required_action": "Remove deploy-time and default-test dependence on external incubation context. Keep outer admission responsible for hashing Research/prototype artifacts; runtime source and deployable tests must be self-contained and must not ship or read research history.",
            },
            {
                "id": "F3",
                "status": "parent_preexisting",
                "finding": "The complete G7 parent independently has five test_tool_failure_recovery failures; the assembled G11 tree has the same five plus the seven G11 context failures.",
                "required_action": "Do not modify or claim to fix the five inherited failures. Prove the repaired candidate has exactly the same inherited failure set and no G11-specific failures.",
            },
        ],
        "excluded": [
            "benchmark tasks", "answers", "hints", "validators", "raw traces",
            "results", "credentials", "network", "server", "formal evaluation",
        ],
    }
    binding_path = WORK / "repair_input_binding_001.json"
    rendered_binding = json.dumps(binding, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    if binding_path.exists():
        if binding_path.read_text(encoding="utf-8") != rendered_binding:
            raise RuntimeError("G11 repair input binding differs")
    else:
        binding_path.write_text(rendered_binding, encoding="utf-8")
    OUT.mkdir(exist_ok=False)
    prompt = (
        "You are G11 Implementation Meta repair attempt 1 of at most 3. Work only "
        "inside the existing candidate/ directory. The selected mechanism and revised "
        "Research semantics are frozen; do not reopen selection or change the exact "
        "record schema, freeform carrier, semantic boundary, authoring policy, caps, "
        "fixed protocol, or measurements. Read the revised contract only from "
        "context/research_contract_revision_004.json and the prior implementation "
        "manifest from implementation_manifest.json. Fix the mechanical findings in "
        "repair_input_binding_001.json. In particular, bind source constants and tests "
        "to Research Revision 004 and make the deployable source/tests self-contained: "
        "runtime or default tests must not depend on an adjacent incubation context, "
        "must not package research history, and must not read prototype/Research files "
        "during a task. Outer orchestration will independently verify those artifact "
        "hashes. Preserve an optional explicit-context verification function only if it "
        "is strictly admission-only and tests pass without that context. Keep the five "
        "independently confirmed G7 parent failures unchanged; do not modify unrelated "
        "parent behavior. Re-run all G11 focused tests and the complete candidate suite. "
        "The repair succeeds only if focused G11 tests all pass and the complete suite "
        "has exactly the inherited five failures and no new failures. Do not access the "
        "repository outside this workspace, network, server, benchmark/corpus, tasks, "
        "answers, hints, validators, raw messages/tool content, traces, results, old "
        "research lines, or credentials. Do not deploy or evaluate. Preserve the prior "
        "implementation_manifest.json unchanged as history and write "
        "implementation_manifest_revision_001.json with revised file hashes, before/"
        "after candidate tree hashes, test results, claim-to-check mapping, unresolved "
        "risks, formal_candidate only if repaired, and evaluation_run=false. Saved "
        "artifacts are authoritative. The repair binding follows:\n"
        + json.dumps(binding, sort_keys=True, ensure_ascii=True)
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab",
        "--model", "deepseek-flash", "exec", "--sandbox", "workspace-write",
        "-c", 'approval_policy="never"', "--skip-git-repo-check", "--json",
        "--output-last-message", str(OUT / "final_raw.txt"), "-",
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
        raise RuntimeError("G11 Implementation repair failed; attempt retained")


if __name__ == "__main__":
    main()
