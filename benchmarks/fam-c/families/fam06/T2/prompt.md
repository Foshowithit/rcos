# fam06-T2 — reconcile pipe files, asymmetric coverage
Match `a.psv` (`id|amount`) against `b.psv`. Expect one-sided gaps.
Same output contract in `OUTPUT.json`:
`{matched:[ids], missing_in_b:[ids], missing_in_a:[ids], conflicts:[{id,a,b}], unreconcilable:[ids]} (entries that cannot be compared on one consistent basis go under `unreconcilable`)`.
