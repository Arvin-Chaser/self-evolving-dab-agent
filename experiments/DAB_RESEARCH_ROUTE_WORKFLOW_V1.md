# Evidence-conditioned research route workflow

This opt-in research entry extends the DAB harness evolution workflow. The old
candidate roadmap remains immutable. The new memory is an evidence-bound view
plus an append-only update event log; it does not resume a paused campaign.

## Operational loop

The research route is a second graph projected from the immutable candidate
roadmap. Its unit of reasoning is a question and hypothesis, while candidate
source remains an experiment artifact. Each completed roadmap generation imports
four linked nodes: a reported problem, the hypothesis embodied by its intent, the
candidate experiment, and its measured evidence. Later reviews may change the
scoped state of a hypothesis but cannot rewrite an imported observation.

New questions enter the route through five explicit origins: unexplained failure,
contradicted prediction, missing opportunity measurement, a competing explanation,
or residual failure after an intervention. The deterministic research agenda
surfaces these gaps from evidence limits and reviewed hypotheses. A new problem,
hypothesis, or experiment must cite existing evidence, declare its origin, and
attach through a type-valid relation.

The planner proposes two or three competing questions and assesses every one on
impact, evidence strength, discriminating power, cost, novelty, and readiness.
Selection follows one recorded lexicographic policy: exclude blocked options,
then prefer impact, discrimination, evidence strength, lower cost, and novelty.
This avoids an opaque preference score while keeping the choice reproducible.
Each lower-ranked option remains in the snapshot as an unresolved route.

An implementation choice needs a positive opportunity count and coverage
denominator read through exact JSON pointers from a cited evidence node. Unknown
or zero opportunity routes to diagnosis/probe. A probe can be imported without
pretending to be a candidate generation: only finite scalar measurements from
hash-bound files inside the campaign are accepted, and the importer creates the
experiment/evidence nodes. The reviewer then updates hypothesis states and the
agenda is regenerated.

Research ancestry and code ancestry remain separate. Research parents explain
why the experiment is useful; one verified source tree supplies code. Only an
`implement` plan can cross the source-bound handoff into the existing candidate,
admission, frozen evaluation, review, and roadmap append pipeline.

Reviewed research state carries into the next roadmap boundary with immutable
content checks. New generations are imported while prior assessments, open
questions, and independently imported probes remain. Every update/probe event
binds the previous and resulting snapshot hashes in an append-only event chain.

## Research entities and update rules

- Problems record observed phenomena and coverage. Historical intent limitations
  are imported as reported interpretations, not independently established causes.
- Hypotheses hold a testable mechanism explanation, predictions, scope, competing
  explanations and falsification conditions. An experiment can test several
  hypotheses; a hypothesis can be tested by several experiments.
- Experiments bind the diagnostic/probe/code intervention and its execution
  regime. A candidate is an experiment artifact, not a research-memory identity.
- Evidence retains measurements, representative evolution-query rows, limits,
  reviewer interpretation, source hashes and JSON pointers. Full raw traces are
  not yet available through this initial importer. Answers and the held-out split
  are not projected; the retired partial-overlap metric is excluded.

Review uses a fixed causal chain rather than a fixed diagnostic checklist:
opportunity (the target condition occurs), reachability (the mechanism can
intercept it), behavior (execution changes), target failure (the intended failure
changes), and task effect (the outcome improves). Confounding is the one required
validity judgment. Beyond that skeleton, the reviewer may add any evidence-backed,
open-named diagnostic facets needed by the experiment, such as timing, cost,
regressions, state consistency, tool semantics, or cross-turn credit assignment.
Facet names are not an ontology and are not pre-enumerated; absent facets mean
"not diagnostically material here," not "unchecked." Duplicate facet names are
rejected. Every causal link, validity judgment, facet and relation cites existing
evidence IDs. A decision may
also cite problem, hypothesis or experiment IDs as research context, but those
references cannot stand in for a measured observation. Unknown telemetry stays
unknown; an inactive implementation alone does not refute all versions of an
idea. States are unassessed/open/supported-in-scope/challenged-in-scope/mixed/
inconclusive/retired. Updates append prior and resulting snapshot bindings;
historical evidence is never rewritten. New problem/hypothesis nodes require
evidence references. Review cannot invent measured-evidence nodes.

Unknown, challenged, or mixed causal links are promoted back into the research
agenda as missing measurements, contradicted predictions, or competing
explanations. Open facets in those states can also create agenda questions. This
keeps the causal skeleton comparable across experiments without constraining the
diagnostic vocabulary available to Meta.

## Research choice and implementation ancestry

The planner compares 2-3 explanations/questions with opportunity, coverage,
task value, discriminating observations and falsification conditions. It may
choose diagnose, probe, implement or stop. These are documented judgments, not
invented numeric utility scores. The ranking fields use ordered categories and a
fixed policy. Implementation requires an explicitly measured positive opportunity
and a hash-verified frozen code base.

Research parents cite hypotheses, mechanism donors or counterevidence. Code
ancestry separately selects at most one available, compatible source. The live
handoff builds the existing source-bound interface card and intent schema;
the existing source admission, runtime admission and frozen benchmark workflow
still own implementation and evaluation. A stale research boundary, changed
source, or probe decision cannot be handed off as an implementation intent.

