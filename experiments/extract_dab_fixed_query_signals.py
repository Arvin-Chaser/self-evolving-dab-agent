#!/usr/bin/env python3
"""Extract six passive, post-hoc query-observation families from a DAB trace.

Only successful ``query_db`` calls actually made by the parent are observed.
No database query is issued, no error diagnosis is added, and no repair is
recommended.  The resulting packet is evidence for the next Meta Agent only.
"""

from __future__ import annotations

from collections import Counter
import json
import re
from pathlib import Path
from typing import Any


SIGNAL_FAMILIES = (
    "distinct_values",
    "filtered_count",
    "min_max_range",
    "topk_groupby",
    "join_overlap",
    "evidence_sample",
)
SIGNAL_SCHEMA_VERSION = "dab_passive_refined_query_signals_v001"
MAX_JSONL_RECORD_BYTES = 4 * 1024 * 1024
MAX_PREVIEW_CHARS = 1800
MAX_PROFILE_VALUES = 8

PASSIVE_FEEDBACK_MODE = {
    "timing": "after_parent_evaluation",
    "source": "parent_executed_successful_queries_only",
    "additional_database_queries": False,
    "visible_to_parent_data_agent": False,
    "diagnostic_labels_added": False,
    "repair_recommendations_added": False,
}


def iter_jsonl(path: Path, *, max_record_bytes: int = MAX_JSONL_RECORD_BYTES):
    """Yield bounded records while skipping oversized or malformed JSONL rows."""
    if not path.exists():
        return
    with path.open("rb") as handle:
        while True:
            raw = handle.readline(max_record_bytes + 1)
            if not raw:
                return
            if len(raw) > max_record_bytes and not raw.endswith(b"\n"):
                while raw and not raw.endswith(b"\n"):
                    raw = handle.readline(max_record_bytes + 1)
                continue
            try:
                value = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def _sql_for(row: dict[str, Any]) -> str:
    args = row.get("args") if isinstance(row.get("args"), dict) else {}
    validated = row.get("val_args") if isinstance(row.get("val_args"), dict) else {}
    exec_args = validated.get("exec_args") if isinstance(validated.get("exec_args"), dict) else {}
    return str(args.get("query") or exec_args.get("sql") or exec_args.get("query") or "").strip()


def classify_sql(sql: str) -> str | None:
    """Classify one observed query by its lexical SQL form."""
    normalized = re.sub(r"\s+", " ", sql.lower()).strip()
    if not normalized.startswith(("select", "with")):
        return None
    if re.search(r"\bselect\s+distinct\b", normalized):
        return "distinct_values"
    if " join " in normalized and ("count(" in normalized or "intersect" in normalized):
        return "join_overlap"
    if " group by " in normalized and (
        " order by " in normalized or re.search(r"\blimit\s+\d+", normalized)
    ):
        return "topk_groupby"
    if re.search(r"\b(min|max)\s*\(", normalized):
        return "min_max_range"
    if "count(" in normalized and " where " in normalized:
        return "filtered_count"
    limit = re.search(r"\blimit\s+(\d+)\b", normalized)
    if limit and int(limit.group(1)) <= 5:
        return "evidence_sample"
    return None


def _compact_preview(value: Any) -> tuple[str, bool]:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    if len(text) <= MAX_PREVIEW_CHARS:
        return text, False
    return text[:MAX_PREVIEW_CHARS] + "...[truncated]", True


def _parse_preview(value: Any) -> tuple[Any, str]:
    if isinstance(value, (list, dict, int, float, bool)) or value is None:
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None, "text"
    else:
        return None, "unparsed"
    if isinstance(parsed, list):
        return parsed, "row_list"
    if isinstance(parsed, dict):
        return parsed, "object"
    return parsed, "scalar"


def _split_sql_list(value: str) -> list[str]:
    parts: list[str] = []
    start = depth = 0
    quote: str | None = None
    for index, char in enumerate(value):
        if quote:
            if char == quote and (index == 0 or value[index - 1] != "\\"):
                quote = None
            continue
        if char in ("'", '"', "`"):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            part = value[start:index].strip()
            if part:
                parts.append(part)
            start = index + 1
    final = value[start:].strip()
    if final:
        parts.append(final)
    return parts


