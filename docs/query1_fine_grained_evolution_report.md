# Query1 evolution report: fine-grained feedback to near-miss repair

## 1. One-sentence summary

PATENTS query1 evolved from a zero-start/basic DAB tool-agent into a strict-pass agent through four archived meta-agent candidate repairs. The important story is not only that query1 passed, but that fine-grained feedback changed the repair target over time: from “no usable answer” to “build a reusable local helper”, then to “reduce extra candidates”, then to “near-miss boundary refinement”.

Final archived query1 parent:

```text
data_agent_shadow_codex_native_near_miss_refine_iter001_20260715_090844
```

Final result:

```text
PATENTS query1 strict_match_passed = true
precision = 1.0
recall = 1.0
F1 = 1.0
```

Main reference files:

- Query1 workspace: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1`
- Patch chain metadata: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patch_chain.json`
- Query1 reproduction policy: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/agent/policy.txt`
- Query1 current parent state: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/state/current_parent.json`

## 2. Basic agent to passed agent: how many evolutions?

The query1 reproduction lineage records four candidate patches:

```text
base_agent_id  = dab_tool_agent_zero_start_current
final_agent_id = data_agent_shadow_codex_native_near_miss_refine_iter001_20260715_090844
number of candidate evolutions = 4
```

Reference:

- `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patch_chain.json`

The four candidate stages are:

| Stage | Candidate | Patch file | Parent F1 → Child F1 | Outcome |
|---|---|---|---:|---|
| 1 | `codex_native_iter10_script_first_iter001_20260715_074941` | `001_script_first.patch` | `0.0 → 0.5818` | First measurable answer |
| 2 | `codex_native_iter10_two_step_selfobs_iter001_20260715_081931` | `002_two_step_selfobs.patch` | `0.5818 → 0.9412` | Large precision/recall improvement |
| 3 | `codex_native_iter10_two_step_selfobs_iter002_20260715_082928` | `003_two_step_selfobs_refine.patch` | `0.9412 → 0.9505` | Small boundary improvement |
| 4 | `codex_native_near_miss_refine_iter001_20260715_090844` | `004_near_miss_refine.patch` | `0.9505 → 1.0` | Strict pass |

## 3. Stage 0: basic agent

Initial parent:

```text
dab_tool_agent_zero_start_current
```

The basic agent had a multi-turn DAB tool workflow, but did not yet contain the query1-specific reusable computation needed for PATENTS CPC EMA reasoning.

Observed baseline in the first candidate evaluation:

```text
F1 = 0.0
predicted_count = 0
expected_count = 50
missing_count = 50
```

Interpretation:

- The DataAgent did not produce a usable final answer.
- The useful repair was not merely to rewrite the final answer prompt.
- The system needed a reusable local computation path for CPC hierarchy parsing, filing-year aggregation, and EMA ranking.

## 4. Stage 1: script-first helper creation

Candidate:

```text
codex_native_iter10_script_first_iter001_20260715_074941
```

