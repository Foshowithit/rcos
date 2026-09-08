# fam01-T1 — nested-JSON record normalization

Normalize `input.json` to canonical JSON: a list of
`{id, name, amount_cents (integer), tags (list)}`.
Keys differ from other instances; `labels` may be absent (means `[]`).
Ignore non-record fields. Write the list to `OUTPUT.json`.