def _clause(sql: str, start: str, stops: tuple[str, ...]) -> str | None:
    stop_pattern = "|".join(re.escape(stop) for stop in stops)
    match = re.search(
        rf"\b{re.escape(start)}\b\s+(.*?)(?=\b(?:{stop_pattern})\b|;|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None


def _sql_structure(sql: str) -> dict[str, Any]:
    selected = _clause(sql, "select", ("from",)) or ""
    predicate = _clause(
        sql, "where", ("group by", "having", "order by", "limit", "union", "intersect")
    )
    group_by = _clause(sql, "group by", ("having", "order by", "limit", "union", "intersect"))
    order_by = _clause(sql, "order by", ("limit", "union", "intersect"))
    limit_match = re.search(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    tables = [
        token.strip('`"[]')
        for token in re.findall(
            r"\b(?:from|join)\s+([`\"\[\]\w.]+)", sql, flags=re.IGNORECASE
        )
    ]
    joins = []
    for match in re.finditer(
        r"\bjoin\s+([`\"\[\]\w.]+)(?:\s+(?:as\s+)?(\w+))?\s+on\s+"
        r"(.*?)(?=\b(?:join|where|group\s+by|having|order\s+by|limit)\b|;|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        joins.append({
            "table": match.group(1).strip('`"[]'),
            "alias": match.group(2),
            "condition": re.sub(r"\s+", " ", match.group(3)).strip(),
        })
    aggregates = []
    for match in re.finditer(
        r"\b(count|sum|avg|min|max)\s*\((.*?)\)"
        r"(?:\s+as\s+([\w\"`\[\]]+))?",
        selected,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        aggregates.append({
            "function": match.group(1).upper(),
            "expression": re.sub(r"\s+", " ", match.group(2)).strip(),
            "alias": match.group(3).strip('`"[]') if match.group(3) else None,
        })
    return {
        "selected_expressions": _split_sql_list(selected),
        "tables": list(dict.fromkeys(tables)),
        "predicate": predicate,
        "group_by": _split_sql_list(group_by) if group_by else [],
        "order_by": _split_sql_list(order_by) if order_by else [],
        "limit": int(limit_match.group(1)) if limit_match else None,
        "joins": joins,
        "aggregates": aggregates,
    }


def _rows(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return [parsed] if isinstance(parsed, dict) else []


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(key) for row in rows for key in row))


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _visible_profiles(rows: list[dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for column in _columns(rows):
        values = [row.get(column) for row in rows]
        encoded = [_canonical(value) for value in values]
        normalized = [value.strip().lower() for value in values if isinstance(value, str)]
        lengths = [len(value) for value in values if isinstance(value, str)]
        top_values = []
        for raw, count in Counter(encoded).most_common(MAX_PROFILE_VALUES):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw
            top_values.append({"value": value, "visible_count": count})
        profiles[column] = {
            "visible_count": len(values),
            "visible_null_count": sum(value is None for value in values),
            "visible_distinct_count": len(set(encoded)),
            "visible_unique_ratio": round(len(set(encoded)) / len(values), 6) if values else None,
            "observed_types": sorted({_type_name(value) for value in values}),
            "visible_top_values": top_values,
            "visible_normalized_string_distinct_count": len(set(normalized)) if normalized else None,
            "visible_string_length_range": (
                {"min": min(lengths), "max": max(lengths)} if lengths else None
            ),
        }
    return profiles


def _scalar_outputs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) != 1:
        return {}
    return {
        str(key): value for key, value in rows[0].items()
        if value is None or isinstance(value, (str, int, float, bool))
    }


UNAVAILABLE_WITHOUT_PARENT_OBSERVATION = {
    "distinct_values": [
        "population_row_count", "population_distinct_count",
        "population_unique_ratio", "population_null_ratio",
    ],
    "filtered_count": [
        "input_row_count", "filter_selectivity", "per_predicate_row_counts",
    ],
    "min_max_range": [
        "population_quantiles", "population_parse_success_ratio", "population_null_ratio",
    ],
    "topk_groupby": [
        "source_row_count", "expected_output_grain", "full_boundary_tie_count",
    ],
    "join_overlap": [
        "left_key_population_unique_ratio", "right_key_population_unique_ratio",
        "population_match_rate", "population_row_amplification",
    ],
    "evidence_sample": [
        "population_null_ratio", "population_type_distribution", "sample_representativeness",
    ],
}


def _measurements(family: str, structure: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "sql_structure": structure,
        "observed_scalar_outputs": _scalar_outputs(rows),
    }
    if family == "distinct_values":
        value["visible_value_profile"] = _visible_profiles(rows)
    elif family == "filtered_count":
        value["predicate"] = structure["predicate"]
    elif family == "min_max_range":
        value["range_expressions"] = [
            item for item in structure["aggregates"]
            if item["function"] in ("MIN", "MAX")
        ]
    elif family == "topk_groupby":
        value.update({
            "group_by": structure["group_by"],
            "order_by": structure["order_by"],
            "limit": structure["limit"],
            "aggregate_expressions": structure["aggregates"],
            "visible_boundary_row": rows[-1] if rows else None,
        })
    elif family == "join_overlap":
        value.update({"tables": structure["tables"], "join_clauses": structure["joins"]})
    elif family == "evidence_sample":
        value.update({
            "selected_expressions": structure["selected_expressions"],
            "limit": structure["limit"],
            "visible_column_profiles": _visible_profiles(rows),
        })
    return value


def _signal_item(
    *, family: str, family_index: int, tool_call_index: int,
    database: Any, sql: str, preview: Any,
) -> dict[str, Any]:
    compact, truncated = _compact_preview(preview)
    parsed, parsed_as = _parse_preview(preview)
    rows = _rows(parsed)
    measurements = _measurements(family, _sql_structure(sql), rows)
    return {
        "signal_id": f"{family}_{family_index:03d}",
        "source": {
            "tool_call_indices": [tool_call_index],
            "database": database,
            "sql": [sql],
        },
        "observation": {
            "result_preview": compact,
            "preview_truncated": truncated,
            "parsed_as": parsed_as,
            "visible_row_count": len(rows) if rows else None,
            "visible_columns": _columns(rows),
        },
        "measurements": measurements,
        "availability": {
            "status": "observed" if rows or parsed_as in ("object", "scalar") else "partial",
            "available_fields": sorted(measurements),
            "unavailable_without_additional_queries": list(
                UNAVAILABLE_WITHOUT_PARENT_OBSERVATION[family]
            ),
        },
    }


def extract_fixed_query_signals(run_dir: Path, *, per_family_limit: int = 3) -> dict[str, Any]:
    """Build a passive packet without issuing any additional database query."""
    family_items: dict[str, list[dict[str, Any]]] = {
        family: [] for family in SIGNAL_FAMILIES
    }
    for tool_call_index, row in enumerate(iter_jsonl(run_dir / "tool_calls.jsonl"), start=1):
        if row.get("tool_name") != "query_db":
            continue
        sql = _sql_for(row)
        family = classify_sql(sql)
        if not family or len(family_items[family]) >= per_family_limit:
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        if not result.get("success"):
            continue
        args = row.get("args") if isinstance(row.get("args"), dict) else {}
        family_items[family].append(_signal_item(
            family=family,
            family_index=len(family_items[family]) + 1,
            tool_call_index=tool_call_index,
            database=args.get("db_name"),
            sql=sql,
            preview=result.get("preview", ""),
        ))
    return {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "feedback_mode": dict(PASSIVE_FEEDBACK_MODE),
        "signals": {
            family: {
                "status": "observed" if family_items[family] else "not_observed",
                "items": family_items[family],
            }
            for family in SIGNAL_FAMILIES
        },
        "researcher_provenance": {
            "source_trace": str(run_dir / "tool_calls.jsonl"),
            "per_family_limit": per_family_limit,
            "observed_signal_count": sum(len(items) for items in family_items.values()),
        },
    }
