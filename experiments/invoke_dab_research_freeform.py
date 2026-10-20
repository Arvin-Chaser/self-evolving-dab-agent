"""Invoke the campaign Meta model for a research prompt without provider JSON schema."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.dab_meta_runtime import meta_environment, resolve_codex, run_logged_command
from experiments.dab_roadmap_protocol import read_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--additional-context", type=Path)
    args = parser.parse_args()
    root, prompt_path, output = (path.resolve() for path in
                                 (args.campaign_root, args.prompt, args.output))
    if output.exists() or not prompt_path.is_file():
        raise SystemExit("Output must be new and prompt must exist")
    meta = read_json(root / "campaign.json")["meta_agent"]
    command = [resolve_codex(str(meta["codex"])), "--no-daemon", "-C", str(output.parent),
               "--model", str(meta["model"]), "--profile", str(meta["profile"]),
               "exec", "--sandbox", "read-only", "-c", 'approval_policy="on-request"',
               "-c", 'approvals_reviewer="auto_review"', "--skip-git-repo-check",
               "--output-last-message", str(output), "-"]
    stem = output.stem
    prompt = prompt_path.read_text(encoding="utf-8")
    if args.additional_context:
        extra = args.additional_context.resolve()
        prompt += "\n\n# Additional operational constraint\n" + extra.read_text(encoding="utf-8")
    (output.parent / f"{stem}.request_prompt.txt").write_text(prompt, encoding="utf-8")
    process = run_logged_command(
        command, cwd=output.parent, prompt=prompt,
        stdout_path=output.parent / f"{stem}.stdout.log",
        stderr_path=output.parent / f"{stem}.stderr.log",
        env=meta_environment(meta["profile"]), timeout=None,
    )
    if process.returncode != 0:
        raise SystemExit(f"Meta invocation failed: exit {process.returncode}")
    print(output)


if __name__ == "__main__":
    main()
