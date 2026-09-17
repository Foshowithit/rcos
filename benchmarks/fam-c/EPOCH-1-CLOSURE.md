# RCOS Fam-C — EPOCH-1 CLOSURE RECORD

Ruling source: independent reviewer (third-party seat, owner-directed), 2026-09-17.
Ruling: **EPOCH-2 PROTOCOL (a)** — close epoch 1 terminated-not-repaired; NO
post-FINAL defect-abatement mechanism for epoch 1.

## Epoch-1 identity (frozen, immutable)

- Execution ref lineage: r4-reconcile; finalization commit
  `1e146279077b8b442e8c0542887349156aa4571f`; certification ref
  `2a1309d302440ef060a436b31152fb646758840a` (battery 38/38, direct exit codes).
- Lock bytes at closure:
  - EXECUTION-LOCK.json sha256 `f6616ea2a495ae3f5a5d2f5d5b35b503eddc9aaca21a43358d756c1bd49b0f24`
  - PROTOCOL-LOCK.json sha256 `96eac57be905b2f030f02615e4774d2a9ac2adab8c7e1aa26fe3e39efe695a54`
- Frozen defective state machine: `harness/order.py` sha256
  `f08e3edc87993688d11cc742cf0bf58436820247a09c2ed1d35071de367fa268`

## Executed cells and validated terminal states

| Cell | id | Terminal state (validated) |
|---|---|---|
| PQ/fam05/T0/A acquisition | `9907c5cb038c02e0` | COMPLETE; arrival fresh; checker verdict fix; evidence chain 4 links |
| PQ/fam05/T1/A validation | `7554ee63c700e234` | COMPLETE; arrival ship; candidate validation FAILED (`candidate-output-missing`); chain 5 links |
| PQ/fam05/PROMOTION/A | `55cee7075b462312` | NOT-PROMOTED (validated); PROMOTION-OUTCOME.json sha256 `e96adaf1e3baabe1c9a0e58d4018aa9615365c8094f10b67960c2681ca088d94` |

Deadlock reproduction (empirical): after the denial was recorded, every order
probe refused — `ORDER-DENY: out of order — ... earliest missing is
55cee7075b462312 (PQ/fam05/PROMOTION/A)` — while `cell_state()` validates the
same cell as NOT-PROMOTED. Root cause: `completed_cells()` (A11.6) accepts
only `status == COMPLETE`, so the prefix walk never advances past a lawful
NOT-PROMOTED terminal; the sibling CAPABILITY_LOCK cell (`011ec0ecf88b81e1`)
has no terminal writer at all (no NOT-LOCKED path). Tests covered the denial
WRITING (h23) but never order progress after a denial — the untested seam.
The repair is a harness-bytes change and is correctly blocked by the epoch-1
FINAL seal (re-mint refused: EXECUTION-LOCK-FINAL-REFUSED).

**No-capability statement:** no capability was promoted or locked, no
capability reuse occurred, and no downstream reuse/cost estimand cell
executed. Epoch-1 evidence is acquisition-path evidence plus one validated
promotion denial.

## Epoch-1 closure — TERMINATED, NOT REPAIRED (ruling language, verbatim)

Epoch 1 remains immutable at its recorded FINAL protocol and execution locks.
During real execution, a validated failed acquisition produced the lawful
terminal state NOT-PROMOTED, but the frozen A11.6 order-progress
implementation recognized only COMPLETE as progress-valid. The resulting
prefix deadlock is a harness/state-machine defect, not an invalidation of the
recorded T0, T1, or promotion-denial evidence. No capability was promoted or
locked, no capability reuse occurred, and no downstream reuse/cost estimand
cell executed. Epoch 1 is therefore closed at the defect boundary. Its
artifacts remain historical evidence and MUST NOT be amended, reclassified,
replayed into, or used to satisfy cells in a later epoch.

## Epoch-2 amendment — TERMINAL-OUTCOME PROGRESS SEMANTICS (ruling language, verbatim)

Epoch 2 introduces an explicit event-specific set of progress-valid terminal
states. PROMOTION may progress on validated COMPLETE or validated
NOT-PROMOTED; CAPABILITY_LOCK may progress on validated COMPLETE or validated
NOT-LOCKED; downstream cells belonging to a capability universe whose
acquisition has validly failed may progress only as validated NOT-EVALUABLE.
INCOMPLETE and INADMISSIBLE are never progress-valid. These terminal states
do not imply successful promotion, locking, execution, or estimand
observation and MUST NOT be converted to COMPLETE. The harness MUST prove by
test that a failed-acquisition universe advances the frozen prefix without
authorizing promotion, lock creation, capability consumption, retry, or
fabricated evidence. Epoch 2 receives fresh protocol/execution locks and a
new finalization commit, and its ordered cells execute from the beginning
under that lineage.

## Epoch-1 cell disposition (ruling language, verbatim)

Archive, do not carry forward as satisfied epoch-2 cells. Re-run
T0/T1/PROMOTION clean under epoch 2. Their epoch-1 artifacts remain valid
historical evidence of epoch 1 and of the defect, but they must not populate
epoch-2 done_ids, satisfy epoch-2 prefix positions, seed promotion, or become
epoch-2 experimental observations.
