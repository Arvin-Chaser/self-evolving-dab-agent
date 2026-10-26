# G13 Intent-First Data Agent

This exploratory agent tests the problem-solving intent behind G13 without the
formal G13 carrier, sidecar, native-reasoning binding, coverage-record schema,
or admission-oriented persistence machinery.

Its task-time loop is:

1. decompose the user request into concrete answer requirements;
2. inspect the real schemas and data needed by those requirements;
3. treat each tool result as covered, partial, conflicting, or unknown evidence;
4. let the highest-impact unresolved requirement choose the next tool action;
5. verify joins, filters, aggregation grain, ordering, ties, units, and output
   shape before returning the answer.

The checklist is ordinary model reasoning, not a new tool protocol. The launcher
disables both `record_self_observation` and evolved helper tools so the first
comparison measures the policy intent on the existing database/Python action
space.

Entry point:

```powershell
python -m experiments.run_dab_tool_agent_g013_intent_first <normal run arguments>
```

No benchmark or provider run is authorized by this file. Any evaluation must
use a fresh run ID and an explicitly chosen protocol. Results are exploratory
and must not mutate or reinterpret the immutable formal G13 Graph or Evidence.

## Cost-bounded paired protocol

The frozen exploratory panel is
`dab_corpus/batches/g013_intent_first_smoke_v1_20261021.json`. It contains four
queries from the existing odd-query split and is ordered by historical baseline
LLM-call count. Correctness was not used to choose or order the tasks.

Stage 1 is one paired query (`crmarenapro/query1`) using `--max-queries 1`, the
same model route, base/no-hint description, 20-turn cap, one worker, no observer,
no evolved helpers, and no self-observation tool. Both arms use the current
runner; only `--tool-agent-policy` differs:

- baseline: `prompts/dab/dab_tool_agent_policy_zero_start.txt`;
- intent-first: `prompts/dab/dab_tool_agent_policy_g013_intent_first.txt`.

The hard ceiling is 40 model turns across the pair. The historical baseline used
11 calls on this task, but token usage was not recorded, so a defensible token
estimate is unknown. Use zero SDK retries and one application attempt when the
real run is authorized. Stop after Stage 1 and compare strict result, termination,
tool trajectory, call count, and whether unresolved requirements actually drove
the next evidence action. Do not expand to the remaining three tasks unless the
pair is operationally valid and informative.

`experiments/run_multi_query_baseline.py` accepts the policy and tool-disable
flags directly and records the policy path/hash and both disable flags in the
execution context. This keeps the comparison inside one evaluator rather than
maintaining two divergent source trees.
