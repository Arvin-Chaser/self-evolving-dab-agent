"""Official DeepSeek native response wire and reasoning history; no retries."""
import hashlib,json,os
from pathlib import Path

def install_native_transport(client, root):
    """Keep exact native provider wire remotely; never log headers or keys."""
    import base64
    import time
    from adapters.deepseek_client_v1 import install_client
    raw_create = client.chat.completions.with_raw_response.create
    def create(**request):
        started = time.monotonic()
        response = raw_create(**request)
        wire = response.content
        value = response.parse()
        record = {'schema':'deepseek_native_wire_v1', 'model': request['model'],
                  'wire_sha256':hashlib.sha256(wire).hexdigest(),
                  'wire_base64':base64.b64encode(wire).decode('ascii'),
                  'elapsed_seconds':time.monotonic()-started,
                  'automatic_replay':False}
        with (Path(root)/'deepseek_native_wire.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        return value
    client.chat.completions.create = create
    return install_client(client)
