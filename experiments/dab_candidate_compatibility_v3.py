"""Mechanism-neutral frozen compatibility for future Meta candidates.

Existing checker, delivery harness, parent tests, guards and validators remain
immutable. New mechanism tests are separate additions, not a prescribed topic.
"""
import hashlib, json, os, subprocess, sys
from pathlib import Path
from experiments import dab_candidate_compatibility_v2 as frozen
from experiments import intent_candidate_workspace as source

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def gate_verdict(report):
    names={'wrapper38','delivery6','frozen_parent_units_and_new_mechanism','cli_help','runtime_state_contract'}
    tests=report.get('tests',[])
    return (report.get('protected_existing_files_changed')==[] and report.get('source_unchanged') is True
            and report.get('new_mechanism_test_files') and len(tests)==5
            and {t.get('name') for t in tests}==names
            and all(t.get('passed') is True and t.get('returncode')==0 for t in tests)
            and report.get('model_calls')==report.get('database_calls')==0)
def audit(workspace, output, python=sys.executable):
    workspace=Path(workspace); output=Path(output); output.mkdir(exist_ok=False)
    repo=workspace/'repo'; manifest=read(workspace/'workspace_manifest.json'); parent=Path(manifest['source_root'])
    if source.source_tree_hash(parent)!=manifest['parent_source_sha256']: raise RuntimeError('Selected parent changed')
    if sha(frozen.CHECKER)!=frozen.FROZEN_CHECKER or sha(frozen.DELIVERY)!=frozen.FROZEN_DELIVERY: raise RuntimeError('Frozen harness changed')
    protected=frozen.protected_changes(repo,manifest)
    # Active original protocol/admission/guards are also immutable research scaffolding.
    protected_prefixes=('experiments/dab_roadmap_protocol.py','experiments/intent_candidate_workspace.py')
    for row in manifest['files']:
        if row['path'] in protected_prefixes and (not (repo/row['path']).is_file() or sha(repo/row['path'])!=row['sha256']): protected.append(row['path'])
    parent_paths={x['path'] for x in manifest['files']}
    added=sorted(x['path'] for x in source.source_tree_manifest(repo) if x['path'].startswith('tests/test_') and x['path'].endswith('.py') and x['path'] not in parent_paths)
    before=source.source_tree_hash(repo)
    fixed=['tests/test_dab_turn_checkpoints.py','tests/test_dab_turn_checkpoint_recovery.py','tests/test_dab_checkpoint_delivery.py','tests/test_dab_artifact_recovery_budget.py']
    inherited_tests=['tests/test_dab_gen7_runtime_turn_budget.py','tests/test_gen008_duplicate_failure_gate.py']
    paths=[parent/p for p in fixed]+[parent/p for p in inherited_tests if p in parent_paths]+[repo/p for p in added]
    dependencies=[frozen.CHECKER,frozen.DELIVERY,frozen.WORKER,workspace/'workspace_manifest.json',workspace/'context/sealed_intent.json',Path(__file__)]+paths
    bindings={str(p):sha(p) for p in dependencies if p.is_file()}
    temp=output/'temp';temp.mkdir()
    env=os.environ.copy()
    for k in ('PYTHONPATH','CRS_API_KEY','OPENAI_API_KEY','DEEPSEEK_API_KEY','DAB_RESEARCH_API_CONFIG'):env.pop(k,None)
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',TMP=str(temp),TEMP=str(temp),TMPDIR=str(temp))
    tests=[]
    def check(name,argv,count=None):
        stdout=output/(name+'.stdout'); stderr=output/(name+'.stderr')
        with stdout.open('x',encoding='utf-8') as out,stderr.open('x',encoding='utf-8') as err:
            result=subprocess.run([str(python),*map(str,argv)],cwd=repo,env=env,stdout=out,stderr=err,timeout=180,check=False)
        passed=result.returncode==0; failures=[]
        if count:
            try:
                value=read(stdout);passed=passed and value.get('passed') is True and len(value.get('checks',[]))==count
                failures=[{k:str(c.get(k,''))[:300] for k in ('name','error','error_type')} for c in value.get('checks',[]) if c.get('passed') is not True]
            except (ValueError,UnicodeError):passed=False
        tests.append({'name':name,'passed':passed,'returncode':result.returncode,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),'failures':failures,'bounded_stderr':stderr.read_text(encoding='utf-8',errors='replace')[-2000:] if not passed else ''})
    check('wrapper38',[frozen.WORKER,'--worker',repo,parent/fixed[1],frozen.CHECKER,temp],38)
    check('delivery6',[frozen.DELIVERY,repo,frozen.CHECKER],6)
    code=('import unittest,importlib.util,tempfile,sys;tempfile.tempdir='+repr(str(temp))+';paths='+repr([str(p) for p in paths])+';s=[]\n'
          'for i,p in enumerate(paths):\n'
          ' spec=importlib.util.spec_from_file_location("frozen_unit_"+str(i),p);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);s.append(unittest.defaultTestLoader.loadTestsFromModule(m))\n'
          'counts=[x.countTestCases() for x in s];assert counts[:4]==[5,1,3,4],counts;'
          'assert '+str(len(added))+'>0 and all(x>0 for x in counts[-'+str(max(1,len(added)))+':]),counts;'
          'r=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(s));sys.exit(not r.wasSuccessful())')
    check('frozen_parent_units_and_new_mechanism',['-c',code])
    check('cli_help',['experiments/run_dab_tool_agent.py','--help'])
    contract_code=('import json;v=json.load(open("candidate_workspace_report.json",encoding="utf-8")).get("runtime_state_contract");'
                   'assert isinstance(v,dict) and set(v)=={"persistent_fields","stateless"};'
                   'f=v["persistent_fields"];assert type(v["stateless"]) is bool and isinstance(f,list) and len(f)<=100;'
                   'assert v["stateless"] is (len(f)==0);'
                   'assert all(isinstance(x,dict) and set(x)=={"name","type"} and isinstance(x["name"],str) and x["name"].isidentifier() and x["type"] in ("json","string_set") for x in f);'
                   'assert len({x["name"] for x in f})==len(f);'
                   'assert not {x["name"] for x in f}&{"client","tools","messages","journal","turn_checkpoint_recovery","_gen9_candidate_state"}')
    check('runtime_state_contract',['-c',contract_code])
    report={'schema':'dab_candidate_compatibility_v3','workspace':str(workspace),'source_sha256':before,'patch_sha256':sha(workspace/'candidate.patch'),'bindings':bindings,'protected_existing_files_changed':sorted(set(protected)),'new_mechanism_test_files':added,'tests':tests,'source_unchanged':source.source_tree_hash(repo)==before and all(sha(p)==d for p,d in bindings.items()),'model_calls':0,'database_calls':0}
    report['passed']=bool(gate_verdict(report));frozen.save_new(output/'report.json',report);return report
def bounded_feedback(report):
    return json.dumps({'protected_existing_files_changed':report['protected_existing_files_changed'],'new_mechanism_test_files':report['new_mechanism_test_files'],'failed_synthetic_checks':[{'name':t['name'],'returncode':t['returncode'],'checks':t['failures'],'bounded_stderr':t['bounded_stderr']} for t in report['tests'] if not t['passed']]},ensure_ascii=False)
