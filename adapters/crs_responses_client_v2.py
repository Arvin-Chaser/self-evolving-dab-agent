"""CRS streaming Responses transport; same exact native history contract.

One HTTP dispatch, buffer raw SSE wire, accept only the complete final native
response item. No delta-derived calls, stream reconnect, or request replay.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from adapters.crs_responses_client_v1 import (MODEL, ENDPOINT, NATIVE_FIELD,
    NativeResponse, NativeMessage, input_items, request_options)


def parse_completed_wire(wire):
    text = wire.decode('utf-8')
    completed = []
    data = []
    def consume():
        if not data:
            return
        value = '\n'.join(data)
        data.clear()
        if value == '[DONE]':
            return
        event = json.loads(value)
        kind = event.get('type')
        if kind in ('error', 'response.failed', 'response.incomplete'):
            raise RuntimeError('Terminal Responses stream error')
        if kind == 'response.completed':
            completed.append(event['response'])
    for line in text.splitlines():
        if not line:
            consume()
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
        elif not line.startswith(('event:', 'id:', 'retry:', ':')):
            raise RuntimeError('Invalid SSE wire')
    consume()
    if len(completed) != 1:
        raise RuntimeError('Missing or duplicate complete native response; no replay')
    return completed[0]


def install_client(client, root):
    root = Path(root)
    def create(**request):
        options = request_options(request)
        options.update(stream=True, instructions='')
        started = time.monotonic()
        # Buffer transport only; expose the same completed-message API to DAB.
        with client.responses.with_streaming_response.create(**options) as raw:
            wire = raw.read()
        record = {'schema': 'gen008_gpt_native_sse_wire_v2', 'requested_model': MODEL,
            'wire_sha256': hashlib.sha256(wire).hexdigest(), 'wire_base64': base64.b64encode(wire).decode(),
            'input_sha256': hashlib.sha256(json.dumps(options['input'], sort_keys=True, ensure_ascii=False,
                separators=(',', ':')).encode()).hexdigest(), 'elapsed_seconds': time.monotonic()-started,
            'automatic_replay': False}
        with (root / 'gpt_native_wire.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(record)+'\n');f.flush();os.fsync(f.fileno())
        native = parse_completed_wire(wire)
        return NativeResponse(native, options['tools'])
    client.chat.completions.create = create
    return client
