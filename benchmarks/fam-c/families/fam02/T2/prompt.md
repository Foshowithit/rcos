# fam02-T2 — paginated acquisition, alternate layout

Same protocol as T0/T1 over `pages/r1.json…` (different page shapes).
Follow `next`, retry transient faults via `fetch.py`, log attempts in
`retry.log`, merge into `OUTPUT.json`.
