# Fam-C execution order (frozen; seeded shuffle, seed 20260907)

fam05, fam03, fam01, fam04, fam06, fam02

Within each family: T0, T1, PROMOTION, CAPABILITY_LOCK, T2, T3, T4.
Arm order per downstream task (fully enumerated, base rotation
[correct, forced, disabled] shifted by family index):
- fam05 (index 0): T2 [correct, forced, disabled], T3 [correct, forced, disabled], T4 [correct, forced, disabled]
- fam03 (index 1): T2 [forced, disabled, correct], T3 [forced, disabled, correct], T4 [forced, disabled, correct]
- fam01 (index 2): T2 [disabled, correct, forced], T3 [disabled, correct, forced], T4 [disabled, correct, forced]
- fam04 (index 3): T2 [correct, forced, disabled], T3 [correct, forced, disabled], T4 [correct, forced, disabled]
- fam06 (index 4): T2 [forced, disabled, correct], T3 [forced, disabled, correct], T4 [forced, disabled, correct]
- fam02 (index 5): T2 [disabled, correct, forced], T3 [disabled, correct, forced], T4 [disabled, correct, forced]

Do not reorder after seeing results. Record actual order in run manifests; deviation voids the run.
