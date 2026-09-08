# fam03-T1 — dedup by action+target identity
Count data rows in `events.csv` (skip header). Identity = (action,target)
pair. Emit `OUTPUT.json`: `{total, unique, removed}`.
