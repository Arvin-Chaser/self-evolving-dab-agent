"""Validate and optionally apply a meta-agent candidate patch.

The meta-agent's first interface is deliberately patch-based. This script is
the local safety gate: it checks touched paths, runs ``git apply --check``, and
only then applies the unified diff when not in dry-run mode.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from experiments.script_run_report import path_ref, utc_now_iso, write_script_run_report


DEFAULT_ALLOWED_PREFIXES = [
    "prompts/dab/",
    "adapters/runtime_observer.py",
    "adapters/feedback/",
    "experiments/analyze_agent_error.py",
    "experiments/build_evolution_task.py",
    "experiments/run_meta_agent_loop.py",
    "experiments/call_meta_agent.py",
    "experiments/apply_candidate_patch.py",
    "meta_agent/",
]

FORBIDDEN_PREFIXES = [
    ".git/",
    "legacy/",
    "logs/",
]

FORBIDDEN_EXACT = {
    ".env",
    "llm_client.py",
}

FORBIDDEN_SUBSTRINGS = [
    "ground_truth",
    "validate.py",
]


def normalize_patch_path(path_text: str) -> str | None:
    path_text = path_text.strip()
    if not path_text or path_text == "/dev/null":
        return None
    if path_text.startswith("a/") or path_text.startswith("b/"):
        path_text = path_text[2:]
    return path_text


def touched_paths_from_patch(patch_text: str) -> list[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            parts = line.split()
            for item in parts[2:4]:
                normalized = normalize_patch_path(item)
                if normalized:
                    paths.add(normalized)
        elif line.startswith("--- ") or line.startswith("+++ "):
            item = line[4:].split("\t", 1)[0]
            normalized = normalize_patch_path(item)
            if normalized:
                paths.add(normalized)
    return sorted(paths)


def is_allowed_path(path_text: str, allowed_prefixes: list[str]) -> tuple[bool, str]:
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        return False, "Patch paths must be repo-relative and cannot contain '..'."
    if path_text in FORBIDDEN_EXACT:
        return False, f"{path_text} is protected."
    if any(path_text.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return False, f"{path_text} is under a forbidden prefix."
    lowered = path_text.lower()
    if any(token in lowered for token in FORBIDDEN_SUBSTRINGS):
        return False, f"{path_text} looks like validator or ground-truth scope."
    if not any(path_text == prefix.rstrip("/") or path_text.startswith(prefix) for prefix in allowed_prefixes):
        return False, f"{path_text} is outside the allowed evolution scope."
    return True, "allowed"


def run_git_apply(repo_root: Path, patch_path: Path, check_only: bool) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "apply", "--whitespace=nowarn"]
    if check_only:
        cmd.append("--check")
    cmd.append(str(patch_path))
    return subprocess.run(
        cmd,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def apply_candidate_patch(
    candidate_dir: Path,
    patch_path: Path | None = None,
    repo_root: Path = BASE_DIR,
    allowed_prefixes: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    candidate_dir = candidate_dir.resolve()
    repo_root = repo_root.resolve()
    patch_path = (patch_path or candidate_dir / "patch.diff").resolve()
    allowed_prefixes = allowed_prefixes or DEFAULT_ALLOWED_PREFIXES
    report_path = candidate_dir / "apply_report.json"

    checks: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None

    patch_exists = patch_path.exists()
    patch_text = patch_path.read_text(encoding="utf-8", errors="replace") if patch_exists else ""
    touched_paths = touched_paths_from_patch(patch_text)

    checks.append({"name": "patch_exists", "passed": patch_exists, "message": str(patch_path)})
    checks.append({"name": "patch_nonempty", "passed": bool(patch_text.strip()), "message": str(patch_path)})
    checks.append(
        {
            "name": "patch_has_touched_paths",
            "passed": bool(touched_paths),
            "message": "Unified diff should include touched file paths.",
            "details": touched_paths,
        }
    )

    path_results = []
    for path_text in touched_paths:
        allowed, reason = is_allowed_path(path_text, allowed_prefixes)
        path_results.append({"path": path_text, "allowed": allowed, "reason": reason})
    paths_allowed = bool(touched_paths) and all(item["allowed"] for item in path_results)
    checks.append(
        {
            "name": "touched_paths_allowed",
            "passed": paths_allowed,
            "message": "Patch must stay inside the allowed evolution scope.",
            "details": path_results,
        }
    )

    apply_check = None
    applied = False
    if patch_exists and patch_text.strip() and paths_allowed:
        apply_check = run_git_apply(repo_root=repo_root, patch_path=patch_path, check_only=True)
        checks.append(
            {
                "name": "git_apply_check",
                "passed": apply_check.returncode == 0,
                "message": apply_check.stderr.strip() or apply_check.stdout.strip(),
            }
        )
        operations.append(
            {
                "name": "git_apply_check",
                "status": "completed" if apply_check.returncode == 0 else "failed",
                "outputs": {
                    "returncode": apply_check.returncode,
                    "stdout": apply_check.stdout,
                    "stderr": apply_check.stderr,
                },
            }
        )

        if apply_check.returncode == 0 and not dry_run:
            apply_result = run_git_apply(repo_root=repo_root, patch_path=patch_path, check_only=False)
            applied = apply_result.returncode == 0
            operations.append(
                {
                    "name": "git_apply",
                    "status": "completed" if applied else "failed",
                    "outputs": {
                        "returncode": apply_result.returncode,
                        "stdout": apply_result.stdout,
                        "stderr": apply_result.stderr,
                    },
                }
            )
            checks.append(
                {
                    "name": "git_apply",
                    "passed": applied,
                    "message": apply_result.stderr.strip() or apply_result.stdout.strip(),
                }
            )
            if not applied:
                error = {"type": "git_apply_failed", "message": apply_result.stderr.strip()}
        elif dry_run:
            operations.append({"name": "git_apply", "status": "skipped", "outputs": {"dry_run": True}})
    else:
        error = {"type": "patch_rejected", "message": "Patch missing, empty, or outside allowed scope."}

    status = "success" if (dry_run and all(check["passed"] for check in checks)) or applied else "failed"
    if dry_run and apply_check is not None and apply_check.returncode == 0:
        status = "success"

    apply_report = {
        "candidate_dir": str(candidate_dir),
        "repo_root": str(repo_root),
        "patch_path": str(patch_path),
        "dry_run": dry_run,
        "status": status,
        "applied": applied,
        "touched_paths": touched_paths,
        "path_results": path_results,
        "checks": checks,
        "error": error,
    }
    write_json(report_path, apply_report)

    script_report_path, _ = write_script_run_report(
        output_dir=candidate_dir,
        script_name="experiments/apply_candidate_patch.py",
        script_role="candidate_patch_gate",
        started_at=started_at,
        status=status,
        inputs=[path_ref("patch", patch_path)],
        operations=operations,
        outputs=[path_ref("apply_report", report_path)],
        checks=checks,
        self_feedback={
            "confidence": "high",
            "uncertainties": [] if status == "success" else ["Patch did not pass the local safety gate."],
            "evolution_hints": [
                "Keep meta-agent patches reviewable and inside the allowed scope.",
                "If git apply fails because the patch was already applied, run a fresh meta-agent candidate.",
            ],
            "suggested_target_modules": ["experiments/apply_candidate_patch.py"],
        },
        error=error,
        report_stem="apply_candidate_patch",
    )
    apply_report["script_run_report_path"] = str(script_report_path)
    write_json(report_path, apply_report)
    return apply_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--patch")
    parser.add_argument("--repo-root", default=str(BASE_DIR))
    parser.add_argument("--allowed-prefix", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    allowed_prefixes = args.allowed_prefix or DEFAULT_ALLOWED_PREFIXES
    result = apply_candidate_patch(
        candidate_dir=Path(args.candidate_dir),
        patch_path=Path(args.patch) if args.patch else None,
        repo_root=Path(args.repo_root),
        allowed_prefixes=allowed_prefixes,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
