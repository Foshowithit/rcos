# Slice 3 — Paired Benefit Test (cross-model design aborted pre-run)

## Paired table (9 held-outs × 3 arms)

| arm | ships | fails |
|---|---|---|
| correct (capability executes, consumed) | 9/9 | 0 |
| forced-wrong (preregistered incident engine) | 0/9 | 9/9 FIX as predicted |
| disabled (fresh solve) | 9/9 | 0 |

## Null-arm correction (post-run, prereg unchanged)

The shipped run initially executed the wrong null: Slice-0
`normalize-invoice-v1` instead of the preregistered Slice-2
`extract-incident-v1`. The invoice outputs are preserved untouched as
`runs/arm-<id>-forced.json` (superseded evidence, not counted). The
corrected arm re-ran all nine held-outs through the exact frozen
`extract-incident-v1` engine (`runs/forced-incident/run_forced_incident.py`;
engine sha `10a8fa4eec0f…`, matching the committed blob): engine rc=0 on
all nine, shipment checker rc=1 on all nine. Corrected trace rows carry
`record_kind: forced-wrong-corrected` plus `supersedes_output_sha256`
pointing at the invoice outputs. Tally above counts only corrected rows.

## What this proves

- **Specificity**: wrong knowledge fails everywhere it is forced. Benefit
  tracks the specific procedure, not extra context.
- **Portability shape**: the artifact + interface sufficed for 9 unseen
  formats with no transcripts; router-equivalent selection was mechanical.
- **Prereg-first history**, sealed truth, fresh workdirs throughout.

## What this does NOT prove (the honest headline)

**No benefit-over-fresh-solving delta at this scale**: disabled ships 9/9
too. Script-scale tasks with a competent operator are too easy for success
rate to separate arms — exactly the limitation the audit predicted ("no
registry arm also ships"). The experiment measured specificity + reuse
mechanics correctly and found no compounding signal, because none could
appear here: single-look tasks, millisecond costs, same operator.

## Consequences (binding on next work)

1. Lane design collapsed to single session lane (Amendments 1–2):
   minimax/agnes outputs quarantined, B redone in-lane, delegation
   unavailable. Cross-model separation is UNTESTED — needs live B/C lanes.
2. Benefit measurement needs harder tasks (fresh solves must sometimes
   fail) and real cost accounting (tokens/calls/wall at model scale), or
   longitudinal repetition where reuse amortizes. That is Fam-C design,
   not another 3-task slice.
3. Do not run Slice 4 as another deterministic slice. Next: EITHER live
   cross-model lanes with model-cognition tasks, OR Fam-C longitudinal
   with cost curves. More script slices add no information.
