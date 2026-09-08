# fam02-T4 — paginated acquisition
Same protocol over `pages/t1.json…`: follow `next`, retry via
`fetch.py`, log in `retry.log`, merge into `OUTPUT.json`.
If the pages cannot be acquired as a disjoint series, emit
`{"abstained": true, "reason": "...", "answer": ...}` with your best
independent answer instead.
