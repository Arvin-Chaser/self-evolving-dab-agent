# Research Memory Policy

This file governs the DAB cross-session memory mechanism. It is read when changing memory or Agent orchestration, not during ordinary startup.

## Goals

- Recover the verified research boundary without replaying a transcript.
- Preserve failures, corrections, provenance, and immutable evidence.
- Keep default model context small and make cold evidence discoverable.
- Prevent memory synchronization and Agent orchestration from becoming an autonomous workload.

## Memory tiers

### Hot state

`CURRENT_STATE_BRIEF.md` is the sole default startup document. It must remain at or below 8,192 bytes and contain only:

- the verified current boundary;
- the current interruption point;
- blockers and unknowns that change the next action;
- the next safe research action;
- pointers to canonical evidence.

Replace superseded hot facts instead of appending a chronological diary. Every claim must be labeled by wording as verified, historical, inferred, or unknown when ambiguity matters.

### Routing index

`MEMORY_INDEX.json` owns file routing and canonical ownership. It must remain valid JSON and at or below 8,192 bytes. Add a route only when an existing route cannot locate a necessary source.

### Cold human-readable records

The detailed state, handoff, overview, decisions, experiment ledger, environment, history index, and one-time recovery handoff are cold. Preserve existing conclusions and failed attempts. Retrieve them by stable generation, decision, experiment, node, run, or artifact ID.

Do not read all cold records merely to become oriented. Do not copy their contents into the hot state, task prompts, or child-Agent packets.

### Immutable artifacts and machine memory

Experiment artifacts, manifests, reviews, hashes, raw logs, and versioned Research Graph memory are evidence, not narrative context. Query only the fields or named nodes needed for the current decision. Large raw logs and historical session JSONL are last-resort provenance sources.

## Canonical ownership and materiality

Record information only when omitting it could change scope, research direction, an invariant, acceptance criteria, operational safety, or a future interpretation of evidence.

- Current brief owns only the compact present boundary.
- Detailed current state owns expanded present evidence.
- Handoff owns safe next actions and prohibitions.
- Decisions owns rationales and corrected beliefs.
- Experiments owns append-only run outcomes, including failures and invalid runs.
- Environment owns non-secret operational facts verified by bounded checks.
- History index owns provenance into old sessions.

Link to the canonical owner instead of duplicating content. Do not store routine command output, narration, scratch work, full prompts, source code, credentials, or speculative conclusions in memory.

## Update protocol

Update memory only after a material milestone or when the verified boundary changes.

1. Verify the relevant immutable artifact, current code/test evidence, and Git metadata.
2. Update the canonical cold owner without erasing failed or superseded evidence.
3. Refresh the hot brief by replacement, keeping it within budget.
4. Update the routing index only if ownership, paths, or the current machine-memory version changed.
5. Run `python scripts/validate_agent_memory.py` and `git diff --check`.
6. Report changes; do not commit, push, run providers, or begin the next research phase without separate authorization.

No automatic per-turn or per-command memory update is allowed. A context file is not proof that implementation, admission, formal evaluation, or independent verification succeeded.

## Agent and context budgets

- One Agent is the default.
- Delegation requires explicit user authorization. Use at most one child at a time with no nested delegation.
- Start a child without inherited conversation history and send a self-contained packet no larger than 8 KB: objective, exact inputs, constraints, acceptance criteria, and output schema.
- A child returns concise findings and artifact paths, not copied logs or a full restatement of repository memory.
- Use at most one bounded Agent wait before doing independent work; after two unchanged waits, stop and return control.
- Prefer one batched read-only command over many sequential discovery calls, but cap output and avoid recursive listings.
- Do not use a fixed model/tool-cycle count or compaction count to stop work or force a context rotation. The user normally chooses when to start a fresh conversation, such as once per day or at a natural work-stage boundary.
- When context pressure, repeated compaction, degraded recall, or a platform-limit warning creates a material reliability or cost risk, briefly recommend a fresh conversation. Continue the current task unless a platform hard limit prevents reliable work, and never create, fork, hand off to, or continue a replacement thread without the user's explicit request.
- If a hard limit prevents reliable continuation, make only the minimum deterministic state capture required for recovery and prepare a handoff no larger than 4 KB for the user to use or explicitly authorize.
- Never inject raw session history into a new task. Use the hot brief plus targeted evidence pointers.

## Deterministic checks

Use scripts rather than LLM calls for file sizes, JSON/schema validity, hashes, Git status, manifest equality, terminal-row counts, and budget enforcement. LLM review is appropriate for research judgment, not unchanged-state synchronization.

## Execution boundary

Memory restores knowledge, never authorization. Before provider, server, database, benchmark, formal-run, destructive, commit, or push work, verify the current worktree and external state and obtain the user's current authorization.
