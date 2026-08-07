#!/usr/bin/env python3
"""Codex-native candidate launcher for the meta-agent evolution loop.

Unlike the Qwen structured patch-spec launcher, this launcher lets Codex act as
an actual tool-using coding agent inside an isolated workspace.  The outer
runner still owns experiment safety: workspace isolation, diff extraction,
profile gates, validation, child eval handoff, and archive artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import experiments.run_codex_qwen_repair_launcher as base


CODEX_NATIVE_REPAIR_PROTOCOL_VERSION = "codex_native_long_context_usable_patch_v002"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_text(path: Path, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars] + "\n\n[TRUNCATED]\n"
    return text


def profile_scope_text(profile: base.RepairProfile) -> str:
    return "\n".join(
        [
            f"- repair_profile: `{profile.name}`",
            f"- risk_scope: `{profile.risk_scope}`",
            f"- max_changed_lines: `{profile.max_changed_lines}`",
            "- allowed file patterns:",
            *[f"  - `{item}`" for item in profile.allowed_patterns],
            "- forbidden file patterns:",
            *[f"  - `{item}`" for item in profile.forbidden_patterns],
        ]
    )


def quote(value: Path | str) -> str:
    return shlex.quote(str(value))


def codex_native_eval_instructions(
    *,
    profile: base.RepairProfile,
    candidate_dir: Path,
    parent_run: Path | None,
    repair_seed: Path | None = None,
) -> str:
    case_dir = os.environ.get("META_LOOP_CASE_DIR")
    dab_root = os.environ.get("META_LOOP_DAB_ROOT")
    parent_agent_id = os.environ.get("META_LOOP_PARENT_AGENT_ID")
    parent_prompt = os.environ.get("META_LOOP_PARENT_PROMPT")
    query_workspace = os.environ.get("META_LOOP_QUERY_WORKSPACE")
    max_iterations = os.environ.get(
        "CODEX_NATIVE_DATA_AGENT_MAX_ITERATIONS",
        os.environ.get("DAB_TOOL_AGENT_CHILD_MAX_ITERATIONS", "4"),
    )
    child_run_id = f"codex_native_inner_child_{base.utc_slug()}"
    inner_output_root = candidate_dir / "codex_native_inner_runs"
    multi_query_batch_path: Path | None = None
    multi_query_dab_root = Path("external/DataAgentBench_sparse")
    if profile.name == "multi_query_architecture_evolution" and repair_seed and repair_seed.exists():
        try:
            seed = json.loads(repair_seed.read_text(encoding="utf-8", errors="replace"))
            batch = seed.get("batch") if isinstance(seed.get("batch"), dict) else {}
            batch_id = str(seed.get("batch_id") or batch.get("batch_id") or "").strip()
            if batch_id:
                candidate_batch = ROOT / "dab_corpus" / "batches" / f"{batch_id}.json"
                if candidate_batch.exists():
                    multi_query_batch_path = Path("dab_corpus") / "batches" / f"{batch_id}.json"
            batch_dab_root = str(batch.get("dab_root") or "").strip()
            if batch_dab_root:
                multi_query_dab_root = Path(batch_dab_root)
        except Exception:
            multi_query_batch_path = None

    lines = [
        "## Codex-native self-debug loop",
        "",
        f"protocol_version: `{CODEX_NATIVE_REPAIR_PROTOCOL_VERSION}`",
        "",
        "Codex itself is the looping meta-agent. Use the long-context task window as working memory: keep the causal diagnosis, file/interface facts, failed commands, and revised hypotheses in this same task until the patch is usable or no safe patch exists.",
        "Do not stop merely because a patch compiles, and do not stop after writing a patch-like idea in text.",
        "After making a candidate edit, use your own tool calls to run the existing data-agent/evidence tools, inspect the result, and revise the patch if the child did not improve or the patch is not wired into generated behavior.",
        "The outer Python launcher is only a sandbox/archiver/final auditor; it is not the debugging loop.",
        "",
        "### Usable patch completion contract",
        "",
        "A usable patch means all conditions below are satisfied inside this same Codex task unless the environment makes a condition impossible:",
        "- A real project source diff exists in allowed files, not just a textual suggestion.",
        "- The diff can be replayed against a fresh/materialized parent baseline with `experiments/check_candidate_patch_replay.py`.",
        "- Changed Python files compile, and focused imports/checks relevant to the repair pass.",
        "- For DAB tool-agent repairs, an inner data-agent/evidence run is attempted when META_LOOP_CASE_DIR and META_LOOP_DAB_ROOT are available.",
        "- If the inner child run fails, you inspect stderr/logs and either fix the patch in this same task or explain why the failure is external to the patch with concrete file paths.",
        "- If a helper/tool/script is created or modified, generated child behavior must actually call it and use its output, not only log it.",
        "",
        "You may finish only when one of these is true:",
        "- You produced a real source diff and local checks plus an inner data-agent/evidence run indicate the repair is wired into the generated child behavior.",
        "- You produced a real source diff, replay/compile checks pass, and you explain why full child improvement could not be confirmed within the local/environment budget, with concrete evidence.",
        "- You leave the tree unchanged because no safe repair is possible, and explain the no-op reason.",
        "",
        "If an inner run shows the helper/prompt/script is not actually used by generated code, continue debugging inside this same Codex task instead of stopping.",
        "If patch replay, compile, import, or focused behavior checks fail, treat that as a repair input and revise the patch in this same Codex task instead of ending with a failed candidate.",
        "Before your final response, run the patch replay self-check below. If it fails, inspect the reported file conflicts and revise your patch in this same Codex task.",
        "",
        "### Multi-query architecture evolution",
        "",
        "If this task uses `multi_query_architecture_evolution`, do not optimize a single query in isolation.",
        "Use the multi-query evidence to identify cross-query workflow weaknesses and decide whether the candidate should be a planner, verifier, tool-use controller, schema explorer, observer, memory/performance tracker, near-miss refinement controller, helper script, prompt glue, or no-op.",
        "Before finishing, explicitly state `candidate_structure_type` and whether the patch is query-specific or cross-query reusable.",
        "",
        "### Evolvable observability / fine-grained feedback",
        "",
        "The DataAgent observability layer is part of the evolvable agent, not a fixed human-designed interface.",
        "If current parent/child behavior logs are insufficient to explain, prevent, or compare a failure, you may evolve how the DataAgent records runtime behavior.",
        "Valid observability repairs include new or changed logging/tracing/self-observation events, helper contract records, answer-dependency records, fallback-decision records, or richer parent/child behavior artifacts.",
        "Do not assume fixed observer artifact filenames or schemas; future observers read raw run directories and infer from whatever artifacts the DataAgent emits.",
        "Prefer reusable observability improvements that help future meta-agent iterations diagnose multiple queries over one-off query-specific comments.",
        "",
        "### Open self-observation evidence",
        "",
        "If the evidence pack contains `agent_self_observation_summary` or raw `agent_self_observations.jsonl`, treat those as DataAgent-authored open self-observations.",
        "Use them as high-priority causal clues, but do not reduce them to fixed analyzer labels; infer the repair layer yourself from the observations plus raw trace/tool evidence.",
        "If self-observations mention uncertainty, missing evidence, interface mismatch, unused helper output, or an intended next step that never happened, inspect the corresponding files/logs and repair the reusable workflow capability when safe.",
        "",
        "### Query workspace isolation",
        "",
        "When META_LOOP_QUERY_WORKSPACE is set, treat that query-local agent policy and helper registry as the mutable DataAgent state.",
        "Create query-specific helpers under <query_workspace>/agent/helpers and register them only in that workspace registry.",
        "Do not copy a helper or policy from another query workspace unless current trace/validation evidence independently justifies the transfer.",
        f"Active query workspace: `{query_workspace or 'legacy_global_fallback'}`",
        "",
        "### Interface-alignment observations to perform yourself",
        "",
        "- Inspect the generated child `generated_solve.py` after any inner data-agent run.",
        "- If you add a helper/tool/script, verify generated code imports it, calls it with the intended full inputs, and uses its output to construct the final answer or next workflow state.",
        "- Treat patterns such as `helper_called_but_output_not_used_for_final_answer`, passing pre-filtered data where full evidence is required, or logging-only helper use as failed wiring that needs another edit attempt.",
        "- Prefer changing the reusable helper/tool/script plus minimal prompt glue over adding more ungrounded prompt text.",
        "",
        "### Suggested existing commands",
        "",
        "Use these as templates; adapt run ids and output dirs as needed.",
        "",
        "Patch replay self-check against a fresh child baseline; this should pass before you finish:",
        "",
        "```bash",
        (
            ".venv/bin/python experiments/check_candidate_patch_replay.py "
            f"--source-root {quote(ROOT)} "
            "--candidate-workspace . "
            f"--report {quote(candidate_dir / 'codex_native_patch_replay_report.json')} "
            f"--patch-out {quote(candidate_dir / 'codex_native_patch_replay.patch')}"
            + (f" --parent-agent-id {quote(parent_agent_id)}" if parent_agent_id else "")
            + (f" --parent-prompt {quote(parent_prompt)}" if parent_prompt else "")
        ),
        "```",
    ]
    if profile.name == "multi_query_architecture_evolution" and multi_query_batch_path:
        multi_query_run_id = f"codex_native_inner_multi_query_{base.utc_slug()}"
        lines.extend(
            [
                "",
                "For multi-query architecture evolution, prefer this two-query inner child attempt before relying on a single-query smoke:",
                "",
                "```bash",
                "mkdir -p " + quote(inner_output_root),
                (
                    ".venv/bin/python experiments/run_multi_query_baseline.py "
                    f"--batch {quote(multi_query_batch_path)} "
                    "--registry dab_corpus/registry.json "
                    f"--dab-root {quote(multi_query_dab_root)} "
                    f"--output-root {quote(inner_output_root)} "
                    f"--run-id {quote(multi_query_run_id)} "
                    f"--max-iterations {quote(max_iterations)}"
                ),
                "```",
                "",
                "After this run, inspect the multi-query summary and per-query feedback:",
                "",
                "```bash",
                f"sed -n '1,220p' {quote(inner_output_root / multi_query_run_id / 'multi_query_summary.json')}",
                f"find {quote(inner_output_root / multi_query_run_id / 'runs')} -maxdepth 2 -type f | sort",
                "```",
                "",
                "If the summary shows helper_registered_but_not_called, max_iterations, empty final answers, or tool failures, keep debugging the patch in this same Codex task.",
            ]
        )

    if case_dir and dab_root and profile.name in {"data_agent_project_repair", "data_agent_tool_repair", "data_agent_prompt_repair", "multi_query_architecture_evolution"}:
        lines.extend(
            [
                "",
                "Run a child data-agent attempt from this isolated workspace:",
                "",
                "```bash",
                "mkdir -p " + quote(inner_output_root),
                (
                    ".venv/bin/python experiments/run_dab_tool_agent.py "
                    f"--dab-data-root {quote(dab_root)} "
                    f"--query-dir {quote(case_dir)} "
                    f"--output-root {quote(inner_output_root)} "
                    f"--run-id {quote(child_run_id)} "
                    f"--max-iterations {quote(max_iterations)}"
                ),
                "```",
                "",
                "Then analyze its trace/fine-grained feedback:",
                "",
                "```bash",
                (
                    ".venv/bin/python experiments/analyze_dab_tool_agent_trace.py "
                    f"--run-dir {quote(inner_output_root / child_run_id)} "
                    f"--output-dir {quote(inner_output_root / child_run_id)}"
                ),
                "```",
                "",
                "Useful follow-up inspections:",
                "",
                "```bash",
                f"sed -n '1,260p' {quote(inner_output_root / child_run_id / 'generated_solve.py')}",
                f"find {quote(inner_output_root / child_run_id)} -maxdepth 2 -type f | sort",
                "git diff --stat",
                "git diff --check",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "- The loop did not provide META_LOOP_CASE_DIR/META_LOOP_DAB_ROOT, so do focused local checks and inspect parent evidence instead of a full child run.",
            ]
        )
    if parent_run:
        lines.extend(
            [
                "",
                "Parent evidence run available for comparison:",
                f"- `{parent_run}`",
            ]
        )
    return "\n".join(lines)


def script_first_policy_text(profile: base.RepairProfile) -> str:
    if profile.name not in {"data_agent_project_repair", "data_agent_tool_repair", "data_agent_prompt_repair", "multi_query_architecture_evolution"}:
        return ""
    return "\n".join([
        "## Script-first repair policy",
        "",
        "You are not a prompt-only optimizer. For DAB tool-agent evolution, first ask whether the failure can be addressed by an executable capability that the DataAgent can actually use.",
        "",
        "Preferred repair order:",
        "1. Reusable helper/script/tool capability, plus minimal registration/glue so it is visible to the DataAgent workflow.",
        "2. Runner/tool-schema/workflow-observer changes that make existing capabilities usable or produce better evidence for future iterations.",
        "3. Analyzer/evidence-pack changes that expose open observations without deciding the repair target for the meta-agent.",
        "4. Prompt/policy edits only as glue for a concrete capability, or when you can explain why an executable repair is unnecessary or unsafe.",
        "",
        "If you create or modify a helper/script/tool, wire it into the active path in the same patch. Do not merely append an unused function.",
        "",
        "For multi-query architecture evolution, every candidate must declare one `candidate_structure_type`: helper_script, workflow_controller, planner, verifier, memory, observer, tool_policy, schema_explorer, near_miss_refinement_controller, performance_tracker, architecture_refactor, prompt_glue, or no_op.",
        "Prefer changes that create reusable DataAgent structure when multiple query failures share the same workflow weakness.",
        "If your final patch is prompt-only, explicitly include `why_not_script_first` in your final response: explain why no helper/script/tool/runner repair was the right minimal move for this evidence.",
        "If the evidence is too weak to choose a helper, improve generic logging/observer/evidence plumbing rather than adding benchmark-specific prompt text.",
        "If the repair seed contains `evidence_sufficiency.status=insufficient` or `feedback_evolution_opportunity=true`, treat observer/trace/feedback-pipeline evolution as the preferred next repair target unless you can prove the evidence is already sufficient from raw artifacts.",
        "If `evidence_sufficiency.missing_evidence_diagnostic_tasks` is present, use it as a required diagnostic checklist: identify producer path, preservation path, and consumer path for each missing artifact before selecting files to edit.",
        "Do not satisfy evidence insufficiency by only improving analyzer interpretation when the missing artifact is not produced or preserved by the runtime/eval path.",
        "For such cases, prefer a candidate_structure_type of `observer`, `workflow_controller`, `tool_policy`, or `architecture_refactor` over another query-specific helper.",
        "",
        "Near-miss refinement policy:",
        "- If the repair seed/context pack says `repair_mode.active=true` and `mode=near_miss_refinement`, treat the task as a targeted boundary repair.",
        "- Inspect why the current reusable helper/workflow excludes the missing-code samples and includes the extra-code samples; do not restart with a broad parser rewrite.",
        "- Use missing/extra samples as diagnostic evidence only. Do not hardcode the exact expected answer list, and do not blindly append/remove those samples without a generalizable rule.",
        "- Prefer small helper/filter/ranking/tie-breaker edits plus minimal prompt glue, then rerun child/evidence checks to compare missing/extra counts.",
        "",
    ])


def build_codex_task_prompt(
    *,
    profile: base.RepairProfile,
    context_path: Path,
    candidate_dir: Path,
    repair_seed: Path | None,
    parent_run: Path | None,
) -> Path:
    lines = [
        "# Codex-native Meta-Agent Repair Task",
        "",
        "You are Codex acting as the project meta-agent for this DAB/DataAgentBench evolution loop.",
        "Unlike the structured Qwen patch-spec mode, you may inspect files, edit files, and run focused local checks inside this isolated workspace.",
        "Continue working until you have either produced a minimal real project patch or determined that no safe patch is possible.",
        "",
        "## Non-negotiable experiment boundaries",
        "",
        "- This is an isolated candidate workspace. Do not merge anything into the main project.",
        "- Modify only files allowed by the repair profile below.",
        "- Do not edit logs, candidates, archive, trajectories, reports, benchmarks, data files, virtualenvs, pycache, or git metadata.",
        "- Do not hardcode benchmark answers, exact expected counts, or ground-truth output lists.",
        "- Prefer a small, reusable executable project repair. For DAB tool-agent zero-start evidence, prefer helper/tool/script/runner/observer capability plus minimal prompt glue over standalone prompt text.",
        "- `generated_solve.py` and run logs are evidence only, not patch targets.",
        "- If no safe minimal repair is possible, leave the source tree unchanged and explain why in your final message.",
        "",
        "## Repair profile",
        "",
        profile_scope_text(profile),
        "",
        script_first_policy_text(profile),
        "## Required workflow",
        "",
        "1. Read the context pack below and identify the causal failure layer. Prioritize DataAgent-authored open self-observations when present, while treating analyzer selected_stage/selected_signal as weak context only.",
        "2. Check `evidence_sufficiency` if present. If it is insufficient, first perform producer-path root-cause search: who should produce each missing artifact, who should preserve it, and who consumes it next?",
        "3. If the missing evidence is runtime/stdout/stderr/tool-list/helper-call trace, patch the runtime/eval producer or preservation path before patching analyzer interpretation. Synthetic analyzer-only tests are not enough.",
        "4. Before editing prompt text, inspect whether a reusable helper/script/tool/runner/observer repair can address the failure more directly. If not, keep a concrete why-not-script-first rationale.",
        "5. Inspect only the files needed to make a minimal repair.",
        "6. Make real source edits in the workspace if a safe repair exists.",
        "7. Run focused checks proportional to the change. At minimum, run `python -m py_compile` on changed Python files when applicable.",
        "8. Use the Codex-native self-debug loop below: run the relevant existing data-agent/evidence commands, inspect generated child behavior, and revise if your patch is not actually wired into the child.",
        "9. Keep iterating within this same Codex task after any patch replay, compile, interface, or child-run failure. Do not hand back a known-broken patch unless the failure is clearly external and documented.",
        "10. If you create or modify `adapters/dab_tool_agent_helpers`, ensure `registry.py` uses entries with `name`, `function`, `description`, and `input_contract`, and helper functions accept `(payload, inputs)`.",
        "11. Do not spend time on broad refactors. If the task is not safely repairable, no-op rather than fabricating a patch.",
        "",
        codex_native_eval_instructions(profile=profile, candidate_dir=candidate_dir, parent_run=parent_run, repair_seed=repair_seed),
        "",
        "## Final response format",
        "",
        "End with a concise summary containing:",
        "- changed files",
        "- script/tool/runner capability attempted, or `why_not_script_first` if the patch is prompt-only",
        "- self-debug attempts made after the first patch",
        "- tests/checks run, including patch replay result when possible",
        "- whether this is intended as a candidate for child eval",
        "- any known risks or reasons for no-op",
        "",
        "## Artifact paths",
        "",
        f"- candidate_dir: `{candidate_dir}`",
        f"- repair_seed: `{repair_seed}`" if repair_seed else "- repair_seed: none",
        f"- parent_run: `{parent_run}`" if parent_run else "- parent_run: none",
        f"- context_pack: `{context_path}`",
        "",
        "## Context pack",
        "",
        "```markdown",
        read_text(context_path, 120000),
        "```",
        "",
    ]
    out = candidate_dir / "codex_native_task_prompt.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def run_codex_exec(*, workspace: Path, prompt_path: Path, candidate_dir: Path) -> subprocess.CompletedProcess[str]:
    final_message = candidate_dir / "codex_native_final_message.txt"
    stdout_path = candidate_dir / "codex_native.stdout"
    stderr_path = candidate_dir / "codex_native.stderr"
    run_info_path = candidate_dir / "codex_native_run.json"

    command = ["codex"]
    profile = os.environ.get("CODEX_NATIVE_PROFILE")
    model = os.environ.get("CODEX_NATIVE_MODEL")
    sandbox = os.environ.get("CODEX_NATIVE_SANDBOX", "workspace-write")
    approval = os.environ.get("CODEX_NATIVE_APPROVAL", "never")
    timeout = int(os.environ.get("CODEX_NATIVE_TIMEOUT_SEC", "1800"))
    if profile:
        command.extend(["--profile", profile])
    if model:
        command.extend(["--model", model])
    command.extend([
        "--sandbox",
        sandbox,
        "-a",
        approval,
        "exec",
        "--skip-git-repo-check",
        "--output-last-message",
        str(final_message),
        "-",
    ])
    prompt = read_text(prompt_path)
    started_at = utc_now()
    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8", errors="replace")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8", errors="replace")
        write_json(
            run_info_path,
            {
                "backend": "codex_native",
                "status": "timeout",
                "timeout_sec": timeout,
                "started_at": started_at,
                "command": command,
                "workspace": str(workspace),
                "final_message": str(final_message),
            },
        )
        return subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "")

    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    write_json(
        run_info_path,
        {
            "backend": "codex_native",
            "status": "completed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "exit_code": proc.returncode,
            "command": command,
            "workspace": str(workspace),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "final_message": str(final_message),
        },
    )
    return proc


def write_codex_native_metadata(candidate_dir: Path, profile: base.RepairProfile, codex_proc: subprocess.CompletedProcess[str]) -> None:
    """Write a compatibility metadata file for validation helpers reused from the structured launcher."""

    final_message_path = candidate_dir / "codex_native_final_message.txt"
    final_message = read_text(final_message_path, 20000) if final_message_path.exists() else ""
    write_json(
        candidate_dir / "validated_patch_spec.json",
        {
            "status": "codex_native_patch",
            "repair_profile": profile.name,
            "risk_scope": profile.risk_scope,
            "edits": [],
            "proposed_contracts": [],
            "public_functions_to_preserve": list(profile.required_public_functions),
            "forbidden_actions_ack": {key: True for key in profile.required_ack},
            "codex_native": {
                "exit_code": codex_proc.returncode,
                "final_message_path": str(final_message_path),
                "final_message_excerpt": final_message[:4000],
            },
        },
    )


def run_launcher(args: argparse.Namespace) -> int:
    profile = base.PROFILES[args.repair_profile]
    candidate_id = args.candidate_id or os.environ.get("META_LOOP_CANDIDATE_ID") or f"codex_native_{profile.name}_{base.utc_slug()}"
    candidate_dir = Path(args.candidate_dir or os.environ.get("META_LOOP_CANDIDATE_DIR") or ROOT / "candidates/dab" / candidate_id)
    candidate_dir.mkdir(parents=True, exist_ok=True)

    gate_protocol = base.profile_gate_protocol(profile)
    write_json(candidate_dir / "gate_protocol.json", gate_protocol)
    write_json(
        candidate_dir / "codex_native_repair_protocol.json",
        {
            "protocol_version": CODEX_NATIVE_REPAIR_PROTOCOL_VERSION,
            "mode": "long_context_usable_patch_contract",
            "intent": "Codex should keep debugging within one repair task until it has a real replayable/compilable candidate patch or a concrete no-op reason.",
            "default_timeout_sec": int(os.environ.get("CODEX_NATIVE_TIMEOUT_SEC", "1800")),
        },
    )

    repair_seed = Path(args.repair_seed or os.environ.get("META_LOOP_REPAIR_SEED", "")) if (args.repair_seed or os.environ.get("META_LOOP_REPAIR_SEED")) else None
    repair_seed_override = os.environ.get("META_LOOP_REPAIR_SEED_OVERRIDE") == "1"
    parent_run = Path(args.parent_run or os.environ.get("META_LOOP_PARENT_RUN", "")) if (args.parent_run or os.environ.get("META_LOOP_PARENT_RUN")) else None
    parent_prompt = Path(args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT", "")) if (args.parent_prompt or os.environ.get("META_LOOP_PARENT_PROMPT")) else None
    parent_agent_id = os.environ.get("META_LOOP_PARENT_AGENT_ID")
    if parent_prompt is None and profile.name in {"data_agent_prompt_repair", "data_agent_project_repair", "data_agent_tool_repair", "multi_query_architecture_evolution"}:
        parent_prompt = Path("prompts/dab/dab_code_agent_prompt_v005_runtime_observer.txt")

    workspace = base.make_workspace(candidate_dir)
    base.materialize_parent_source_patch(profile=profile, workspace=workspace, candidate_dir=candidate_dir, parent_agent_id=parent_agent_id)
    parent_prompt = base.materialize_parent_prompt(profile=profile, workspace=workspace, candidate_dir=candidate_dir, parent_prompt=parent_prompt)
    context = base.build_context_pack(
        profile=profile,
        workspace=workspace,
        candidate_dir=candidate_dir,
        repair_seed=repair_seed,
        parent_run=parent_run,
        parent_prompt=parent_prompt,
        repair_seed_override=repair_seed_override,
    )
    prompt = build_codex_task_prompt(
        profile=profile,
        context_path=context,
        candidate_dir=candidate_dir,
        repair_seed=repair_seed,
        parent_run=parent_run,
    )

    proc = run_codex_exec(workspace=workspace, prompt_path=prompt, candidate_dir=candidate_dir)
    write_codex_native_metadata(candidate_dir, profile, proc)

    diff_info = base.diff_artifacts(workspace, candidate_dir)
    if not (candidate_dir / "patch.diff").read_text(encoding="utf-8", errors="replace").strip():
        base.write_manifest(
            candidate_dir,
            {
                "candidate_id": candidate_id,
                "status": "no_op_failed" if proc.returncode == 0 else "patch_apply_failed",
                "reason": "Codex-native run produced no source diff" if proc.returncode == 0 else f"Codex-native run failed with exit code {proc.returncode} and produced no source diff",
                "repair_profile": profile.name,
                "profile_gate_version": gate_protocol["profile_gate_version"],
                "gate_protocol": gate_protocol,
                "workspace": str(workspace),
                "codex_native_exit_code": proc.returncode,
                "codex_native_protocol_version": CODEX_NATIVE_REPAIR_PROTOCOL_VERSION,
                **diff_info,
            },
        )
        return 20 if proc.returncode == 0 else 71

    gate_ok, gate_status, gate_reason = base.post_apply_gate(profile, workspace, candidate_dir, diff_info)
    if not gate_ok:
        base.write_manifest(
            candidate_dir,
            {
                "candidate_id": candidate_id,
                "status": gate_status,
                "reason": gate_reason,
                "repair_profile": profile.name,
                "profile_gate_version": gate_protocol["profile_gate_version"],
                "gate_protocol": gate_protocol,
                "workspace": str(workspace),
                "codex_native_exit_code": proc.returncode,
                "codex_native_protocol_version": CODEX_NATIVE_REPAIR_PROTOCOL_VERSION,
                **diff_info,
            },
        )
        return 72

    validation_ok, validation_results = base.run_validation(profile, workspace, candidate_dir, repair_seed=repair_seed)
    final_status = "valid_candidate_pending_child_eval" if validation_ok else "failed_validation"
    base.write_manifest(
        candidate_dir,
        {
            "candidate_id": candidate_id,
            "status": final_status,
            "repair_profile": profile.name,
            "profile_gate_version": gate_protocol["profile_gate_version"],
            "gate_protocol": gate_protocol,
            "workspace": str(workspace),
            "codex_native_exit_code": proc.returncode,
            "codex_native_protocol_version": CODEX_NATIVE_REPAIR_PROTOCOL_VERSION,
            "project_changed_files": [path for path in diff_info["changed_files"] if base.is_allowed_file(path, profile)],
            "total_changed_lines": diff_info["total_changed_lines"],
            "patch_numstat": diff_info["patch_numstat"],
            "post_apply_gate_status": gate_status,
            "validation_results": validation_results,
            "scope_note": "Codex-native meta-agent repair; feedback/child-eval still decide promotion, not Codex final text.",
        },
    )
    return 0 if validation_ok else 80


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-profile", choices=sorted(base.PROFILES), default=os.environ.get("REPAIR_PROFILE", "data_agent_project_repair"))
    parser.add_argument("--candidate-id")
    parser.add_argument("--candidate-dir")
    parser.add_argument("--repair-seed")
    parser.add_argument("--parent-run")
    parser.add_argument("--parent-prompt")
    parser.set_defaults(func=run_launcher)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
