"""Fresh Gen8 physical DB isolation. Never overwrite existing destinations."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def physical_name(run_id, logical):
    return 'dabg8_' + hashlib.sha256((run_id + '\0' + logical).encode()).hexdigest()[:32]


def dispatch_once(request, save):
    from experiments.dab_runtime_repair_v1 import ProviderFailure
    try:
        return request()
    except Exception as error:
        save({'classification': 'permanent_provider_failure', 'error_type': type(error).__name__,
              'status_code': getattr(error, 'status_code', None), 'attempts': 1, 'automatic_replay': False})
        raise ProviderFailure('gen008_gpt_dispatch_failed_no_replay: ' + type(error).__name__) from None


def isolated_clients(clients, root, run_id, postgres, mongo, restore=subprocess.run):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    records = []
    for logical, client in clients.items():
        kind = client['db_type']
        if kind in ('sqlite', 'duckdb'):
            source = Path(client['db_path']).resolve()
            target = root / (physical_name(run_id, logical) + source.suffix)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            shutil.copy2(source, target)
            if before != hashlib.sha256(source.read_bytes()).hexdigest() or before != hashlib.sha256(target.read_bytes()).hexdigest():
                raise RuntimeError('Isolated input copy changed')
            client['db_path'] = str(target)
            records.append({'logical': logical, 'type': kind, 'copy_sha256': before, 'path': str(target)})
        elif kind in ('postgres', 'mongo'):
            old = client['db_name']
            name = physical_name(run_id, logical)
            util = postgres if kind == 'postgres' else mongo
            if name == old or util.check_db_exists(name):
                raise RuntimeError('Physical DB destination exists; no overwrite')
            if kind == 'postgres':
                postgres.load_db(client['sql_file'], name)
            else:
                restore(['mongorestore', '--nsInclude=' + old + '.*', '--nsFrom=' + old + '.*',
                         '--nsTo=' + name + '.*', client['dump_folder']], check=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            client['db_name'] = name
            records.append({'logical': logical, 'type': kind, 'physical': name})
        else:
            raise RuntimeError('Unsupported isolation DB type')
    with (root / 'isolation_manifest.json').open('x', encoding='utf-8') as stream:
        json.dump({'policy': 'gen008_physical_isolation_v1', 'run_id': run_id, 'clients': records}, stream, indent=2)
    return records


def prepare_isolation(module, args):
    from common_scaffold.tools.db_utils import postgres_utils, mongo_utils
    root = Path(args.query_dir) / 'logs/data_agent' / args.run_id
    mapping = {}
    seen = set()
    for cls in module.DataAgent.__mro__:
        globals_ = getattr(getattr(cls, '__init__', None), '__globals__', {})
        original = globals_.get('QueryDBTool')
        if original is None or id(globals_) in seen:
            continue
        seen.add(id(globals_))
        original_list = globals_.get('ListDBTool')
        if original_list is None:
            raise RuntimeError('Missing native list DB binding')

        class IsolatedQueryDBTool(original):
            def __init__(self, *pos, **kw):
                kw['check_load'] = False
                super().__init__(*pos, **kw)
                isolated_clients(self.db_clients, root / 'gen008_isolated_inputs', args.run_id, postgres_utils, mongo_utils)
                mapping.update(copy.deepcopy(self.db_clients))

        class IsolatedListDBTool(original_list):
            def __init__(self, *pos, **kw):
                kw['check_load'] = False
                super().__init__(*pos, **kw)
                if self.db_clients.keys() != mapping.keys():
                    raise RuntimeError('Logical query/list DB bindings disagree')
                self.db_clients = copy.deepcopy(mapping)

        globals_['QueryDBTool'] = IsolatedQueryDBTool
        globals_['ListDBTool'] = IsolatedListDBTool
    if not seen:
        raise RuntimeError('Actual upstream DB constructor binding missing')
