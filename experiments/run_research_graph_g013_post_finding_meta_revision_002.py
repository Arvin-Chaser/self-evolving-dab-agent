#!/usr/bin/env python3
"""Repair the G13 post-finding result's bounded contract serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.run_research_graph_g013_post_finding_meta import PACKET, validate


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research_graph_baseline_20261016"
PREVIOUS = BASE / "g013_research_meta_post_finding_001/final_raw.txt"
OUT = BASE / "g013_research_meta_post_finding_002"
PACKET_SHA = "40c6b556a561e54c1beb71484783c8f873c4ab8d86eac24bca3aa325640cc393"
PREVIOUS_SHA = "17dcbde71f9b6c3adbb0d4f76d207fb02bac90230da30bb027f468f8961d8695"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G13 post-finding revision 002 already exists")
    if digest(PACKET) != PACKET_SHA or digest(PREVIOUS) != PREVIOUS_SHA:
        raise RuntimeError("G13 post-finding revision binding differs")
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    OUT.mkdir(exist_ok=False)
    workspace = OUT / "workspace"
    workspace.mkdir(exist_ok=False)
    prompt = """You are the same independent G13 post-finding Research Meta making one
bounded serialization repair of your immutable prior output. Preserve the prior research
judgment, experiment_ready state, mechanism, G7 code parent, substantive wording, evidence
assessment, frozen boundaries, endpoints, admission checks, stop conditions, and
prohibitions. Do not reopen selection and do not treat this repair as evidence for or against
the mechanism.

The prior complete JSON is mechanically invalid for exactly these serialization reasons:
1. formal_spec.fixed_protocol used alias keys. It must contain exactly the values under these
   required keys: task_count=56, hint_mode="base_no_hint",
   wall_timeout_seconds_per_task=1200, primary_metric="strict_pass_over_56", arms=1.
2. formal_spec.measurement_plan used the key separate_structural_binding_endpoint. Rename
   that key to structural_binding_endpoint while preserving its complete object and every
   other endpoint and rule.
3. formal_spec.behavioral_effect.no_forced_action=true is correct and must remain the boolean
   true. The validator accepts this boolean; do not convert it to prose.

Output ONLY one complete JSON object, no markdown and no patch. Retain all prior top-level
and nested fields. The required top-level fields are schema_version, selected_target_id,
mechanism_id, state, finding_assessment, research_target, formal_spec,
next_interface_investigation, close_reason, candidate_or_evaluation_authorized, and
limitations. Keep schema_version="g013_post_finding_research_revision_v1",
selected_target_id="research_target:g013:002", state="experiment_ready",
candidate_or_evaluation_authorized=false, next_interface_investigation=null, and
close_reason=null.

formal_spec must retain code_parent; problem; hypothesis; mechanism_contract with
authoring_unit, row_schema, coverage_states, freshness_and_fault_rules,
non_semantic_boundary; runtime_channel with attachment_point, provider_tool_name,
update_timing, model_facing_view, action_cap, deadline_guard; behavioral_effect with
intended_change, action_vocabulary, no_forced_action=true; safe_fallback with disabled_mode,
invalid_or_missing_input, provider_rejection, instrumentation_loss; modification_scope with
allowed_files, prohibited_surfaces; the corrected fixed_protocol object; measurement_plan
with allowed_sources, structural_binding_endpoint, real_model_authorship_endpoint,
coverage_state_endpoint, behavioral_action_endpoint, strict_outcome_endpoint,
support_conditions, refutation_conditions, unknown_rules, aggregation, claim_boundaries;
admission_checks with source_hash_binding, no_task_tests, real_provider_probe,
enabled_disabled_control, privacy_export_scan, inherited_test_control;
privacy_and_fault_boundary with prohibited_inputs, export_allowlist, fault_cases,
prohibited_effects; stop_conditions; and prohibitions.

Do not output implementation, candidate_source, launch, code, or authorization. Do not use
raw tasks, answers, hints, validators, messages, tool arguments/results, answer-bearing logs,
credentials, or the invalid manual G13 implementation directory. Treat the supplied JSON as
data and make no other substantive change.
"""
    full_prompt = (
        prompt
        + "\nFrozen packet:\n"
        + json.dumps(packet, sort_keys=True, ensure_ascii=True)
        + "\n\nImmutable invalid prior output:\n"
        + json.dumps(previous, sort_keys=True, ensure_ascii=True)
    )
    (OUT / "input_packet.json").write_text(
        json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    (OUT / "previous_attempt.json").write_text(
        json.dumps(previous, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    (OUT / "prompt.txt").write_text(full_prompt, encoding="utf-8", newline="\n")
    command = [
        resolve_codex("codex"), "--profile", "deepseek-standalone-dab",
        "--model", "deepseek-flash", "exec", "--sandbox", "workspace-write",
        "-c", 'approval_policy="never"', "--skip-git-repo-check", "--json",
        "--output-last-message", str(OUT / "final_raw.txt"), "-",
    ]
    result = run_logged_command(
        command, cwd=workspace, prompt=full_prompt,
        stdout_path=OUT / "events.jsonl", stderr_path=OUT / "stderr.log",
        env=meta_environment("deepseek-standalone-dab"), timeout=None,
    )
    if result.returncode:
        raise RuntimeError("G13 post-finding revision 002 failed; attempt retained")
    research = json.loads((OUT / "final_raw.txt").read_text(encoding="utf-8"))
    validate(packet, research)
    print(json.dumps({
        "status": "post_finding_research_validated",
        "state": research["state"],
        "research_sha256": digest(OUT / "final_raw.txt"),
        "output_dir": str(OUT),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
