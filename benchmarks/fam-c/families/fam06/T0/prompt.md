# fam06-T0 — reconcile two CSVs by id
Match `a.csv` against `b.csv` on id. Write `OUTPUT.json`:
`{matched:[ids], missing_in_b:[ids], missing_in_a:[ids],
conflicts:[{id,a,b}]}`. Equal amounts match; unequal amounts conflict.
