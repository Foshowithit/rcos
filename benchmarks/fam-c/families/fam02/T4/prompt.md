# fam02-T4 — paginated acquisition with declared policy
Same protocol over `pages/t1.json…`: follow `next`, retry via
`fetch.py`, log in `retry.log`, merge into `OUTPUT.json`.
A `POLICY` file in the task dir declares duplicate handling; follow it.
