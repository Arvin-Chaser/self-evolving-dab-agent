"""Direct native DeepSeek tools; preserve reasoning and never infer tool calls."""
from __future__ import annotations
import copy
import json

ENDPOINT = 'https://api.deepseek.com/v1'
MODEL = 'deepseek-flash'

def request_options(request):
    if request.get('model') != MODEL:
        raise RuntimeError('DeepSeek adapter model binding mismatch')
    result = copy.deepcopy(request)
    extra = result.setdefault('extra_body', {})
    if 'thinking' in extra and extra['thinking'] != {'type':'enabled'}:
        raise RuntimeError('Conflicting DeepSeek thinking policy')
    extra['thinking'] = {'type':'enabled'}
    result.setdefault('reasoning_effort', 'high')
    return result

def native_assistant_message(message):
    value = message.model_dump() if hasattr(message, 'model_dump') else message.to_dict()
    if value.get('role') != 'assistant':
        raise RuntimeError('Unexpected provider message role')
    # Do not reconstruct reasoning, IDs or arguments from text. Preserve the
    # exact native fields needed by subsequent thinking-mode tool requests.
    return copy.deepcopy({k:value[k] for k in ('role','content','reasoning_content','tool_calls') if k in value})

def install_client(client):
    original = client.chat.completions.create
    remembered = {}
    def create(**request):
        request = request_options(request)
        for msg in request.get('messages', []):
            if not isinstance(msg, dict):
                continue
            calls = msg.get('tool_calls')
            if msg.get('role') != 'assistant' or not calls:
                continue
            key = json.dumps(calls, sort_keys=True, separators=(',', ':'))
            native = remembered.get(key)
            if native is None:
                if not isinstance(msg.get('reasoning_content'), str):
                    raise RuntimeError('Unbound historical DeepSeek reasoning; no fabricated replay')
                continue
            for field in ('content','reasoning_content'):
                if field in msg and msg[field] not in (None, native.get(field)):
                    raise RuntimeError('Conflicting native DeepSeek assistant history')
                if field in native:
                    msg[field] = copy.deepcopy(native[field])
        response = original(**request)
        native = native_assistant_message(response.choices[0].message)
        if native.get('tool_calls'):
            key = json.dumps(native['tool_calls'], sort_keys=True, separators=(',', ':'))
            if key in remembered and remembered[key] != native:
                raise RuntimeError('Provider reused an ambiguous tool call identity')
            remembered[key] = native
        return response
    client.chat.completions.create = create
    return client
