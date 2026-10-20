#!/usr/bin/env python3
"""Run the second same-spec G11 repair for multi-query activation wiring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.intent_candidate_workspace import source_tree_hash


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
WORK = BASE / "g011_solution_loop_formal_implementation_001"
CANDIDATE = WORK / "candidate"
RESEARCH = BASE / "g011_research_meta_solution_loop_revision_004/final_raw.txt"
PRIOR_MANIFEST = WORK / "implementation_manifest_revision_001.json"
OUT = BASE / "g011_solution_loop_formal_implementation_meta_004"

CANDIDATE_SHA256 = "2bad7999f98d3359a0407724b3aba66a0b83e6e11aa69e00e5e8a47f05a6277b"
RESEARCH_SHA256 = "9a0d6943a4b262429b8270664b0ede8bc9effbae5a15d0c882d63691e236d193"
PRIOR_MANIFEST_SHA256 = "5f484ff5278b35d43a4f2dfbf21c0c27b354c91c4b5019428abe9f01bc42eaba"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G11 formal Implementation repair attempt 2 already exists")
    if (
        source_tree_hash(CANDIDATE) != CANDIDATE_SHA256
        or sha256(RESEARCH) != RESEARCH_SHA256
        or sha256(PRIOR_MANIFEST) != PRIOR_MANIFEST_SHA256
    ):
        raise RuntimeError("G11 repair-attempt-2 input binding differs")

    binding = {
        "schema_version": "g011_solution_loop_formal_repair_input_v2",
        "repair_attempt": 2,
        "candidate_tree_sha256_before_repair": CANDIDATE_SHA256,
        "prior_implementation_manifest_sha256": PRIOR_MANIFEST_SHA256,
        "research_sha256": RESEARCH_SHA256,
        "mechanical_findings": [
            {
                "id": "F4",
                "status": "implementation_repair_required",
                "finding": (
                    "The single-task runner exposes --enable-g011-plan-evidence-ledger "
                    "and leaves it false by default, but run_multi_query_baseline.py "
                    "has no matching opt-in and never appends that flag to its child command. "
                    "The fixed 56-task launcher therefore cannot explicitly activate the "
                    "selected mechanism without an unrecorded orchestration substitution."
                ),
                "required_action": (
                    "Add one explicit outer-runner opt-in with the same name and propagate it "
                    "verbatim to every single-task child command. Keep the default disabled. "
                    "Add no-task tests proving default-off, enabled propagation, prepare-only "
                    "propagation, and no unrelated command or protocol changes."
                ),
            }
        ],
        "success_criteria": {
            "research_semantics_unchanged": True,
            "single_task_default_remains_disabled": True,
            "outer_runner_default_remains_disabled": True,
            "formal_launcher_can_enable_explicitly": True,
            "g011_focused_tests_all_pass": True,
            "complete_suite_failure_set": "exactly_the_five_inherited_g7_tool_failure_recovery_failures",
        },
        "excluded": [
            "benchmark tasks",
            "answers",
            "hints",
            "validators",
            "raw traces",
            "results",
            "credentials",
            "network",
            "server",
            "formal evaluation",
        ],
    }
    binding_path = WORK / "repair_input_binding_002.json"
    rendered = json.dumps(binding, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    if binding_path.exists():
        if binding_path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError("G11 repair-attempt-2 binding differs")
    else:
        binding_path.write_text(rendered, encoding="utf-8")

    OUT.mkdir(exist_ok=False)
    prompt = (
        "You are G11 Implementation Meta repair attempt 2 of at most 3. Work only "
        "inside the existing candidate/ directory. The Research Revision 004 mechanism, "
        "record schema, freeform carrier, authoring policy, semantic boundary, caps, "
        "measurement plan, G7 parent, exact56/base/no-hint/1200-second protocol, and "
        "safe fallbacks are frozen. Do not reopen selection or change them. Read the "
        "mechanical finding only from repair_input_binding_002.json and the prior formal "
        "manifest only from implementation_manifest_revision_001.json. Repair F4 by "
        "adding an explicit opt-in flag to run_multi_query_baseline.py and propagating it "
        "to each run_dab_tool_agent.py child. Both runners must remain disabled by default; "
        "the future hash-bound formal launcher, not an environment default, will pass the "
        "outer flag. Add minimal synthetic no-task tests for default-off and enabled "
        "propagation, including prepare-only command construction. Do not smuggle the flag "
        "through an environment variable or silently enable G11. Do not change any G11 "
        "semantic logic, evidence rules, source parent, task selection, scoring, prompt "
        "content, no-hint input, timeout, worker count, or unrelated inherited behavior. "
        "Run all G11-focused tests and the complete candidate suite using a short basetemp. "
        "Success requires all G11 tests passing and exactly the same five inherited G7 "
        "test_tool_failure_recovery failures, with no new failure. Preserve every existing "
        "manifest and report. Write implementation_manifest_revision_002.json with exact "
        "before/after source hashes, changed-file hashes, tests, F4 resolution, remaining "
        "risks, formal_candidate=true only if repaired, and evaluation_run=false. Do not "
        "access the repository outside this workspace, the network, server, benchmark, "
        "corpus, tasks, answers, hints, validators, raw messages/tool content, traces, "
        "results, old research lines, or credentials. Do not deploy or evaluate. Saved "
        "artifacts are authoritative. The repair binding follows:\n"
        + json.dumps(binding, ensure_ascii=True, sort_keys=True)
    )
    (OUT / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [
        resolve_codex("codex"),
        "--profile",
        "deepseek-standalone-dab",
        "--model",
        "deepseek-flash",
        "exec",
        "--sandbox",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "--skip-git-repo-check",
        "--json",
        "--output-last-message",
        str(OUT / "final_raw.txt"),
        "-",
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
        raise RuntimeError("G11 Implementation repair attempt 2 failed; artifacts retained")


if __name__ == "__main__":
    main()
