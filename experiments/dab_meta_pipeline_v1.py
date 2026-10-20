"""Durable, generation-neutral Meta workflow. Original protocol owns decisions.

Review -> Graph -> selector -> sealed intent -> coding -> frozen checks ->
bounded independent same-intent repair -> original admission -> Data handoff.
No Data/SSH, next-generation authority inference, API replay or weaker sandbox.
"""
from __future__ import annotations
import argparse,contextlib,hashlib,json,os,shutil,sys,tomllib
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments import dab_roadmap_protocol as protocol
from experiments import intent_candidate_workspace as workspace
from experiments import dab_candidate_compatibility_v3 as compatibility
from experiments import dab_native_meta_audit_v3 as native
from experiments import dab_meta_sandbox_health_v1 as health
from experiments.dab_meta_runtime import meta_environment,run_logged_command
from experiments.dab_bound_meta_tools_v1 import bind_environment
MODEL='gpt-5.5';PROFILE='crs-gpt55-dab'
POLICY='compact_result_graph_safe_details_v2'
INTEGRATION=ROOT/'tmp/meta_native_mxc_v2/report.json'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def new(p,value):
    with Path(p).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=True);f.write('\n');f.flush();os.fsync(f.fileno())

def require_native_integration(report=INTEGRATION):
    """Standalone sandbox success is NOT a native model/tool release gate."""
    report=Path(report)
    if not report.is_file():raise RuntimeError('Actual native tool integration not verified; zero Meta dispatch')
    value=read(report)
    if value.get('passed') is not True or value.get('model')!=MODEL or value.get('successful_command_count',0)<2 or value.get('completed_file_change_count',0)<1 or value.get('research_generation_started') is not False:raise RuntimeError('Actual native tool integration failed/unverified; zero Meta dispatch')
    directory=report.parent
    actual=native.verify(directory,directory/'native.stdout',directory/'native.stderr',health.HOME,'workspace-write')
    if actual!=value.get('actual_native_audit'):raise RuntimeError('Actual native tool proof changed')
    health_record=read(directory/'health_binding.json')
    if health_record.get('passed') is not True or health_record.get('network_policy_validation')!='passed':raise RuntimeError('Native denial boundaries unverified')
    bind_environment({},health_record['tools'])
    return value

class StageStore:
    """A completed receipt may be reused, but never a dispatch without receipt."""
    def __init__(self,root):self.root=Path(root);self.root.mkdir(exist_ok=True,parents=True)
    def step(self,name,action):
        if not name.replace('_','').isalnum():raise ValueError('Invalid stage')
        receipt=self.root/(name+'.receipt.json');intent=self.root/(name+'.intent.json')
        if receipt.exists():
            value=read(receipt)
            if value.get('stage')!=name or value.get('status')!='completed':raise RuntimeError('Incomplete stage receipt')
            for path,digest in value['bindings'].items():
                if sha(path)!=digest:raise RuntimeError('Completed evidence changed; no replay')
            return value['value']
        if intent.exists():raise RuntimeError('Dispatched stage has no completed receipt; reconcile, never replay: '+name)
        new(intent,{'stage':name,'started_at':protocol.utc_now(),'automatic_retry':False})
        try:
            value,artifacts=action()
            receipt_value={'stage':name,'status':'completed','value':value,'bindings':{str(p):sha(p) for p in artifacts},'finished_at':protocol.utc_now()}
            new(receipt,receipt_value);return value
        except (Exception,SystemExit) as exc:
            new(self.root/(name+'.failure.json'),{'stage':name,'failure_type':type(exc).__name__,'automatic_retry':False,'paid_stage_may_have_executed':True})
            raise

