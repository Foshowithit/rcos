# Fam-C execution order (frozen; seeded shuffle, seed 20260907)

Family order: fam05, fam03, fam01, fam04, fam06, fam02.

Lane blocks (reciprocal, independent, report separately, no pooling):

- Block PQ: P produces, Q consumes.
  Lanes per downstream task: A (P→P + K), B (P→P no K).
  Then lanes: C (P→Q + K), D (P→Q no K).
- Block QP: Q produces, P consumes.
  Lanes per downstream task: A' (Q→Q + K), B' (Q→Q no K).
  Then lanes: C' (Q→P + K), D' (Q→P no K).

Within each family: T0, T1, PROMOTION, CAPABILITY_LOCK, T2, T3, T4.
Arm order per downstream task (fully enumerated): treatment lane
first (A, then C), then its paired control (B, then D):
T2 [A, B, C, D], T3 [A, B, C, D], T4 [A, B, C, D].
No forced-wrong arms in Fam-C execution (the Slice forced diagnostic
is frozen evidence, not rerun here; §21 optional probe not taken).
Do not reorder after seeing results. Record actual order in run
manifests; deviation voids the run.
