# Fam-C execution order (frozen; seeded shuffle, seed 20260907)

Family order: fam05, fam03, fam01, fam04, fam06, fam02.

Two reciprocal blocks. Each block runs its four lanes to completion
before the next block starts. Block order: PQ first, QP second.
(Interleaving blocks would let observations in one direction inform
the other; sequential blocks with committed per-block receipts prevent it.)

Within each family: T0, T1, PROMOTION, CAPABILITY_LOCK, T2, T3, T4.

Arm order per downstream task (fully enumerated; base pair order
[treatment, control], flipped on alternate families to balance drift):

Block PQ (P produces, Q consumes):
- fam05: T2 [A,B,C,D], T3 [A,B,C,D], T4 [A,B,C,D]
- fam03: T2 [B,A,D,C], T3 [B,A,D,C], T4 [B,A,D,C]
- fam01: T2 [A,B,C,D], T3 [A,B,C,D], T4 [A,B,C,D]
- fam04: T2 [B,A,D,C], T3 [B,A,D,C], T4 [B,A,D,C]
- fam06: T2 [A,B,C,D], T3 [A,B,C,D], T4 [A,B,C,D]
- fam02: T2 [B,A,D,C], T3 [B,A,D,C], T4 [B,A,D,C]

Block QP (Q produces, P consumes; same pattern, primed lanes):
- fam05: T2 [A',B',C',D'], T3 [A',B',C',D'], T4 [A',B',C',D']
- fam03: T2 [B',A',D',C'], T3 [B',A',D',C'], T4 [B',A',D',C']
- fam01: T2 [A',B',C',D'], T3 [A',B',C',D'], T4 [A',B',C',D']
- fam04: T2 [B',A',D',C'], T3 [B',A',D',C'], T4 [B',A',D',C']
- fam06: T2 [A',B',C',D'], T3 [A',B',C',D'], T4 [A',B',C',D']
- fam02: T2 [B',A',D',C'], T3 [B',A',D',C'], T4 [B',A',D',C']

Lane key: A = P→P + K; B = P→P no K; C = P→Q + K; D = P→Q no K
(primed: producer/consumer swapped). No forced-wrong arms in Fam-C
execution (Slice forced diagnostic is frozen evidence, not rerun here).
Do not reorder after seeing results. Record actual order in run
manifests; deviation voids the run.
