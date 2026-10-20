# Graph-selected intent with a bound interface card

The Graph remains the strategy input: a read-only Meta selection chooses one
materialization base and any evidence parents. That response is provisional;
it is **not** sealed and cannot authorize candidate generation.

`dab_meta_interface_card_v1.py` then reads that one frozen source base and the
official scaffold. It binds the source-tree hash, source-file hashes, AST
handler signatures/return/message-append facts, inherited suppression call
sites, the current checkpoint journal's handler-call/cursor-advance sites, and
allowlisted tool argument types. An extra `role=tool` message for one call ID
is flagged as a protocol-shape risk, not assumed to be valid. It does not expose source excerpts,
per-query records, answers, raw traces, or historical patches. Stock tool
modules missing from the campaign snapshot are explicitly labeled as
hash-bound current-workspace scaffold files; they are not falsely described as
frozen in that snapshot.

`dab_meta_interface_bound_intent_v1.py` makes one fresh Meta call with the
compact Graph plus this card. Its response schema requires an `interface_binding`
matching the card and a concrete treatment of inherited suppression and tool
message attachment/cardinality. The deterministic check rejects a changed materialization
base, stale source/card hash, missing native-session audit, or mismatched facts.
Without a separate protocol-compatibility proof, it rejects a proposed second
`role=tool` message for one call ID. The final intent must state whether it
preserves or removes inherited suppression and must modify an existing tool
message (or leave messages unchanged) rather than assuming an extra response
is valid.
This is a factual gate, not proof that the proposed algorithm is safe or will
activate in an evaluation.

The workflow must stop for independent semantic review before a versioned
intent is sealed. In particular, review whether the mechanism's claims about
dispatch, return values, status/payload preservation, and checkpoint ownership
actually follow from the bound source. A synthetic unit test proves a branch is
reachable in a fixture, not that it activates on the frozen DAB tasks. Failed
attempts, prior intents, source trees, and Graph records remain immutable.
The current overlay journal is explicitly hash-bound but not a promise about a
future derived runtime: the actual candidate-specific overlay must be rebound
and compatibility-tested again before any formal evaluation.

`run_dab_meta_two_stage_intent_v1.py --run-once` is the single-command path for
a future `ready_for_intent` generation: provisional Graph selection, strict
native audit, selected-base card, and interface-bound final Meta completion.
It stops on the first failure, never replays an ambiguous dispatch, and leaves
the final intent unsealed for independent semantic review. The current Gen12
application instead used its already-completed Graph selection as the
provisional first stage; the later card-bound response remains unadmitted.
