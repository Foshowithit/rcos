# D3 APPARATUS REPAIR — FROZEN RULING (external gate, 2026-09-11)

Status of the superseded 13:56 run (preserved at
`/tmp/d3gen/d3run-SUPERSEDED-no-prediction-binding`):

    D3 APPARATUS INVALID
    reason = PROVIDER_MEASUREMENT_APPARATUS_ABSENT
    empty ledger != zero provider opportunity

D3 v1.0 contract: UNCHANGED. The repair below is an apparatus repair required to
satisfy the ALREADY-FROZEN contract — not a new D3 boundary, not a weakening.
No D3-A..E result may be produced until the repair AND both falsifiers are green.

## Required sequence (exact; one D1/D2 provider/capture sequence per D3 arm)

    arm starts
     -> D1 exclusive provider gate + independent mock boundary live
     -> exactly ONE authorized provider opportunity
     -> exactly ONE dispatch
     -> exactly ONE mock receive
     -> D2 cell captures exactly ONE response
     -> response sealed into the D2 memfd handoff
     -> all three D3 legs start
     -> denial policy installed
     -> legs stop at entry barrier
     -> /proc/<pid>/fd sets externally measured
     -> seccomp activation established
     -> capability allowlists reconciled
     -> SNAPSHOT PRE-LEG BASELINE   (must be SEALED before release)
          provider attempts = 1
          dispatches        = 1
          receives          = 1
          model cells       = 1
          ORDER cells       = 0
          captured response = D2 sealed identity
     -> ONLY THEN release leg business logic
     -> SNAPSHOT POST-LEG STATE

    require attempts_after   == attempts_before
            dispatch_after   == dispatch_before
            receives_after   == receives_before
            model_cells_after == model_cells_before == 1
            order_cells_after == order_cells_before == 0

TIGHTENING (load-bearing): the baseline must be established BEFORE any
counterfactual leg business logic is released.

## Load-bearing rule — NOT "1/1/1"

    D1 apparatus valid
    AND baseline == expected one-opportunity state
    AND post-leg counts == baseline

Do NOT make 1/1/1 itself the primary semantic condition: a malformed or truncated
ledger that happens to decode to 1/1/1 could satisfy a count check without
establishing D1 authority. Preserve D1's own eligibility/completeness conditions
around the counts.

## Cell counting — must NOT use provider ledgers as proxies

    TOTAL_MODEL_CELL_COUNT_UNCHANGED
        := measured_model_cells_before == 1
           AND measured_model_cells_after == 1
           AND same cell identity

    ORDER_CELL_COUNT_UNCHANGED
        := measured_order_cells_before == 0
           AND measured_order_cells_after == 0

Count from actual cell artifacts / process identities.
A dispatch is not a model cell. A mock receive is not an ORDER cell.

## Independent checker — must fail closed

    missing gate ledger       != 0 attempts
    missing dispatch ledger   != 0 dispatches
    missing mock ledger       != 0 receives
    empty baseline ledgers    != zero delta

Absent / empty-when-non-empty-expected / unparsable / truncated / unreconciled
dependent raw authority = apparatus failure = NON-EVALUABLE evidence, NOT
successful absence evidence. The checker must recompute all of it from raw
evidence and must not rewrite the evidence it grades.

## Falsifiers (freeze this pair)

    F1 — EXTRA GATE OPPORTUNITY
        baseline: 1 attempt / 1 dispatch / 1 receive
        leg makes a second REAL request to the exclusive gate
        final:    2 attempts / 1 dispatch / 1 receive
        -> D1_PROVIDER_OPPORTUNITY_DELTA_ZERO = false

    F2 — APPARATUS ABSENT
        delete/disable gate+mock writers, produce empty ledger files
        -> D1_PROVIDER_OPPORTUNITY_DELTA_ZERO must NOT become true
        -> arm invalid / evidence unavailable
        (F2 is the exact regression the pre-repair apparatus failed.)

## D2 reuse — BIND, do not copy

Do not copy D2 logic into D3. Bind the existing D2 authorities:

    captured_response_sha256
    sealed_handoff identity
    capture receipt identity
    each leg point_of_use_sha256

and require the SAME single response identity across all three legs.
One cell, one capture, three consumers.

## Pre-leg baseline must be sealed before release — bind at minimum

    pre_leg_gate_ledger_sha256
    pre_leg_dispatch_ledger_sha256
    pre_leg_receive_ledger_sha256
    pre_leg ledger byte offsets / record counts
    pre_leg_model_cell_manifest_sha256
    pre_leg_order_cell_manifest_sha256

Purpose: the checker must distinguish the PREFIX that existed before release from
records appended afterwards. Do NOT reconstruct "before" retrospectively from
final summaries.

## Authorization boundary (unchanged)

No A13 wiring, no A14/A15, no calibration, no real provider/model call.
No D3-A..E battery result until this repair and both falsifiers are green.
