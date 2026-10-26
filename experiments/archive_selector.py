"""Archive parent/evidence pool selection for meta-agent evolution.

The selector separates two roles that used to be conflated:

- parent_pool: archived agents/candidates safe enough to inherit from.
- evidence_pool: failed or non-parent candidates that still carry useful
  observations for the next meta-agent repair.

This is an MVP selector, not a bandit yet. It exposes explicit scores and
reason fields so later iterations can evolve the policy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES_INDEX = ROOT / "archive" / "indexes" / "candidates.jsonl"
DEFAULT_AGENTS_INDEX = ROOT / "archive" / "indexes" / "agents.jsonl"
RECENT_PARENT_REPEAT_PENALTY = 0.15


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def load_json_if_exists(path: Path | str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _bool(value: Any) -> bool:
    return bool(value)


def _lineage_family(row: dict[str, Any], card: dict[str, Any] | None = None) -> str:
    value = row.get("source_lineage_family") or row.get("lineage_family")
    if value:
        return str(value)
    card = card or load_json_if_exists(row.get("card"))
    value = card.get("source_lineage_family") or card.get("lineage_family")
    if value:
        return str(value)
    source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
    runner = str(source_refs.get("runner") or "")
    if runner == "experiments/run_dab_tool_agent.py":
        return "dab_tool_agent_workflow"
    if runner == "experiments/run_dab_agent.py":
        return "generated_solve_legacy"
    return "unknown"


def _matches_lineage_family(row: dict[str, Any], requested: str | None, card: dict[str, Any] | None = None) -> bool:
    if not requested:
        return True
    return _lineage_family(row, card) == requested


def _tags(row: dict[str, Any]) -> list[str]:
    tags = row.get("failure_observation_tags")
    return [str(item) for item in tags] if isinstance(tags, list) else []


def _matches_current_failure(row: dict[str, Any], current_failure_tags: list[str]) -> int:
    if not current_failure_tags:
        return 0
    row_tags = set(_tags(row))
    return len(row_tags & set(current_failure_tags))


def best_agent_f1(agent_card: dict[str, Any]) -> float | None:
    evals = agent_card.get("evals") if isinstance(agent_card.get("evals"), dict) else {}
    values: list[float] = []
    for item in evals.values():
        if not isinstance(item, dict):
            continue
        metrics = item.get("answer_metrics") if isinstance(item.get("answer_metrics"), dict) else {}
        if not metrics:
            metrics = item.get("answer_quality") if isinstance(item.get("answer_quality"), dict) else {}
        value = metrics.get("f1")
        try:
            if value is not None:
                values.append(float(value))
        except Exception:
            pass
    return max(values) if values else None


def parent_agent_score(row: dict[str, Any], *, recent_parent_ids: set[str] | None = None) -> dict[str, Any]:
    recent_parent_ids = recent_parent_ids or set()
    agent_id = str(row.get("agent_id") or row.get("candidate_id") or "")
    card = load_json_if_exists(row.get("card"))
    reasons: list[str] = []
    score = 0.0

    f1 = best_agent_f1(card)
    if f1 is not None:
        score += f1
        reasons.append(f"best_f1:{f1:.6f}")

    status = str(row.get("status") or "")
    if "active" in status:
        score += 0.05
        reasons.append("active_status")
    if "partial_improvement" in status:
        score += 0.03
        reasons.append("partial_improvement_status")
    if row.get("can_use_as_parent"):
        score += 0.05
        reasons.append("can_use_as_parent")

    source_refs = card.get("source_refs") if isinstance(card.get("source_refs"), dict) else {}
    runner = str(source_refs.get("runner") or "")
    if runner == "experiments/run_dab_tool_agent.py":
        score += 0.30
        reasons.append("active_dab_tool_agent_mainline")
    elif runner == "experiments/run_dab_agent.py":
        score -= 0.05
        reasons.append("legacy_generated_solve_parent_penalty")

    if agent_id in recent_parent_ids:
        score -= RECENT_PARENT_REPEAT_PENALTY
        reasons.append("recent_parent_penalty")

    return {"score": round(score, 6), "reasons": reasons, "best_f1": f1, "card": card}


def parent_candidate_score(row: dict[str, Any], *, recent_parent_ids: set[str] | None = None) -> dict[str, Any]:
    recent_parent_ids = recent_parent_ids or set()
    candidate_id = str(row.get("candidate_id") or "")
    reasons: list[str] = []
    score = 0.0

    score += _float(row.get("promotion_score"))
    if row.get("answer_quality_f1") is not None:
        score += max(0.0, min(0.2, _float(row.get("answer_quality_f1"), 0.0)))
        reasons.append("answer_quality_f1")
    delta_f1 = _float(row.get("metric_delta_f1"), 0.0)
    score += max(-0.05, min(0.2, delta_f1))

    if row.get("contract_eval_status") == "contract_eval_supported":
        score += 0.05
        reasons.append("contract_eval_supported")
    elif row.get("contract_eval_status") == "contract_eval_has_violations":
        score -= 0.05
        reasons.append("contract_eval_has_violations")

    if row.get("has_open_diagnosis"):
        score += 0.02
        reasons.append("has_open_diagnosis")
    if row.get("proposed_contracts_present"):
        score += 0.02
        reasons.append("has_proposed_contracts")

    if candidate_id in recent_parent_ids:
        score -= RECENT_PARENT_REPEAT_PENALTY
        reasons.append("recent_parent_penalty")

    return {"score": round(score, 6), "reasons": reasons}


def evidence_candidate_score(row: dict[str, Any], *, current_failure_tags: list[str] | None = None) -> dict[str, Any]:
    current_failure_tags = current_failure_tags or []
    reasons: list[str] = []
    score = 0.0

    if row.get("can_seed_next_repair"):
        score += 0.2
        reasons.append("can_seed_next_repair")
    if row.get("use_as_negative_example"):
        score += 0.1
        reasons.append("use_as_negative_example")
    if row.get("has_open_diagnosis"):
        score += 0.1
        reasons.append("has_open_diagnosis")
    if row.get("proposed_contracts_present"):
        score += 0.05
        reasons.append("has_proposed_contracts")

    contract_status = row.get("contract_eval_status")
    if contract_status == "contract_eval_has_violations":
        score += 0.08
        reasons.append("contract_violation_evidence")
    elif contract_status == "contract_eval_supported":
        score += 0.03
        reasons.append("contract_supported_evidence")

    matched = _matches_current_failure(row, current_failure_tags)
    if matched:
        score += 0.08 * matched
        reasons.append(f"matched_current_failure_tags:{matched}")

    if "severe_child_answer_regression" in _tags(row):
        score += 0.04
        reasons.append("negative_example_severe_regression")
    if "helper_output_sink_mismatch" in _tags(row):
        score += 0.04
        reasons.append("helper_output_sink_mismatch")

    return {"score": round(score, 6), "reasons": reasons}


def build_selection_pools(
    candidate_rows: list[dict[str, Any]],
    *,
    agent_rows: list[dict[str, Any]] | None = None,
    current_failure_tags: list[str] | None = None,
    recent_parent_ids: list[str] | None = None,
    parent_limit: int = 5,
    evidence_limit: int = 5,
    parent_agent_type: str | None = "data_agent",
    source_lineage_family: str | None = None,
) -> dict[str, Any]:
    recent = set(recent_parent_ids or [])
    parent_pool: list[dict[str, Any]] = []
    evidence_pool: list[dict[str, Any]] = []

    for row in agent_rows or []:
        agent_id = row.get("agent_id")
        if not agent_id or not row.get("can_use_as_parent"):
            continue
        if parent_agent_type and row.get("agent_type") != parent_agent_type:
            continue
        card = load_json_if_exists(row.get("card"))
        if not _matches_lineage_family(row, source_lineage_family, card):
            continue
        scored = parent_agent_score(row, recent_parent_ids=recent)
        parent_pool.append(
            {
                **row,
                "selection_role": "parent",
                "selection_source": "archive_agents",
                "selection_score": scored["score"],
                "selection_reasons": scored["reasons"],
                "best_f1": scored["best_f1"],
            }
        )

    for row in candidate_rows:
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue

        is_parent_eligible = _bool(row.get("eligible_as_parent") or row.get("can_be_parent"))
        if is_parent_eligible:
            scored = parent_candidate_score(row, recent_parent_ids=recent)
            parent_pool.append({**row, "selection_role": "parent", "selection_source": "archive_candidates", "selection_score": scored["score"], "selection_reasons": scored["reasons"]})

        if (not is_parent_eligible) and (_bool(row.get("can_seed_next_repair")) or _bool(row.get("use_as_negative_example"))):
            scored = evidence_candidate_score(row, current_failure_tags=current_failure_tags or [])
            evidence_pool.append({**row, "selection_role": "evidence", "selection_source": "archive_candidates", "selection_score": scored["score"], "selection_reasons": scored["reasons"]})

    parent_pool.sort(key=lambda item: (item.get("selection_score", 0), item.get("created_or_observed_at") or item.get("created_at") or "", item.get("agent_id") or item.get("candidate_id") or ""), reverse=True)
    evidence_pool.sort(key=lambda item: (item.get("selection_score", 0), item.get("created_at") or "", item.get("candidate_id") or ""), reverse=True)

    return {
        "schema_version": "archive_selection_v001",
        "policy": {
            "pool_split": "parent_pool_and_evidence_pool",
            "parent_pool_sources": ["archive/indexes/agents.jsonl", "eligible archive/indexes/candidates.jsonl"],
            "evidence_pool_sources": ["non-parent archive/indexes/candidates.jsonl"],
            "parent_pool_role": "inheritance source for next data/meta-agent state",
            "evidence_pool_role": "failed or non-parent candidates used as observations/negative examples",
            "recent_parent_repeat_penalty": RECENT_PARENT_REPEAT_PENALTY,
            "parent_agent_type": parent_agent_type,
        },
        "current_failure_tags": current_failure_tags or [],
        "recent_parent_ids": list(recent_parent_ids or []),
        "parent_pool": parent_pool[:parent_limit],
        "evidence_pool": evidence_pool[:evidence_limit],
        "counts": {
            "candidate_rows": len(candidate_rows),
            "agent_rows": len(agent_rows or []),
            "parent_pool": len(parent_pool),
            "evidence_pool": len(evidence_pool),
        },
    }


def select_from_archive(
    candidates_index_path: Path = DEFAULT_CANDIDATES_INDEX,
    *,
    agents_index_path: Path = DEFAULT_AGENTS_INDEX,
    current_failure_tags: list[str] | None = None,
    recent_parent_ids: list[str] | None = None,
    parent_limit: int = 5,
    evidence_limit: int = 5,
    parent_agent_type: str | None = "data_agent",
    source_lineage_family: str | None = None,
) -> dict[str, Any]:
    candidate_rows = load_jsonl(candidates_index_path)
    agent_rows = load_jsonl(agents_index_path)
    return build_selection_pools(
        candidate_rows,
        agent_rows=agent_rows,
        current_failure_tags=current_failure_tags,
        recent_parent_ids=recent_parent_ids,
        parent_limit=parent_limit,
        evidence_limit=evidence_limit,
        parent_agent_type=parent_agent_type,
        source_lineage_family=source_lineage_family,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates-index", type=Path, default=DEFAULT_CANDIDATES_INDEX)
    parser.add_argument("--agents-index", type=Path, default=DEFAULT_AGENTS_INDEX)
    parser.add_argument("--current-failure-tag", action="append", default=[])
    parser.add_argument("--recent-parent-id", action="append", default=[])
    parser.add_argument("--parent-limit", type=int, default=5)
    parser.add_argument("--evidence-limit", type=int, default=5)
    parser.add_argument("--parent-agent-type", default="data_agent")
    parser.add_argument("--source-lineage-family", default="dab_tool_agent_workflow", help="Filter parent agents to one source lineage family; use empty string to disable.")
    args = parser.parse_args()
    parent_agent_type = args.parent_agent_type if args.parent_agent_type else None
    result = select_from_archive(
        args.candidates_index,
        agents_index_path=args.agents_index,
        current_failure_tags=args.current_failure_tag,
        recent_parent_ids=args.recent_parent_id,
        parent_limit=args.parent_limit,
        evidence_limit=args.evidence_limit,
        parent_agent_type=parent_agent_type,
        source_lineage_family=args.source_lineage_family or None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
