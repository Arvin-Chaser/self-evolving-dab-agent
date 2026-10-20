"""Answer-blind r8 citation proxy for human diagnosis, never Meta input."""

import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path


BASE = Path("/srv/text2sql/evolution_runtime/half56_v1/campaigns/dataset17_half56_deepseek_v1_20261011/gen015_handoff_reach_repair_r8_revision001")
RUN = BASE / "evaluation/gen015_handoff_reach_formal_r8_revision001"
sys.path.insert(0, str(BASE / "candidate_source"))
from experiments.phase_evidence_handoff import EXPLORATION_CONTEXT_RULES
from experiments.runtime_directive_channel import split_runtime_directives

LABEL = re.compile(r"\bE[1-9][0-9]*\b")


def phase_b_request(messages):
    if not messages or not isinstance(messages[0], dict):
        return False
    system = str(messages[0].get("content") or "")
    return not system.endswith(EXPLORATION_CONTEXT_RULES) and any(
        "# COMPOSITION PHASE (sealed evidence only)" in str(message.get("content") or "")
        for message in messages if isinstance(message, dict)
    )


def main():
    rows = json.loads((RUN / "multi_query_summary.json").read_text(encoding="utf-8"))["per_query_feedback"]
    counts = Counter()
    answer_argument_keys = Counter()
    answer_fields_with_labels = Counter()
    score_by_answer_label = Counter()
    exploration_observation_shapes = Counter()
    exploration_observation_statuses = Counter()
    exploration_shape_by_tool_status = Counter()
    execution_trace_event_types = Counter()
    trace_tool_end_keys = set()
    trace_tool_end_result_types = Counter()
    trace_tool_end_raw_call_keys = set()
    trace_tool_end_result_keys = set()
    text_query_parse = Counter()
    text_query_prefix_shapes = Counter()
    for row in rows:
        if row["status"] != "completed":
            continue
        task = json.loads((Path(row["run_dir"]) / "summary.json").read_text(encoding="utf-8"))
        state = task["phase_handoff_summary"]
        text_query_ids = set()
        with Path(task["artifacts"]["phase_evidence_events"]).open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("event") == "phase_call_recorded" and event.get("phase") == "exploration":
                    shape = str(event.get("result_kind") or "missing")
                    status = str(event.get("status") or "missing")
                    exploration_observation_shapes[shape] += 1
                    exploration_observation_statuses[status] += 1
                    exploration_shape_by_tool_status[
                        f"{event.get('tool_name') or 'missing'}:{status}:{shape}"] += 1
                    if (event.get("tool_name") == "query_db" and status == "ok"
                            and shape == "text"):
                        text_query_ids.add(event.get("tool_call_id"))
        with Path(task["artifacts"]["full_execution_trace"]).open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    event = json.loads(line)
                    execution_trace_event_types[str(event.get("event_type") or "missing")] += 1
                    if event.get("event_type") == "tool_call_end":
                        trace_tool_end_keys.update(event)
                        trace_tool_end_result_types[type(event.get("result")).__name__] += 1
                        if isinstance(event.get("raw_tool_call"), dict):
                            trace_tool_end_raw_call_keys.update(event["raw_tool_call"])
                        if isinstance(event.get("result"), dict):
                            trace_tool_end_result_keys.update(event["result"])
        with Path(task["artifacts"]["llm_calls"]).open(encoding="utf-8") as stream:
            calls = [json.loads(line) for line in stream if line.strip()]
        observations = {}
        for call in calls:
            for message in call.get("messages") or []:
                if (isinstance(message, dict) and message.get("role") == "tool"
                        and message.get("tool_call_id") in text_query_ids):
                    observations[message["tool_call_id"]] = str(message.get("content") or "")
        for call_id in text_query_ids:
            if call_id not in observations:
                text_query_parse["observation_missing_from_recorded_requests"] += 1
                continue
            body = split_runtime_directives(observations[call_id])[0].strip()[:12000]
            text_query_parse["observation_found"] += 1
            prefix = " ".join(body[:80].split())
            text_query_prefix_shapes["".join(
                "A" if char.isalpha() else "0" if char.isdigit() else char
                for char in prefix)] += 1
            text_query_parse["has_list_or_object_opener"] += "[" in body or "{" in body
            first_opener = min((position for char in "[{" if (position := body.find(char)) >= 0),
                               default=-1)
            candidates = [body]
            if first_opener > 0:
                candidates.append(body[first_opener:])
            parsed = None
            for candidate in candidates:
                try:
                    parsed = ast.literal_eval(candidate)
                    break
                except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
                    pass
            text_query_parse["python_literal_parseable"] += parsed is not None
            if parsed is not None:
                text_query_parse[f"python_literal_type_{type(parsed).__name__}"] += 1
        counts["completed_rows"] += 1
        row_phase_b = row_query = row_answer = row_answer_ref = False
        row_answer_field_label = False
        row_invalid_answer_ref = False
        for call in calls:
            if not phase_b_request(call.get("messages") or []):
                continue
            row_phase_b = True
            counts["phase_b_model_calls"] += 1
            choices = (call.get("response") or {}).get("choices") or []
            message = choices[0].get("message") or {} if choices else {}
            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function") or {}
                name = function.get("name")
                raw_args = function.get("arguments") or ""
                if isinstance(raw_args, dict):
                    args = raw_args
                    raw_args = json.dumps(raw_args, ensure_ascii=False)
                else:
                    try:
                        args = json.loads(raw_args)
                    except (TypeError, ValueError):
                        args = {}
                if name in {"query_db", "list_db"}:
                    row_query = True
                    counts["phase_b_query_tool_calls"] += 1
                    ref = args.get("bundle_ref") if isinstance(args, dict) else None
                    counts["query_calls_with_bundle_ref"] += bool(
                        isinstance(ref, str) and LABEL.fullmatch(ref))
                elif name == "return_answer":
                    row_answer = True
                    counts["phase_b_return_answer_calls"] += 1
                    if isinstance(args, dict):
                        for key, value in args.items():
                            answer_argument_keys[key] += 1
                            if LABEL.search(json.dumps(value, ensure_ascii=False)):
                                answer_fields_with_labels[key] += 1
                                row_answer_field_label |= key == "answer"
                    labels = LABEL.findall(raw_args)
                    cited = bool(labels)
                    row_answer_ref |= cited
                    counts["return_answer_calls_with_E_label"] += cited
                    counts["answer_label_mentions"] += len(labels)
                    invalid = any(int(label[1:]) > state["bundle_entry_count"] for label in labels)
                    row_invalid_answer_ref |= invalid
                    counts["return_answer_calls_with_invalid_E_label"] += invalid
            content = message.get("content")
            if isinstance(content, str) and content.strip() and not message.get("tool_calls"):
                counts["phase_b_free_text_responses"] += 1
                counts["phase_b_free_text_with_E_label"] += bool(LABEL.search(content))
        counts["phase_b_rows"] += row_phase_b
        counts["phase_b_query_rows"] += row_query
        counts["phase_b_return_answer_rows"] += row_answer
        counts["return_answer_rows_with_E_label"] += row_answer_ref
        counts["return_answer_rows_with_invalid_E_label"] += row_invalid_answer_ref
        counts["fallback_rows"] += bool(state["fallback_used"])
        if row_answer:
            verdict = row.get("strict_match_passed")
            score = "pass" if verdict is True else "fail" if verdict is False else "unscored"
            score_by_answer_label[f"{'cited' if row_answer_field_label else 'uncited'}_{score}"] += 1
    print(json.dumps({"counts": dict(sorted(counts.items())),
                      "return_answer_argument_keys": dict(sorted(answer_argument_keys.items())),
                      "return_answer_fields_with_E_label": dict(sorted(answer_fields_with_labels.items())),
                      "score_by_answer_label": dict(sorted(score_by_answer_label.items())),
                      "exploration_observation_shapes": dict(sorted(exploration_observation_shapes.items())),
                      "exploration_observation_statuses": dict(sorted(exploration_observation_statuses.items())),
                      "exploration_shape_by_tool_status": dict(sorted(exploration_shape_by_tool_status.items())),
                      "execution_trace_event_types": dict(sorted(execution_trace_event_types.items())),
                      "trace_tool_end_keys": sorted(trace_tool_end_keys),
                      "trace_tool_end_result_types": dict(sorted(trace_tool_end_result_types.items())),
                      "trace_tool_end_raw_call_keys": sorted(trace_tool_end_raw_call_keys),
                      "trace_tool_end_result_keys": sorted(trace_tool_end_result_keys),
                      "successful_text_query_parse": dict(sorted(text_query_parse.items())),
                      "text_query_prefix_shapes_top10": text_query_prefix_shapes.most_common(10)},
                     sort_keys=True))


if __name__ == "__main__":
    main()
