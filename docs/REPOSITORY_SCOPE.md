# Migration Scope

This repository starts as a clean Git history rather than a mirror of the
legacy working repository. It contains only the active DAB / DataAgentBench
research mainline and a small set of answer-free, auditable evidence records.

Included:

- active DAB adapters, runners, observer/evidence tooling, and Research Graph
  orchestration scripts;
- DAB policies and focused tests;
- canonical research-memory documents;
- `research_graph_memory_v19.json`, its G0-G13 final graph references, and
  selected manifest/review/validation records for the current G11-G13 line.

Excluded:

- legacy Text-to-SQL demos and prior repository history;
- external repositories, benchmark datasets, databases, and copied sandbox
  environments;
- provider settings, credentials, raw prompts/traces, task answers, logs, and
  temporary workspaces;
- experimental attempt directories that are not selected evidence records.

This policy is enforced by `.gitignore` and should be retained unless a new
artifact is independently reviewed for privacy, license, and reproducibility.
