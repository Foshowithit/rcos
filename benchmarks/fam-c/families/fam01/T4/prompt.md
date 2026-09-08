# fam01-T4 — CSV with aggregate row (near-neighbor null)

Normalize `input.csv` to canonical JSON: a list of
`{id, name, amount_cents (integer), tags (list)}`.
Not every row is a record: decide which rows qualify before emitting.
Write the list to `OUTPUT.json`.