Reference files:

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/001_script_first.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_script_first_iter001_20260715_074941`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_script_first_iter001_20260715_074941/child_eval/child_eval_report.json`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_script_first_iter001_20260715_074941/candidate_state.json`

Changed files:

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

Metrics:

```text
parent F1 = 0.0
child F1 = 0.5818
precision = 0.5333
recall = 0.64
missing_count = 18
extra_count = 28
predicted_count = 60
expected_count = 50
```

What the meta-agent added:

The meta-agent added a reusable local helper:

```python
cpc_level_ema_best_year
```

and supporting functions:

```python
_helper_path
_patents_data_paths
_cpc_copy_columns
_load_cpc_level_symbols
_filing_year
_cpc_level_group
_ema_best_year
```

This helper:

1. reads the PATENTS publication database;
2. reads the CPC definition SQL dump;
3. parses CPC hierarchy symbols at the requested level;
4. extracts filing years;
5. computes yearly counts;
6. applies EMA;
7. returns CPC codes whose EMA peaks in the target year.

Fine-grained feedback role:

The feedback signal had moved beyond a vague “answer failed”. The parent had no usable answer, so the repair direction became: create a local, reusable computation helper instead of relying on the LLM to repeatedly improvise SQL/Python logic.

This is the first concrete example where fine-grained feedback pushed the meta-agent toward script-level evolution rather than prompt-only repair.

## 5. Stage 2: primary CPC filtering and self-observation-driven refinement

Candidate:

```text
codex_native_iter10_two_step_selfobs_iter001_20260715_081931
```

Reference files:

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/002_two_step_selfobs.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/child_eval/child_eval_report.json`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter001_20260715_081931/candidate_state.json`

Changed files:

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

Metrics:

```text
parent F1 = 0.5818
child F1 = 0.9412
precision = 0.9231
recall = 0.96
missing_count = 2
extra_count = 4
predicted_count = 52
expected_count = 50
```

What changed in the helper:

The meta-agent added boolean payload parsing:

```python
_payload_bool
```

and extended the helper with:

```python
primary_only
inventive_only
unique_per_publication
```

Key logic:

```python
if primary_only and item.get("first") is not True:
    continue
if inventive_only and item.get("inventive") is not True:
    continue
```

Fine-grained feedback role:

This stage should not be read as ?extra codes were high, so the agent randomly narrowed candidates.? The important point is that fine-grained feedback turned a validation failure into an actionable causal chain.

The answer-quality signal after Stage 1 was:

```text
predicted_count = 60
expected_count = 50
extra_count = 28
precision = 0.5333
recall = 0.64
```

This indicated that the agent could recover many true positives, but its candidate set was too broad and precision was being pulled down by extra codes.

The trace/helper-level evidence then made the failure actionable: the helper was reading `publicationinfo.cpc` and counting all CPC assignments from each publication without distinguishing primary, secondary, or inventive assignments. Therefore the concrete diagnosis was not merely ?the answer has too many codes?, but:

```text
CPC assignment selection policy is too broad.
```

The script-level repair followed directly:

```python
primary_only = _payload_bool(payload, "primary_only", True)
inventive_only = _payload_bool(payload, "inventive_only", False)

if primary_only and item.get("first") is not True:
    continue
if inventive_only and item.get("inventive") is not True:
    continue
```

The policy also guided the DataAgent to call the helper with:

```json
{"primary_only": true}
```

Causal chain:

```text
high recall + low precision + high extra_count
? candidate set is too broad
? trace shows helper counts all CPC assignments
? CPC records expose primary / secondary / inventive distinctions
? change helper selection policy
? F1 improves from 0.5818 to 0.9412
```

This is the key decision role of fine-grained feedback: F1 alone says whether the result is good; trace and helper diagnostics explain which script-level decision should change.

## 6. Stage 3: sparse false-positive filtering

Candidate:

```text
codex_native_iter10_two_step_selfobs_iter002_20260715_082928
```

Reference files:

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/003_two_step_selfobs_refine.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter002_20260715_082928`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter002_20260715_082928/child_eval/child_eval_report.json`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_iter10_two_step_selfobs_iter002_20260715_082928/candidate_state.json`

Changed files:

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

Metrics:

```text
parent F1 = 0.9412
child F1 = 0.9505
precision = 0.9412
recall = 0.96
missing_count = 2
extra_count = 3
predicted_count = 51
expected_count = 50
```

What changed:

The meta-agent added:

```python
min_target_year_count
```

and filtered out low-support target-year peaks:

```python
target_count = yearly_counts.get(target_year, 0)
if best_year == target_year and target_count >= min_target_year_count:
    scores.append(...)
```

Fine-grained feedback role:

After Stage 2, the feedback shape had changed:

```text
F1 = 0.9412
precision = 0.9231
recall = 0.96
missing_count = 2
extra_count = 4
```

