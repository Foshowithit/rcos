# Slice 2 Results: Replication Under Procedural Barriers — SHIP (primitive)

## Three-arm outcome

|  | Arm 1 correct | Arm 2 forced-wrong | Arm 3 disabled |
|---|---|---|---|
| Outcome | ship, reuse=true | fix (predicted) | ship (baseline) |
| Mechanism | incident engine executed, output consumed | config engine executed cleanly, eval rejected every field | fresh solve, no registry |

The null test holds: benefit tracks the SPECIFIC procedure. The wrong
engine ran without error yet failed all six acceptance fields; a first
hostile attempt crashed outright (ValueError on domain-mismatched input) —
wrong-domain reuse fails loudly or wrongly, never usefully here.

## Barrier audit

- Prereg + T3 hash pushed before any solver/capability/run existed
  (public history proves ordering).
- Fresh workdirs; T3 arms contain only permitted inputs; router artifact
  committed.
- Single lane by operator order (muse-spark xhigh-attempt); cross-model
  separation NOT tested — procedural replication only, labeled as such.
- Same operator throughout (declared in PREREG). Residual hole per audit:
  needs A/B/C/D with independent models for the portability claim.

## Non-claims

Not compounding. Not publishable deltas. New family (no invoice/config
reuse). IR v0.1 needed zero patches this slice — expressiveness holds
across a second domain.