## Entry points

Run from the repository root with `python -m experiments.run_dab_research_workflow`:

1. `prepare --campaign-root CAMPAIGN --through-generation N --output NEW_DIR`
   creates an immutable research snapshot, retrieval IDs, decision/review schemas
   and compact/flat/route contexts. Pass `--previous-snapshot SNAPSHOT` to carry
   reviewed states and probe evidence into a later roadmap boundary. It does not
   call a model.
2. `retrieve --snapshot SNAPSHOT --ids ID ...` returns selected bound nodes and
   nearby relations, without opening unrelated archive paths.
3. Have an independent reviewer produce the supplied update schema; then
   `apply-review --snapshot SNAPSHOT --update UPDATE --events EVENT_LOG
   --output NEW_SNAPSHOT` validates and appends the state update.
   `prepare` writes one- or two-hypothesis briefs in `review_batches/`: each has
   the local problem/experiment/evidence neighbourhood and the signed full
   snapshot hash. The reviewer must assess every and only the listed hypothesis
   IDs. This keeps review evidence-rich without asking one request to reason over
   the whole historical graph at once.
   Use `--review-hypothesis-ids ID ...` when continuing from an updated snapshot
   and auditing a specific unresolved branch; the fresh brief will bind that
   snapshot rather than reusing an earlier review request.
4. Have the planner answer `navigation_prompt.txt`, then `validate-navigation
   --snapshot SNAPSHOT --response RESPONSE` checks all option ranks, citations,
   exact opportunity measurements, research ancestry and code ancestry.
5. A diagnosis/probe writes its aggregate scalar counters to a campaign artifact.
   `import-probe --campaign-root CAMPAIGN --snapshot SNAPSHOT --record RECORD
   --events EVENT_LOG --output NEW_SNAPSHOT` verifies file hashes and JSON
   pointers, then appends experiment/evidence nodes without a candidate launch.
6. For an authorized live implementation decision, `prepare-handoff
   --campaign-root CAMPAIGN --snapshot SNAPSHOT --plan RESPONSE
   --output NEW_DIR` prepares the original source-bound intent completion.
   `seal-handoff --campaign-root CAMPAIGN --session NEW_DIR --response INTENT`
   is an explicit production write, never part of a historical replay.

The separate Meta CLI runtime must pass its original health/binding checks before
running a live tool-enabled Meta stage. A successful direct API replay does not
certify that runtime or relax its checks. The existing automation remains paused.

## Initial offline pilot

`python -m experiments.replay_dab_research_route --campaign-root CAMPAIGN
--output NEW_DIR --targets 2 7 8 --prepare-only` fixes three boundaries:
only generations <=1, <=6 and <=7 respectively. All predictions are prepared
before any later outcomes are revealed. `--run-once` dispatches one no-tool
native official DeepSeek chat request per arm and boundary. `--reveal` requires
every prediction to have a receipt. Requests/responses/usage/hashes are retained,
with no automatic transport retry or response repair.

Compact is the reconstructed old compact-card view under the new decision
schema, not a replication of the old forced-change prompt. Flat and route expose
identical retrieved evidence-node contents; route additionally provides typed
relations and relation-navigation instructions. The retrieval policy selects the
active research agenda, the most recent four completed generations, and their
one-hop research/code lineage.
It is deterministic, recorded with every request, and keeps the signed full
snapshot available for audit. All arms have the same input character ceiling and
output-token cap, but actual token usage differs and is reported.
One response per condition cannot support a significance or superiority claim.
This first pilot tests the evidence import and decision contract, not adaptive
retrieval efficiency, refreshed graph judgments or hypothetical candidate scores.
Follow-up pilots should use repeated seeds, blinded quality adjudication,
controlled retrieval budgets and prospective independent evolution runs.

Pilot `half56_route_pilot_20261012_r5` exercised the revised contract at the
three cutoffs. Eight of nine decisions were contract-valid and all nine chose a
diagnostic/probe rather than direct implementation. Route used matched-control
language in all three responses, but passed the contract in only two; compact and
flat passed all three. One sample per cell does not establish representation
superiority. See the replay directory's `OFFLINE_REPLAY_REPORT.md` and
`audit.json` for the frozen receipts and descriptive comparison.

Historical views are reconstructed from immutable archived records at generation
boundaries. Created/recorded/reviewed times are checked where available; later
reviews are omitted. This is not a bit-exact reconstruction of historic prompts.
The method and boundary selection were designed after inspecting failures, so
retrospective bias must be disclosed. Gen8 is absent from the candidate roadmap;
its deleted intent/source are not reconstructed. Its separate preserved recovery
report may be read after predictions, without merging recovery into frozen scores.

## Proposed contribution and evidence needed

The research claim is that maintaining scoped, revisable hypotheses and
counterevidence improves the choice of the next harness experiment. Rich trace
access, failure diagnosis, activation screening and source archives are existing
components, not claimed novelties. Measure unsupported-premise proposals,
repeated failed premises, effective activation, evaluations-to-useful-candidate,
meta cost, benchmark outcome and held-out transfer. Failed experiments may add
knowledge; they are not automatically eligible code parents. Old eight-generation
results motivate the method but do not prove compact graphs universally fail.
