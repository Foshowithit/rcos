# fam03-T0 — dedup by exact line identity
Count events in `events.txt`. Identity = the full line. Emit `OUTPUT.json`:
`{total, unique, removed}` where removed = total - unique.