def drive(store,actions,mode,max_repairs=2):
    """All effects are stage actions; fixtures test the complete control flow."""
    if mode not in ('review','candidate','review_then_candidate') or type(max_repairs) is not int or not 0<=max_repairs<=2:raise ValueError('Invalid authority/repair bounds')
    store.step('sandbox_health',actions.health)
    if mode!='candidate':
        context=store.step('review_context',actions.review_context)
        response=store.step('independent_review',lambda:actions.review(context))
        graph=store.step('original_graph_append',lambda:actions.graph(response))
        if mode=='review':return {'status':'review_and_graph_complete','graph':graph,'candidate_started':False}
    # Validate generation authority AFTER append, before preparing another session.
    store.step('candidate_authority',actions.candidate_authority)
    context=store.step('selector_context',actions.selector_context)
    response=store.step('independent_selector',lambda:actions.selector(context))
    intent=store.step('original_seal_intent',lambda:actions.seal(response,context))
    seed=None;diagnostic=None
    for index in range(max_repairs+1):
        candidate=store.step(f'prepare_candidate_{index:03d}',lambda:actions.prepare_candidate(intent,index,seed,diagnostic))
        store.step(f'independent_coding_{index:03d}',lambda:actions.code(candidate))
        audit=store.step(f'deterministic_audit_{index:03d}',lambda:actions.audit(candidate))
        if audit.get('passed') is True:
            admitted=store.step('original_record_candidate',lambda:actions.admit(candidate,audit))
            return store.step('data_handoff',lambda:actions.handoff(admitted))
        if audit.get('failure_kind')!='candidate_validation':raise RuntimeError('Infrastructure/permission/transport failure is not a candidate repair request')
        if index==max_repairs:raise RuntimeError('Bounded independent repairs exhausted; failures retained')
        diagnostic=store.step(f'bounded_diagnostic_{index:03d}',lambda:actions.diagnostic(candidate,audit))
        seed=candidate
    raise RuntimeError('Unreachable')

def stable_config(plan,allowed_new_projects=()):
    """Accept only CLI trust-only records for exact newly prepared workspaces."""
    cfg=tomllib.loads((health.HOME/'config.toml').read_text(encoding='utf-8'))
    baseline=plan['base_config'];current_projects=cfg.pop('projects',{})
    base_projects=baseline.get('projects',{})
    if cfg!={k:v for k,v in baseline.items() if k!='projects'}:raise RuntimeError('Model/provider/policy config changed')
    if any(current_projects.get(k)!=v for k,v in base_projects.items()):raise RuntimeError('Original project configuration changed')
    allowed={str(Path(p).resolve()).casefold() for p in allowed_new_projects}
    for p,v in current_projects.items():
        if p not in base_projects and (p.casefold() not in allowed or v!={'trust_level':'trusted'}):raise RuntimeError('Unexpected project layer')
    health.validate_config(health.HOME)
    if sha(health.HOME/(PROFILE+'.config.toml'))!=plan['profile_sha256']:raise RuntimeError('Profile changed')

