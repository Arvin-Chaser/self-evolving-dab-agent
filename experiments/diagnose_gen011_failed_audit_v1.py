"""Read-only boolean diagnostics for a failed Gen11 terminal audit check."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930/generations/gen_011/deepseek_evaluation_v1"
binding = json.loads((EVAL / "launch_binding.json").read_bytes())
code = r'''
import hashlib,json,sys
from pathlib import Path
s=__BINDING__
run=Path(s['run_dir']);raw=(run/'multi_query_summary.json').read_bytes();rows=json.loads(raw)['per_query_feedback']
checks={}
checks['remote_binding_same']=json.loads((Path(s['audit_dir'])/'launch_binding.json').read_bytes())==s
checks['summary_sha_same']=hashlib.sha256(raw).hexdigest()=='6c463aefda569d186615b8a6d129d1f8ccb579f398ff244c22c7aed757d70f8c'
checks['ids_order']=len(rows)==17 and [r['query_id'] for r in rows]==s['query_ids']
checks['compact_failures']=sum(r.get('run_exit_code')==1 and r.get('analyze_exit_code')==0 and r.get('run_error')=='UnsafeResume: Actual candidate field missing: deliveries' and r.get('tool_call_count')==0 and r.get('final_answer_nonempty') is False for r in rows)
sys.path.insert(0,s['candidate_repo'])
from experiments.intent_candidate_workspace import source_tree_hash
checks['source_sha_same']=source_tree_hash(Path(s['candidate_repo']))==s['derived_source_sha256']
active=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  tail=(p/'stat').read_text().rsplit(')',1)[1].split();a=(p/'cmdline').read_bytes()
 except (FileNotFoundError,ProcessLookupError):continue
 if tail[0] not in ('Z','X','x') and (int(tail[2])==s['pgid'] or int(tail[3])==s['sid'] or s['run_id'].encode() in a):active.append(int(p.name))
checks['active_process_count']=len(active)
checks['run_path_count']=sum(Path(r['run_dir']).is_dir() and Path(r['run_dir']).parent==run/'runs' for r in rows)
details=[json.loads((Path(r['run_dir'])/'summary.json').read_bytes()) for r in rows]
checks['per_run_llm_counts']=sorted(set(str(d.get('llm_call_count')) for d in details))
checks['per_run_tool_counts']=sorted(set(str(d.get('tool_call_count')) for d in details))
checks['empty_workflow_count']=sum((Path(r['run_dir'])/'workflow_trace.jsonl').stat().st_size==0 for r in rows)
checks['empty_final_count']=sum((Path(r['run_dir'])/'final_answer.txt').stat().st_size==0 for r in rows)
checks['remote_mutations']=0
print(json.dumps(checks))
'''.replace("__BINDING__", repr(binding))
proc = subprocess.run(["ssh", "-i", "C:/Users/34934/.ssh/codex_ct104", "-o", "BatchMode=yes",
                       "-o", "ConnectTimeout=15", "root@100.83.10.33", "/srv/text2sql/.venv/bin/python -"],
                      input=code, capture_output=True, text=True, encoding="utf-8", timeout=60)
if proc.returncode:
    raise RuntimeError("Read-only Gen11 audit diagnosis failed")
print(proc.stdout)
