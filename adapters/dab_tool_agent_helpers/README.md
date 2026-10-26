# DAB Tool-Agent Evolvable Helpers

This directory is the new helper-first/tool-first target for the DAB-style multi-turn DataAgent line.

The initial zero-start DataAgent must not preload task-specific helpers. Therefore `registry.py` starts with `HELPERS = []`. During evolution, the meta-agent may create new helper modules here and register them in `registry.py` when fine-grained workflow evidence shows repeated schema grounding, SQL, date parsing, CPC hierarchy, or data-processing failures.

A registered helper is exposed to the DataAgent as the `run_evolved_helper` tool by `experiments/run_dab_tool_agent.py`.

Helper contract:

```python
def helper_name(payload: dict, inputs: dict[str, object]) -> object:
    ...
```

- `payload` is JSON parsed from the LLM-provided `payload_json`.
- `inputs` contains selected prior tool outputs keyed by result-storage variable names such as `var_call_...`.
- return values must be JSON-serializable.

Candidate quality requirements:

- include the helper module;
- update `registry.py`;
- provide minimal policy/tool glue if needed so the DataAgent knows when to call `run_evolved_helper`;
- include child-observable contracts proving the helper was listed/called and affected the workflow;
- do not hardcode benchmark answers, expected counts, or query-specific output lists.