class OriginalActions:
    def __init__(self,plan,run):
        self.plan=plan;self.run=Path(run);self.campaign=Path(plan['campaign']);self.generation=plan.get('candidate_generation');self.tools=plan['tools']
    def verify(self):
        for p,d in self.plan['bindings'].items():
            if sha(p)!=d:raise RuntimeError('Workflow authority/source binding changed')
        repos=[]
        for receipt in self.run.glob('prepare_candidate_*.receipt.json'):
            repos.append(Path(read(receipt)['value']['workspace'])/'repo')
        sessions=[Path(read(p)['value']['session']) for p in self.run.glob('*_context.receipt.json')]
        stable_config(self.plan,[*repos,*sessions]);bind_environment({},self.tools)
        for repo in repos:
            if (repo/'.codex').exists():raise RuntimeError('Unbound candidate project configuration')
    def health(self):
        self.verify();value=health.check(tools=self.tools,implementation='mxc',boundary_checks=True)
        if value.get('passed') is not True or value.get('network_policy_validation')!='passed':raise RuntimeError('Native health/denial check failed; no model dispatch')
        return value,[Path(value['fixture_dir'])/'report.json']
    def _session_environment(self):
        self.verify()
        # Existing approved route owns credential handling; never print environment.
        os.environ['DAB_RESEARCH_API_CONFIG']=str(ROOT/'configs/dab_crs_gpt55_route_v1.json')
        env=bind_environment(meta_environment(PROFILE),self.tools)
        env.pop('CODEX_MCP_NODE_PATH',None)
        if Path(env.get('CODEX_HOME','')).resolve()!=health.HOME.resolve():raise RuntimeError('Native runtime home mismatch')
        return env
    def _json(self,context,output):
        session=Path(context['session']);self.verify()
        prompt=session/'pipeline_prompt.md'
        note=('\n\n# Current execution regime\nMeta and Data GPT-5.5 via CRS, medium reasoning, frozen inputs and base_description_plus_hints_v1 unchanged. '
              'Select parents and direction independently; exactly ONE materialization base. Read compact full Graph and relevant indexed safe details, not rows/query IDs/raw traces/answers/patch history. '
              'Historical model/runtime/concurrency differences are not causal baselines. Missing mechanism activation is UNKNOWN. No credentials, network, subagents or permission changes.\n')
        prompt.write_text((session/'prompt.md').read_text(encoding='utf-8')+note,encoding='utf-8')
        campaign,_=protocol.load_campaign(self.campaign)
        if campaign['meta_agent'].get('model')!=MODEL or campaign['meta_agent'].get('profile')!=PROFILE:raise RuntimeError('Campaign Meta route changed')
        campaign['meta_agent']['codex']=self.tools['codex']['path']
        env=self._session_environment();old_env=protocol.meta_environment;old_run=protocol.run_logged_command
        def bound_run(command,**kwargs):
            if command[0]!=self.tools['codex']['path'] or '--no-daemon' not in command or '--sandbox' not in command:raise RuntimeError('Unbound native command')
            return old_run(health.mxc_command(command[0],*command[1:]),**kwargs)
        try:
            protocol.meta_environment=lambda _:env;protocol.run_logged_command=bound_run
            result=protocol.invoke_codex_json(campaign=campaign,session=session,prompt=prompt.read_text(encoding='utf-8'),schema_path=session/'output_schema.json',output_name=output)
        finally:protocol.meta_environment=old_env;protocol.run_logged_command=old_run
        audit=native.verify(session,session/'codex.stdout',session/'codex.stderr',health.HOME,'read-only')
        new(session/'pipeline_native_audit.json',audit);self.verify()
        return {'response':result,'session':str(session)},[session/output,session/'codex.stdout',session/'codex.stderr',session/'pipeline_native_audit.json',Path(audit['session_path'])]
    def review_context(self):
        _,state=protocol.load_campaign(self.campaign)
        if state['stage']!='result_recorded' or state['next_generation']!=self.plan['review_generation']:raise RuntimeError('Audited recorded result required before review')
        session,_=protocol.prepare_review_context(self.campaign)
        return {'session':str(session)},[session/'prompt.md',session/'output_schema.json']
    def review(self,context):return self._json(context,'review_response.json')
    def graph(self,response):
        record=protocol.append_review(self.campaign,response['response']);audit=protocol.verify_roadmap(self.campaign)
        if not audit['ok']:raise RuntimeError('Original Graph validation failed')
        path=self.run/'graph_verification.json';new(path,audit)
        return {'record_sha256':record['record_sha256'],'node_id':record['node_id']},[path,self.campaign/'details'/f'review_gen_{self.plan["review_generation"]:03d}.json']
    def candidate_authority(self):
        campaign,state=protocol.load_campaign(self.campaign)
        if self.generation not in self.plan['authorized_candidate_generations'] or self.generation>campaign['max_generations']:raise RuntimeError('Next generation lacks human/campaign authority')
        if state['stage']!='ready_for_intent' or state['next_generation']!=self.generation:raise RuntimeError('Unexpected selector stage')
        return {'generation':self.generation,'authorized':True},[]
    def selector_context(self):
        session,snapshot,_=protocol.prepare_intent_context(self.campaign)
        if snapshot.get('context_policy')!=POLICY:raise RuntimeError('Bound safe Graph detail policy required')
        return {'session':str(session)},[session/'prompt.md',session/'output_schema.json',session/'roadmap_snapshot.json']
    def selector(self,context):return self._json(context,'intent_response.json')
    def seal(self,response,context):
        value=protocol.seal_intent(self.campaign,response['response'],read(Path(context['session'])/'roadmap_snapshot.json'))
        return value,[protocol.generation_dir(self.campaign,self.generation)/'sealed_intent.json']
    def prepare_candidate(self,intent,index,seed,diagnostic):
        gen=protocol.generation_dir(self.campaign,self.generation)
        evidence=gen/'selected_parent_evidence.json'
        if not evidence.exists():
            value=protocol.build_selected_parent_evidence(self.campaign,intent);protocol.materialize_safe_details(self.campaign,value);protocol.write_json(evidence,value)
        base=protocol.resolve_materialization_parent(self.campaign,intent['code_parent_node_id'])
        output=gen/('candidate_workspace' if index==0 else f'meta_retry{index:03d}')
        upstream=Path(protocol.load_root_node(self.campaign)['source_root'])/'external/DataAgentBench_official/common_scaffold/DataAgent.py'
        workspace.prepare(argparse.Namespace(source_root=Path(base['source_root']),output=output,intent=gen/'sealed_intent.json',parent_source=None,parent_context=evidence,upstream_source=upstream if upstream.is_file() else None,mechanism_contract=None))
        if seed:
            prior=Path(seed['workspace'])/'repo';repo=output/'repo'
            for name in sorted({r['path'] for r in workspace.source_tree_manifest(prior)}|{r['path'] for r in workspace.source_tree_manifest(repo)}):
                origin=prior/name;target=repo/name
                if not origin.is_file() or origin.is_symlink():raise RuntimeError('Removed/symlink repair seed requires reconciliation')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin,target)
            shutil.copy2(prior/'candidate_workspace_report.json',repo/'candidate_workspace_report.json')
            if workspace.source_tree_hash(prior)!=workspace.source_tree_hash(repo):raise RuntimeError('Exact failed-source repair seed mismatch')
        task=output/'implementation_task.md'
        task.write_text(task.read_text(encoding='utf-8')+'\n\n# Bound workflow contracts\nPreserve sealed intent, exactly one materialization source, ALL existing tests/guards/validators/protocol bytes. Add separate new synthetic mechanism tests. '
            'Declare runtime_state_contract exactly {persistent_fields:[{name: actual_attribute,type: json or string_set}],stateless: boolean}; declare every newly introduced recovery-relevant state; verify actual roundtrips. '
            'New artifacts stay in the existing checkpointed workspace. Unsupported state/artifact infrastructure must be reported, never silently dropped. '
            'No benchmark/DB/network/credentials/subagents, no permission changes or retry after denial. Synthetic failures return to a distinct independent Meta session. '
            'Missing mechanism activation UNKNOWN.\n'+('Same-intent repair of exact failed Meta source:\n'+json.dumps(diagnostic,ensure_ascii=True) if diagnostic else ''),encoding='utf-8')
        return {'workspace':str(output),'attempt':index},[output/'workspace_manifest.json',task,evidence]
    def code(self,candidate):
        output=Path(candidate['workspace']);repo=output/'repo';task=output/'implementation_task.md'
        env=self._session_environment()
        temporary=ROOT/'tmp'/('mp_'+self.run.name[-8:]+'_'+str(candidate['attempt']));temporary.mkdir(exist_ok=False)
        env.update(TMP=str(temporary),TEMP=str(temporary),TMPDIR=str(temporary))
        command=health.mxc_command(self.tools['codex']['path'],'--no-daemon','-C',str(repo),'--model',MODEL,'--profile',PROFILE,'exec','--sandbox','workspace-write','-c','approval_policy="on-request"','-c','approvals_reviewer="auto_review"','--json','--skip-git-repo-check','-')
        result=run_logged_command(command,cwd=repo,prompt=task.read_text(encoding='utf-8'),stdout_path=output/'meta.stdout',stderr_path=output/'meta.stderr',env=env,timeout=None)
        if result.returncode:raise RuntimeError('Native model failed; no automatic replay')
        audit=native.verify(repo,output/'meta.stdout',output/'meta.stderr',health.HOME,'workspace-write')
        new(output/'pipeline_native_audit.json',audit);self.verify()
        snapshot={'source_sha256':workspace.source_tree_hash(repo),'report_sha256':sha(repo/'candidate_workspace_report.json')}
        new(output/'coded_source_binding.json',snapshot)
        return snapshot,[output/'coded_source_binding.json',output/'meta.stdout',output/'meta.stderr',output/'pipeline_native_audit.json',Path(audit['session_path'])]
    def audit(self,candidate):
        output=Path(candidate['workspace'])
        snapshot=read(output/'coded_source_binding.json')
        if workspace.source_tree_hash(output/'repo')!=snapshot['source_sha256'] or sha(output/'repo/candidate_workspace_report.json')!=snapshot['report_sha256']:raise RuntimeError('Completed Meta source changed before audit')
        with (output/'source_preflight.stdout').open('x',encoding='utf-8') as log,contextlib.redirect_stdout(log):code=workspace.audit(argparse.Namespace(workspace=output,python=self.tools['python']['path']))
        audit=compatibility.audit(output,output/'compatibility',self.tools['python']['path'])
        # Unchanged original compatibility verdict, no synthetic error hiding.
        value={'passed':code==0 and bool(compatibility.gate_verdict(audit)),'failure_kind':'candidate_validation','source_sha256':audit['source_sha256'],'patch_sha256':audit['patch_sha256']}
        return value,[output/'candidate_admission.json',output/'candidate.patch',output/'compatibility/report.json']
    def diagnostic(self,candidate,audit):
        output=Path(candidate['workspace'])
        value={'synthetic_compatibility':json.loads(compatibility.bounded_feedback(read(output/'compatibility/report.json'))),'source_preflight_failures':read(output/'candidate_admission.json')['failures']}
        path=output/'bounded_repair_diagnostic.json';new(path,value)
        return value,[path]
    def admit(self,candidate,audit):
        output=Path(candidate['workspace']);report=read(output/'compatibility/report.json')
        if not compatibility.gate_verdict(report) or workspace.source_tree_hash(output/'repo')!=audit['source_sha256'] or sha(output/'candidate.patch')!=audit['patch_sha256']:raise RuntimeError('Independent gate binding changed')
        protocol.record_candidate(argparse.Namespace(campaign_root=self.campaign,workspace=output))
        path=protocol.generation_dir(self.campaign,self.generation)/'candidate_ref.json'
        return {'candidate_ref':str(path),'candidate_ref_sha256':sha(path)},[path]
    def handoff(self,admitted):
        value={'status':'meta_complete_candidate_admitted','generation':self.generation,'model':MODEL,**admitted,'data_evaluation_started':False,'fresh_candidate_runtime_and_input_audits':'required_before_Data_launch','full_evolution_cycle_complete':False}
        path=self.run/'meta_handoff.json';new(path,value);return value,[path]