The helper was mostly correct. The remaining error was no longer a broad candidate-generation failure, but a small boundary problem.

The meta-agent formed a local hypothesis: remaining extra codes may be sparse target-year peaks with low support. It encoded this as a verifiable helper parameter, `min_target_year_count`, and checked whether filtering sparse peaks improves the child.

Result:

```text
F1: 0.9412 ? 0.9505
extra_count: 4 ? 3
missing_count: 2 ? 2
```

This stage matters because it shows hypothesis-test-refine behavior. The threshold hypothesis slightly improved precision but did not solve the query, leaving evidence for the next near-miss repair to revise that assumption.

Causal chain:

```text
high-F1 + few extras
? hypothesize sparse peaks are false positives
? add min_target_year_count
? small improvement, still not strict pass
? Stage 4 revisits the threshold assumption
```

## 7. Stage 4: near-miss refinement and strict pass

Candidate:

```text
codex_native_near_miss_refine_iter001_20260715_090844
```

Reference files:

- Patch: `/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/lineage/patches/004_near_miss_refine.patch`
- Candidate dir: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844`
- Child eval: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/child_eval/child_eval_report.json`
- Candidate state: `/home/m0st1ma/research/text2sql/candidates/dab/codex_native_near_miss_refine_iter001_20260715_090844/candidate_state.json`

Changed files:

```text
experiments/run_dab_tool_agent.py
prompts/dab/dab_tool_agent_policy_zero_start.txt
```

Metrics:

```text
parent F1 = 0.9505
child F1 = 1.0
precision = 1.0
recall = 1.0
missing_count = 0
extra_count = 0
predicted_count = 50
expected_count = 50
strict_match_passed = true
```

What changed:

First, EMA year iteration changed from continuous years to observed years only:

```python
# before
for year in range(min(counts), max(counts) + 1):
    ema = alpha * counts.get(year, 0) + (1.0 - alpha) * ema

# after
for year in sorted(counts):
    ema = alpha * counts[year] + (1.0 - alpha) * ema
```

Second, the earlier arbitrary support threshold was relaxed:

```python
min_target_year_count = 1
```

The policy was also revised:

```text
Do not add an arbitrary minimum target-year filing threshold unless the user asks for one;
sparse CPC groups can still have a valid observed-year EMA peak.
```

Fine-grained feedback role:

This is the clearest near-miss example. Before this patch:

```text
F1 = 0.9505
precision = 0.9412
recall = 0.96
missing_count = 2
extra_count = 3
```

The system was no longer in a broad failure regime. The remaining issue was a small boundary error. More importantly, Stage 3 had shown that a stricter threshold only slightly helped and did not remove the missing codes. That gave the meta-agent a reason to revise, rather than merely strengthen, the previous hypothesis.

The near-miss diagnosis narrowed the repair to two local mathematical assumptions:

```text
1. Should EMA decay across continuous years, including years with no filings?
2. Should sparse target-year peaks be removed by an arbitrary threshold?
```

The meta-agent then made two small helper changes instead of rewriting the pipeline:

```text
continuous-year EMA ? observed-year EMA
min_target_year_count = 3 ? min_target_year_count = 1
```

Result:

```text
F1: 0.9505 ? 1.0
missing_count: 2 ? 0
extra_count: 3 ? 0
strict_match_passed = true
```

Causal chain:

```text
high-F1 near miss
+ very few missing/extra codes
+ previous threshold repair was insufficient
? suspect local mathematical assumption
? observed-year EMA + remove arbitrary threshold
? strict pass
```

This is the central evidence that fine-grained feedback can drive near-miss boundary repair, not just broad prompt or parser changes.

## 8. What scripts or mechanisms were added during query1 evolution?

Strictly speaking, the historical query1 chain did not create a separate new query-local `.py` helper file. Instead, it added an evolved helper directly into the DAB tool-agent runner:

```text
/home/m0st1ma/research/text2sql/experiments/run_dab_tool_agent.py
```

Main evolved helper:

