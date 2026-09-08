# fam01-T0 — CSV record normalization

Normalize `input.csv` to canonical JSON: a list of
`{id, name, amount_cents (integer), tags (list)}`.
USD amounts convert at 100 cents; empty tags mean `[]`.
Write the list to `OUTPUT.json`.