def prepare(campaign,run,mode,authority,review_generation=None,candidate_generation=None):
    """Explicit scope, no model/key read, config changes or next-gen inference."""
    campaign=Path(campaign).resolve();run=Path(run).resolve();_,state=protocol.load_campaign(campaign)
    if not authority.strip():raise ValueError('Human authority description required')
    if run.parent!=campaign/'meta_workflows' or run.exists():raise RuntimeError('Fresh workflow must be within campaign/meta_workflows')
    if mode not in ('review','candidate','review_then_candidate'):raise ValueError('Unknown workflow mode')
    config,_=protocol.load_campaign(campaign)
    if mode!='candidate' and (state['stage']!='result_recorded' or review_generation!=state['next_generation']):raise RuntimeError('Review not ready')
    if mode!='review':
        required=state['next_generation']+(mode=='review_then_candidate')
        if candidate_generation!=required or candidate_generation>config['max_generations'] or mode=='candidate' and state['stage']!='ready_for_intent':raise RuntimeError('Candidate generation unavailable/unauthorized')
    require_native_integration()
    health.validate_config(health.HOME)
    paths=[Path(__file__),ROOT/'experiments/dab_meta_sandbox_health_v1.py',ROOT/'experiments/dab_bound_meta_tools_v1.py',ROOT/'experiments/dab_native_meta_audit_v3.py',ROOT/'experiments/dab_native_meta_audit_v2.py',ROOT/'experiments/dab_candidate_compatibility_v3.py',ROOT/'experiments/dab_candidate_compatibility_v2.py',ROOT/'experiments/intent_candidate_workspace.py',ROOT/'experiments/dab_roadmap_protocol.py',ROOT/'experiments/dab_meta_runtime.py',ROOT/'experiments/dab_api_routing.py',ROOT/'experiments/dab_meta_context_policy.md',ROOT/'configs/dab_crs_gpt55_route_v1.json']
    tools={n:{'path':str(p),'sha256':sha(p)} for n,p in [('codex',health.CODEX),('python',health.PYTHON),('powershell',health.NATIVE)]}
    run.mkdir(parents=True,exist_ok=False)
    plan={'schema':'dab_meta_pipeline_v1','authority':authority,'campaign':str(campaign),'mode':mode,'review_generation':review_generation,'candidate_generation':candidate_generation,'authorized_candidate_generations':[] if mode=='review' else [candidate_generation],'max_repairs':2,'model':MODEL,'profile':PROFILE,'implementation':'mxc','base_config':tomllib.loads((health.HOME/'config.toml').read_text(encoding='utf-8')),'profile_sha256':sha(health.HOME/(PROFILE+'.config.toml')),'tools':tools,'bindings':{str(p):sha(p) for p in paths},'Data_or_SSH_authorized':False,'automatic_transport_replay':False}
    new(run/'plan.json',plan);return plan

