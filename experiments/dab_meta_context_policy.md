# DAB meta-agent default context

Default policy: `compact_result_graph_v1`, effective for calls after 2026-10-05.
Historical prompts/artifacts keep their original policy. The opt-in extension
below applies only to future contexts for a human-authorized campaign.

The evolution selector and reviewer receive two default inputs: a compact
generation result and brief graph cards. Results expose batch-level metrics,
bounded aggregate diagnostics, and minimal intent/candidate identity bindings.
They do not expose per-query rows, query identifiers, observations, traces,
full source patches, or detailed historical reviews. Brief graph cards retain
ancestry, mechanism, aggregate result, outcome, and short review. Archival detail
links remain provenance references, not instructions to expand history.

The coding meta-agent still needs the sealed implementation intent and exactly
one materialized source base. Its selected-parent pack contains compact cards
and aggregate results only; historical patches/reviews/results are not expanded.

Raw summaries, traces, complete reviews, and patches remain archived for human
audit. Existing graph nodes, sealed intents, results, and candidates are not
rewritten. Legacy results containing rows are filtered through an explicit
allowlist before inclusion in a new prompt. Future result.json files omit rows.

Missing activation evidence means unknown, not zero activations or failed
integration. Review must not infer causal effectiveness from aggregate metrics
alone; the existing `inconclusive` label remains available.

These are input-projection and prompt constraints, not an operating-system
access-control boundary. They do not change the coding agent's workspace powers.

## Human-authorized on-demand detail extension (2026-10-08)

Policy: `compact_result_graph_safe_details_v2`, enabled only when that campaign
has `meta_detail_policy_v1.json` with explicit human authority. Other campaigns
retain the default. Read the compact graph first; for a relevant inconclusive
or unknown node, unclear novelty, or parent comparison, the selector/reviewer
may read the indexed safe mechanism summary. The implementation agent gets
only its selected parents' safe-detail index. Start with relevant nodes, not
all history, and cite the node and evidence gap motivating the read.

Safe summaries preserve more of the sealed mechanism, proposed control-flow
changes, validation expectations, bounding rules, and historical review's
activation/behavior/task reasoning and recommendations. They expose only
allowlisted fields and aggregate evaluation metadata. Whole sentences with
known frozen task identifiers/corpus names, task examples, SQL/output/trace or
credential markers are omitted rather than rewritten. Original evidence_refs,
rows, answers, patches, and raw traces are never projected. This conservative
filter is not a general secrets detector; inspect new projection coverage when
introducing a different archive format. Summaries report their omissions.

Every view is bounded, content-addressed, and bound to the original graph
record, canonical sealed intent, review bytes, generation, and candidate patch.
Missing/invalid views remain unavailable/UNKNOWN; never fall back to originals.
Original archival `detail_links` remain provenance only. Safe files and their
SHA256 are indexed separately under `safe_detail_access`. Prepare-context stages
materialize new safe files without overwriting old artifacts; `read-meta-detail`
can return one bound safe view without model calls or stage writes.

More prose does not create activation measurements. Existing labels and
recommendations stay historical/nonbinding; missing evidence is not zero or
failure, and heterogeneous model/runtime comparisons remain non-causal. This
extension does not add terminal/edit/deployment permission, resume automations,
launch models/evaluations, select a parent/intent, or start the next generation.
If the agent cannot read a safe file, it must report the limitation.
