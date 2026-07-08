"""Registry for meta-agent-created DAB tool-agent helpers.

Helpers listed here are exposed to the upstream DAB DataAgent through the
run_evolved_helper tool installed by experiments/run_dab_tool_agent.py.

Each entry must use this schema:

{
    "name": "stable_helper_name",
    "function": "module.path:function_name",
    "description": "Short tool-facing description.",
    "input_contract": "Expected payload/input schema.",
}

The function must accept (payload: dict, inputs: dict[str, object]) and return
a JSON-serializable object. Do not hardcode benchmark answers, expected counts,
or query-specific output lists.
"""

HELPERS: list[dict[str, str]] = []
