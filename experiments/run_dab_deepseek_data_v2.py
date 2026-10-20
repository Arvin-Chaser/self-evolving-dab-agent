"""Future Data entry: explicit official DeepSeek, no historical run resume.

This is not a remote campaign launcher or candidate admission bypass. Frozen
campaign runs still require a fresh candidate-specific audited runtime.
"""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments import dab_api_routing as routing
from experiments.run_dab_tool_agent import build_parser,run_agent

def parser():
    from experiments.dab_meta_standalone_runtime_v1 import ROUTE
    os.environ['DAB_RESEARCH_API_CONFIG']=str(ROUTE)
    route=routing.active_route()
    if not route or route['provider']!='deepseek_official' or not route.get('meta_runtime_binding'):
        raise RuntimeError('Dedicated shared DeepSeek route required')
    p=build_parser()
    p.set_defaults(deployment_name=route['model'],openai_compatible_base_url=route['base_url'],
        openai_compatible_api_key_env=route['api_key_env'],bailian_api_key_env=None,bailian_base_url=None,
        max_iterations=0,llm_retries=0,client_max_retries=0,llm_retry_sleep=0)
    return p

def main():
    args=parser().parse_args()
    r=routing.active_route()
    if (args.deployment_name!=r['model'] or args.openai_compatible_base_url!=r['base_url']
            or args.openai_compatible_api_key_env!=r['api_key_env'] or args.bailian_api_key_env
            or args.bailian_base_url):
        raise RuntimeError('This entry only permits the bound official DeepSeek API')
    if args.llm_retries or args.client_max_retries:
        raise RuntimeError('Automatic model request retries are disabled')
    return run_agent(args)
if __name__=='__main__':raise SystemExit(main())
