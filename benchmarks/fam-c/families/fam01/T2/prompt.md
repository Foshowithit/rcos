# fam01-T2 — pipe-delimited record normalization

Normalize `input.psv` (pipe-delimited, reordered columns) to canonical
JSON: a list of `{id, name, amount_cents (integer), tags (list)}`.
Write the list to `OUTPUT.json`.