def run_workflow(run):
    run=Path(run);plan=read(run/'plan.json');lock=run/'execution.lock.json'
    require_native_integration()
    # Abandoned/concurrent lock requires read-only reconciliation, never deletion.
    new(lock,{'pid':os.getpid(),'started_at':protocol.utc_now(),'plan_sha256':sha(run/'plan.json')})
    actions=OriginalActions(plan,run)
    try:
        actions.verify();value=drive(StageStore(run),actions,plan['mode'],plan['max_repairs'])
        return value
    finally:lock.unlink()

def main():
    p=argparse.ArgumentParser();p.add_argument('--campaign',type=Path);p.add_argument('--run',type=Path)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--run-once',action='store_true');g.add_argument('--start',action='store_true');g.add_argument('--status',action='store_true')
    p.add_argument('--mode',choices=('review','candidate','review_then_candidate'));p.add_argument('--authority');p.add_argument('--review-generation',type=int);p.add_argument('--candidate-generation',type=int);args=p.parse_args()
    if args.prepare or args.start:
        if not args.run or not args.campaign or not args.mode or not args.authority:p.error('Explicit run/campaign/mode/authority required')
        if args.start and (args.run/'plan.json').is_file():
            plan=read(args.run/'plan.json')
            requested={'campaign':str(args.campaign.resolve()),'mode':args.mode,'authority':args.authority,'review_generation':args.review_generation,'candidate_generation':args.candidate_generation}
            if any(plan.get(k)!=v for k,v in requested.items()):raise RuntimeError('Existing workflow scope differs; no reuse')
        else:prepare(args.campaign,args.run,args.mode,args.authority,args.review_generation,args.candidate_generation)
        if args.prepare:print(json.dumps({'prepared':True,'model_calls':0}));return 0
        print(json.dumps(run_workflow(args.run),indent=2));return 0
    if args.status:
        if not args.campaign:p.error('--campaign required')
        _,s=protocol.load_campaign(args.campaign)
        try:require_native_integration();integration='passed'
        except RuntimeError:integration='failed_or_unverified'
        print(json.dumps({'stage':s['stage'],'generation':s['next_generation'],'native_tool_integration':integration,'model_calls':0,'research_stage_started':False}));return 0
    if not args.run:p.error('--run required')
    print(json.dumps(run_workflow(args.run),indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
