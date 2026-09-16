# FAM-C AUDIT — ROUND 4 (independent seat, 2026-09-16)

Auditor: fresh general seat, no shared context with the implementers, read-only.
Scope: the accumulated post-A11b state (main b4ce064 + branch
rcos-harness-readiness a61d104) against the Round-3/A11b work orders and the
A12–A15 roadmap. All numbers below were independently re-executed by the seat;
recorded implementer numbers were not trusted (see P0-R4-2).

## Preamble — what was independently run

- Trees: Mac clone + Dell clone at b4ce064; throwaway clones of
  rcos-harness-readiness (tip a61d104, 166 commits past the landing: A12l/A12n
  slices, A13 canonical adaptation, Ruling-3). No repo modified; no lock
  mutated; no live provider call (`--live` stayed guarded; the quota-gated
  P/Q pair stands).
- Full 37-suite battery, three ways: Dell clone @ main 23/37; fresh clone
  @ main 26/37; branch @ a61d104 31/37 (h18/h25/h27 pass individually;
  h35 = 55/56 at the branch tip).
- preflight.py: main RED (V1-instance 1, V2-protocol 4, V3 0); branch GREEN
  0/0/0.
- Runner selfchecks ok on both trees; calibrate --offline 2/2 lanes green.
- admissibility.py: estimand-grade = 0 on both trees; all runs/ dirs EXCLUDED
  (2 H1-* harness-validation; rest pre-harness ad-hoc); no state/ namespace
  has ever existed.
- ORDER-EXPANSION.json: 240 events / 192 model calls, order_sha256
  byte-identical main↔branch (4510076a…).
- Locks: EXECUTION-LOCK.json status "open-round2" (68 amendments on main /
  67 on branch); PROTOCOL-LOCK.json has no FINAL status (living-lock mode,
  52 amendments) — non-FINAL is legitimate pre-calibration; finalization is
  gated on this review + the live P/Q pair.

## Code spot-checks (main, real production paths)

(a) H6 byte-identity: strip_capability_block(treatment) == control is the
literal invariant (run_arm_h1.py:507-596); the weaker legacy assertions are
deleted, not supplemented. (b) Production request binding: messages= is
passed to record_identity and verify_request_binding/verify_adapter_binding
run inside _wire_chain (run_arm_h1.py:1519-1545, 1694-1712). (c) cell_state:
exact 13-field equality incl. cell_kind/cell_universe, real module-level
verify_chain (chain.py:183, order.py:793-794), admissibility ELIGIBLE
required. (d) Event-kind dispatch + causal rooting: _promotion_state
re-derives the candidate from THIS universe's T0 arrival payload (copied-in
artifacts cannot promote); _lock_state binds the promotion receipt sha.
(e) Namespace ancestry: lstat every component from state/ downward, verified
before realpath comparison.

## Verdict

| Roadmap unit | Verdict |
|---|---|
| A11.1 calibration live branch | PASS |
| A11b.1 production request binding | PASS |
| A11b.2 unified output contract/parser | PASS |
| A11b.3 real chain verification in cell_state | PASS |
| A11b.4 manifest schema exact equality | PASS |
| A11b.5 event-kind-specific cell_state | PASS |
| A11b.6 no-symlink namespace ancestry | PASS |
| A11.4 ordering / A11.5 namespaces / A11.6 validated state | PASS |
| A12 #8 promotion controller | PASS |
| A12 #9 estimand-aware CAPABILITY_LOCK | PASS |
| A12 #10 USE/REJECT/fresh | PASS |
| A13 #11 objective material contribution | PASS |
| A14 #12 infrastructure/retry state machine | PASS |
| A15 #13 full chain + §24 admissibility | PASS |
| FULL synthetic Fam-C family attack | PARTIAL PASS (coverage real but distributed across h12/h13/h16/h25/h34; the FINAL-lock record must cite the set explicitly) |
| Readiness protocol / lock FINAL state | PARTIAL PASS (non-FINAL correct pre-calibration; but the audited public main failed its own preflight — P0-R4-1) |
| Closure documentation + verification claims | FAIL (status docs stopped at A12/D10; A12b–A13 replies uncommitted; 37/37 claim did not reproduce) |

estimand-grade runs: 0

**permission for real Fam-C execution: NO**

