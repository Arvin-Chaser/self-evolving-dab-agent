# Agent / Candidate Archive MVP

This archive is the lightweight memory layer for the DAB / DataAgentBench
agent-evolution line.

The archive separates two granularities:

- `archive/agents/`: stable or reviewable agent checkpoints that may be used as
  future evolution parents.
- `archive/candidates/`: mutation attempts and experimental patches, including
  rejected, failed, and promoted candidates.
- `archive/indexes/`: JSONL/JSON indexes for selection, lineage, and quick scans.

Current intended workflow:

1. Generate or review a candidate.
2. Record it in `archive/candidates/<candidate_id>/candidate_card.json`.
3. If it passes child eval and small regression, mark it promoted and link it
   from `archive/indexes/candidates.jsonl`.
4. Only promoted candidates should become new agent checkpoints in
   `archive/agents/`.

Scope note: archive entries are research records. They do not imply that a
candidate patch has been merged into the main project.

