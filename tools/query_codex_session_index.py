#!/usr/bin/env python3
"""Query a redacted Codex session index without reading the raw session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index_dir", type=Path)
    parser.add_argument("--start-line", type=int, default=1)
    parser.add_argument("--end-line", type=int, default=2**63 - 1)
    parser.add_argument("--role", action="append", choices=("user", "assistant", "developer", "tool"))
    parser.add_argument("--phase", action="append")
    parser.add_argument("--theme", action="append")
    parser.add_argument("--subtype-contains")
    parser.add_argument("--messages-only", action="store_true")
    parser.add_argument("--compactions-only", action="store_true")
    parser.add_argument("--include-duplicates", action="store_true")
    parser.add_argument("--max-events", type=int, default=200)
    parser.add_argument("--max-chars", type=int, default=1200)
    return parser.parse_args()


def selected(event: dict[str, Any], args: argparse.Namespace) -> bool:
    line_no = event.get("source_line")
    if not isinstance(line_no, int) or not args.start_line <= line_no <= args.end_line:
        return False
    if not args.include_duplicates and event.get("duplicate_of_line") is not None:
        return False
    if args.role and event.get("role") not in set(args.role):
        return False
    if args.phase and event.get("phase") not in set(args.phase):
        return False
    themes = event.get("themes") or []
    if args.theme and not set(args.theme).intersection(themes):
        return False
    subtype = str(event.get("record_subtype") or "")
    if args.subtype_contains and args.subtype_contains.lower() not in subtype.lower():
        return False
    if args.messages_only and not (event.get("record_type") == "response_item" and subtype == "message"):
        return False
    if args.compactions_only and "compact" not in (str(event.get("record_type")) + subtype).lower():
        return False
    return bool(event.get("excerpt"))


def main() -> int:
    args = parse_args()
    events_path = args.index_dir.resolve(strict=True) / "events.jsonl"
    emitted = 0
    with events_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            event = json.loads(raw_line)
            if not selected(event, args):
                continue
            excerpt = str(event.get("excerpt") or "")[: args.max_chars]
            header = {
                "source_line": event.get("source_line"),
                "timestamp": event.get("timestamp"),
                "turn_id": event.get("turn_id"),
                "role": event.get("role"),
                "phase": event.get("phase"),
                "record_type": event.get("record_type"),
                "record_subtype": event.get("record_subtype"),
                "themes": event.get("themes"),
            }
            print(json.dumps(header, ensure_ascii=False, sort_keys=True))
            print(excerpt)
            print("---")
            emitted += 1
            if emitted >= args.max_events:
                break
    print(f"EMITTED={emitted}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
