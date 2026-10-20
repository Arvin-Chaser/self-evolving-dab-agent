"""Versioned infrastructure overlay; never install into a sealed candidate.

Recovery boundary: completed tool calls are committed with agent state and the
workspace digest. An interrupted in-flight tool is ambiguous and resume rejects
it, rather than promising impossible exactly-once external side effects.
Upstream ExecTool executes each Python snippet in a fresh subprocess; its durable
state is its workspace plus result_storage, not a Python interpreter snapshot.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import time
from types import SimpleNamespace

POLICY = "input_and_transport_recovery_v1"
CHECKPOINT_CODEC = "dab_lossless_nonfinite_json_v1"
_CODEC_TAG = "__dab_checkpoint_codec_v1__"
STATE_FIELDS = ("messages", "result_storage", "llm_call_count", "final_result",
                "terminate_reason", "turn_state")


class UnsafeResume(RuntimeError):
    pass


class ProviderFailure(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def encode_checkpoint_value(value):
    """Encode non-finite floats without weakening strict JSON persistence."""
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if math.isfinite(value):
            return value
        return {_CODEC_TAG: ["float64_nonfinite", struct.pack(">d", value).hex()]}
    if type(value) is list:
        return [encode_checkpoint_value(item) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise UnsafeResume("Checkpoint dictionary keys must be strings")
        if _CODEC_TAG in value:
            return {_CODEC_TAG: ["escaped_dict", [
                [key, encode_checkpoint_value(item)] for key, item in value.items()
            ]]}
        return {key: encode_checkpoint_value(item) for key, item in value.items()}
    raise UnsafeResume("Unsupported checkpoint value type: " + type(value).__name__)


def decode_checkpoint_value(value):
    """Validate the versioned wire grammar before recreating agent values."""
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise UnsafeResume("Nonfinite JSON literal is not a valid checkpoint wire value")
        return value
    if type(value) is list:
        return [decode_checkpoint_value(item) for item in value]
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise UnsafeResume("Invalid checkpoint wire value type")
    if _CODEC_TAG not in value:
        return {key: decode_checkpoint_value(item) for key, item in value.items()}
    tag = value[_CODEC_TAG]
    if set(value) != {_CODEC_TAG} or type(tag) is not list or len(tag) != 2:
        raise UnsafeResume("Malformed checkpoint codec tag")
    kind, data = tag
    if kind == "float64_nonfinite":
        if type(data) is not str or len(data) != 16 or any(c not in "0123456789abcdef" for c in data):
            raise UnsafeResume("Malformed nonfinite float bits")
        restored = struct.unpack(">d", bytes.fromhex(data))[0]
        if math.isfinite(restored):
            raise UnsafeResume("Finite float is not a nonfinite codec value")
        return restored
    if kind == "escaped_dict" and type(data) is list:
        restored = {}
        for pair in data:
            if type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str or pair[0] in restored:
                raise UnsafeResume("Malformed escaped checkpoint dictionary")
            restored[pair[0]] = decode_checkpoint_value(pair[1])
        if _CODEC_TAG not in restored:
            raise UnsafeResume("Noncanonical escaped checkpoint dictionary")
        return restored
    raise UnsafeResume("Unknown checkpoint codec tag")


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, sort_keys=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def compose_description(family):
    family = Path(family)
    base = (family / "db_description.txt").read_text(encoding="utf-8").strip()
    hint = family / "db_description_withhint.txt"
    hints = hint.read_text(encoding="utf-8").strip() if hint.exists() else ""
    # Some datasets ship a full description in the hint file, others hints only.
    return hints if base and base in hints else base + ("\n\n" + hints if hints else "")


def transient(error):
    status = getattr(error, "status_code", None)
    return status in (429, 500, 502, 503, 504) or isinstance(error, (ConnectionError, TimeoutError)) or type(error).__name__ in {
        "APIConnectionError", "APITimeoutError", "ConnectTimeout", "ReadTimeout",
        "ConnectError", "ReadError", "RemoteProtocolError"}


def request_with_recovery(request, save, sleep=time.sleep):
    attempt = 0
    while True:
        try:
            return request()
        except Exception as error:
            if not transient(error):
                # Never persist provider bodies, which may contain credentials.
                save({"classification": "permanent_provider_failure",
                      "error_type": type(error).__name__, "status_code": getattr(error, "status_code", None)})
                raise ProviderFailure("permanent_provider_failure: " + type(error).__name__) from error
            attempt += 1
            delay = min(120, 5 * 2 ** min(attempt - 1, 5))
            save({"classification": "transient_provider_failure", "attempt": attempt,
                  "error_type": type(error).__name__, "status_code": getattr(error, "status_code", None),
                  "backoff_seconds": delay})
            sleep(delay)


def workspace_manifest(root):
    root = Path(root)
    if any(p.is_symlink() for p in root.rglob("*")):
        raise UnsafeResume("Workspace symlink requires explicit reconciliation")
    return {p.relative_to(root).as_posix(): file_digest(p)
            for p in sorted(root.rglob("*")) if p.is_file() and not p.is_symlink()}


class Journal:
    def __init__(self, agent, binding, path=None):
        self.agent = agent
        self.binding = binding
        self.path = Path(path or agent.root_dir / "recovery_checkpoint.json")
        self.pending = None
        self.cursor = 0
        self.inflight = None
        self.recovery = None

    def save(self, recovery=None):
        if recovery is not None:
            self.recovery = recovery
        a = self.agent
        controller = getattr(a, "checkpoint_controller", None)
        state = {k: copy.deepcopy(getattr(a, k)) for k in STATE_FIELDS if hasattr(a, k)}
        if controller is not None:
            state["checkpoint_controller"] = {
                f.name: sorted(getattr(controller, f.name)) if isinstance(getattr(controller, f.name), set)
                else copy.deepcopy(getattr(controller, f.name))
                for f in dataclasses.fields(controller) if f.name != "trace_emitter"}
        payload = {"policy": POLICY, "binding": self.binding, "state": state,
                   "pending_response": self.pending, "cursor": self.cursor,
                   "inflight_tool": self.inflight, "recovery": self.recovery,
                   "workspace": workspace_manifest(a.exec_tool_work_dir)}
        wire = encode_checkpoint_value(payload)
        atomic_json(self.path, {"checkpoint_codec": CHECKPOINT_CODEC,
                               "payload": wire, "sha256": digest(wire)})

    @staticmethod
    def read(path, binding, workspace):
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        wire = envelope["payload"]
        if envelope["sha256"] != digest(wire):
            raise UnsafeResume("Checkpoint integrity/source/configuration mismatch")
        codec = envelope.get("checkpoint_codec")
        if codec is None:
            p = wire
        elif codec == CHECKPOINT_CODEC:
            p = decode_checkpoint_value(wire)
        else:
            raise UnsafeResume("Checkpoint codec mismatch")
        if p["policy"] != POLICY or p["binding"] != binding:
            raise UnsafeResume("Checkpoint integrity/source/configuration mismatch")
        if p["inflight_tool"] is not None:
            raise UnsafeResume("Ambiguous in-flight tool; reconcile side effects before resuming")
        if p["workspace"] != workspace_manifest(workspace):
            raise UnsafeResume("Workspace changed or artifact missing")
        return p

    def restore(self, p):
        for k, v in p["state"].items():
            if k == "checkpoint_controller":
                for name, item in v.items():
                    setattr(self.agent.checkpoint_controller, name, set(item) if name == "restored_intents" else item)
            else:
                setattr(self.agent, k, v)
        self.pending, self.cursor = p["pending_response"], p["cursor"]
        self.inflight, self.recovery = p["inflight_tool"], p["recovery"]

    def dispatch(self):
        a = self.agent
        calls = self.pending.get("tool_calls")
        if calls is None:
            a.messages.append({"role": "assistant", "content": self.pending.get("content")})
            a._handle_content(self.pending.get("content"))
            self.pending = None
            self.save()
            return
        while self.cursor < len(calls) and a.final_result is None:
            call = calls[self.cursor]
            self.inflight = {"tool_call_id": call["id"], "signature": digest(call)}
            self.save()  # write-ahead fence: fail closed if interrupted after this
            proxy = SimpleNamespace(id=call["id"], function=SimpleNamespace(**call["function"]),
                                    model_dump=lambda c=call: copy.deepcopy(c))
            a._handle_tool_call(proxy)
            self.cursor += 1
            self.inflight = None
            self.save()  # messages, completed results and cursor commit together
        self.pending = None
        self.cursor = 0
        self.save()

    def accept(self, message):
        self.pending = message.model_dump() if hasattr(message, "model_dump") else message.to_dict()
        self.cursor = 0
        if self.pending.get("tool_calls") is not None:
            self.agent.messages.append({"role": "assistant", "tool_calls": self.pending["tool_calls"]})
        self.save()


def source_manifest(root):
    root = Path(root)
    files = list((root / "experiments").glob("*.py"))
    files += [p for folder in ("adapters", "prompts/dab", "meta_agent")
             for p in (root / folder).rglob("*")
             if p.is_file() and not p.is_symlink() and p.suffix in (".py", ".txt", ".md")
             and "__pycache__" not in p.parts]
    return digest({p.relative_to(root).as_posix(): file_digest(p) for p in files
                   if p.is_file() and not p.name.startswith(".")})


def install(module, args):
    """Install LAST, after the sealed candidate's tool wrappers and retry patch."""
    base_class = module.DataAgent
    repo = Path(__file__).resolve().parents[1]
    upstream = Path(args.dab_upstream_root)
    runtime_hash = digest({p.relative_to(upstream).as_posix(): file_digest(p)
                           for p in (upstream / "common_scaffold").rglob("*.py")})
    binding = {"policy": POLICY, "source": source_manifest(repo), "upstream_runtime": runtime_hash,
               "query": file_digest(Path(args.query_dir) / "query.json"),
               "db_config": file_digest(args.db_config), "description": digest(args.repaired_db_description),
               "model": args.deployment_name, "endpoint": args.openai_compatible_base_url,
               "exec_timeout": args.exec_python_timeout,
               "tool_configuration": digest({k: str(v) for k, v in vars(args).items()
                   if k in ("disable_self_observation_tool", "self_observation_tool_name",
                            "disable_query_capacity_guard", "disable_exec_python_tool", "tool_agent_policy",
                            "evolved_helper_registry", "evolved_helper_specs")}),
               "root_dir": str(Path(args.query_dir) / "logs/data_agent" / args.run_id)}
    binding["policy_artifacts"] = {k: file_digest(v) for k in ("tool_agent_policy", "evolved_helper_registry")
                                   if (v := getattr(args, k, None)) and Path(v).is_file()}

    class RepairedDataAgent(base_class):
        def __init__(self, **kw):
            root = Path(binding["root_dir"])
            if os.name != "nt":
                import fcntl
                root.parent.mkdir(parents=True, exist_ok=True)
                self._recovery_lease = (root.parent / (root.name + ".recovery.lock")).open("a")
                fcntl.flock(self._recovery_lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            cp = root / "recovery_checkpoint.json"
            resume = os.environ.get("DAB_REPAIR_RESUME") == "1"
            restored = Journal.read(cp, binding, root / "exec_tool_work_dir") if resume else None
            if restored and (restored.get("recovery") or {}).get("classification") == "permanent_provider_failure":
                raise UnsafeResume("Permanent provider failure requires explicit configuration reconciliation")
            if resume:
                kw["root_name"] += "_resume_bootstrap_" + str(time.time_ns())
            kw["db_description"] = args.repaired_db_description
            # Upstream QueryDBTool.__init__(check_load=True) DROPS and reloads
            # existing Mongo/Postgres databases. Never replay that on resume.
            patched_globals = []
            if resume:
                for cls in base_class.__mro__:
                    globals_ = getattr(getattr(cls, "__init__", None), "__globals__", {})
                    if "QueryDBTool" in globals_ and not any(g is globals_ for g, _ in patched_globals):
                        original_db_tool = globals_["QueryDBTool"]
                        def no_reload(*pos, _original=original_db_tool, **options):
                            options["check_load"] = False
                            return _original(*pos, **options)
                        patched_globals.append((globals_, original_db_tool))
                        globals_["QueryDBTool"] = no_reload
            try:
                super().__init__(**kw)
            finally:
                for globals_, original_db_tool in patched_globals:
                    globals_["QueryDBTool"] = original_db_tool
            if resume:
                # Recreate clients/executor; restore durable workspace, not messages alone.
                exec_spec = copy.deepcopy(self.tools["execute_python"].get_spec())
                self.tools["execute_python"].clean_up()
                self.root_dir = root
                self.exec_tool_work_dir = root / "exec_tool_work_dir"
                self.file_storage_dir = self.exec_tool_work_dir / "file_storage"
                self.llm_log_path, self.tool_log_path = root / "llm_calls.jsonl", root / "tool_calls.jsonl"
                self.validation_log_path = root / "validation.jsonl"
                self.tools["execute_python"] = module.ExecTool(self.tool_log_path, "execute_python",
                    self.exec_tool_work_dir, timeout=args.exec_python_timeout)
                self.tools["execute_python"].get_spec = lambda: copy.deepcopy(exec_spec)
                for tool in self.tools.values():
                    tool.log_path = self.tool_log_path
                    if hasattr(tool, "observation_log_path"):
                        tool.observation_log_path = root / "agent_self_observations.jsonl"
            self.journal = Journal(self, binding)
            if restored:
                self.journal.restore(restored)
            else:
                self.journal.save()

        def call_llm(self):
            request = copy.deepcopy({"model": self.deployment_name, "messages": self.messages,
                                     "tools": [t.get_spec() for t in self.tools.values()],
                                     "timeout": args.llm_timeout})
            self.journal.save()
            start = time.time()
            response = request_with_recovery(lambda: self.client.chat.completions.create(**request), self.journal.save)
            self.llm_call_count += 1
            self.terminate_reason = None
            with self.llm_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": time.time(), "duration": time.time()-start,
                                   "model": self.deployment_name, "response": response.to_dict(),
                                   "messages": self.messages, "repair_policy": POLICY}) + "\n")
            # Commit received response before executing any tool.
            self.journal.accept(response.choices[0].message)
            return response.choices[0].message

        def run(self):
            while self.final_result is None:
                if self.journal.pending is None:
                    self.call_llm()
                self.journal.dispatch()
            self.journal.save()
            data = self.to_dict()
            data["max_iterations"] = None
            data["repair_policy"] = POLICY
            data["repair_binding"] = binding
            atomic_json(self.root_dir / "final_agent.json", data)
            # Retain workspace artifacts for audited resume; close only the executor.
            self.tools["execute_python"].clean_up()
            return self.final_result

    module.DataAgent = RepairedDataAgent
