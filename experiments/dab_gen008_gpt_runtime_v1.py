"""Gen8-only infrastructure: isolated DB, lossless checkpoint, native Responses.

Runs only on a fresh admitted-candidate-derived repo with verified bootstrap.
No candidate logic, old checkpoint migration, SDK retry, or tool replay.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import time
from adapters.crs_responses_client_v1 import ENDPOINT, MODEL, NATIVE_FIELD, install_client
from experiments import dab_runtime_repair_v1 as base
from experiments.dab_gpt_isolation_v1 import prepare_isolation, dispatch_once

POLICY = 'gen008_gpt55_responses_medium_isolated_lossless_once_v1'
GATE_FIELDS = ('duplicate_failure_ledger_size', 'duplicate_failure_ledger',
    'duplicate_failure_gate_counters', 'duplicate_failure_expired_signatures',
    'duplicate_failure_gate_one_shot_signatures', 'failed_request_suppression_counts')
SET_FIELDS = ('duplicate_failure_expired_signatures', 'duplicate_failure_gate_one_shot_signatures')
COUNTERS = {'pass_through', 'duplicate_suppression', 'artifact_context_reuse',
            'declined_no_prior_failure', 'declined_no_valid_checkpoint', 'declined_new_or_changed_inputs'}


def serialize_gate(agent, required=False):
    if not any(hasattr(agent, key) for key in GATE_FIELDS):
        if required:
            raise base.UnsafeResume('Actual Gen8 candidate gate missing')
        return None
    if not all(hasattr(agent, key) for key in GATE_FIELDS):
        raise base.UnsafeResume('Incomplete Gen8 gate state')
    value = {key: copy.deepcopy(getattr(agent, key)) for key in GATE_FIELDS}
    for key in SET_FIELDS:
        if not isinstance(value[key], set) or any(not isinstance(x, str) for x in value[key]):
            raise base.UnsafeResume('Invalid Gen8 signature set')
        value[key] = sorted(value[key])
    validate_gate(value)
    return value


def validate_gate(value):
    if not isinstance(value, dict) or set(value) != set(GATE_FIELDS):
        raise base.UnsafeResume('Missing/extra Gen8 checkpoint fields')
    cap = value['duplicate_failure_ledger_size']
    ledger = value['duplicate_failure_ledger']
    if type(cap) is not int or not 1 <= cap <= 10000 or not isinstance(ledger, list) or len(ledger) > cap:
        raise base.UnsafeResume('Invalid bounded Gen8 ledger')
    if any(not isinstance(entry, dict) for entry in ledger):
        raise base.UnsafeResume('Invalid Gen8 ledger entry')
    counters = value['duplicate_failure_gate_counters']
    if (not isinstance(counters, dict) or set(counters) != COUNTERS
            or any(type(n) is not int or n < 0 for n in counters.values())):
        raise base.UnsafeResume('Invalid Gen8 gate counters')
    counts = value['failed_request_suppression_counts']
    if not isinstance(counts, dict) or any(not isinstance(k, str) or type(n) is not int or n < 0 for k, n in counts.items()):
        raise base.UnsafeResume('Invalid Gen8 suppression counts')
    for key in SET_FIELDS:
        if not isinstance(value[key], list) or any(not isinstance(x, str) for x in value[key]) or sorted(set(value[key])) != value[key]:
            raise base.UnsafeResume('Noncanonical Gen8 signature set')


class NativeJournal(base.Journal):
    def save(self, recovery=None):
        gate = serialize_gate(self.agent)
        if gate is not None:
            self.agent._gen8_checkpoint_state = gate
        super().save(recovery)

    def restore(self, payload):
        required = any(hasattr(self.agent, key) for key in GATE_FIELDS)
        gate = payload['state'].get('_gen8_checkpoint_state')
        if required or gate is not None:
            validate_gate(gate)
        super().restore(payload)
        if gate is not None:
            for key, value in gate.items():
                setattr(self.agent, key, set(value) if key in SET_FIELDS else copy.deepcopy(value))

    def accept(self, message):
        self.pending = message.model_dump() if hasattr(message, 'model_dump') else message.to_dict()
        self.cursor = 0
        if self.pending.get('tool_calls') is not None:
            self.agent.messages.append(copy.deepcopy({k: self.pending[k] for k in
                ('role', 'content', 'tool_calls', NATIVE_FIELD) if k in self.pending}))
        self.save()

    def dispatch(self):
        if self.pending.get('tool_calls') is not None:
            return super().dispatch()
        message = copy.deepcopy({k: self.pending[k] for k in ('role', 'content', NATIVE_FIELD) if k in self.pending})
        self.agent.messages.append(message)
        self.agent._handle_content(self.pending.get('content'))
        self.pending = None
        self.cursor = 0
        self.save()


def install(module, args):
    if (args.deployment_name != MODEL or args.openai_compatible_base_url != ENDPOINT
            or args.client_max_retries != 0 or args.llm_retries != 1
            or os.environ.get('DAB_REPAIR_RESUME')
            or os.environ.get('DAB_DEEPSEEK_SINGLE_TRIAL') or os.environ.get('DAB_SCHOOL_REMAINING8_TRIAL')):
        raise RuntimeError('Fresh GPT Gen8 binding/no-replay policy mismatch')
    prepare_isolation(module, args)
    binding = json.loads((Path(__file__).resolve().parents[1] / 'gen008_runtime_binding.json').read_text())
    base.POLICY = POLICY
    base.ADMITTED_SOURCE_SHA256 = binding['admitted_source_sha256']
    base.ADMITTED_PATCH_SHA256 = binding['admitted_patch_sha256']
    base.SEALED_INTENT_SHA256 = binding['sealed_intent_sha256']
    base.STATE_FIELDS = tuple(base.STATE_FIELDS) + ('_gen8_checkpoint_state',)
    base.Journal = NativeJournal
    base.install(module, args)
    inherited = module.DataAgent

    class GPTGen8DataAgent(inherited):
        def __init__(self, **kw):
            super().__init__(**kw)
            serialize_gate(self, required=True)
            install_client(self.client, self.root_dir)

        def call_llm(self):
            self.journal.save()
            request = {'model': self.deployment_name, 'messages': copy.deepcopy(self.messages),
                       'tools': [tool.get_spec() for tool in self.tools.values()], 'timeout': args.llm_timeout}
            started = time.monotonic()
            response = dispatch_once(lambda: self.client.chat.completions.create(**request), self.journal.save)
            self.llm_call_count += 1
            self.terminate_reason = None
            with self.llm_log_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'timestamp': time.time(), 'duration': time.monotonic() - started,
                    'model': MODEL, 'response': response.to_dict(), 'messages': self.messages,
                    'repair_policy': POLICY}) + '\n')
            self.journal.accept(response.choices[0].message)
            return response.choices[0].message

        def to_dict(self):
            data = super().to_dict()
            data['gen8_duplicate_gate_state'] = serialize_gate(self, required=True)
            data['native_responses_history'] = {'policy': POLICY, 'reasoning_effort': 'medium',
                'opaque_output_items_preserved': True, 'automatic_request_replay': False}
            return data

    module.DataAgent = GPTGen8DataAgent
