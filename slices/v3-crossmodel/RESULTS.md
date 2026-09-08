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

## What this does NOT prove (the honest headline, audit-corrected)

**No success-rate benefit was observable at script scale** (correct 9/9,
disabled 9/9). The preregistered token/call efficiency endpoint became
**unevaluable** after the lane-collapse replacement execution, because
per-arm model usage was not preserved — marked unavailable, not zero.
The benefit hypothesis is therefore INCONCLUSIVE, not falsified.

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

## Audit findings adopted (no rerun)

- **B→C freeze not publicly proven**: capability, promotion, and C results
  share one execution commit, so history cannot exclude post-hoc fitting.
  Disclosed as part of the same-operator limitation. Fam-C rule: commit
  `B_ARTIFACT_LOCK.json` (id, version, impl+manifest SHAs, training
  receipts, builder identity) and PUSH before any held-out execution.
- **Adapters own most semantics here**: the generic map is near-identity
  and per-task adapters do parsing, discovery, and restructuring before
  the engine executes. Accurate claim: task-specific adapters composed
  with the frozen capability on nine unseen formats. Fam-C adapter
  boundary: adapters MAY parse syntax; adapters MAY NOT rename fields
  into canonical semantics, choose mappings, implement rules, or validate
  — that work belongs to the capability under test.
- **Weak null (schema-level failure)**: the incident engine fails at the
  output-schema level, showing domain specificity but not
  procedure-minus-procedure advantage. Fam-C null must be
  interface-compatible and same-domain with a wrong procedure (units,
  optionals, grouping, policy).
- **Lifecycle source of truth**: manifests now carry artifact facts only;
  `registry.json` owns lifecycle status (this manifest's stale
  `status: candidate` removed; registry already records promoted).
- **Reuse-field convention (adopted for Fam-C)**: `capability_selected`,
  `capability_executed`, `capability_consumed`, `reuse_validated`,
  `outcome`. Reuse attempt = consumed; successful reuse = consumed +
  SHIP; negative transfer = consumed + worse-than-control. Slice-3 trace
  rows predate this split and are read accordingly (forced rows:
  executed + consumed + FIX).
- **h05 vindication accepted**: generator-deterministic, hash-matched —
  a gitignore artifact, not a seal failure. Noted, no action.
