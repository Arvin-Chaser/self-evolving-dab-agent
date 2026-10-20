#!/usr/bin/env python3
"""Stream a Codex session JSONL into a redacted, source-indexed memory corpus.

The source file is opened read-only and processed one physical line at a time.
Generated files contain bounded excerpts, hashes, and source line references;
they never contain encrypted reasoning payloads or known credential patterns.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SESSION_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")

SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
            re.I | re.S,
        ),
    ),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    (
        "credential_assignment",
        re.compile(
            r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth(?:orization)?|password|passwd|cookie|secret)\b\s*[=:]\s*)(?!null\b|none\b|false\b|true\b)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}]+)"
        ),
    ),
    ("openai_style_key", re.compile(r"\b(?:sk|sess)-[A-Za-z0-9_-]{16,}\b")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
)

THEME_PATTERNS: dict[str, re.Pattern[str]] = {
    "architecture": re.compile(r"(?i)\b(?:architecture|pipeline|workflow|mainline|entry point|架构|主线|流程|入口)\b"),
    "evolution_graph": re.compile(r"(?i)\b(?:evolution|generation|gen\s*\d+|g\d{3}|graph|roadmap|archive|parent|演化|代际|父代)\b"),
    "observer_feedback": re.compile(r"(?i)\b(?:observer|feedback|trace|signal|evidence pack|观察|反馈|轨迹|信号|证据)\b"),
    "prompt_policy": re.compile(r"(?i)\b(?:prompt|policy|instruction|提示词|策略)\b"),
    "experiment_eval": re.compile(r"(?i)\b(?:experiment|evaluation|benchmark|strict pass|score|cohort|实验|评测|得分)\b"),
    "tests_manifests": re.compile(r"(?i)\b(?:pytest|test(?:s|ed)?|passed|failed|manifest|admission|audit|preflight|测试|清单|准入|审验)\b"),
    "git_code": re.compile(r"(?i)\b(?:git|commit|branch|diff|patch|source|implementation|代码|实现|分支|提交)\b"),
    "environment_remote": re.compile(r"(?i)\b(?:ssh|server|remote|ct104|docker|postgres|mongo|venv|environment|环境|服务器|远端)\b"),
    "failure_blocker": re.compile(r"(?i)\b(?:fail(?:ed|ure)?|error|timeout|blocked|incident|regression|故障|失败|超时|阻塞|错误)\b"),
    "decision_correction": re.compile(r"(?i)\b(?:decision|decided|reject|abandon|deprecated|legacy|incorrect|correction|决策|放弃|推翻|修正|旧方案)\b"),
    "next_state": re.compile(r"(?i)\b(?:next step|todo|pending|current state|handoff|resume|unfinished|下一步|待办|当前状态|交接|未完成)\b"),
    "security": re.compile(r"(?i)\b(?:credential|secret|api key|token|password|private key|凭据|密钥|密码)\b"),
}

HIGH_VALUE_RE = re.compile(
    r"(?i)(?:\b(?:status|result|summary|manifest|admission|audit|preflight|passed|failed|error|timeout|strict|score|sha256|commit|branch|run_id|generation|next_generation|blocked|pending|completed)\b|状态|结果|测试|失败|完成|阻塞|下一步|结论|决策|推翻)"
)
MAX_INDEX_SCAN_CHARS = 250_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def redact(text: str, counters: collections.Counter[str]) -> str:
    value = text
    for label, pattern in SENSITIVE_PATTERNS:
        def replacement(match: re.Match[str], *, category: str = label) -> str:
            counters[category] += 1
            if category == "credential_assignment" and match.lastindex:
                return match.group(1) + f"[REDACTED:{category}]"
            return f"[REDACTED:{category}]"

        value = pattern.sub(replacement, value)
    return value


def normalize_text(text: str) -> str:
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(line for line in lines if line)


def bounded_excerpt(text: str, max_chars: int = 5000, high_value_lines: int = 18) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    lines = text.splitlines()
    selected: list[str] = []
    for line in lines:
        if HIGH_VALUE_RE.search(line):
            selected.append(line)
            if len(selected) >= high_value_lines:
                break
    head = text[: max_chars // 3]
    tail = text[-max_chars // 4 :]
    evidence = "\n".join(selected)
    combined = f"{head}\n[...TRUNCATED; HIGH-VALUE LINES FOLLOW...]\n{evidence}\n[...TAIL...]\n{tail}"
    return combined[:max_chars], True


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [text_from_content(item) for item in content]
        return "\n".join(part for part in parts if part)
    if not isinstance(content, dict):
        return ""
    content_type = str(content.get("type") or "")
    if content_type in {"reasoning", "encrypted_content"}:
        return ""
    for key in ("text", "content", "message", "summary"):
        if key in content:
            value = text_from_content(content[key])
            if value:
                return value
    return ""


def safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and len(value) <= 240:
        return value
    return None


def classify_themes(text: str) -> list[str]:
    return [name for name, pattern in THEME_PATTERNS.items() if pattern.search(text)]


def find_turn_id(record: dict[str, Any], current_turn_id: str | None) -> str | None:
    payload = record.get("payload")
    candidates: list[Any] = [record.get("turn_id")]
    if isinstance(payload, dict):
        candidates.extend((payload.get("turn_id"), payload.get("root_turn_id")))
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            candidates.extend((metadata.get("turn_id"), metadata.get("root_turn_id")))
    for value in candidates:
        if isinstance(value, str) and value:
            return value
    return current_turn_id


def detect_kind(record: dict[str, Any]) -> tuple[str, str, str | None, str | None, Any]:
    top_type = str(record.get("type") or "unknown")
    payload = record.get("payload")
    subtype = ""
    role: str | None = None
    phase: str | None = None
    content: Any = None
    if isinstance(payload, dict):
        subtype = str(payload.get("type") or "")
        role_value = payload.get("role")
        role = str(role_value) if isinstance(role_value, str) else None
        phase_value = payload.get("phase")
        phase = str(phase_value) if isinstance(phase_value, str) else None
        if top_type == "response_item" and subtype == "message":
            content = payload.get("content")
        elif top_type == "response_item" and subtype in {"custom_tool_call", "function_call"}:
            content = payload.get("input") or payload.get("arguments")
        elif top_type == "response_item" and subtype in {"custom_tool_call_output", "function_call_output"}:
            content = payload.get("output")
        elif top_type == "event_msg":
            if subtype in {"user_message", "agent_message", "task_complete", "compacted", "context_compacted"}:
                content = payload.get("message") or payload.get("text") or payload.get("summary")
            item = payload.get("item")
            if isinstance(item, dict):
                subtype = f"{subtype}:{item.get('type', 'item')}"
                content = (
                    item.get("aggregated_output")
                    or item.get("output")
                    or item.get("text")
                    or item.get("message")
                    or content
                )
        elif top_type == "turn_context":
            content = payload.get("summary")
        elif top_type == "compacted":
            content = payload.get("message")
        elif "compaction" in subtype:
            content = payload.get("summary") or payload.get("content")
    return top_type, subtype, role, phase, content


@dataclass
class TurnSummary:
    turn_id: str
    ordinal: int
    first_line: int
    last_line: int
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    user_messages: list[dict[str, Any]] = field(default_factory=list)
    assistant_messages: list[dict[str, Any]] = field(default_factory=list)
    compactions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: collections.Counter[str] = field(default_factory=collections.Counter)
    tool_output_lines: list[int] = field(default_factory=list)
    themes: collections.Counter[str] = field(default_factory=collections.Counter)

    def touch(self, line_no: int, timestamp: str | None) -> None:
        self.last_line = line_no
        if timestamp:
            if self.first_timestamp is None:
                self.first_timestamp = timestamp
            self.last_timestamp = timestamp

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "turn_ordinal": self.ordinal,
            "source_lines": [self.first_line, self.last_line],
            "timestamps": [self.first_timestamp, self.last_timestamp],
            "user_messages": self.user_messages,
            "assistant_messages": self.assistant_messages,
            "compactions": self.compactions,
            "tool_calls": dict(self.tool_calls),
            "important_tool_output_lines": self.tool_output_lines[:40],
            "themes": dict(self.themes),
        }


def iter_message_records(payload: dict[str, Any], text: str) -> Iterable[tuple[str, str]]:
    role = payload.get("role")
    if isinstance(role, str) and text:
        yield role, text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="Source Codex rollout JSONL")
    parser.add_argument("output_dir", type=Path, help="New directory for redacted extraction files")
    parser.add_argument("--chunk-lines", type=int, default=10000)
    parser.add_argument("--max-excerpt-chars", type=int, default=5000)
    parser.add_argument(
        "--replace-output",
        action="store_true",
        help="Replace files in an existing generated index directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.session.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    if source.suffix.lower() != ".jsonl":
        raise SystemExit("source must be a JSONL file")
    if output_dir.exists() and any(output_dir.iterdir()) and not args.replace_output:
        raise SystemExit(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    if source == output_dir or output_dir in source.parents:
        raise SystemExit("output directory cannot contain the source session")

    source_stat_start = source.stat()
    session_match = SESSION_ID_RE.search(source.name)
    session_id = session_match.group(0) if session_match else "unknown"
    source_hash = hashlib.sha256()
    record_types: collections.Counter[str] = collections.Counter()
    payload_types: collections.Counter[str] = collections.Counter()
    roles: collections.Counter[str] = collections.Counter()
    tool_names: collections.Counter[str] = collections.Counter()
    theme_counts: collections.Counter[str] = collections.Counter()
    redaction_counts: collections.Counter[str] = collections.Counter()
    duplicate_first_line: dict[str, int] = {}
    turns: dict[str, TurnSummary] = {}
    turn_order: list[str] = []
    current_turn_id: str | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    parse_errors: list[dict[str, Any]] = []
    line_count = 0
    byte_count = 0
    chunk_start_line = 1
    chunk_start_byte = 0
    chunk_first_timestamp: str | None = None
    chunk_last_timestamp: str | None = None
    chunk_types: collections.Counter[str] = collections.Counter()
    chunk_themes: collections.Counter[str] = collections.Counter()
    chunk_important = 0
    encoding_replacement_char_count = 0
    encoding_damaged_record_count = 0

    events_path = output_dir / "events.jsonl"
    chunks_path = output_dir / "coverage_chunks.jsonl"
    turns_path = output_dir / "turns.jsonl"
    coverage_path = output_dir / "coverage.json"
    readme_path = output_dir / "README.md"

    with (
        source.open("rb") as source_handle,
        events_path.open("w", encoding="utf-8", newline="\n") as events_handle,
        chunks_path.open("w", encoding="utf-8", newline="\n") as chunks_handle,
    ):
        for raw_line in source_handle:
            line_count += 1
            byte_count += len(raw_line)
            source_hash.update(raw_line)
            try:
                record = json.loads(raw_line)
            except Exception as exc:
                if len(parse_errors) < 100:
                    parse_errors.append({"line": line_count, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if not isinstance(record, dict):
                continue

            timestamp_value = record.get("timestamp")
            timestamp = str(timestamp_value) if isinstance(timestamp_value, str) else None
            if timestamp:
                first_timestamp = first_timestamp or timestamp
                last_timestamp = timestamp
                chunk_first_timestamp = chunk_first_timestamp or timestamp
                chunk_last_timestamp = timestamp

            top_type, subtype, role, phase, content = detect_kind(record)
            record_types[top_type] += 1
            payload_types[f"{top_type}:{subtype or '-'}"] += 1
            chunk_types[f"{top_type}:{subtype or '-'}"] += 1
            if role:
                roles[role] += 1

            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
            if top_type == "event_msg" and str(payload.get("type") or "") == "task_started":
                possible_turn = payload.get("turn_id") or payload.get("root_turn_id")
                if isinstance(possible_turn, str):
                    current_turn_id = possible_turn
            turn_id = find_turn_id(record, current_turn_id)
            if turn_id and turn_id not in turns:
                turns[turn_id] = TurnSummary(turn_id, len(turn_order) + 1, line_count, line_count)
                turn_order.append(turn_id)
            if turn_id:
                current_turn_id = turn_id
                turns[turn_id].touch(line_count, timestamp)

            tool_name: str | None = None
            if top_type == "response_item" and str(payload.get("type") or "") in {"custom_tool_call", "function_call"}:
                name_value = payload.get("name")
                tool_name = str(name_value) if isinstance(name_value, str) else "unknown"
                tool_names[tool_name] += 1
                if turn_id:
                    turns[turn_id].tool_calls[tool_name] += 1
            item = payload.get("item") if isinstance(payload, dict) else None
            item_type_normalized = str(item.get("type") or "").replace("_", "").lower() if isinstance(item, dict) else ""
            if isinstance(item, dict) and item_type_normalized in {"commandexecution", "mcptoolcall", "filechange"}:
                name_value = item.get("name") or item.get("tool_name") or item.get("type")
                tool_name = str(name_value)
                tool_names[tool_name] += 1
                if turn_id and str(payload.get("type") or "") == "item_started":
                    turns[turn_id].tool_calls[tool_name] += 1

            text = text_from_content(content)
            is_compaction = "compact" in top_type.lower() or "compact" in subtype.lower()
            is_message = top_type == "response_item" and str(payload.get("type") or "") == "message"
            is_tool_record = (
                (
                    top_type == "response_item"
                    and str(payload.get("type") or "")
                    in {"custom_tool_call", "custom_tool_call_output", "function_call", "function_call_output"}
                )
                or (isinstance(item, dict) and item_type_normalized in {"commandexecution", "mcptoolcall", "filechange"})
            )
            important = bool(text and (is_message or is_compaction or is_tool_record or HIGH_VALUE_RE.search(text)))
            if top_type in {"session_meta", "turn_context"}:
                important = important or bool(text)
            if text and important:
                original_chars = len(text)
                replacement_chars = text.count("\ufffd")
                if replacement_chars:
                    encoding_replacement_char_count += replacement_chars
                    encoding_damaged_record_count += 1
                content_hash = sha256_text(text)
                omitted_chars = 0
                index_text = text
                if original_chars > MAX_INDEX_SCAN_CHARS:
                    head_chars = MAX_INDEX_SCAN_CHARS // 2
                    tail_chars = MAX_INDEX_SCAN_CHARS // 4
                    omitted_chars = original_chars - head_chars - tail_chars
                    index_text = (
                        text[:head_chars]
                        + f"\n[...OMITTED {omitted_chars} CHARS FROM LARGE TOOL/MEDIA PAYLOAD...]\n"
                        + text[-tail_chars:]
                    )
                redacted = redact(index_text, redaction_counts)
                normalized = normalize_text(redacted)
                excerpt, truncated = bounded_excerpt(normalized, args.max_excerpt_chars)
                text_hash = content_hash
                duplicate_of = duplicate_first_line.get(text_hash)
                if duplicate_of is None:
                    duplicate_first_line[text_hash] = line_count
                theme_scan = normalized
                if len(theme_scan) > 80_000:
                    theme_scan = theme_scan[:60_000] + "\n[...THEME SCAN BOUNDED...]\n" + theme_scan[-20_000:]
                themes = classify_themes(theme_scan)
                for theme in themes:
                    theme_counts[theme] += 1
                    chunk_themes[theme] += 1
                    if turn_id:
                        turns[turn_id].themes[theme] += 1
                event = {
                    "source_line": line_count,
                    "timestamp": timestamp,
                    "turn_id": turn_id,
                    "record_type": top_type,
                    "record_subtype": subtype,
                    "role": role,
                    "phase": phase,
                    "tool_name": tool_name,
                    "themes": themes,
                    "original_char_count": original_chars,
                    "source_replacement_char_count": replacement_chars,
                    "excerpt_truncated": truncated or omitted_chars > 0,
                    "omitted_char_count": omitted_chars,
                    "content_sha256": text_hash,
                    "duplicate_of_line": duplicate_of,
                    "excerpt": excerpt if duplicate_of is None else None,
                }
                events_handle.write(json_dump(event) + "\n")
                chunk_important += 1

                message_ref = {
                    "line": line_count,
                    "timestamp": timestamp,
                    "phase": phase,
                    "content_sha256": text_hash,
                    "duplicate_of_line": duplicate_of,
                    "excerpt": (excerpt[:2500] if duplicate_of is None else None),
                }
                if turn_id and is_message:
                    if role == "user" and len(turns[turn_id].user_messages) < 12:
                        turns[turn_id].user_messages.append(message_ref)
                    elif role == "assistant" and len(turns[turn_id].assistant_messages) < 30:
                        turns[turn_id].assistant_messages.append(message_ref)
                if turn_id and is_compaction and len(turns[turn_id].compactions) < 8:
                    turns[turn_id].compactions.append(message_ref)
                if turn_id and is_tool_record and HIGH_VALUE_RE.search(theme_scan):
                    turns[turn_id].tool_output_lines.append(line_count)

            if line_count % args.chunk_lines == 0:
                chunks_handle.write(
                    json_dump(
                        {
                            "source_lines": [chunk_start_line, line_count],
                            "source_bytes": [chunk_start_byte, byte_count],
                            "timestamps": [chunk_first_timestamp, chunk_last_timestamp],
                            "record_types": dict(chunk_types),
                            "themes": dict(chunk_themes),
                            "important_event_count": chunk_important,
                        }
                    )
                    + "\n"
                )
                chunk_start_line = line_count + 1
                chunk_start_byte = byte_count
                chunk_first_timestamp = None
                chunk_last_timestamp = None
                chunk_types.clear()
                chunk_themes.clear()
                chunk_important = 0

        if chunk_start_line <= line_count:
            chunks_handle.write(
                json_dump(
                    {
                        "source_lines": [chunk_start_line, line_count],
                        "source_bytes": [chunk_start_byte, byte_count],
                        "timestamps": [chunk_first_timestamp, chunk_last_timestamp],
                        "record_types": dict(chunk_types),
                        "themes": dict(chunk_themes),
                        "important_event_count": chunk_important,
                    }
                )
                + "\n"
            )

    with turns_path.open("w", encoding="utf-8", newline="\n") as turns_handle:
        for turn_id in turn_order:
            turns_handle.write(json_dump(turns[turn_id].as_dict()) + "\n")

    source_stat_end = source.stat()
    coverage = {
        "schema_version": "codex_session_memory_extraction_v1",
        "generated_at_utc": utc_now(),
        "source": {
            "session_id": session_id,
            "path": str(source),
            "size_at_start": source_stat_start.st_size,
            "size_at_end": source_stat_end.st_size,
            "mtime_at_start_ns": source_stat_start.st_mtime_ns,
            "mtime_at_end_ns": source_stat_end.st_mtime_ns,
            "bytes_read": byte_count,
            "sha256_of_bytes_read": source_hash.hexdigest(),
            "stable_during_read": (
                source_stat_start.st_size == source_stat_end.st_size
                and source_stat_start.st_mtime_ns == source_stat_end.st_mtime_ns
            ),
            "opened_read_only": True,
        },
        "coverage": {
            "physical_line_count": line_count,
            "parse_error_count": len(parse_errors),
            "parse_errors_capped": parse_errors,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "turn_count": len(turn_order),
            "important_event_count": sum(1 for _ in events_path.open("r", encoding="utf-8")),
            "unique_content_fingerprints": len(duplicate_first_line),
            "encoding_replacement_char_count": encoding_replacement_char_count,
            "encoding_damaged_record_count": encoding_damaged_record_count,
        },
        "record_types": dict(record_types),
        "payload_types": dict(payload_types),
        "roles": dict(roles),
        "tool_names": dict(tool_names),
        "themes": dict(theme_counts),
        "redactions": dict(redaction_counts),
        "outputs": {
            "events": events_path.name,
            "turns": turns_path.name,
            "coverage_chunks": chunks_path.name,
        },
        "claim_boundary": {
            "raw_session_copied": False,
            "encrypted_reasoning_copied": False,
            "known_credentials_copied": False,
            "excerpts_are_complete_transcripts": False,
            "tool_outputs_are_bounded_and_deduplicated": True,
        },
    }
    coverage_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme_path.write_text(
        "\n".join(
            [
                f"# Redacted session index: {session_id}",
                "",
                "This directory is generated from a read-only streaming pass over the source Codex JSONL.",
                "It contains bounded, redacted excerpts and source line numbers, not a transcript copy.",
                "",
                f"- Source lines covered: 1-{line_count}",
                f"- Source bytes read: {byte_count}",
                f"- Stable during read: {coverage['source']['stable_during_read']}",
                f"- Parse errors: {len(parse_errors)}",
                f"- Turns indexed: {len(turn_order)}",
                f"- Sensitive matches redacted: {sum(redaction_counts.values())}",
                "",
                "Use `coverage.json` for completeness, `coverage_chunks.jsonl` for batch coverage,",
                "`turns.jsonl` for task-level summaries, and `events.jsonl` for source-indexed evidence.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
