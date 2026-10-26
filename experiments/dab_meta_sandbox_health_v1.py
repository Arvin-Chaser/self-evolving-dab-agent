"""Native sandbox health is measured, not inferred from desktop process presence.

No API/auth hook, credential, model, network, ACL or configuration access changes.
The installed sandbox includes managed requirements. One fresh fixture per check.
"""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys,time,tomllib,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.dab_bound_meta_tools_v1 import bind_environment
from experiments.run_gen008_gpt55_meta_once_v1 import CODEX,NATIVE,PYTHON,HOME

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mxc_command(executable,*args):
    # Unified exec consults prefer_mxc as well as the sandbox implementation.
    # Explicit selection disallows silently retrying commands in legacy mode.
    return [str(executable),'-c','windows.sandbox="mxc"','-c','features.prefer_mxc=true',*args]
def environment(home,tools):
    # Diagnostic executor is model-free. Never invoke meta_environment/auth hooks.
    env=bind_environment(os.environ.copy(),tools)
    for k in list(env):
        if k in ('CODEX_MCP_NODE_PATH','CODEX_NATIVE_META_BRIDGE_CONFIG','DAB_RESEARCH_API_CONFIG') or k.endswith(('API_KEY','API_TOKEN')):env.pop(k,None)
    env['CODEX_HOME']=str(home)
    return env

def validate_config(home):
    cfg=tomllib.loads((home/'config.toml').read_text(encoding='utf-8'))
    required={'model':'gpt-5.5','model_provider':'dab_crs_gpt55','approval_policy':'on-request','approvals_reviewer':'auto_review','sandbox_mode':'workspace-write','default_permissions':':workspace'}
    if any(cfg.get(k)!=v for k,v in required.items()) or cfg.get('sandbox_workspace_write',{}).get('network_access') is not False or cfg.get('windows',{}).get('sandbox')!='elevated':raise RuntimeError('Bound native policy differs; no override')
    return cfg

def check(home=HOME,tools=None,output=None,implementation='elevated',boundary_checks=False):
    if implementation not in ('elevated','mxc'):raise ValueError('No weaker sandbox fallback')
    home=Path(home);validate_config(home)
    tools=tools or {name:{'path':str(p),'sha256':sha(p)} for name,p in [('codex',CODEX),('python',PYTHON),('powershell',NATIVE)]}
    env=environment(home,tools)
    base=ROOT/'tmp';base.mkdir(exist_ok=True)
    directory=Path(output) if output else base/('mh_'+uuid.uuid4().hex[:10])
    if directory.resolve().parent!=base.resolve() or directory.is_symlink():raise RuntimeError('Health fixture must be a fresh direct child of repo tmp')
    directory.mkdir(exist_ok=False)
    marker='sandbox-model-free-'+uuid.uuid4().hex
    fixture=directory/'fixture.txt';fixture.write_text(marker,encoding='utf-8')
    script="from pathlib import Path; p=Path('fixture.txt'); v=p.read_text(encoding='utf-8'); Path('verified.txt').write_text(v,encoding='utf-8'); print(v)"
    command=mxc_command(tools['codex']['path']) if implementation=='mxc' else [tools['codex']['path']]
    command+=['sandbox','-P',':workspace','--include-managed-config','-C',str(directory),'--',tools['python']['path'],'-B','-c',script]
    start=time.monotonic();before={str(p):sha(p) for p in (home/'config.toml',home/'crs-gpt55-dab.config.toml')}
    try:
        result=subprocess.run(command,cwd=directory,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        rc=result.returncode;out=result.stdout;err=result.stderr
    except subprocess.TimeoutExpired:
        rc=124;out='';err='Native sandbox health timeout; no automatic retry'
    unchanged=all(sha(p)==d for p,d in before.items())
    passed=rc==0 and out.strip()==marker and (directory/'verified.txt').is_file() and (directory/'verified.txt').read_text(encoding='utf-8')==marker and unchanged
    boundaries=[]
    if passed and boundary_checks:
        def probe(name,profile,args,expected):
            cmd=command[:command.index('sandbox')]+['sandbox','-P',profile,'--include-managed-config','-C',str(directory),'--',*args]
            r=subprocess.run(cmd,cwd=directory,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
            ok=r.returncode==0 and r.stdout.strip()==expected
            boundaries.append({'name':name,'passed':ok,'exit_code':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest()})
            return ok
        probe('powershell_read',':workspace',[tools['powershell']['path'],'-NoProfile','-NonInteractive','-Command',"Get-Content -LiteralPath './fixture.txt'"],marker)
        deny="from pathlib import Path\ntry: Path('denied.txt').write_text('synthetic',encoding='utf-8')\nexcept PermissionError: print('READ_ONLY_DENIED')\nelse: raise SystemExit(2)"
        probe('read_only_write_denied',':read-only',[tools['python']['path'],'-B','-c',deny],'READ_ONLY_DENIED')
        network="import socket\ntry: s=socket.create_connection(('1.1.1.1',443),timeout=2)\nexcept OSError as e:\n print('NETWORK_DENIED' if getattr(e,'winerror',None)==10013 or e.errno==13 else 'NETWORK_POLICY_UNKNOWN')\nelse: s.close(); raise SystemExit(2)"
        probe('disabled_network_denied',':workspace',[tools['python']['path'],'-B','-c',network],'NETWORK_DENIED')
        passed=passed and all(r['passed'] for r in boundaries) and not (directory/'denied.txt').exists()
    report={'schema':'dab_meta_sandbox_health_v1','requested_implementation':implementation,'checked_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':round(time.monotonic()-start,3),'passed':passed,'exit_code':rc,'read_write_verified':passed,'managed_requirements_included':True,'policy_configuration_unchanged':unchanged,'configuration_bindings':before,'tools':tools,'fixture_dir':str(directory),'model_calls':0,'credential_reads_by_helper':0,'network_calls':0,'stderr_sha256':hashlib.sha256(err.encode()).hexdigest(),'failure_type':None if passed else 'native_sandbox_health_failure','bounded_error':err[-1800:] if not passed else None,'desktop_presence_is_not_health_evidence':True,'automatic_retry':False}
    report.update(boundary_checks=boundaries,network_attempts=1 if boundaries else 0,network_policy_validation='passed' if boundaries and all(r['passed'] for r in boundaries) else 'not_verified')
    (directory/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true',required=True);p.add_argument('--implementation',choices=('elevated','mxc'),default='elevated');p.add_argument('--boundary-checks',action='store_true');args=p.parse_args()
    value=check(implementation=args.implementation,boundary_checks=args.boundary_checks);print(json.dumps(value,indent=2));raise SystemExit(0 if value['passed'] else 1)
