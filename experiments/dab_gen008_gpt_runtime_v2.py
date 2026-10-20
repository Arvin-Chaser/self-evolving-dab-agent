"""Gen8 streaming transport only; all audited isolation/state machinery retained."""
from experiments import dab_gen008_gpt_runtime_v1 as prior
from adapters.crs_responses_client_v2 import install_client

POLICY = 'gen008_gpt55_native_sse_medium_isolated_lossless_once_v2'

def install(module, args):
    prior.install_client = install_client
    prior.POLICY = POLICY
    prior.install(module, args)