```python
cpc_level_ema_best_year
```

Supporting helper functions:

```python
_helper_path
_patents_data_paths
_cpc_copy_columns
_load_cpc_level_symbols
_filing_year
_cpc_level_group
_ema_best_year
_payload_bool
```

Policy guidance was added to:

```text
/home/m0st1ma/research/text2sql/prompts/dab/dab_tool_agent_policy_zero_start.txt
```

The query1 reproduction workspace now preserves the final policy here:

```text
/home/m0st1ma/research/text2sql/query_workspaces/PATENTS/query1/agent/policy.txt
```

Important architecture note:

```text
Query1 is a historical reproduction workspace.
At that time, the evolved helper was embedded in the global runner.
Later, query2 moved toward query-local helpers under agent/helpers/registry.py.
```

This is useful for the presentation: query1 shows that fine-grained feedback can produce useful helper logic; query2 shows the newer architecture for isolating such helper evolution per query.

## 9. How fine-grained feedback shaped the evolution

The query1 evolution can be summarized as a sequence of increasingly precise feedback regimes.

### 9.1 From no-answer to helper creation

Observed:

```text
F1 = 0.0
predicted_count = 0
missing_count = 50
```

Meta-agent response:

```text
Create cpc_level_ema_best_year helper.
```

Why it matters:

The repair became a script/tool repair, not a pure prompt rewrite.

### 9.2 From noisy answer to primary CPC filtering

Observed after Stage 1:

```text
F1 = 0.5818
precision = 0.5333
recall = 0.64
extra_count = 28
```

Meta-agent response:

```text
Add primary_only / inventive_only / unique_per_publication controls.
```

Why it matters:

The feedback identified that the candidate set was too broad.

### 9.3 From high-F1 but still extra-heavy to sparse filtering

Observed after Stage 2:

```text
F1 = 0.9412
missing_count = 2
extra_count = 4
```

Meta-agent response:

```text
Add min_target_year_count to filter sparse false positives.
```

Why it matters:

The repair became a boundary/ranking adjustment rather than a broad algorithm rewrite.

### 9.4 From near-miss to mathematical correction

Observed after Stage 3:

```text
F1 = 0.9505
missing_count = 2
extra_count = 3
```

Meta-agent response:

```text
Use observed years for EMA.
Remove arbitrary minimum target-year threshold.
```

Why it matters:

The near-miss feedback made the meta-agent revisit a small mathematical assumption in the helper. That was enough to reach strict pass.

## 10. How this leads into query2

Query1 is the positive example:

```text
fine-grained feedback → helper/script evolution → near-miss repair → strict pass
```

Query2 is now the stress test for whether the same mechanism generalizes.

Current query2 best parent:

```text
F1 = 0.9545
precision = 1.0
recall = 0.913
missing = [A21, H03]
extra = []
```

Query2 has already reached a near-miss regime, but recent near-miss repair exposed a limitation:

```text
parent: F1 = 0.9545, missing = [A21, H03]
child:  F1 = 0.9048, missing = [A21, B62, H02, H03]
```

The meta-agent tried to fix the missing boundary codes, but accidentally broke codes that were previously correct.

This motivates the next research step:

```text
Near-miss repair should not only target missing/extra codes.
It should also preserve the current correct set.
```

In other words:

```text
query1 demonstrates why fine-grained feedback helps;
query2 shows what near-miss repair still lacks.
```

## 11. Suggested presentation framing

A concise way to present the story:

> In query1, the feedback signal evolved from “the answer is wrong” into structured information about F1, precision, recall, missing codes, extra codes, and helper/tool behavior. That made the meta-agent change the DataAgent at the script level: first adding a CPC EMA helper, then adding primary-CPC filtering, then refining sparse false positives, and finally fixing a near-miss EMA boundary issue. Query1 passed after four candidate evolutions. Query2 now reaches the same near-miss regime, but shows the next challenge: repairing the missing boundary codes without damaging already-correct outputs.
