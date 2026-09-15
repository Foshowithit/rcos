# fam06-T1 — reconcile JSON orders vs shipments
Match `a.json` orders (`oid`/`amt`) against `b.json` ships (`id`/`total`).
Same output contract in `OUTPUT.json`:
`{matched:[ids], missing_in_b:[ids], missing_in_a:[ids], conflicts:[{id,a,b}], unreconcilable:[ids]} (entries that cannot be compared on one consistent basis go under `unreconcilable`)`.
