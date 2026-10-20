# Research Decisions and Corrected Beliefs

Each entry separates the decision from its evidence and current status.

## D1. Use Research Graph as research memory, not a candidate leaderboard

- Decision: represent `Problem / Hypothesis / Experiment / Evidence` separately; candidate code is an Experiment artifact, not the Hypothesis itself. Separate research parents from the single code parent.
- Reason: earlier compact candidate summaries encouraged narrow repair loops and confused code lineage with research explanation.
- Evidence: session `S:20125`; implemented G0-G11 Graph files and `DAB_RESEARCH_GRAPH_BASELINE_WORKFLOW_V1.md`.
- Version: current local Research Graph line, not represented by a later Git commit than HEAD `9e0c752`.
- Status: **verified and active**.

## D2. Replace fixed ten-axis ontology with extensible evidence structure

- Decision: keep core causal fields and allow named facets rather than requiring ten fixed axes as Graph ontology.
- Reason: the ten axes were an audit checklist; forcing all of them recreated an overcompressed template.
- Evidence: session `S:20125`; corresponding route/workflow tests were reported passing historically.
- Status: **implemented historically; current Graph schema supersedes the original route implementation**.

## D3. Measure opportunity and reachability before implementing a repair

- Decision: when opportunity denominator, live interface reachability, or predicted observable is unknown, create a diagnostic/interface investigation instead of a production candidate.
- Evidence: Gen4-Gen11 repeatedly integrated mechanisms that did not activate; G11 had zero authored records/bindings. G12 explicitly passed through two interface investigations before `experiment_ready`.
- Code/artifacts: `research_graph_memory_v11.json`; G12 independent verifications.
- Status: **verified and active**.

## D4. Keep strict/56 as the new-line primary score

- Decision: score strict passes over all frozen 56 tasks; timeouts remain failures and missing verdicts remain unknown.
- Correction: the older campaign often reported strict/non-timeout-completed. That denominator is not comparable to the Research Graph baseline line.
- Evidence: G0 Evidence explicitly records `completed_and_strict_true_over_all_56;timeout_is_failure`; session `S:67525`.
- Status: **verified and active**.

## D5. Do not treat score differences as causal without matched design

- Decision: report unpaired generation differences descriptively. Mechanism status and score movement are separate endpoints.
- Evidence: all G0-G11 Evidence limitations; G10's repaired two-run view is explicitly supplementary; G6's 37/56 is not a causal gain claim.
- Status: **verified and active**.

## D6. Preserve failed, interrupted, superseded, and invalid runs

- Decision: never overwrite a failed candidate, incident, or interrupted attempt with a later revision. Store revisions and explain why they were rejected.
- Evidence: Gen8 candidate revisions, Gen15 repair branches, G3 DNS incident, G10 infrastructure incident/reconciliation, G11 preflight incident. Session `S:21197`, `S:52505`, `S:72800`, `S:83708`, `S:87981`.
- Status: **verified policy; artifacts present**.

## D7. Separate formal Evidence from incubation/interface research

- Decision: formal completed generations remain exactly four nodes; interface findings, blocked directions, and candidate feasibility live in an incubation layer. Promotion requires `experiment_ready` plus engineering admission.
- Evidence: `research_graph_memory_v11.json`; session `S:86667`, `S:88815`, `S:90137`.
- Status: **verified and active**.

## D8. Meta selects research direction; deterministic engineering owns admission

- Decision: Research Meta may select a target but does not authorize a run or certify source/interface feasibility. Implementation Meta writes the candidate; deterministic checks own hashes, tests, privacy, provider boundary, and launch claims.
- Corrected belief: `implementation_ready=true` from a Meta response was renamed/reframed because it had been mistaken for source feasibility and run readiness.
- Evidence: session `S:69401`; current workflow and G12 manifest.
- Status: **verified and active**.

## D9. Do not expose answers, hints, validator targets, held-out tasks, or raw answer-bearing logs to Meta

- Decision: Meta receives bounded, hash-bound, answer-blind research packets. Official hints were evaluated only as a separate historical ablation and must not contaminate no-hint Graph evidence.
- Evidence: workflow documents; G0-G11 evidence manifests; session `S:39795`, `S:40908`.
- Status: **verified policy**.

## D10. Provider or infrastructure failure is not a mechanism result

- Decision: classify DNS, provider 503, database-load, protocol, and disk failures separately. Do not merge them into a valid formal score or infer the hypothesis failed.
- Evidence: Gen15 503 interruption (`S:52505`), G3 DNS incident (`S:72800`), G10 PostgreSQL load incident and user-authorized reconciliation (`S:82626`, `S:83708`).
- Status: **verified and active**.

## D11. Mixed F1 was removed from Meta and promotion decisions

- Decision: do not use heterogeneous task F1 as an evolution signal in this line; preserve it only as historical evaluation data where applicable.
- Reason: mixed task types made the aggregate misleading.
- Evidence: historical session lines before `S:20125`; Baseline/Gen records in the older campaign.
- Status: **historical decision, still respected**.

## D12. The old “mechanism present in code” inference was overturned

- Rejected conclusion: a mechanism is active because code, counters, or a synthetic reachability test exists.
- Corrected conclusion: require live opportunity, binding/delivery, and target-effect observations. Zero observations may mean untested, not ineffective.
- Evidence: Gen2 replay=0; Gen8 repair=0; Gen9 checks almost never triggered; G11 authored record=0 and guidance binding=0. Session `S:21792`, `S:30590`, `S:88815`.
- Status: **overturned; replacement verified**.

## D13. “17 datasets” is not “official 17 domains”

- Correction: the half-56 campaign was constructed from 17 local dataset directories and 104 queries, selecting the first `ceil(n/2)` for 56 and holding out 48. This is not the same as an official 17-domain benchmark claim.
- Evidence: early session history summarized in `HISTORY_INDEX.md`; current campaign artifacts.
- Status: **corrected historical terminology**.
