# fam01-T4 — normalize records file
Normalize `input.csv` to canonical JSON: a list of
`{id, name, amount_cents (integer), tags (list)}`.
If the file cannot be normalized as records, emit
`{"abstained": true, "reason": "...", "answer": ...}` with your best
independent answer instead. Write the result to `OUTPUT.json`.
