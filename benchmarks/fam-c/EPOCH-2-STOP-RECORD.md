# RCOS Fam-C — EPOCH-2 STOP RECORD (stopped / incomplete, preserved)

Ruling source: third-party governance seat (ChatGPT campaign thread
https://chatgpt.com/c/6aab60f4-15a4-83e9-b239-75a40df4218d), 2026-09-17
~10:30Z. Verbatim text at
`/home/chow/rcos-campaign/RULING-2026-09-17-parse-denial.md`.

Ruling (operative lines, verbatim): **"CONTRACT-PARSE-DENY = EXPERIMENTAL
OUTCOME. N=1. NO RETRY-UNTIL-ADMISSIBLE. ATTEMPT 2 PRESERVED, NON-ESTIMAND.
EPOCH 2 STOPS AT THE UNREPRESENTABLE FINAL CELL. EPOCH 3 MAY ADD A
PRE-FROZEN MODEL-OUTPUT-INVALID TERMINAL AND RESTART CLEAN."** … "Do not
mutate FINAL to make the walk convenient." … "Epoch 2 remains preserved as a
stopped/incomplete experimental epoch."

This record is an epoch-stop annex. It is NOT a cell terminal and it writes
nothing under `state/`. Frozen wording (adjudication 2026-09-17, FR-11):

> Highest progress-valid epoch-2 cell index is 63. The stop record MUST NOT
> make cell index 64 progress-valid, and MUST NOT cause any walk to include
> cell 64 or any later cell in the completed prefix.

## Epoch-2 identity (frozen, immutable)

- Transition record `EPOCH-2-TRANSITION.json` sha256
  `047aef2fcfef76803cb0999edcd17027aa2997b91a7face8ad9a83012136bb6b`,
  citing the epoch-1 closure record `EPOCH-1-CLOSURE.md` sha256
  `917f379429a90f50edb20972763da028b1c86a79c04b7c3f0106fbd708758dd9`.
- Epoch-2 FINAL locks, at their recorded bytes:
  - `EXECUTION-LOCK-EPOCH2.json` sha256
    `e662463e50fbb7d08115063595a4392437ccac54e6d2dd989a730ecafe619a80`
    (status FINAL, finalized_at 2026-09-17T06:42:11Z, finalization_commit
    `53e72ef4cec5ec7ecc9628c348a36635c02bd2d4`, four own-lineage
    amendments, harness manifest
    `778c5e9829c29967bfc7df3a1e3de209d0e4df0320b6d69d3afe8e912623b3be`).
  - `PROTOCOL-LOCK-EPOCH2.json` sha256
    `978d5e3e8d6f8797343830d565583804ae58a426b114331e74b2f4ebe1f74b00`
    (status FINAL, finalized_at 2026-09-17T06:42:09Z, 0 amendments).
- State namespace `state/epoch2/` (all derived runs). Epoch-1 state
  (`state/**`) and both epoch-1 FINAL locks untouched.
- Instance freeze: `d1292434a261f44ad910c556e18624cef1676f37`.

## What ran (ordered prefix, cells 0–63 of 240)

The walk consumed the strict prefix of the frozen order through cell index
63 (64 cells), all under FINAL epoch-2 locks, block PQ only:

| Family | Universe | Cells executed / recorded |
|---|---|---|
| fam05 | A + C | T0, T1, PROMOTION, CAPABILITY_LOCK (both universes) |
| fam03 | A + C | T0, T1, PROMOTION, CAPABILITY_LOCK (both universes) |
| fam01 | A + C | T0, T1, PROMOTION, CAPABILITY_LOCK (both universes) |
| fam04 | A only | T0, T1, PROMOTION, CAPABILITY_LOCK |
| fam05/fam03/fam01 | B + D | 18 disabled-arm downstream runs (T2/T3/T4 × 3 blocks × 2 arms) |
| fam05/fam03/fam01 | A + C | 18 downstream cells resolved NOT-EVALUABLE (acquisition-failed, derived) |

Recorded governance terminals for the failed universes: seven
`PROMOTION-OUTCOME.json` (outcome `NOT-PROMOTED`, reason
`candidate-validation-failed`) and seven `CAPABILITY-LOCK-OUTCOME.json`
(outcome `NOT-LOCKED`, reason `no-promotion-no-lock`), written by the A12.1
controller (`harness/promotion.py`, `order.emit_promotion_outcome` /
`order.emit_capability_lock_outcome`).

## Acquisitions: 8 attempted, zero valid candidates

Eight T0 acquisition cells were authorized and attempted (fam05 A/C, fam03
A/C, fam01 A/C, fam04 A/C); seven produced an admissible arrival and one
(cell 64) did not:

| Cell | id | lane | arrived | artifact rc | T1 candidate validation |
|---|---|---|---|---|---|
| PQ/A/fam05/T0 | `9907c5cb038c02e0` | P | yes | rc 1 (blocked) | n/a |
| PQ/A/fam05/T1 | `7554ee63c700e234` | P | yes | rc 0 (ship) | FAILED (candidate rc 1) |
| PQ/C/fam05/T0 | `3122872f1ac60568` | Q | yes | rc 1 (blocked) | n/a |
| PQ/C/fam05/T1 | `86d4fe1e9d56956c` | Q | yes | rc 1 (blocked) | FAILED (candidate rc 1) |
| PQ/A/fam03/T0 | `16f04953f5be5e81` | P | yes | rc 1 (blocked) | n/a |
| PQ/A/fam03/T1 | `995b6f2cc33268a1` | P | yes | rc 0 (ship) | FAILED (candidate rc 1) |
| PQ/C/fam03/T0 | `d3f896e4b923471b` | Q | yes | rc 1 (blocked) | n/a |
| PQ/C/fam03/T1 | `dfbef4088c393e3f` | Q | yes | rc 1 (blocked) | FAILED (candidate rc 1) |
| PQ/A/fam01/T0 | `f5a43ddbdfe74422` | P | yes | rc 1 (blocked) | n/a |
| PQ/A/fam01/T1 | `0913224c72cd9693` | P | yes | rc 0 (ship) | FAILED (candidate rc 1) |
| PQ/C/fam01/T0 | `e5c9e32a16ecf314` | Q | yes | rc 1 (blocked) | n/a |
| PQ/C/fam01/T1 | `474a349793c905ae` | Q | yes | rc 1 (blocked) | FAILED (candidate rc 1) |
| PQ/A/fam04/T0 | `172452163c2084e3` | P | yes | rc 1 (blocked) | n/a |
| PQ/A/fam04/T1 | `42464dda2f115eae` | P | yes | rc 0 (ship) | FAILED (candidate rc 1) |
| PQ/C/fam04/T0 | `b933d9322add55cc` | Q | **no** | (no terminal) | not reached |

Seven `candidate-validation` links exist across the epoch-2 tree, each with
`"validated": false`, `"validation_failure": "candidate-failed: the frozen
T0 candidate exited non-zero (rc=1) on the adapter's input"`,
`checker_returncode: null`. The eighth T1 cell (`0fadf881b57a069c`,
PQ/C/fam04/T1) was never reached. Every failure above is a recorded
experimental outcome, preserved, not retried, not reclassified.

## The unrepresentable final cell (the epoch-2 stopping point)

- Cell: index **64 / 240**, id `b933d9322add55cc`, block PQ, universe C,
  family fam04, task T0, lane Q (kenari `agnes-2-0-flash:free`).
- Ordered prefix tip before the cell: `e38ed4c1c456fe6a`
  (PQ/A/fam04 CAPABILITY_LOCK, NOT-LOCKED), worktree head at the time
  `cc08bf1b87a0a9b39402d3acf93886ce44b9d3a5`.
- Attempt 1 — the experimental outcome: provider call
  `f23da2d0f49e052b`, wall 10.83 s, 1444 response bytes, response sha256
  `05a3f636c0c8793c18913011d708d38db4aafce6ecda0ca52d24d225b542413c`;
  structurally invalid JSON, refused by the frozen A11b.2 contract with
  `CONTRACT-PARSE-DENY`. Classification: EXPERIMENTAL_MODEL_OUTPUT_FAILURE.
- Attempt 2 — non-estimand diagnostic repeat: provider call
  `a63ba445157af666`, wall 78.52 s, 42,766 response bytes, response sha256
  `1aa65724232cc1d38e0b424c3542bca609232d2ed310fa23dfc07f452dfcbbf0`,
  `completion_tokens 9000 == max_tokens` (degenerate runaway, truncated
  mid-string). `estimand_eligible: false`; reason "post-outcome diagnostic
  repeat before adjudication". It does not replace, rescue, or reclassify
  attempt 1. Both attempts carried byte-identical request bodies
  (`request_body_sha256
  071dc9124388bc24e1e9bad87de126532ccfdfcf03d7222f9dba0f32a6fd2647`).
- Preserved evidence (read-only, do not move, do not delete, do not commit):
  `benchmarks/fam-c/state/epoch2/_operator-errors/PQ-C-fam04-T0-lane-Q-attempt/`
  (note the directory-name casing) —
  - `INCIDENT.json` sha256
    `ccf2dc65adf1e8f8c2f23bb62f168457fcf00ddcf1546def3f43a1233fce49b5`
    (schema `famc-no-arrival-incident-v1`; `contract_result
    CONTRACT-PARSE-DENY`, `classification
    EXPERIMENTAL_MODEL_OUTPUT_FAILURE`, `arrival_written: false`,
    `manifest_written: false`, `chain_terminal_written: false`,
    `ordered_path_advanced: false`, `estimand_disposition
    EPOCH_STOPPED_INCOMPLETE`);
  - `NOTE.md` sha256
    `d98c490bf3c0bd2b0463f1dbb4b8b3cef3dbac0254e8769c07532238e580c777`;
  - `attempt-1/raw.txt` sha256 `05a3f636…` (1444 B), attempt-1 receipt
    `cd6cdab2…`, identity `2c2b03fd…`;
  - `attempt-2/raw.txt` sha256 `1aa65724…` (42,766 B), attempt-2 receipt
    `3f8c089a…`, identity `66b1a5e4…`.
- Representational fact: the epoch-2 FINAL lineage has no lawful ordered-path
  representation for "provider call exists + usage/identity exist + raw
  response exists + CONTRACT-PARSE-DENY + therefore no `arrival.json`". That
  defect is the reason epoch 2 stops here, and it does not license retrying
  around it.

Accounting observation (recorded, not hidden, no classification invented):
the run `state/epoch2/PQ/C/fam05/runs/86d4fe1e9d56956c/` preserves TWO
provider-call receipts with byte-identical request bodies —
`dda8f5746cfaa800` (676 completion tokens) and `53cdb3e6bd66731e` (6149
completion tokens, the chained call; chain `call_count: 1`, response sha256
`6cd0a370e7368f74299a79de8fab4162211e774e14584fa6d9bf3c9c2e589214`).
The first call's response text is not preserved per attempt (its reply is not
on disk; `raw.txt` belongs to the chained call), so its per-attempt contract
admissibility is not derivable from preserved evidence; no classification is
asserted here. The first call counts in the all-provider-calls denominator.
Epoch-3 accounting must preserve response text per attempt
(`FREEZE-REQUEST.md` FR-6).

