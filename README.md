# Roadmap-Based Self-Evolving Agents

Research code and curated reproducibility records for a roadmap-based,
self-evolving multi-turn tool agent evaluated in the DataAgentBench setting.

## Scope

This repository is a clean migration snapshot of the active DAB research
mainline. It contains the current tool-agent implementation, Research Graph
orchestration, policies, focused tests, and selected answer-free evidence.
It intentionally does not contain provider credentials, benchmark datasets,
database dumps, raw model traces, task answers, or runtime workspaces.

The current Research Graph records formal generations G0 through G13 and an
unfrozen G14 interface-investigation target. The graph and selected manifests
are evidence records; they do not by themselves establish causal improvement.

## Layout

- `adapters/`: DAB tool-agent integration helpers.
- `experiments/`: active runners, Research Graph control scripts, and curated
  graph/evidence records.
- `prompts/dab/`: policy and meta-agent prompts.
- `tests/`: focused regression and protocol tests.
- `docs/agent_memory/`: cross-session research state, decisions, and routing.

## Reproducibility Boundary

DataAgentBench and other external datasets must be obtained separately under
their own licenses. Runtime configuration is deliberately excluded. Before
running a provider, benchmark, database, or formal evaluation, read `AGENTS.md`
and the brief research state under `docs/agent_memory/`.

## Artifact Policy

Only final graph snapshots and selected manifests, validation reports, and
reviews are versioned. Raw logs, JSONL traces, credentials, database files,
and copied sandbox trees remain outside this repository.
