# Slice 3 Results: Cross-Lane Design, Procedural Execution — MIXED verdict

## Paired table (9 held-outs × 3 arms)

| arm | ships | fails |
|---|---|---|
| correct (capability executes, consumed) | 9/9 | 0 |
| forced-wrong (invoice engine, best-effort) | 0/9 | 9/9 FIX as predicted |
| disabled (fresh solve) | 9/9 | 0 |

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
