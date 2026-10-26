#!/usr/bin/env python3
"""Launch the frozen six-task G11-G13 integrated engineering panel."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments import run_multi_query_baseline


PANEL_RELATIVE = Path("experiments/g011_g013_integrated_small_panel_20261022")
INTEGRATED_RUNNER_RELATIVE = Path("experiments/run_dab_tool_agent_g011_g013_integrated.py")

# These bindings come from the frozen protocol and freeze manifest. The batch
# launcher fails closed if the reviewed candidate or selected panel drifts.
FROZEN_SHA256 = {
    Path("experiments/g011_g013_integrated_agent.py"): "c16b09d13f30acb8aa6539d7993d1c9cf30f94f75f0b430371d1449fd60f79a7",
    Path("experiments/run_dab_tool_agent.py"): "d9f5b037e0974a44bc7cf95e8e94022df46799ca2dbd1e364931570b10bc6023",
    Path("experiments/run_multi_query_baseline.py"): "a0ab044f307e736a2941846d0c69790eab727cc09cbe9834e775508741c0e6c3",
    INTEGRATED_RUNNER_RELATIVE: "bedb1aa93b3c3c0eba539168009f317c18226aa1b2d7de30be847bb186cde9af",
    Path("experiments/analyze_dab_tool_agent_trace.py"): "7098732c74b00c063d1d63c9c77436a18822d5e2e9f18009324f977cdaed3e4c",
    Path("experiments/build_dab_tool_agent_evidence_pack.py"): "8f00fc5a7850b2943773ab9ba74d21eb5c133ff3366c51a423d5f3b111c9ce85",
    Path("prompts/dab/dab_tool_agent_policy_g011_g013_integrated.txt"): "869cfa801d785f07b5af1a853c68b0dd8d5ace8c7168f55182ce600780bb0dfb",
    PANEL_RELATIVE / "operational_batch.json": "7f00732f7811c441f5127f78f7b931d8fb3635218637bf9b88fe59b9aee30978",
    PANEL_RELATIVE / "protocol.json": "4d941b9d1ffb736cc967cbb0fbba2e1205df77d8ca673a268e83cb110ac01035",
    PANEL_RELATIVE / "freeze_manifest.json": "c09f2577f587e654f9aabe5aa3dcc1c28a202962432f87336045c31ae3eff0c1",
    PANEL_RELATIVE / "anonymous_task_manifest.json": "af8ceffdb56bdd33e9dbe57edda9d4d741521cbea00eb5a17a8f1c4adb8d3aa9",
    PANEL_RELATIVE / "runtime_repair_001.json": "c8d405aa9abb190e20eb62081bf0be14287bcc79455a3313b7603f300342a1a0",
    PANEL_RELATIVE / "runtime_repair_002.json": "0f289e1ecc7cefaaa25e80f826074405f9355a15ad799e84728b4beef571d2e7",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_frozen_inputs(source_root: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative_path, expected in FROZEN_SHA256.items():
        path = source_root / relative_path
        if not path.is_file():
            raise SystemExit(f"Frozen panel input missing: {path}")
        digest = sha256_file(path)
        if digest != expected:
            raise SystemExit(
                f"Frozen panel input changed: {relative_path.as_posix()} "
                f"(expected {expected}, observed {digest})"
            )
        observed[relative_path.as_posix()] = digest
    return observed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--dab-root", type=Path, required=True)
    parser.add_argument("--dab-upstream-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--skip-docker-check", action="store_true")
    parser.add_argument("--skip-postgres-check", action="store_true")
    return parser


def build_baseline_argv(args: argparse.Namespace, source_root: Path) -> list[str]:
    panel_dir = source_root / PANEL_RELATIVE
    argv = [
        "--source-root", str(source_root),
        "--batch", str(panel_dir / "operational_batch.json"),
        "--tool-agent-runner", str(INTEGRATED_RUNNER_RELATIVE),
        "--tool-agent-runner-module", "experiments.run_dab_tool_agent_g011_g013_integrated",
        "--batch-launcher", str(Path(__file__).resolve()),
        "--max-iterations", "0",
        "--llm-timeout", "600",
        "--llm-retries", "1",
        "--llm-retry-sleep", "0",
        "--client-max-retries", "0",
        "--deployment-name", "deepseek-flash",
        "--openai-compatible-base-url", "https://api.deepseek.com/v1",
        "--openai-compatible-api-key-env", "DEEPSEEK_API_KEY",
        "--query-timeout-sec", "1200",
        "--postgres-statement-timeout-ms", "300000",
        "--bootstrap-databases",
        "--database-bootstrap-timeout-sec", "2400",
        "--workers", "1",
        "--skip-observer",
        "--operational-only",
        "--stop-on-query-error",
    ]
    path_options = (
        ("--registry", args.registry),
        ("--dab-root", args.dab_root),
        ("--dab-upstream-root", args.dab_upstream_root),
        ("--output-root", args.output_root),
        ("--python", args.python),
    )
    for option, value in path_options:
        if value is not None:
            argv.extend([option, str(value)])
    argv.extend(["--run-id", args.run_id])
    for enabled, option in (
        (args.prepare_only, "--prepare-only"),
        (args.skip_docker_check, "--skip-docker-check"),
        (args.skip_postgres_check, "--skip-postgres-check"),
    ):
        if enabled:
            argv.append(option)
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.prepare_only and (args.skip_docker_check or args.skip_postgres_check):
        parser.error("database checks may be skipped only for provider-free --prepare-only verification")
    source_root = args.source_root.resolve()
    if source_root != ROOT.resolve():
        parser.error("--source-root must be the checkout containing this dedicated launcher")
    imported_batch_runner = Path(run_multi_query_baseline.__file__).resolve()
    expected_batch_runner = source_root / "experiments/run_multi_query_baseline.py"
    if imported_batch_runner != expected_batch_runner:
        raise SystemExit(
            f"Imported batch runner mismatch: expected {expected_batch_runner}, observed {imported_batch_runner}"
        )
    validate_frozen_inputs(source_root)
    return run_multi_query_baseline.main(build_baseline_argv(args, source_root))


if __name__ == "__main__":
    raise SystemExit(main())
