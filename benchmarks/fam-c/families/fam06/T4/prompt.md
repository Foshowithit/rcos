# fam06-T4 — reconcile two sources
Match `a.csv` against `b.csv` by id. Same output contract in
`OUTPUT.json`:
`{matched:[ids], missing_in_b:[ids], missing_in_a:[ids], conflicts:[{id,a,b}], unreconcilable:[ids]}` (entries that cannot be compared on one consistent basis go under `unreconcilable`).