## No-capability statement

No capability was promoted, no `CAPABILITY_LOCK.json` was minted, no
capability was loaded, invoked, or consumed by any cell, and no downstream
reuse/cost estimand cell executed. Every epoch-2 capability artifact path
terminated in a recorded `NOT-PROMOTED` / `NOT-LOCKED` refusal. Epoch-2
evidence is acquisition-path evidence (T0/T1 verdicts, seven failed candidate
validations, the disabled-arm downstream runs) plus governance terminal
records.

## Epoch-2 disposition (ruling language, applied)

EPOCH 2 STOPS AT THIS PREFIX. The ~176 later events remain withheld. With no
lawful terminal representation under FINAL, advancing past cell 64 would
require changing frozen execution semantics after observing the outcome;
FINAL is not mutated to make the walk convenient. Epoch 2 remains exactly
STOPPED / INCOMPLETE — not "closed" — preserved at its recorded FINAL locks
and state bytes, and no new epoch-2 state write is required or permitted. Its artifacts are immutable historical evidence and MUST NOT be
amended, reclassified, replayed into, carried forward, or used to satisfy
cells in a later epoch. The epoch-2 cell prefix may be reported only as
stopped-prefix evidence, never as a completed segment of the 240-event order.

This record creates no terminal for cell 64, does not make the cell
COMPLETE-FAILURE, does not write under `state/`, and must not cause
`completed_cells()` to advance: the highest progress-valid epoch-2 cell index
is 63, and no walk may include cell 64 or any later cell in the completed
prefix. The lawful representation of this failure
class arrives only with the pre-frozen epoch-3 terminal
(`EPOCH-3-PROTOCOL-SPEC.md`), and epoch 3 restarts the order from event 0
(`FREEZE-REQUEST.md` FR-7/FR-8).
