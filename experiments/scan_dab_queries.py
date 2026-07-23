#!/usr/bin/env python3
"""Scan a local DataAgentBench checkout into a query registry.

The upstream DAB repository is organized by domain directories such as
`query_PATENTS/`, each containing shared domain files, `query_dataset/`, and
per-case directories like `query1/`, `query2/`, ... .

This scanner converts that raw layout into project-local corpus metadata used
by the meta-agent evolution loop:

* `dab_corpus/registry.json` for scripts
* `dab_corpus/registry.md` for human inspection
* `dab_corpus/splits/{train,dev,heldout}.json` for early multi-query batches

It deliberately separates query-definition readiness from dataset
materialization. The GitHub zip often contains query prompts/validators but not
large database files listed in `dataset_manifest.tsv`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAB_ROOT = ROOT / "external" / "DataAgentBench"
DEFAULT_OUTPUT_ROOT = ROOT / "dab_corpus"


DATASET_FILE_SUFFIXES = {
    ".db",
    ".duckdb",
    ".sql",
    ".bson",
    ".json",
    ".jsonl",
    ".csv",
    ".tsv",
    ".parquet",
    ".sqlite",
}


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    sha256: str | None
    expected_size_bytes: int | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path, max_chars: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if max_chars is None else text[:max_chars]


def load_json_or_text(path: Path) -> tuple[Any | None, str]:
    text = read_text(path)
    if not text:
        return None, ""
    try:
        return json.loads(text), text
    except json.JSONDecodeError:
        return None, text


def parse_dataset_manifest(dab_root: Path) -> dict[str, ManifestEntry]:
    manifest_path = dab_root / "dataset_manifest.tsv"
    entries: dict[str, ManifestEntry] = {}
    if not manifest_path.exists():
        return entries
    for line in read_text(manifest_path).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        relative_path = parts[0].strip()
        sha256 = parts[1].strip() or None
        try:
            expected_size = int(parts[2])
        except ValueError:
            expected_size = None
        entries[relative_path] = ManifestEntry(relative_path, sha256, expected_size)
    return entries


def query_sort_key(path: Path) -> tuple[int, str]:
    match = re.fullmatch(r"query(\d+)", path.name)
    if match:
        return int(match.group(1)), path.name
    return 10**9, path.name


def domain_name(domain_dir: Path) -> str:
    name = domain_dir.name
    return name.removeprefix("query_")


def list_query_dirs(domain_dir: Path) -> list[Path]:
    dirs = []
    for child in domain_dir.iterdir():
        if not child.is_dir():
            continue
        if re.fullmatch(r"query\d+", child.name):
            dirs.append(child)
    return sorted(dirs, key=query_sort_key)


def list_dataset_files(dataset_dir: Path, dab_root: Path) -> list[dict[str, Any]]:
    if not dataset_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(dataset_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in DATASET_FILE_SUFFIXES:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        rows.append(
            {
                "path": rel(path, dab_root),
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": size,
            }
        )
    return rows


def expected_dataset_entries(domain_dir: Path, manifest: dict[str, ManifestEntry], dab_root: Path) -> list[dict[str, Any]]:
    prefix = rel(domain_dir, dab_root).rstrip("/") + "/query_dataset/"
    rows = []
    for relative_path, entry in sorted(manifest.items()):
        if not relative_path.startswith(prefix):
            continue
        actual_path = dab_root / relative_path
        actual_size = actual_path.stat().st_size if actual_path.exists() and actual_path.is_file() else None
        size_matches = (
            actual_size == entry.expected_size_bytes
            if actual_size is not None and entry.expected_size_bytes is not None
            else False
        )
        rows.append(
            {
                "path": relative_path,
                "sha256": entry.sha256,
                "expected_size_bytes": entry.expected_size_bytes,
                "present": actual_path.exists(),
                "actual_size_bytes": actual_size,
                "size_matches_manifest": size_matches,
            }
        )
    return rows


def dataset_status(expected_rows: list[dict[str, Any]], discovered_rows: list[dict[str, Any]]) -> str:
    if expected_rows:
        if all(row.get("present") and row.get("size_matches_manifest") for row in expected_rows):
            return "materialized_complete"
        if any(row.get("present") for row in expected_rows):
            return "materialized_incomplete"
        return "manifest_expected_files_missing"
    if discovered_rows:
        return "discovered_without_manifest"
    return "no_dataset_files_detected"


def classify_data_modalities(dataset_rows: list[dict[str, Any]], expected_rows: list[dict[str, Any]]) -> list[str]:
    suffixes = {str(row.get("suffix") or "").lower() for row in dataset_rows}
    for row in expected_rows:
        suffixes.add(Path(str(row.get("path") or "")).suffix.lower())
    modalities = []
    if suffixes & {".db", ".sqlite"}:
        modalities.append("sqlite")
    if ".duckdb" in suffixes:
        modalities.append("duckdb")
    if ".sql" in suffixes:
        modalities.append("sql")
    if suffixes & {".json", ".jsonl", ".csv", ".tsv", ".parquet"}:
        modalities.append("files")
    if ".bson" in suffixes:
        modalities.append("bson")
    return modalities or ["unknown"]


def scan_case(domain_dir: Path, query_dir: Path, dab_root: Path, manifest: dict[str, ManifestEntry]) -> dict[str, Any]:
    domain = domain_name(domain_dir)
    query_json_path = query_dir / "query.json"
    query_value, query_text_raw = load_json_or_text(query_json_path)
    if isinstance(query_value, str):
        query_text = query_value
    elif isinstance(query_value, dict):
        query_text = str(query_value.get("query") or query_value.get("question") or query_value)[:2000]
    else:
        query_text = query_text_raw.strip().strip('"')

    has_query = bool(query_text.strip())
    has_validator = (query_dir / "validate.py").exists()
    has_ground_truth = (query_dir / "ground_truth.csv").exists()
    domain_has_db_config = (domain_dir / "db_config.yaml").exists()
    domain_has_description = (domain_dir / "db_description.txt").exists()
    domain_has_hint_description = (domain_dir / "db_description_withhint.txt").exists()
    dataset_dir = domain_dir / "query_dataset"
    discovered_dataset = list_dataset_files(dataset_dir, dab_root)
    expected_dataset = expected_dataset_entries(domain_dir, manifest, dab_root)
    materialization = dataset_status(expected_dataset, discovered_dataset)

    missing_definition = []
    if not has_query:
        missing_definition.append("query.json")
    if not has_validator:
        missing_definition.append("validate.py")
    if not has_ground_truth:
        missing_definition.append("ground_truth.csv")
    if not domain_has_db_config:
        missing_definition.append("domain/db_config.yaml")
    if not domain_has_description:
        missing_definition.append("domain/db_description.txt")

    definition_status = "definition_ready" if not missing_definition else "definition_incomplete"
    runnable_status = (
        "runnable_if_dataset_available"
        if definition_status == "definition_ready"
        else "not_runnable_missing_definition"
    )
    if materialization not in {"materialized_complete", "discovered_without_manifest"}:
        runnable_status = "not_runnable_dataset_incomplete"

    query_id = f"{domain}/{query_dir.name}"
    return {
        "query_id": query_id,
        "domain": domain,
        "domain_dir": rel(domain_dir, ROOT),
        "query_dir": rel(query_dir, ROOT),
        "upstream_domain_dir": rel(domain_dir, dab_root),
        "upstream_query_dir": rel(query_dir, dab_root),
        "query_name": query_dir.name,
        "query_number": query_sort_key(query_dir)[0],
        "query_text": query_text,
        "query_text_preview": re.sub(r"\s+", " ", query_text).strip()[:240],
        "definition_status": definition_status,
        "missing_definition_files": missing_definition,
        "runnable_status": runnable_status,
        "dataset_materialization_status": materialization,
        "has_query_json": has_query,
        "has_validator": has_validator,
        "has_ground_truth": has_ground_truth,
        "domain_has_db_config": domain_has_db_config,
        "domain_has_description": domain_has_description,
        "domain_has_hint_description": domain_has_hint_description,
        "dataset_dir": rel(dataset_dir, ROOT),
        "data_modalities": classify_data_modalities(discovered_dataset, expected_dataset),
        "discovered_dataset_files": discovered_dataset,
        "expected_dataset_files": expected_dataset,
    }


def scan_dab(dab_root: Path) -> dict[str, Any]:
    manifest = parse_dataset_manifest(dab_root)
    domains = sorted(
        [path for path in dab_root.iterdir() if path.is_dir() and path.name.startswith("query_")],
        key=lambda p: p.name.lower(),
    )
    cases: list[dict[str, Any]] = []
    domain_summaries: list[dict[str, Any]] = []
    for domain_dir in domains:
        query_dirs = list_query_dirs(domain_dir)
        expected = expected_dataset_entries(domain_dir, manifest, dab_root)
        discovered = list_dataset_files(domain_dir / "query_dataset", dab_root)
        domain_cases = [scan_case(domain_dir, query_dir, dab_root, manifest) for query_dir in query_dirs]
        cases.extend(domain_cases)
        domain_summaries.append(
            {
                "domain": domain_name(domain_dir),
                "domain_dir": rel(domain_dir, ROOT),
                "query_count": len(query_dirs),
                "dataset_materialization_status": dataset_status(expected, discovered),
                "data_modalities": classify_data_modalities(discovered, expected),
                "expected_dataset_file_count": len(expected),
                "discovered_dataset_file_count": len(discovered),
            }
        )
    counts = {
        "domains": len(domains),
        "queries": len(cases),
        "definition_ready": sum(1 for row in cases if row["definition_status"] == "definition_ready"),
        "dataset_materialized_complete": sum(
            1 for row in cases if row["dataset_materialization_status"] == "materialized_complete"
        ),
        "runnable": sum(1 for row in cases if row["runnable_status"] == "runnable_if_dataset_available"),
    }
    return {
        "schema_version": "dab_query_registry_v001",
        "created_at": utc_now(),
        "dab_root": rel(dab_root, ROOT),
        "dataset_manifest_path": rel(dab_root / "dataset_manifest.tsv", ROOT),
        "counts": counts,
        "domains": domain_summaries,
        "queries": cases,
    }


def round_robin_cases_by_domain(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in sorted(cases, key=lambda row: (str(row["domain"]).lower(), int(row["query_number"]))):
        grouped[str(case["domain"])].append(case)
    ordered_domains = sorted(grouped)
    ordered: list[dict[str, Any]] = []
    while any(grouped.values()):
        for domain in ordered_domains:
            if grouped[domain]:
                ordered.append(grouped[domain].pop(0))
    return ordered


def build_splits(cases: list[dict[str, Any]], train_ratio: float, dev_ratio: float) -> dict[str, Any]:
    ordered = round_robin_cases_by_domain(cases)
    total = len(ordered)
    if total == 0:
        split_ids = {"train": [], "dev": [], "heldout": []}
    else:
        train_count = max(1, round(total * train_ratio))
        dev_count = max(1, round(total * dev_ratio)) if total >= 3 else 0
        if train_count + dev_count >= total:
            train_count = max(1, total - 2) if total >= 3 else max(1, total - 1)
            dev_count = 1 if total >= 3 else 0
        split_ids = {
            "train": [row["query_id"] for row in ordered[:train_count]],
            "dev": [row["query_id"] for row in ordered[train_count : train_count + dev_count]],
            "heldout": [row["query_id"] for row in ordered[train_count + dev_count :]],
        }
    return {
        "schema_version": "dab_query_splits_v001",
        "created_at": utc_now(),
        "policy": {
            "name": "deterministic_domain_round_robin",
            "train_ratio": train_ratio,
            "dev_ratio": dev_ratio,
            "heldout_ratio": round(max(0.0, 1.0 - train_ratio - dev_ratio), 4),
            "note": "Initial split for multi-query harness evolution. Review before formal experiments.",
        },
        "splits": split_ids,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_registry_md(path: Path, registry: dict[str, Any], splits: dict[str, Any]) -> None:
    counts = registry.get("counts", {})
    lines = [
        "# DAB Query Corpus Registry",
        "",
        f"Created at: `{registry.get('created_at')}`",
        "",
        f"DAB root: `{registry.get('dab_root')}`",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Domains | {counts.get('domains', 0)} |",
        f"| Query cases | {counts.get('queries', 0)} |",
        f"| Definition-ready cases | {counts.get('definition_ready', 0)} |",
        f"| Dataset-materialized cases | {counts.get('dataset_materialized_complete', 0)} |",
        f"| Runnable cases | {counts.get('runnable', 0)} |",
        "",
        "## Domains",
        "",
        "| Domain | Queries | Dataset status | Modalities | Expected files | Present dataset files |",
        "|---|---:|---|---|---:|---:|",
    ]
    for row in registry.get("domains", []):
        lines.append(
            "| {domain} | {query_count} | {status} | {modalities} | {expected} | {discovered} |".format(
                domain=row.get("domain"),
                query_count=row.get("query_count"),
                status=row.get("dataset_materialization_status"),
                modalities=", ".join(row.get("data_modalities") or []),
                expected=row.get("expected_dataset_file_count"),
                discovered=row.get("discovered_dataset_file_count"),
            )
        )
    lines.extend(
        [
            "",
            "## Initial Splits",
            "",
        ]
    )
    for split_name, ids in (splits.get("splits") or {}).items():
        lines.append(f"### {split_name} ({len(ids)})")
        lines.append("")
        for query_id in ids:
            lines.append(f"- `{query_id}`")
        lines.append("")
    lines.extend(
        [
            "## Query Cases",
            "",
            "| Query ID | Definition | Dataset | Runnable | Preview |",
            "|---|---|---|---|---|",
        ]
    )
    for row in registry.get("queries", []):
        preview = str(row.get("query_text_preview") or "").replace("|", "\\|")
        lines.append(
            f"| `{row.get('query_id')}` | {row.get('definition_status')} | "
            f"{row.get('dataset_materialization_status')} | {row.get('runnable_status')} | {preview} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_split_files(output_root: Path, splits: dict[str, Any]) -> None:
    split_dir = output_root / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    write_json(split_dir / "splits.json", splits)
    for split_name, ids in (splits.get("splits") or {}).items():
        write_json(
            split_dir / f"{split_name}.json",
            {
                "schema_version": "dab_query_split_v001",
                "created_at": splits.get("created_at"),
                "split": split_name,
                "query_ids": ids,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dab-root", type=Path, default=DEFAULT_DAB_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--train-ratio", type=float, default=0.6)
    parser.add_argument("--dev-ratio", type=float, default=0.2)
    args = parser.parse_args()

    dab_root = args.dab_root.resolve()
    output_root = args.output_root.resolve()
    if not dab_root.exists():
        raise SystemExit(f"DAB root does not exist: {dab_root}")
    if not (dab_root / "dataset_manifest.tsv").exists():
        raise SystemExit(f"DAB root does not look like DataAgentBench; missing dataset_manifest.tsv: {dab_root}")

    registry = scan_dab(dab_root)
    splits = build_splits(registry["queries"], args.train_ratio, args.dev_ratio)
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "registry.json", registry)
    write_json(output_root / "registry_summary.json", {key: registry[key] for key in ("schema_version", "created_at", "dab_root", "counts", "domains")})
    write_split_files(output_root, splits)
    write_registry_md(output_root / "registry.md", registry, splits)

    print(
        json.dumps(
            {
                "status": "ok",
                "registry": str(output_root / "registry.json"),
                "registry_md": str(output_root / "registry.md"),
                "splits": str(output_root / "splits" / "splits.json"),
                "counts": registry.get("counts"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
