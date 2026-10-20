"""Accept the human-authorized stratified Gen4 result without rerunning old rows."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import dab_roadmap_protocol as protocol
from experiments.dab_result_health import provider_failure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign-root', type=Path, required=True)
    parser.add_argument('--human-accepted-mixed', action='store_true', required=True)
    args = parser.parse_args()
    campaign = args.campaign_root.resolve()
    g = campaign/'generations/gen_004'; repair = g/'runtime_repair_v1'
    output = g/'formal_merged_summary.json'
    protocol.require_new(output)
    paths = [g/'retry_api9_serial_base_summary.json', repair/'stopped_serial9_partial_summary.json', repair/'remaining3_summary.json']
    base, stopped, new = [protocol.read_json(p) for p in paths]
    frozen = protocol.read_json(ROOT/'dab_corpus/batches/evolution_domain17_v1_20260929.json')
    healthy = lambda r: r.get('run_exit_code') == 0 and not r.get('run_error') and not provider_failure(r)
    old = [r for r in base['per_query_feedback'] if healthy(r)] + stopped['per_query_feedback']
    assert len(old) == len({r['query_id'] for r in old}) == 14 and all(healthy(r) for r in old)
    fresh = new['per_query_feedback']
    assert [r['query_id'] for r in fresh] == ['stockmarket/query1','usaspending/query1','yelp/query1']
    assert all(healthy(r) for r in fresh)
    by_id = {r['query_id']: copy.deepcopy(r) for r in old+fresh}
    assert len(by_id) == 17 and set(by_id) == set(frozen['query_ids'])
    rows = [by_id[q] for q in frozen['query_ids']]
    old_ids = {r['query_id'] for r in old}
    for r in rows:
        r['evaluation_regime'] = 'historical_unrepaired' if r['query_id'] in old_ids else 'runtime_repair_v1'
    f1s = [r['answer_f1'] for r in rows if isinstance(r.get('answer_f1'), (int,float)) and not isinstance(r.get('answer_f1'), bool)]
    binding = {
        'result_type':'human_accepted_stratified_recovery_v1', 'homogeneous_runtime':False,
        'human_accepted_mixed':True, 'comparability':'Confounded by input/runtime policies and scheduling; no causal claim about candidate or concurrency.',
        'repair_policy':'input_and_transport_recovery_v1', 'input_policy':'mixed_legacy_and_base_description_plus_hints_v1',
        'f1_observed_count':len(f1s), 'f1_denominator':'observed_rows_only; missing F1 unknown',
        'regimes':[
            {'name':'historical_unrepaired','row_count':14,'source_sha256':'4abfa5075fb465dbc4add3a19e660b28e186e595ce8998c4b0c3211010aba228',
             'upstream_runtime_sha256':None,'input_policy':'legacy_hint_file_replaces_description','repair_policy':None,'workers':'mixed6_and1'},
            {'name':'runtime_repair_v1','row_count':3,'source_sha256':'41af29f1fbc7a04ad127adc442eb50d005923d8123d577d3af9494826b4aac9a',
             'upstream_runtime_sha256':'20376b0981a36d9df90c8bc65d42d4afeadb8c1da946bb27e87d942729854e36',
             'input_policy':'base_description_plus_hints_v1','repair_policy':'input_and_transport_recovery_v1','workers':1}],
    }
    merged = {**base, 'created_at':protocol.utc_now(), 'batch':frozen,'batch_id':frozen.get('batch_id'),
              'query_count':17,'successful_run_count':17,'final_answer_nonempty_count':sum(bool(r['final_answer_nonempty']) for r in rows),
              'strict_pass_count':sum(r['strict_match_passed'] is True for r in rows),
              'average_f1':round(sum(f1s)/len(f1s),6) if f1s else None,
              'audit_only':False,'formal_result_eligible':True,'provider_failure_count':0,'per_query_feedback':rows,
              'evaluation_binding':binding,
              'human_acceptance':{'at':protocol.utc_now(),'direction':'Use mixed retained results as new parent evidence; no full rerun; next generation workers3'},
              'provenance':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]}
    for field, rowkey in [('selected_problem_type_counts','selected_problem_type'),('selected_stage_counts','selected_stage')]:
        merged[field] = dict(Counter(str(r.get(rowkey) or 'unknown') for r in rows))
    merged['execution_context'] = {'result_type':binding['result_type'],'homogeneous_runtime':False,
                                 'sealed_candidate_source_sha256':binding['regimes'][0]['source_sha256'],
                                 'regimes':binding['regimes']}
    merged['artifact_paths'] = {'human_accepted_merged_summary':str(output.resolve())}
    protocol.write_json(output, merged)
    policy = {
        'human_authority':'2026-10-06: accept mixed Gen4, use as next-generation parent, set evaluation concurrency3',
        'workers':3,'repair_policy':'input_and_transport_recovery_v1','input_policy':'base_description_plus_hints_v1',
        'concurrency_causality_status':'human_hypothesis_not_established; no comparison experiment',
        'required_parent_generation':5,'required_parent_nodes':['gen_004_turn_level_progress_checkpoints'],
        'overlay_contract':'Human-authorized post-admission infrastructure overlay installs LAST. It owns DataAgent.call_llm/run and checkpointed dispatch invoking candidate _handle_tool_call/_handle_content wrappers; no iteration cap. Preserve compatibility with those owned entrypoints; not a Meta-assigned improvement. Exactly one materialization sourcebase remains Meta-selected.',
        'runtime_overlay_source':str((repair/'derived_repo/experiments/dab_runtime_repair_v1.py').resolve())}
    protocol.write_json(campaign/'runtime_execution_policy.json', policy)
    print(json.dumps({'summary':str(output),'strict_pass_count':merged['strict_pass_count'],'average_f1':merged['average_f1'],'f1_observed_count':len(f1s),'query_count':17,'homogeneous_runtime':False,'next_workers':3}))


if __name__ == '__main__':
    main()
