"""One human-authorized Gen8 selector and implementation, never evaluation/replay.

Preparation is model-free. Run only after normal desktop exit. The original
graph selector, intent validator, workspace audit and candidate recorder own
all research decisions and admission; this helper only binds orchestration.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import dab_roadmap_protocol as protocol
from experiments import intent_candidate_workspace as workspace
from experiments.probe_aligned_meta_v2 import config_alignment

CAMPAIGN = ROOT / 'experiments/dab_evolution_campaigns/domain17_glm53_unbounded_v1_20260930'
GEN = CAMPAIGN / 'generations/gen_008'
RUN = GEN / 'formal_meta_v2'
HOME = ROOT / 'configs/crs_gpt55_meta_runtime_v1'
ROUTE = ROOT / 'configs/dab_crs_gpt55_route_v1.json'
PYTHON = Path('C:/Users/34934/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
CODEX = Path('C:/Users/34934/AppData/Local/OpenAI/Codex/bin/9691020b546a15b2/codex.exe')
NATIVE = Path('C:/Users/34934/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe')
RUNTIME = 'C:/Users/34934/AppData/Local/OpenAI/Codex/runtimes/cua_node/3dd31cfff853001c/bin'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write('\n')


def assert_released():
    # Inspect exact executable paths, never credentials/command lines/ACLs.
    runtime_windows = RUNTIME.replace('/', '\\')
    script = ("$ErrorActionPreference='Stop'; $taskHolders=@(Get-CimInstance Win32_Process | "
              "Where-Object { $_.ExecutablePath -in @('" + runtime_windows + "\\node.exe','" +
              runtime_windows + "\\node_repl.exe') } | Select-Object ProcessId,Name); "
              "ConvertTo-Json -InputObject $taskHolders -Compress")
    result = subprocess.run([str(NATIVE), '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError('Runtime-release inspection unavailable; no dispatch')
    holders = json.loads(result.stdout)
    if holders:
        raise RuntimeError('Desktop Node runtime still active; quit normally. No process killed or model dispatched.')


def assert_stage(stage):
    _, state = protocol.load_campaign(CAMPAIGN)
    if state.get('next_generation') != 8 or state.get('stage') != stage:
        raise RuntimeError('Expected Gen8 stage changed; no automatic resume')
    return state


def assert_config():
    config = tomllib.loads((HOME / 'config.toml').read_text(encoding='utf-8'))
    provider = config['model_providers'][config['model_provider']]
    if (not config_alignment(config) or config['model'] != 'gpt-5.5'
            or config['model_reasoning_effort'] != 'medium'
            or provider['base_url'] != 'https://crs.uuid.im/openai'
            or provider['env_key'] != 'CRS_API_KEY' or provider['wire_api'] != 'responses'
            or provider['request_max_retries'] != 0 or provider['stream_max_retries'] != 0):
        raise RuntimeError('GPT model/provider/permission/no-replay configuration changed')
    audit = protocol.read_json(GEN / 'integration_alignment_v5/independent_integrity_audit.json')
    if audit.get('passed') is not True or not any(
        p.get('provider') == 'gpt' and p.get('model') == 'gpt-5.5' and p.get('passed') is True
        for p in audit.get('providers', [])):
        raise RuntimeError('Independent integration success missing')


def prepare():
    if RUN.exists():
        raise RuntimeError('Prepared formal run already exists; preserve it')
    os.environ['DAB_RESEARCH_API_CONFIG'] = str(ROUTE)
    assert_config()
    assert_stage('ready_for_intent')
    campaign, _ = protocol.load_campaign(CAMPAIGN)
    if campaign['max_generations'] != 8 or campaign['max_agent_iterations'] != 0:
        raise RuntimeError('Only one additional Gen8 cycle with unbounded iterations authorized')
    if any((GEN / name).exists() for name in ('sealed_intent.json', 'candidate_ref.json', 'candidate_workspace')):
        raise RuntimeError('Existing Gen8 research artifacts; no duplicate preparation')
    verification = protocol.verify_roadmap(CAMPAIGN)
    if not verification['ok'] or verification['record_count'] != 7:
        raise RuntimeError('Expected immutable seven-generation graph missing')
    if sha(campaign['evolution_batch']) != campaign['evolution_batch_sha256']:
        raise RuntimeError('Frozen batch changed')
    RUN.mkdir()
    session, snapshot, _ = protocol.prepare_intent_context(CAMPAIGN)
    if snapshot['context_policy'] != 'compact_result_graph_safe_details_v2':
        raise RuntimeError('Human-authorized safe detail context missing')
    # This is an infrastructure annotation, not a direction/parent/intent.
    note = ('\n\n# Current authorized Gen8 execution regime\n\n'
            'Meta and the future isolated Data Agent use GPT-5.5 via the human-selected CRS '
            'Responses route, medium reasoning. The frozen batch and base_description_plus_hints_v1 '
            'input policy remain unchanged. A fresh candidate-specific runtime overlay and four-worker '
            'evaluation are planned, not yet built or validated. No old checkpoint will be migrated '
            'or replayed. execution_environment in the compact snapshot is historical Gen6 runtime '
            'bookkeeping, NOT the current model, concurrency, parent requirement or runtime binding. '
            'Choose parents and one mechanism independently; no recovery direction is prescribed. '
            'Keep missing activation evidence UNKNOWN and cross-regime comparisons non-causal. '
            'Do not use subagents, network, credentials, raw archives or benchmark content. If a '
            'security denial or sandbox setup failure occurs, stop and report it without retry or bypass.\n')
    prompt = RUN / 'intent_prompt.md'
    prompt.write_text((session / 'prompt.md').read_text(encoding='utf-8') + note, encoding='utf-8')
    bindings = [CAMPAIGN / name for name in ('campaign.json', 'campaign_state.json', 'roadmap.jsonl',
        'root_node.json', 'runtime_execution_policy.json', 'meta_detail_policy_v1.json', 'gen008_api_selection_v1.json')]
    bindings += [ROOT / name for name in ('experiments/dab_roadmap_protocol.py',
        'experiments/intent_candidate_workspace.py', 'experiments/dab_meta_runtime.py',
        'experiments/dab_api_routing.py', 'experiments/dab_meta_detail_context_v1.py',
        'experiments/run_gen008_gpt55_meta_once_v1.py')]
    bindings += [ROUTE, CODEX, PYTHON, HOME / 'config.toml', HOME / 'crs-gpt55-dab.config.toml',
        GEN / 'integration_alignment_v5/independent_integrity_audit.json',
        Path(campaign['evolution_batch']), session / 'roadmap_snapshot.json', session / 'output_schema.json', prompt]
    bindings += [Path(e['safe_mechanism_detail']) for e in snapshot['safe_detail_access']['nodes']
                 if e['status'] == 'available']
    plan = {'schema': 'gen008_gpt55_meta_once_v1', 'prepared_at': protocol.utc_now(),
        'authority': 'Human authorized one GPT-5.5 Meta plus Data Agent Gen8 cycle; latest: 继续，我重置了你的额度',
        'generation': 8, 'model': 'gpt-5.5', 'profile': 'crs-gpt55-dab', 'reasoning_effort': 'medium',
        'selector_session': str(session), 'intent_prompt': str(prompt),
        'roadmap_head_sha256': verification['head_record_sha256'],
        'frozen_batch_sha256': campaign['evolution_batch_sha256'],
        'binding_sha256': {str(p): sha(p) for p in bindings},
        'automatic_retry': False, 'maximum_coding_sessions': 1, 'deadline': None,
        'candidate_and_intent_authorship': 'independent_Meta_only',
        'remote_upload': False, 'evaluation_started_by_this_helper': False,
        'next_generation_authorized': False, 'automations_remain_paused': True}
    save_new(RUN / 'plan.json', plan)
    print(json.dumps({'status': 'prepared_no_model_calls', 'session': str(session),
                      'graph_nodes': len(snapshot['nodes']), 'plan': str(RUN / 'plan.json')}))


def verify_native_session(directory, stdout, expected_sandbox):
    events = [json.loads(line) for line in stdout.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = {e['thread_id'] for e in events if e.get('type') == 'thread.started'}
    if len(ids) != 1 or not any(e.get('type') == 'turn.completed' for e in events):
        raise RuntimeError('Unique completed native Meta session missing')
    matches = list((HOME / 'sessions').rglob('*' + next(iter(ids)) + '.jsonl'))
    if len(matches) != 1:
        raise RuntimeError('Unique native session metadata missing')
    contexts, counts, prefix_counts = [], {}, []
    for line in matches[0].read_text(encoding='utf-8').splitlines():
        item = json.loads(line)
        if item.get('type') == 'turn_context':
            contexts.append(item['payload'])
        if item.get('type') == 'world_state':
            permissions = item['payload'].get('state', {}).get('permissions', {})
            prefix_counts.append(len(permissions.get('approved_command_prefixes', [])))
    if not contexts:
        raise RuntimeError('Actual model/permissions not observable')
    for context in contexts:
        if (context.get('model') != 'gpt-5.5' or context.get('model_provider') != 'dab_crs_gpt55'
                or Path(context.get('cwd', '')).resolve() != directory.resolve()
                or context.get('approval_policy') != 'on-request'
                or context.get('approvals_reviewer') != 'auto_review'
                or context.get('sandbox_policy', {}).get('type') != expected_sandbox
                or context.get('permission_profile', {}).get('network') != 'restricted'):
            raise RuntimeError('Actual model or bounded permission binding mismatch')
    if not prefix_counts or any(prefix_counts):
        raise RuntimeError('Unexpected native command grants; preserve for human audit')
    for event in events:
        item = event.get('item', {})
        counts[item.get('type', event.get('type'))] = counts.get(item.get('type', event.get('type')), 0) + 1
        output = str(item.get('aggregated_output', ''))
        if any(mark in output for mark in ('Automatic approval review failed', 'blocked by policy',
                                           'helper_unknown_error: setup refresh had errors')):
            raise RuntimeError('Native Meta reported security/setup failure; no admission or replay')
    return {'model': 'gpt-5.5', 'sandbox': expected_sandbox, 'network': 'restricted',
        'approval_policy': 'on-request', 'approvals_reviewer': 'auto_review',
        'session_sha256': sha(matches[0]), 'events_sha256': sha(stdout), 'event_counts': counts}


def assert_bindings(plan):
    for name, expected in plan['binding_sha256'].items():
        if sha(name) != expected:
            raise RuntimeError('Prepared run binding changed: ' + name)


def run_once():
    os.environ['DAB_RESEARCH_API_CONFIG'] = str(ROUTE)
    plan = protocol.read_json(RUN / 'plan.json')
    assert_released()
    assert_config()
    assert_bindings(plan)
    assert_stage('ready_for_intent')
    # Exclusive marker precedes any credential preflight/model dispatch.
    save_new(RUN / 'dispatch_intent.json', {'recorded_at': protocol.utc_now(),
        'plan_sha256': sha(RUN / 'plan.json'), 'automatic_retry': False,
        'authority': plan['authority'], 'model': 'gpt-5.5'})
    status = {'schema': 'gen008_gpt55_meta_terminal_v1', 'started_at': protocol.utc_now(),
              'model': 'gpt-5.5', 'stage': 'selector', 'formal_evaluation_started': False}
    try:
        campaign, _ = protocol.load_campaign(CAMPAIGN)
        campaign['meta_agent']['codex'] = str(CODEX)
        session = Path(plan['selector_session'])
        raw = protocol.invoke_codex_json(campaign=campaign, session=session,
            prompt=Path(plan['intent_prompt']).read_text(encoding='utf-8'),
            schema_path=session / 'output_schema.json', output_name='intent_response.json')
        status['selector'] = verify_native_session(session, session / 'codex.stdout', 'read-only')
        # Original schema/binding/stage/one-base guards, never a manual intent.
        intent = protocol.seal_intent(CAMPAIGN, raw, protocol.read_json(session / 'roadmap_snapshot.json'))
        status['intent_sha256'] = intent['canonical_json_sha256']
        status['mechanism_key'] = intent['mechanism_key']
        status['selected_parent_node_ids'] = intent['selected_parent_node_ids']
        assert_released()
        status['stage'] = 'implementation'
        args = argparse.Namespace(campaign_root=CAMPAIGN, workspace=None,
            mechanism_contract=None, prepare_only=True)
        protocol.invoke_candidate(args)
        output = GEN / 'candidate_workspace'
        task_path = output / 'implementation_task.md'
        task_path.write_text(task_path.read_text(encoding='utf-8') +
            '\n\nDo not invoke subagents. Stop on security denial or sandbox setup failure; '
            'do not retry, weaken permissions, request alternate tools or seek credentials.\n', encoding='utf-8')
        save_new(RUN / 'implementation_dispatch_intent.json', {'recorded_at': protocol.utc_now(),
            'intent_sha256': intent['canonical_json_sha256'], 'model': 'gpt-5.5',
            'task_sha256': sha(task_path), 'automatic_retry': False, 'max_repairs': 0})
        with (RUN / 'source_admission.stdout').open('x', encoding='utf-8') as admission_log:
            with contextlib.redirect_stdout(admission_log):
                code = workspace.generate(argparse.Namespace(workspace=output, codex=str(CODEX),
                    model='gpt-5.5', profile='crs-gpt55-dab', python=PYTHON, timeout=0, max_repairs=0))
        attempts = protocol.read_json(output / 'generation_status.json')['attempts']
        if code != 0 or len(attempts) != 1 or attempts[0]['exit_code'] != 0:
            raise RuntimeError('Independent implementation or original source preflight failed; no retry')
        status['implementation'] = verify_native_session(output / 'repo', output / 'generation_0.stdout', 'workspace-write')
        with (RUN / 'candidate_record.stdout').open('x', encoding='utf-8') as record_log:
            with contextlib.redirect_stdout(record_log):
                protocol.record_candidate(argparse.Namespace(campaign_root=CAMPAIGN, workspace=output))
        assert_stage('candidate_admitted')
        status.update({'stage': 'candidate_admitted', 'passed': True,
            'candidate_ref_sha256': sha(GEN / 'candidate_ref.json'),
            'evaluation_gate': 'PENDING independent compatibility and candidate-specific GPT runtime audits'})
    except (Exception, SystemExit) as exc:
        status.update({'passed': False, 'failure_type': type(exc).__name__,
                       'failure': str(exc)[:800], 'automatic_retry': False})
    status['finished_at'] = protocol.utc_now()
    save_new(RUN / 'terminal_report.json', status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status.get('passed') else 1


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--run-once', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return 0
    return run_once()


if __name__ == '__main__':
    raise SystemExit(main())
