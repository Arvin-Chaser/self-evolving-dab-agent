"""Explicit research-only provider routing, never rewrite historical bindings."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTE = ROOT / 'configs/dab_active_api_route.json'

def active_route():
    path = Path(os.environ.get('DAB_RESEARCH_API_CONFIG') or DEFAULT_ROUTE)
    if not path.is_file():
        return None
    route = json.loads(path.read_text(encoding='utf-8'))
    if route.get('enabled') is not True:
        return None
    if route.get('schema') == 'dab_crs_gpt55_route_v1':
        expected = {
            'provider': 'crs_gpt55', 'base_url': 'https://crs.uuid.im/openai',
            'model': 'gpt-5.5', 'api_key_env': 'CRS_API_KEY',
            'api_key_file': 'C:/Users/34934/.config/dab/crs_api_key.txt',
            'meta_profile': 'crs-gpt55-dab',
            'meta_codex_home': 'configs/crs_gpt55_meta_runtime_v1',
            'meta_bridge_config': 'configs/codex_crs_gpt55_meta_bridge_v1.json',
            'wire_api': 'responses',
        }
        if any(route.get(key) != value for key, value in expected.items()):
            raise RuntimeError('Unapproved CRS model/endpoint/key/profile binding; no credential forwarding')
        return route
    if route.get('schema') != 'dab_research_api_route_v1':
        raise RuntimeError('Unknown research API routing schema')
    if route.get('provider') != 'deepseek_official' or route.get('base_url') != 'https://api.deepseek.com/v1':
        raise RuntimeError('Unapproved research API route; no credential forwarding')
    if route.get('model') != 'deepseek-flash' or route.get('api_key_env') != 'DEEPSEEK_API_KEY':
        raise RuntimeError('Research model/key binding mismatch')
    if route.get('meta_runtime_binding'):
        validate_standalone_route(route)
    return route

def validate_standalone_route(route):
    from experiments import dab_meta_standalone_runtime_v1 as runtime
    expected = {'meta_runtime_binding':'configs/deepseek_meta_standalone_v2/runtime_binding.json',
                'meta_profile':runtime.PROFILE,'meta_codex_home':'configs/deepseek_meta_standalone_v2',
                'meta_bridge_config':'configs/codex_deepseek_meta_standalone_v2.json',
                'api_key_file':'C:/Users/34934/.config/dab/deepseek_api_key.txt'}
    if any(route.get(k)!=v for k,v in expected.items()):
        raise RuntimeError('Unbound independent Meta route; no credential read or desktop fallback')
    return runtime.validate()

def read_explicit_key(route):
    value = Path(route['api_key_file']).read_text(encoding='utf-8-sig').strip()
    if not value or any(c.isspace() for c in value):
        raise RuntimeError('Invalid single-line research API credential')
    if route.get('provider') == 'crs_gpt55' and (not value.startswith('cr_') or len(value) > 4096):
        raise RuntimeError('Invalid CRS credential format; value not displayed')
    return value

def meta_route(original):
    route = active_route()
    if route is None:
        return dict(original)
    value = {**original, 'model':route['model'], 'profile':route['meta_profile'],
            'wall_clock_timeout_seconds':None, 'active_api_route':route.get('provider', 'deepseek_official')}
    if route.get('meta_runtime_binding'):
        value['codex'] = validate_standalone_route(route)['tools']['codex']['path']
    return value

def routed_meta_environment(profile):
    route = active_route()
    if not route or profile != route['meta_profile']:
        return None
    if route.get('meta_runtime_binding'):
        validate_standalone_route(route)
        from experiments.dab_meta_standalone_runtime_v1 import meta_environment
        return meta_environment(profile)
    env = os.environ.copy()
    env['CODEX_HOME'] = str((ROOT / route['meta_codex_home']).resolve())
    env[route['api_key_env']] = read_explicit_key(route)
    env['CODEX_NATIVE_META_BRIDGE_CONFIG'] = str(ROOT / route['meta_bridge_config'])
    env.pop('PYTHONPATH', None)
    return env

def dab_default(name, fallback=None):
    route = active_route()
    return route.get(name, fallback) if route else fallback
