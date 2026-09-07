# Slice 0 Results: Validated Capability Reuse — SHIP (primitive, not compounding)

## Comparison (both arms ship; the claim is reuse + cost structure, not success)

|  | T3-treatment (reuse) | T3-control (fresh) |
|---|---|---|
| Outcome | ship | ship |
| New code written | ~30-line TSV reader + 10-line field map | ~25-line standalone solver |
| Reusable core executed | YES (engine `cf62373d`, output consumed by eval) | n/a |
| Router | selected normalize-invoice-v1 (3/7 markers), rejected date-reformat-v1 with reason | disabled |
| History | fresh workdir: input + capability only | fresh workdir: input only |

Reuse is proven CAUSAL here, not selected: the engine's bytes (hashed)
executed, its output artifact was consumed by the eval, and the negative
control was considered and rejected. `selected ≠ executed ≠ consumed` —
the trace records all three, and only the third counts.

## What this demonstrates

A system converted experience from two earlier tasks into a separately
persisted, evaluated capability that was retrieved and really reused on an
unseen, materially different task (CSV → JSON → TSV; distinct naming,
ordering, missing/extra fields), independently of conversational memory
(fresh workdirs throughout).

## What this does NOT demonstrate (explicit non-claims)

- **Not compounding.** Nothing learned here helped acquire a further
  capability. The milestone is "Validated Capability Reuse," not recursion.
- **Not a publishable delta.** Same-author, script-level tasks, wall-clock
  differences meaningless at this scale. The T3 A/B harness exists and runs;
  Fam-C scales it to 20–30 tasks where statistics become possible.
- **Order deviation:** treatment ran before control (PREREG said control
  first). Same author throughout (declared in PREREG). Mitigations held:
  T3 held out by hash, mechanical grading, fresh workdirs, negative control.
- **Caching objection answered in advance:** T3 differs structurally (format,
  naming, ordering, junk fields); a memo of T1/T2 could not have produced
  the T3 output. The engine — not a template — executed.

## IR verdict (change-controlled, per slice rule)

IR v0.1 expressed everything the loop needed EXCEPT invocation semantics:
GPT's `capability_refs` sharpening (invocation_id, role executed|composed,
immutable impl resolution, consumed_by) is adopted as a v0.1 patch —
`capability_refs` now carries role + invocation, and the trace (not the IR
claim) is authoritative for reuse. No other IR change. No v0.2.
