# Historical Session Index

## Source and coverage

Session ID: `01a124ff-f402-7763-8200-0fba53b96381`.

Source location used because `CODEX_HOME` was unset:

`C:\Users\34934\.codex\sessions\2026\10\10\rollout-2026-10-10T16-48-36-01a124ff-f402-7763-8200-0fba53b96381.jsonl`

The original file was opened read-only and was not copied, modified, deleted, or overwritten.

| Property | Verified value |
| --- | --- |
| Bytes | 345,029,482 |
| Physical lines | 90,375 |
| SHA-256 | `ad7974724fd849b09028919e38301372b80e8230658baab4a720428e6b148f44` |
| Time span | 2026-10-10T08:48:38.823Z to 2026-10-20T12:08:00.288Z |
| Turns | 864 |
| Compactions | 94 |
| Important indexed events | 35,439 |
| Unique content fingerprints | 30,297 |
| JSON parse errors | 0 |
| Sensitive replacements | 182 |
| Encoding replacement characters | 640 across 88 records |

The source size and mtime were identical before and after extraction. Coverage is complete by byte and physical line.

## Generated index

Directory: `docs/agent_memory/source_index/session_01a124ff-f402-7763-8200-0fba53b96381/`.

- `coverage.json`: source identity, counts, redaction totals, and claim boundary.
- `coverage_chunks.jsonl`: 10,000-line coverage records.
- `events.jsonl`: bounded, redacted, source-line-indexed events.
- `turns.jsonl`: turn-level summaries.
- `README.md`: quick usage notes.

Tools:

- `tools/extract_codex_session_memory.py`: streaming binary line reader, parser, redactor, deduplicator, chunk/turn/theme indexer.
- `tools/query_codex_session_index.py`: bounded queries over the redacted index.

The extractor omits encrypted reasoning, truncates oversized tool/media output, records omitted length, fingerprints duplicates, and redacts credential-like values. The index is not a full transcript copy.

## Citation convention

Memory documents use `S:<line>` for a physical source line in the original JSONL, resolved through `events.jsonl`. Example: `S:90137` is the final G12 implementation checkpoint. A cited compaction is a historical checkpoint, not independent proof; verify against current artifacts when possible.

## Reviewed historical ranges

All ranges were reviewed through their compaction checkpoints, with targeted artifact queries where needed:

| Source lines | Main recovered topics |
| --- | --- |
| 1-10,000 | 56-task construction, baseline v2, Gen1, removal of mixed F1, database-copy cleanup |
| 10,001-20,000 | Gen2-Gen8, activation failures, protocol repair, deletion of obsolete Gen8 candidate, Research Graph redesign |
| 20,001-30,000 | extensible Graph schema, resumed production evolution, Gen8 final, early Gen9 research |
| 30,001-40,000 | Gen9-Gen14 intents/results, stricter stop rule, observer/Meta protocol changes |
| 40,001-50,000 | baseline-denominator correction, hint ablation separation, Gen15 collapse, Gen16-Gen19 progression |
| 50,001-60,000 | Gen19 closure, Gen15 repair branches, provider 503 incident, r2-r5 |
| 60,001-70,000 | Gen15 r5-r8 closure; pivot to the new G0-G2 Research Graph baseline line |
| 70,001-80,000 | G3-G7, diagnostic-vs-behavior intervention rules, Graph simplification, evidence closure |
| 80,001-90,000 | G8-G11, G10 infrastructure reconciliation, two-layer memory, solution-loop target selection |
| 90,001-90,375 | G12 interface investigations, experiment-ready contract, local implementation and admission blockers |

## High-value checkpoints

- `S:20125`: Research Graph ontology and extensible evidence correction.
- `S:21792`: Gen8 formal result and mechanism non-activation.
- `S:30590`: Gen9 formal result, 1/2,673 activation signal.
- `S:33437`: Gen10 closure and Gen11 selection.
- `S:41464`: original Gen15 handoff collapse.
- `S:46874`: Gen16 closure and Gen17 state.
- `S:49382`: Gen18 closure and Gen19 preparation.
- `S:52505`: Gen19 closure and Gen15 repair branch/provider incident context.
- `S:60790`, `S:61923`, `S:63129`: Gen15 r5-r8 results.
- `S:64125`: pivot from old evolution campaign to Research Graph baseline.
- `S:67525`: G0/G1 frozen state.
- `S:69401`: G2 closure and correction of `implementation_ready` semantics.
- `S:72800`: G3/G4 state and infrastructure incident separation.
- `S:77257`: G5 closure.
- `S:78079`: G6 result, 37/56.
- `S:79377`: G7 closure.
- `S:81736`: G8/G9 closure and unexpected remote storage-change warning.
- `S:83708`: G10 repaired-view boundary and G11 selection.
- `S:88815`: G11 closure, zero adoption/binding.
- `S:90137`: G12 experiment-ready and local implementation checkpoint.

## Conflict resolution

Use this precedence:

1. immutable current result/Graph/manifest artifacts and independently recomputed hashes;
2. current code and test records;
3. Git metadata for committed history;
4. source-indexed session events;
5. uncited prose or plans.

If a historical checkpoint says work was “next”, it is not completed unless a later artifact proves completion. If a checkpoint reports a partial metric, use the final terminal artifact. If a run was repaired, interrupted, or infrastructure-invalid, preserve both original and supplementary views.

## Irrecoverable limitations

- 88 records already contained Unicode replacement characters; their original characters cannot be reliably reconstructed.
- Encrypted reasoning is intentionally not copied.
- Oversized tool/media outputs are summarized and indexed, not reproduced verbatim.
- Deduplicated outputs retain source references but not redundant full copies.
- Historical chat statements can be wrong or stale. They do not supersede current files.
- Credential-like content was redacted and cannot be recovered from the index by design.

## Completeness statement

The extraction covers every byte and physical line of the original JSONL, and every 10,000-line range was reviewed at the compaction/theme level. This is complete source coverage, not a claim that every one of 35,439 indexed events was manually paraphrased. The remaining unavoidable loss is limited to pre-existing encoding damage, intentionally omitted encrypted reasoning, bounded long-output excerpts, and redacted secrets.
