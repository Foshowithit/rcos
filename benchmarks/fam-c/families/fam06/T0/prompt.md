# fam06-T0 — reconcile two CSVs by id
Match `a.csv` against `b.csv` on id. Equal amounts match; unequal
amounts conflict. Write `OUTPUT.json`:
`{matched:[ids], missing_in_b:[ids], missing_in_a:[ids], conflicts:[{id,a,b}], unreconcilable:[ids]} (entries that cannot be compared on one consistent basis go under `unreconcilable`)`.