Stop phrase ("Everything on RCOS is perfect for the audited scope. Stop and
produce the final receipt.") NOT issued.

## P0 findings

- **P0-R4-1** — the audited public tree fails its own authority gates:
  main's PR-squash landing left the freeze commit d1292434 a non-ancestor of
  main and 4 V2 lineage nodes unreachable; the runner refuses start
  (PREFLIGHT-LOCK-FAIL, fail-closed correct). Fix: the designated execution
  ref must carry the lineage (merge the branch, or re-mint both locks over
  the landed lineage as listed amendments); acceptance = preflight exit 0.
- **P0-R4-2** — the implementers' verification claim (37/37) did not
  reproduce on any tree measured (23/37, 26/37); stale git worktree
  registrations on the Dell clone; battery-order dependence (h18/h25/h27);
  the recorded greens were not re-validated after the landing wave. Fix:
  prune registrations, unique worktree/fixture paths, re-run the battery in
  a fresh clone and record ref + number.
- **P0-R4-3** — genuine branch-tip regression: h35 H35b-IDENTITY fails at
  a61d104 (map_entries=25; identity-bundle key-set drift, cf. aa96dbd).
  Fix: reconcile writer/suite schema, re-mint.
- **P0-R4-4** — public closure record incomplete: A12b–A13 auditor replies
  and Ruling-3 records were never committed; status docs lag the code.

P2 (non-blocking): hardcoded absolute repo paths in smoke_h7_order.py:23 and
smoke_h23_d1.py:559; battery-order dependence of h18/h25/h27.

## Disposition (R4-RECONCILE, same day, operator-authorized)

- P0-R4-1 CLOSED: execution ref = rcos-harness-readiness reconciled with main
  (merge 24cd07d); preflight 0/0/0 at the merged ref (V1 ancestry restored,
  V2 nodes retrievable). EXECUTION-LOCK re-minted over the merged tree as
  listed amendments 69/70 (R4-RECONCILE-P0-R4-3 and R4-RECONCILE-P0-R4-3b;
  append-only chain anchored at the D11 genesis, preserved), plus one
  PROTOCOL-LOCK forward amendment — the 53rd entry (preflight.py, slice
  R4-RECONCILE-P0-R4-4, base d94dcf4). [Wording corrected at A16, f223675:
  the earlier "amendments 69–71" miscounted the later QPATH re-mint (#71)
  into this slice, and no literal "AMEND-2026-09-16-r4-reconcile" id exists
  in the repo — the actual slice id is R4-RECONCILE-P0-R4-4.]
- P0-R4-3 CLOSED, root cause corrected: the failure is NOT an A13 schema
  break — run_arm_h1.py hardcoded BASE/HARNESS to
  /home/chow/chow-work/rcos, so any real-seal suite bound whichever checkout
  sat at that path instead of the tree under test (the bundle's recorded
  execution_lock_sha256 407b1a54… is byte-for-byte the main checkout's lock).
  BASE/HARNESS/ROOT/LANES keyfiles (runner), p_call.py, smoke_h7_order.py,
  smoke_h23_d1.py now derive from file location; h35 = 56/56 on the
  reconciled ref.
- P0-R4-2 PARTIAL: stale registrations pruned; per-script exit codes now
  captured un-piped (the implementers' earlier 37/37 was a false green from a
  pipeline exit-code bug — recorded as a lesson); battery re-run recorded
  with ref + checkout state (see FAMC-EXECUTION-STATUS.md Round-4 section).
  Suite fixture roots are still shared (/tmp/rcos-runs); per-suite isolated
  roots recommended as a follow-up slice.
- P0-R4-4 PARTIAL: this file is the committed Round-4 reply; A12b–A13/Ruling-3
  seat replies were not preserved by their sessions and are acknowledged
  LOST — the compensating control is this independent re-audit of the
  accumulated state; FAMC-EXECUTION-STATUS.md carries the Round-4 section.
  HARNESS-READINESS.md refresh is deferred to the PROTOCOL-FINAL slice where
  its stanza updates anyway.

## Remaining path to the first authorized cell

P/Q live calibration pair (quota-gated; retry scheduled) → PROTOCOL-LOCK
FINAL pinning ORDER-EXPANSION.json sha256 449be793… (the file's exact
bytes; A16 f223675 recorded the pin in the lock — the "4510076a…"
previously written here is the order_sha256 of ORDER.md inside the
expansion, not the file sha) → EXECUTION-LOCK FINAL →
first real authorized cell. The design is unchanged by this round: what
remained was landing reconciliation, one path-resolution defect, test
hygiene, and record completeness.
