# fam06-T3 — reconcile env files, full agreement
Match `a.env` (`id=amount`) against `b.env`. Same output contract in
`OUTPUT.json`:
`{matched:[ids], missing_in_b:[ids], missing_in_a:[ids], conflicts:[{id,a,b}], unreconcilable:[ids]}` (entries that cannot be compared on one consistent basis go under `unreconcilable`).
