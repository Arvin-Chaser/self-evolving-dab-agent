"""Native Responses bridge for GPT-5.5; no text-inferred calls or request retries.

The unchanged DAB agent sees its existing message/tool interface. Durable history
retains every native output item, including opaque encrypted reasoning, and
uses native call_id values for tool results. Wire bytes stay at the run root.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

MODEL = 'gpt-5.5'
ENDPOINT = 'https://crs.uuid.im/openai'
NATIVE_FIELD = 'dab_native_response_items'


def input_items(messages):
    result = []
    pending = set()
    for message in messages:
        role = message.get('role')
        if role == 'assistant' and NATIVE_FIELD in message:
            outputs = message[NATIVE_FIELD]
            if not isinstance(outputs, list):
                raise RuntimeError('Invalid native Responses history')
            native_calls = [o for o in outputs if o.get('type') == 'function_call']
            visible = message.get('tool_calls') or []
            if [(c.get('call_id'), c.get('name'), c.get('arguments')) for c in native_calls] != [
                (c.get('id'), c.get('function', {}).get('name'), c.get('function', {}).get('arguments')) for c in visible]:
                raise RuntimeError('Native call/history binding mismatch')
            for call in native_calls:
                ident = call.get('call_id')
                if not isinstance(ident, str) or not ident or ident in pending:
                    raise RuntimeError('Ambiguous native function call identity')
                pending.add(ident)
            result.extend(copy.deepcopy(outputs))
        elif role == 'tool':
            ident = message.get('tool_call_id')
            if ident not in pending or not isinstance(message.get('content'), str):
                raise RuntimeError('Unbound native tool output')
            pending.remove(ident)
            result.append({'type': 'function_call_output', 'call_id': ident, 'output': message['content']})
        elif role in ('system', 'developer', 'user', 'assistant'):
            if message.get('tool_calls'):
                raise RuntimeError('Tool history lacks exact native Responses items')
            if not isinstance(message.get('content'), str):
                raise RuntimeError('Unexpected message content type')
            result.append({'role': role, 'content': message['content']})
        else:
            raise RuntimeError('Unsupported role in Responses history')
    if pending:
        raise RuntimeError('Outstanding native tool calls; no ambiguous request replay')
    return result


def request_options(request):
    if request.get('model') != MODEL or request.get('stream', False):
        raise RuntimeError('GPT model or non-streaming binding mismatch')
    if set(request) - {'model', 'messages', 'tools', 'timeout', 'stream'}:
        raise RuntimeError('Unreviewed request option')
    tools = []
    names = set()
    for spec in request.get('tools', []):
        if spec.get('type') != 'function' or not isinstance(spec.get('function'), dict):
            raise RuntimeError('Only original native function tools are permitted')
        function = copy.deepcopy(spec['function'])
        if set(function) - {'name', 'description', 'parameters', 'strict'}:
            raise RuntimeError('Unsupported function specification')
        name = function.get('name')
        if not isinstance(name, str) or not name or name in names:
            raise RuntimeError('Duplicate/missing tool name')
        names.add(name)
        # Responses otherwise normalizes optional schemas into strict required
        # parameters. Preserve the original upstream optional parameter contract.
        function.setdefault('strict', False)
        tools.append({'type': 'function', **function})
    return {'model': MODEL, 'input': input_items(request['messages']), 'tools': tools,
            'reasoning': {'effort': 'medium'}, 'store': False,
            'include': ['reasoning.encrypted_content'], 'stream': False,
            'timeout': request.get('timeout', 600)}


class NativeMessage:
    def __init__(self, data):
        self._data = copy.deepcopy(data)
        self.role, self.content = data['role'], data['content']
        self.tool_calls = [SimpleNamespace(id=c['id'], type='function',
            function=SimpleNamespace(**c['function']), model_dump=lambda c=c: copy.deepcopy(c))
            for c in data['tool_calls']] if data['tool_calls'] is not None else None

    def model_dump(self):
        return copy.deepcopy(self._data)

    to_dict = model_dump


class NativeResponse:
    def __init__(self, native, tools):
        if (native.get('status') != 'completed' or native.get('error') is not None
                or native.get('incomplete_details') is not None
                or not str(native.get('model', '')).startswith(MODEL)):
            raise RuntimeError('Responses request did not complete under GPT-5.5')
        outputs = native.get('output')
        if not isinstance(outputs, list):
            raise RuntimeError('Native output items missing')
        calls, texts, identities = [], [], set()
        allowed = {t['name'] for t in tools}
        for item in outputs:
            kind = item.get('type')
            if kind == 'function_call':
                ident = item.get('call_id')
                if (not isinstance(ident, str) or not ident or ident in identities
                        or item.get('name') not in allowed or not isinstance(item.get('arguments'), str)):
                    raise RuntimeError('Ambiguous/unregistered native function call')
                identities.add(ident)
                calls.append({'id': ident, 'type': 'function',
                              'function': {'name': item['name'], 'arguments': item['arguments']}})
            elif kind == 'message':
                if item.get('role') != 'assistant':
                    raise RuntimeError('Unexpected native output message role')
                for content in item.get('content', []):
                    if content.get('type') != 'output_text' or not isinstance(content.get('text'), str):
                        raise RuntimeError('Unsupported native message content')
                    texts.append(content['text'])
            elif kind != 'reasoning':
                raise RuntimeError('Unreviewed native output item type')
        if not calls and not texts:
            raise RuntimeError('Empty completed Responses output')
        self._native = copy.deepcopy(native)
        self.choices = [SimpleNamespace(message=NativeMessage({'role': 'assistant',
            'content': ''.join(texts) if texts else None, 'tool_calls': calls or None,
            NATIVE_FIELD: outputs}))]

    def to_dict(self):
        return copy.deepcopy(self._native)

    model_dump = to_dict


def install_client(client, root):
    root = Path(root)
    raw_create = client.responses.with_raw_response.create
    def create(**request):
        options = request_options(request)
        started = time.monotonic()
        raw = raw_create(**options)  # Exactly one SDK invocation; client max_retries=0.
        wire = raw.content
        native = raw.parse().model_dump(mode='json')
        response = NativeResponse(native, options['tools'])
        record = {'schema': 'gen008_gpt_native_wire_v1', 'requested_model': MODEL,
                  'response_model': native['model'], 'response_id': native.get('id'),
                  'wire_sha256': hashlib.sha256(wire).hexdigest(),
                  'wire_base64': base64.b64encode(wire).decode('ascii'),
                  'input_sha256': hashlib.sha256(json.dumps(options['input'], sort_keys=True,
                    ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
                  'elapsed_seconds': time.monotonic() - started,
                  'automatic_replay': False}
        with (root / 'gpt_native_wire.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        return response
    client.chat.completions.create = create
    return client
