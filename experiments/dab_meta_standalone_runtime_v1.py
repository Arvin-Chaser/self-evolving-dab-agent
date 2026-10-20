"""Dedicated official CLI binding; no desktop/global config/PATH changes."""
import hashlib,json,os,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HOME=ROOT/'configs/deepseek_meta_standalone_v2'
CODEX=Path('C:/Users/34934/.codex/visualizations/2026/09/02/01a060f2-55f4-7c02-b876-da90418d29b9/meta_cli_deepseek_v1/native_package/node_modules/@openai/codex/vendor/x86_64-pc-windows-msvc/bin/codex.exe')
PYTHON=Path('C:/Users/34934/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
NATIVE=Path('C:/Users/34934/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe')
BINDING=HOME/'runtime_binding.json'
MODEL='deepseek-flash';PROFILE='deepseek-standalone-dab';PROVIDER='dab_deepseek_standalone'
ROUTE=ROOT/'configs/dab_deepseek_standalone_route_v2.json'
INTEGRATION=ROOT/'tmp/meta_deepseek_standalone_probe_v1/report.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate():
    b=json.loads(BINDING.read_bytes())
    if b['model']!=MODEL or Path(b['codex_home']).resolve()!=HOME.resolve() or b['version']!='0.162.0':raise RuntimeError('Dedicated runtime binding differs')
    for n,p in [('codex',CODEX),('python',PYTHON),('powershell',NATIVE)]:
        if b['tools'][n]!={'path':str(p),'sha256':sha(p)}:raise RuntimeError('Bound runtime executable changed')
    cfg=tomllib.loads((HOME/'config.toml').read_text(encoding='utf-8'))
    policy={k:v for k,v in cfg.items() if k!='projects'}
    if hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=b['policy_sha256_excluding_cli_trust_projects']:
        raise RuntimeError('Dedicated runtime policy changed; no auth or model dispatch')
    if any(v!={'trust_level':'trusted'} for v in cfg.get('projects',{}).values()):
        raise RuntimeError('Unexpected project policy override')
    expected={'model':MODEL,'model_provider':PROVIDER,'approval_policy':'on-request','approvals_reviewer':'auto_review','sandbox_mode':'workspace-write','default_permissions':':workspace'}
    if any(cfg.get(k)!=v for k,v in expected.items()) or cfg['sandbox_workspace_write']['network_access'] is not False or cfg['windows']['sandbox']!='mxc' or cfg['features']['prefer_mxc'] is not True:raise RuntimeError('Runtime permission/model policy differs')
    p=cfg['model_providers'][PROVIDER]
    if p['base_url']!='https://api.deepseek.com/v1' or p['env_key']!='DEEPSEEK_API_KEY' or p['wire_api']!='responses' or p['request_max_retries']!=0 or p['stream_max_retries']!=0:raise RuntimeError('Provider endpoint/retry policy differs')
    for path in (HOME/(PROFILE+'.config.toml'),HOME/'models.json'):
        if b['static_configs'][str(path)]!=sha(path):raise RuntimeError('Profile/catalog changed')
    return b
def isolate_environment(env):
    env=dict(env)
    for k in list(env):
        if k in ('CODEX_HOME','CODEX_SQLITE_HOME','CODEX_MCP_NODE_PATH','CODEX_NATIVE_META_BRIDGE_CONFIG','CODEX_API_KEY','CODEX_ACCESS_TOKEN','CODEX_THREAD_ID','CRS_API_KEY','OPENAI_API_KEY','DAB_TOOL_AGENT_API_KEY','PYTHONPATH'):env.pop(k,None)
    env.update(CODEX_HOME=str(HOME),CODEX_SQLITE_HOME=str(HOME),DAB_RESEARCH_API_CONFIG=str(ROUTE))
    return env
def meta_environment(profile):
    validate()
    if profile!=PROFILE:raise RuntimeError('Unbound standalone profile')
    route=json.loads(ROUTE.read_bytes())
    if route['model']!=MODEL or route['meta_codex_home']!='configs/deepseek_meta_standalone_v2' or route['base_url']!='https://api.deepseek.com/v1' or route['api_key_env']!='DEEPSEEK_API_KEY' or route['api_key_file']!='C:/Users/34934/.config/dab/deepseek_api_key.txt':raise RuntimeError('Unbound provider/key route')
    from experiments.dab_api_routing import read_explicit_key
    from experiments.dab_bound_meta_tools_v1 import bind_environment
    env=isolate_environment(os.environ.copy())
    env['DEEPSEEK_API_KEY']=read_explicit_key(route)
    env['CODEX_NATIVE_META_BRIDGE_CONFIG']=str(ROOT/route['meta_bridge_config'])
    return bind_environment(env,validate()['tools'])
