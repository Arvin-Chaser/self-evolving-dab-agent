"""Task-facing successor to G13 requirement-observation coverage.

G13 proved that a bounded requirement/observation state machine could be wired
into the DAB agent, but its opaque carrier was designed for structural audit
rather than for solving tasks.  This module keeps the useful parts--explicit
requirements, evidence references, unresolved-gap selection and bounded next
actions--and turns them into a semantic working-memory tool used directly by
the DataAgent.

The workspace is model-authored.  It is not a correctness oracle.  Runtime
checks only enforce provenance, bounded state, action repetition and a real
synthesis boundary.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


WORKSPACE_TOOL_NAME = "manage_task_workspace"
WORKSPACE_SCHEMA = "g0132_task_workspace_v1"
STATE_MESSAGE_PREFIX = "[TASK_WORKSPACE_STATE_V1]"
ACTION_TOOLS = frozenset(
    {"list_db", "query_db", "execute_python", "run_evolved_helper"}
)
MAX_REQUIREMENTS = 16
MAX_EVIDENCE_PER_REQUIREMENT = 10
MAX_DESCRIPTION_CHARS = 600
MAX_FINDING_CHARS = 900
MAX_PURPOSE_CHARS = 400
REQUIREMENT_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}\Z")


class WorkspaceValidationError(ValueError):
    pass


def _bounded_text(value: Any, field_name: str, limit: int, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise WorkspaceValidationError(f"{field_name} must be a string")
    text = re.sub(r"\s+", " ", value).strip()
    if required and not text:
        raise WorkspaceValidationError(f"{field_name} must not be empty")
    if len(text) > limit:
        raise WorkspaceValidationError(f"{field_name} exceeds {limit} characters")
    return text


def _requirement_id(value: Any) -> str:
    if not isinstance(value, str) or REQUIREMENT_ID_RE.fullmatch(value) is None:
        raise WorkspaceValidationError("requirement_id must be a bounded identifier")
    return value


@dataclass
class EvidenceItem:
    evidence_ref: str
    finding: str
    effect: str

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_ref": self.evidence_ref,
            "finding": self.finding,
            "effect": self.effect,
        }


@dataclass
class Requirement:
    requirement_id: str
    description: str
    priority: str
    success_criterion: str
    status: str = "unresolved"
    status_reason: str = ""
    next_action: str = ""
    attempt_count: int = 0
    evidence: list[EvidenceItem] = field(default_factory=list)

    def to_dict(self, *, evidence_limit: int | None = None) -> dict[str, Any]:
        evidence = self.evidence
        if evidence_limit is not None:
            evidence = evidence[-evidence_limit:]
        return {
            "requirement_id": self.requirement_id,
            "description": self.description,
            "priority": self.priority,
            "success_criterion": self.success_criterion,
            "status": self.status,
            "status_reason": self.status_reason,
            "next_action": self.next_action,
            "attempt_count": self.attempt_count,
            "evidence": [item.to_dict() for item in evidence],
        }


class TaskWorkspaceEngine:
    """Bounded semantic workspace with deterministic provenance checks."""

    def __init__(self) -> None:
        self.requirements: dict[str, Requirement] = {}
        self.phase = "discovery"
        self.revision = 0
        self.phase_reason = ""
        self.pending_evidence: dict[str, dict[str, str]] = {}
        self.successful_action_signatures: set[str] = set()
        self.failed_action_counts: dict[str, int] = {}
        self.tool_action_counts: dict[str, int] = {}
        self.blocked_action_count = 0
        self.compacted_message_count = 0
        self.verification_actions_used = 0

    @property
    def initialized(self) -> bool:
        return bool(self.requirements)

    @property
    def referenced_evidence(self) -> set[str]:
        return {
            item.evidence_ref
            for requirement in self.requirements.values()
            for item in requirement.evidence
        }

    def set_plan(self, raw_requirements: Any, *, reason: Any = "") -> None:
        if self.phase == "synthesis":
            raise WorkspaceValidationError("cannot replace the plan during synthesis")
        if not isinstance(raw_requirements, list) or not (1 <= len(raw_requirements) <= MAX_REQUIREMENTS):
            raise WorkspaceValidationError(
                f"requirements must contain 1..{MAX_REQUIREMENTS} rows"
            )
        planned: dict[str, Requirement] = {}
        for raw in raw_requirements:
            if not isinstance(raw, Mapping):
                raise WorkspaceValidationError("each requirement must be an object")
            rid = _requirement_id(raw.get("requirement_id"))
            if rid in planned:
                raise WorkspaceValidationError(f"duplicate requirement_id: {rid}")
            priority = raw.get("priority", "must")
            if priority not in {"must", "should"}:
                raise WorkspaceValidationError("priority must be must or should")
            planned[rid] = Requirement(
                requirement_id=rid,
                description=_bounded_text(
                    raw.get("description"), "description", MAX_DESCRIPTION_CHARS
                ),
                priority=priority,
                success_criterion=_bounded_text(
                    raw.get("success_criterion"),
                    "success_criterion",
                    MAX_DESCRIPTION_CHARS,
                ),
            )
        if self.requirements:
            removed_with_state = [
                rid
                for rid, existing in self.requirements.items()
                if rid not in planned
                and (
                    existing.evidence
                    or existing.attempt_count
                    or any(
                        row["requirement_id"] == rid
                        for row in self.pending_evidence.values()
                    )
                )
            ]
            if removed_with_state:
                raise WorkspaceValidationError(
                    "cannot remove requirements with actions/evidence: "
                    + ", ".join(sorted(removed_with_state))
                )
            for rid, replacement in planned.items():
                existing = self.requirements.get(rid)
                if existing is None:
                    continue
                replacement.status = existing.status
                replacement.status_reason = existing.status_reason
                replacement.next_action = existing.next_action
                replacement.attempt_count = existing.attempt_count
                replacement.evidence = existing.evidence
        self.requirements = planned
        self.phase_reason = _bounded_text(reason, "reason", MAX_FINDING_CHARS, required=False)
        self.revision += 1

    def update(self, raw_updates: Any) -> None:
        if not self.initialized:
            raise WorkspaceValidationError("set_plan must be called before update")
        if not isinstance(raw_updates, list) or not raw_updates:
            raise WorkspaceValidationError("updates must be a non-empty array")
        staged = copy.deepcopy(self.requirements)
        for raw in raw_updates:
            if not isinstance(raw, Mapping):
                raise WorkspaceValidationError("each update must be an object")
            rid = _requirement_id(raw.get("requirement_id"))
            if rid not in staged:
                raise WorkspaceValidationError(f"unknown requirement_id: {rid}")
            requirement = staged[rid]
            evidence_ref = raw.get("evidence_ref")
            finding = raw.get("finding")
            effect = raw.get("effect")
            if evidence_ref is not None:
                if not isinstance(evidence_ref, str) or evidence_ref not in self.pending_evidence:
                    raise WorkspaceValidationError(
                        "evidence_ref must name a task-tool result exposed by this workspace"
                    )
                pending = self.pending_evidence[evidence_ref]
                if pending["requirement_id"] != rid:
                    raise WorkspaceValidationError(
                        f"evidence_ref {evidence_ref} belongs to {pending['requirement_id']}"
                    )
                if effect not in {"supports", "contradicts", "inconclusive"}:
                    raise WorkspaceValidationError(
                        "effect must be supports, contradicts, or inconclusive"
                    )
                if any(item.evidence_ref == evidence_ref for item in requirement.evidence):
                    raise WorkspaceValidationError(f"duplicate evidence_ref: {evidence_ref}")
                if len(requirement.evidence) >= MAX_EVIDENCE_PER_REQUIREMENT:
                    raise WorkspaceValidationError(
                        f"requirement {rid} reached its evidence cap"
                    )
                requirement.evidence.append(
                    EvidenceItem(
                        evidence_ref=evidence_ref,
                        finding=_bounded_text(
                            finding, "finding", MAX_FINDING_CHARS
                        ),
                        effect=effect,
                    )
                )
            elif finding is not None or effect is not None:
                raise WorkspaceValidationError(
                    "finding/effect require an evidence_ref"
                )

            status = raw.get("status")
            if status is not None:
                if status not in {"unresolved", "satisfied", "blocked"}:
                    raise WorkspaceValidationError(
                        "status must be unresolved, satisfied, or blocked"
                    )
                if status == "satisfied" and not any(
                    item.effect == "supports" for item in requirement.evidence
                ):
                    raise WorkspaceValidationError(
                        f"requirement {rid} cannot be satisfied without supporting evidence"
                    )
                status_reason = _bounded_text(
                    raw.get("status_reason", ""),
                    "status_reason",
                    MAX_FINDING_CHARS,
                    required=status in {"satisfied", "blocked"},
                )
                requirement.status = status
                requirement.status_reason = status_reason

            if "next_action" in raw:
                requirement.next_action = _bounded_text(
                    raw.get("next_action"),
                    "next_action",
                    MAX_PURPOSE_CHARS,
                    required=False,
                )
        self.requirements = staged
        for raw in raw_updates:
            ref = raw.get("evidence_ref") if isinstance(raw, Mapping) else None
            if isinstance(ref, str):
                self.pending_evidence.pop(ref, None)
        self.revision += 1

    def enter_synthesis(self, reason: Any) -> None:
        if not self.initialized:
            raise WorkspaceValidationError("set_plan must be called before synthesis")
        self.phase = "synthesis"
        self.phase_reason = _bounded_text(reason, "reason", MAX_FINDING_CHARS)
        self.revision += 1

    def recommended_action(self) -> dict[str, Any]:
        if not self.initialized:
            return {
                "action": "set_plan",
                "requirement_id": None,
                "reason": "task requirements are not represented yet",
            }
        if self.phase == "synthesis":
            return {
                "action": "synthesize_answer",
                "requirement_id": None,
                "reason": self.phase_reason or "workspace is in synthesis phase",
            }
        ordered = sorted(
            self.requirements.values(),
            key=lambda req: (
                0 if req.priority == "must" else 1,
                0 if req.status == "unresolved" else 1,
                len(req.evidence),
                req.attempt_count,
                req.requirement_id,
            ),
        )
        for req in ordered:
            if req.status != "unresolved":
                continue
            pending = [
                ref
                for ref, row in self.pending_evidence.items()
                if row["requirement_id"] == req.requirement_id
            ]
            if pending:
                return {
                    "action": "interpret_evidence",
                    "requirement_id": req.requirement_id,
                    "reason": f"record findings for {', '.join(sorted(pending))}",
                }
            if not req.evidence:
                action = "acquire_evidence"
                reason = req.next_action or "no evidence recorded"
            elif any(item.effect == "contradicts" for item in req.evidence):
                action = "discriminate_hypotheses"
                reason = req.next_action or "current evidence contains a contradiction"
            else:
                action = "resolve_requirement"
                reason = req.next_action or "evidence exists but status remains unresolved"
            return {
                "action": action,
                "requirement_id": req.requirement_id,
                "reason": reason,
            }
        return {
            "action": "enter_synthesis",
            "requirement_id": None,
            "reason": "all represented requirements are satisfied or explicitly blocked",
        }

    def record_action_result(
        self,
        *,
        requirement_id: str,
        tool_name: str,
        purpose: str,
        signature: str,
        success: bool,
        result_refs: Sequence[str],
    ) -> None:
        requirement = self.requirements.get(requirement_id)
        if requirement is None:
            return
        requirement.attempt_count += 1
        if success:
            self.successful_action_signatures.add(signature)
            for ref in result_refs:
                self.pending_evidence[ref] = {
                    "requirement_id": requirement_id,
                    "tool_name": tool_name,
                    "purpose": purpose,
                }
        else:
            self.failed_action_counts[signature] = (
                self.failed_action_counts.get(signature, 0) + 1
            )
        self.revision += 1

    def public_state(self, *, evidence_limit: int = 3) -> dict[str, Any]:
        return {
            "schema_version": WORKSPACE_SCHEMA,
            "revision": self.revision,
            "phase": self.phase,
            "phase_reason": self.phase_reason,
            "requirements": [
                self.requirements[key].to_dict(evidence_limit=evidence_limit)
                for key in sorted(self.requirements)
            ],
            "pending_evidence": [
                {"evidence_ref": ref, **self.pending_evidence[ref]}
                for ref in sorted(self.pending_evidence)
            ],
            "recommended_action": self.recommended_action(),
            "runtime": {
                "blocked_action_count": self.blocked_action_count,
                "compacted_message_count": self.compacted_message_count,
                "verification_actions_used": self.verification_actions_used,
                "tool_action_counts": dict(sorted(self.tool_action_counts.items())),
            },
        }


def canonical_action_signature(tool_name: str, args: Mapping[str, Any]) -> str:
    value = copy.deepcopy(dict(args))
    if isinstance(value.get("query"), str):
        value["query"] = re.sub(r"\s+", " ", value["query"]).strip().lower()
    if isinstance(value.get("code"), str):
        value["code"] = re.sub(r"[ \t]+", " ", value["code"]).strip()
    encoded = json.dumps(
        {"tool": tool_name, "args": value},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class TaskWorkspaceRuntime:
    def __init__(
        self,
        *,
        path: Path | None,
        synthesis_reserve_turns: int,
        final_verification_actions: int,
        compact_evidence_messages: bool,
        max_view_chars: int,
        synthesis_deadline_reserve_sec: float = 240.0,
        max_actions_per_requirement: int = 3,
        max_python_actions: int = 3,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.synthesis_reserve_turns = max(1, int(synthesis_reserve_turns))
        self.final_verification_actions = max(0, int(final_verification_actions))
        self.compact_evidence_messages = bool(compact_evidence_messages)
        self.max_view_chars = max(1000, int(max_view_chars))
        self.synthesis_deadline_reserve_sec = max(
            30.0, float(synthesis_deadline_reserve_sec)
        )
        self.max_actions_per_requirement = max(1, int(max_actions_per_requirement))
        self.max_python_actions = max(1, int(max_python_actions))
        self.engine = TaskWorkspaceEngine()
        self.last_llm_call_count = 0
        self.synthesis_started_at_call: int | None = None

    def persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.engine.public_state(evidence_limit=None), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def apply(self, args: Mapping[str, Any]) -> dict[str, Any]:
        operation = args.get("operation")
        if operation == "set_plan":
            self.engine.set_plan(args.get("requirements"), reason=args.get("reason", ""))
        elif operation == "update":
            self.engine.update(args.get("updates"))
        elif operation == "enter_synthesis":
            self.engine.enter_synthesis(args.get("reason"))
        elif operation != "review":
            raise WorkspaceValidationError(
                "operation must be set_plan, update, review, or enter_synthesis"
            )
        self.persist()
        return self.engine.public_state()

    def prepare_action(
        self, tool_name: str, args: Mapping[str, Any]
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if tool_name not in ACTION_TOOLS:
            return True, "", None
        rid_raw = args.get("workspace_requirement_id")
        purpose_raw = args.get("workspace_action_purpose")
        try:
            rid = _requirement_id(rid_raw)
            purpose = _bounded_text(
                purpose_raw, "workspace_action_purpose", MAX_PURPOSE_CHARS
            )
        except WorkspaceValidationError as exc:
            return False, str(exc), None
        if not self.engine.initialized:
            return False, "call manage_task_workspace(set_plan) before task tools", None
        if rid not in self.engine.requirements:
            return False, f"unknown workspace requirement: {rid}", None
        requirement = self.engine.requirements[rid]
        if requirement.attempt_count >= self.max_actions_per_requirement:
            self.engine.blocked_action_count += 1
            self.persist()
            return (
                False,
                "requirement action cap reached; mark it blocked, choose another "
                "requirement, or enter synthesis",
                None,
            )
        if (
            tool_name == "execute_python"
            and self.engine.tool_action_counts.get(tool_name, 0)
            >= self.max_python_actions
        ):
            self.engine.blocked_action_count += 1
            self.persist()
            return (
                False,
                "execute_python action cap reached; use existing evidence or enter synthesis",
                None,
            )
        cleaned = {
            key: copy.deepcopy(value)
            for key, value in args.items()
            if key not in {"workspace_requirement_id", "workspace_action_purpose"}
        }
        signature = canonical_action_signature(tool_name, cleaned)
        if signature in self.engine.successful_action_signatures:
            self.engine.blocked_action_count += 1
            self.persist()
            return False, "exact successful action repetition blocked; change the query/code or synthesize", None
        if self.engine.failed_action_counts.get(signature, 0) >= 2:
            self.engine.blocked_action_count += 1
            self.persist()
            return False, "action failed twice unchanged; revise the approach", None
        if self.engine.phase == "synthesis":
            if self.engine.verification_actions_used >= self.final_verification_actions:
                self.engine.blocked_action_count += 1
                self.persist()
                return False, "synthesis phase permits no further acquisition; return the best supported answer", None
            self.engine.verification_actions_used += 1
        return True, "", {
            "requirement_id": rid,
            "purpose": purpose,
            "cleaned_args": cleaned,
            "signature": signature,
        }

    def record_action_result(
        self,
        *,
        tool_name: str,
        metadata: Mapping[str, Any],
        success: bool,
        result_refs: Sequence[str],
    ) -> None:
        self.engine.tool_action_counts[tool_name] = (
            self.engine.tool_action_counts.get(tool_name, 0) + 1
        )
        self.engine.record_action_result(
            requirement_id=str(metadata["requirement_id"]),
            tool_name=tool_name,
            purpose=str(metadata["purpose"]),
            signature=str(metadata["signature"]),
            success=success,
            result_refs=result_refs,
        )
        self.persist()

    def maybe_enter_synthesis(self, *, llm_call_count: int, max_iterations: Any) -> None:
        self.last_llm_call_count = int(llm_call_count)
        if not self.engine.initialized:
            return
        if self.engine.phase == "synthesis":
            if self.synthesis_started_at_call is None:
                self.synthesis_started_at_call = self.last_llm_call_count
            return
        try:
            finite = math.isfinite(float(max_iterations))
        except (TypeError, ValueError):
            finite = False
        if finite and int(max_iterations) - int(llm_call_count) <= self.synthesis_reserve_turns:
            self.engine.enter_synthesis(
                f"runtime reserved the final {self.synthesis_reserve_turns} model turns for synthesis"
            )
            self.synthesis_started_at_call = self.last_llm_call_count
            self.persist()
            return
        raw_deadline = os.environ.get("DAB_TASK_DEADLINE_MONOTONIC")
        try:
            remaining = float(raw_deadline) - time.monotonic() if raw_deadline else None
        except (TypeError, ValueError):
            remaining = None
        if remaining is not None and remaining <= self.synthesis_deadline_reserve_sec:
            self.engine.enter_synthesis(
                "runtime reserved the remaining wall-clock budget for synthesis"
            )
            self.synthesis_started_at_call = self.last_llm_call_count
            self.persist()

    @property
    def final_only(self) -> bool:
        return (
            self.engine.phase == "synthesis"
            and (
                self.engine.verification_actions_used
                >= self.final_verification_actions
                or (
                    self.synthesis_started_at_call is not None
                    and self.last_llm_call_count > self.synthesis_started_at_call
                )
            )
        )

    def compact_messages(self, messages: list[Any], *, keep_recent_tool_messages: int = 4) -> None:
        if not self.compact_evidence_messages:
            return
        refs = self.engine.referenced_evidence
        tool_indexes = [
            index
            for index, message in enumerate(messages)
            if isinstance(message, Mapping) and message.get("role") == "tool"
        ]
        workspace_indexes = [
            index
            for index in tool_indexes
            if messages[index].get("name") == WORKSPACE_TOOL_NAME
        ]
        latest_workspace_index = workspace_indexes[-1] if workspace_indexes else None
        protected = set(tool_indexes[-keep_recent_tool_messages:])
        for index in tool_indexes:
            message = messages[index]
            content = message.get("content")
            if not isinstance(content, str) or content.startswith("[WORKSPACE_COMPACTED]"):
                continue
            if (
                message.get("name") == WORKSPACE_TOOL_NAME
                and index != latest_workspace_index
            ):
                messages[index] = {
                    **dict(message),
                    "content": (
                        "[WORKSPACE_COMPACTED] Earlier workspace snapshot was "
                        "superseded by TASK_WORKSPACE_STATE_V1."
                    ),
                }
                self.engine.compacted_message_count += 1
                continue
            if index in protected:
                continue
            matched = next((ref for ref in refs if ref in content), None)
            if matched is None:
                continue
            messages[index] = {
                **dict(message),
                "content": (
                    f"[WORKSPACE_COMPACTED] Result {matched} was incorporated into "
                    "TASK_WORKSPACE_STATE_V1. Raw data remains in result_storage for "
                    "execute_python if a bounded re-check is necessary."
                ),
            }
            self.engine.compacted_message_count += 1

    def render_state_message(self) -> str:
        state = self.engine.public_state(evidence_limit=2)
        text = STATE_MESSAGE_PREFIX + " " + json.dumps(
            state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(text) > self.max_view_chars:
            compact = {
                "schema_version": WORKSPACE_SCHEMA,
                "revision": self.engine.revision,
                "phase": self.engine.phase,
                "requirements": [
                    {
                        "requirement_id": req.requirement_id,
                        "priority": req.priority,
                        "status": req.status,
                        "attempt_count": req.attempt_count,
                        "evidence_refs": [item.evidence_ref for item in req.evidence[-2:]],
                        "next_action": req.next_action,
                    }
                    for req in self.engine.requirements.values()
                ],
                "pending_evidence": sorted(self.engine.pending_evidence),
                "recommended_action": self.engine.recommended_action(),
            }
            text = STATE_MESSAGE_PREFIX + " " + json.dumps(
                compact, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        return text[: self.max_view_chars]

    def sync_state_message(self, messages: list[Any]) -> None:
        messages[:] = [
            message
            for message in messages
            if not (
                isinstance(message, Mapping)
                and isinstance(message.get("content"), str)
                and message["content"].startswith(STATE_MESSAGE_PREFIX)
            )
        ]
        state_message = {"role": "system", "content": self.render_state_message()}
        insert_at = 1 if messages and isinstance(messages[0], Mapping) and messages[0].get("role") == "system" else 0
        messages.insert(insert_at, state_message)


def _workspace_tool_spec(name: str) -> dict[str, Any]:
    requirement_schema = {
        "type": "object",
        "properties": {
            "requirement_id": {"type": "string"},
            "description": {"type": "string"},
            "priority": {"type": "string", "enum": ["must", "should"]},
            "success_criterion": {"type": "string"},
        },
        "required": ["requirement_id", "description", "priority", "success_criterion"],
    }
    update_schema = {
        "type": "object",
        "properties": {
            "requirement_id": {"type": "string"},
            "evidence_ref": {"type": "string"},
            "finding": {"type": "string"},
            "effect": {
                "type": "string",
                "enum": ["supports", "contradicts", "inconclusive"],
            },
            "status": {
                "type": "string",
                "enum": ["unresolved", "satisfied", "blocked"],
            },
            "status_reason": {"type": "string"},
            "next_action": {"type": "string"},
        },
        "required": ["requirement_id"],
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Maintain the task-solving requirement/evidence workspace. Start with set_plan. "
                "After a task tool returns, use update to bind its var_* evidence_ref, summarize "
                "the finding, and revise requirement status. Use review without mutation. Enter "
                "synthesis when the answer can be produced or remaining gaps must be disclosed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["set_plan", "update", "review", "enter_synthesis"],
                    },
                    "requirements": {"type": "array", "items": requirement_schema},
                    "updates": {"type": "array", "items": update_schema},
                    "reason": {"type": "string"},
                },
                "required": ["operation"],
            },
        },
    }


def _augment_action_spec(spec: Any) -> Any:
    if not isinstance(spec, dict):
        return spec
    function = spec.get("function")
    if not isinstance(function, dict) or function.get("name") not in ACTION_TOOLS:
        return spec
    parameters = function.get("parameters")
    if not isinstance(parameters, dict):
        return spec
    properties = parameters.setdefault("properties", {})
    properties["workspace_requirement_id"] = {
        "type": "string",
        "description": "Existing task-workspace requirement this action advances.",
    }
    properties["workspace_action_purpose"] = {
        "type": "string",
        "description": "Specific information gain expected from this action.",
    }
    required = parameters.setdefault("required", [])
    for name in ("workspace_requirement_id", "workspace_action_purpose"):
        if name not in required:
            required.append(name)
    function["description"] = str(function.get("description") or "").rstrip() + (
        " This action must be tied to an existing task-workspace requirement and a "
        "specific information-gain purpose."
    )
    return spec


def install_task_workspace(data_agent_module: Any, args: Any) -> dict[str, Any]:
    """Install the G13 successor as a real DataAgent tool and runtime controller."""
    if not getattr(args, "enable_g0132_task_workspace", False):
        return {"enabled": False, "installed": False}

    BaseTool = data_agent_module.BaseTool
    original_data_agent = data_agent_module.DataAgent
    if getattr(original_data_agent, "_g0132_task_workspace_installed", False):
        return {"enabled": True, "installed": True, "tool_name": WORKSPACE_TOOL_NAME}

    class TaskWorkspaceTool(BaseTool):
        def __init__(self, log_path: Path, runtime: TaskWorkspaceRuntime):
            super().__init__(log_path, WORKSPACE_TOOL_NAME)
            self.runtime = runtime

        def get_spec(self):
            return _workspace_tool_spec(self.name)

        def _check_args(self, tool_args: dict):
            tool_args = super()._check_args(tool_args)
            if not isinstance(tool_args, dict):
                raise WorkspaceValidationError("workspace arguments must be an object")
            return tool_args

        def _exec(self, tool_args: dict):
            super()._exec(tool_args)
            return self.runtime.apply(tool_args)

        def clean_up(self):
            self.runtime.persist()

    class _FunctionProxy:
        def __init__(self, original: Any, arguments: str):
            self.name = getattr(original, "name", None)
            self.arguments = arguments

    class _ToolCallProxy:
        def __init__(self, original: Any, arguments: str):
            self._original = original
            self.id = getattr(original, "id", None)
            self.type = getattr(original, "type", "function")
            self.function = _FunctionProxy(getattr(original, "function", None), arguments)

        def model_dump(self):
            if hasattr(self._original, "model_dump"):
                value = self._original.model_dump()
                if isinstance(value, dict):
                    value = copy.deepcopy(value)
                    value.setdefault("function", {})["arguments"] = self.function.arguments
                    return value
            return {
                "id": self.id,
                "type": self.type,
                "function": {
                    "name": self.function.name,
                    "arguments": self.function.arguments,
                },
            }

    original_init = original_data_agent.__init__
    original_handle = original_data_agent._handle_tool_call
    original_call_llm = original_data_agent.call_llm
    original_to_dict = original_data_agent.to_dict

    class DataAgentWithTaskWorkspace(original_data_agent):
        def __init__(self, *agent_args: Any, **agent_kwargs: Any):
            original_init(self, *agent_args, **agent_kwargs)
            runtime = TaskWorkspaceRuntime(
                path=Path(self.root_dir) / "task_workspace.json",
                synthesis_reserve_turns=getattr(args, "g0132_synthesis_reserve_turns", 6),
                final_verification_actions=getattr(args, "g0132_final_verification_actions", 1),
                compact_evidence_messages=not getattr(
                    args, "disable_g0132_message_compaction", False
                ),
                max_view_chars=getattr(args, "g0132_workspace_max_view_chars", 6000),
                synthesis_deadline_reserve_sec=getattr(
                    args, "g0132_synthesis_deadline_reserve_sec", 240.0
                ),
                max_actions_per_requirement=getattr(
                    args, "g0132_max_actions_per_requirement", 3
                ),
                max_python_actions=getattr(args, "g0132_max_python_actions", 3),
            )
            self._g0132_task_workspace = runtime
            self.tools[WORKSPACE_TOOL_NAME] = TaskWorkspaceTool(
                self.tool_log_path, runtime
            )
            for name, tool in self.tools.items():
                if name not in ACTION_TOOLS:
                    continue
                original_get_spec = tool.get_spec

                def get_spec(original_get_spec=original_get_spec):
                    return _augment_action_spec(original_get_spec())

                tool.get_spec = get_spec
            runtime.persist()

        def _handle_tool_call(self, tool_call: Any):
            function = getattr(tool_call, "function", None)
            tool_name = getattr(function, "name", None)
            raw_arguments = getattr(function, "arguments", None)
            if tool_name == WORKSPACE_TOOL_NAME:
                try:
                    parsed = json.loads(raw_arguments)
                except (TypeError, json.JSONDecodeError) as exc:
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": getattr(tool_call, "id", None),
                            "name": tool_name,
                            "content": f"Task workspace arguments are invalid JSON: {exc}",
                        }
                    )
                    return None
                exec_result = self.tools[tool_name].exec(parsed)
                if exec_result["success"]:
                    content = (
                        "Task workspace updated. Current compact state:\n"
                        + json.dumps(
                            exec_result["result"],
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    )
                else:
                    content = f"Task workspace update failed: {exec_result['result']}"
                # Unlike database/Python results, workspace snapshots are
                # control state and must not accumulate in result_storage or
                # the execute_python environment.
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": getattr(tool_call, "id", None),
                        "name": tool_name,
                        "content": content,
                    }
                )
                return exec_result
            if tool_name not in ACTION_TOOLS:
                return original_handle(self, tool_call)
            try:
                parsed = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError):
                return original_handle(self, tool_call)
            if not isinstance(parsed, dict):
                return original_handle(self, tool_call)
            runtime = self._g0132_task_workspace
            allowed, reason, metadata = runtime.prepare_action(tool_name, parsed)
            if not allowed or metadata is None:
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": getattr(tool_call, "id", None),
                        "name": tool_name,
                        "content": (
                            f"The task workspace blocked {tool_name}: {reason}. "
                            "Use manage_task_workspace to review/update state, change the action, "
                            "or return the best supported answer."
                        ),
                    }
                )
                return None
            before = set(self.result_storage)
            proxied = _ToolCallProxy(
                tool_call,
                json.dumps(metadata["cleaned_args"], ensure_ascii=False),
            )
            result = original_handle(self, proxied)
            after = set(self.result_storage)
            new_refs = sorted(after - before)
            runtime.record_action_result(
                tool_name=tool_name,
                metadata=metadata,
                success=bool(new_refs),
                result_refs=new_refs,
            )
            return result

        def call_llm(self):
            runtime = self._g0132_task_workspace
            runtime.maybe_enter_synthesis(
                llm_call_count=self.llm_call_count,
                max_iterations=self.max_iterations,
            )
            runtime.compact_messages(self.messages)
            runtime.sync_state_message(self.messages)
            runtime.persist()
            if not runtime.final_only:
                return original_call_llm(self)
            original_tools = self.tools
            self.tools = {
                name: tool
                for name, tool in original_tools.items()
                if name == "return_answer"
            }
            try:
                return original_call_llm(self)
            finally:
                self.tools = original_tools

        def to_dict(self):
            value = original_to_dict(self)
            runtime = self._g0132_task_workspace
            value["g0132_task_workspace"] = runtime.engine.public_state()
            value["g0132_task_workspace_path"] = str(runtime.path)
            value["g0132_final_only"] = runtime.final_only
            return value

    DataAgentWithTaskWorkspace._g0132_task_workspace_installed = True
    data_agent_module.DataAgent = DataAgentWithTaskWorkspace
    return {
        "enabled": True,
        "installed": True,
        "tool_name": WORKSPACE_TOOL_NAME,
        "action_tools": sorted(ACTION_TOOLS),
    }
