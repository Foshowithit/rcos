# fam01-T3 — INI-style record normalization

Normalize `input.env` (`[id]` sections with `name`/`usd`/`tags` keys;
`tags` may be absent) to canonical JSON: a list of
`{id, name, amount_cents (integer), tags (list)}`.
Write the list to `OUTPUT.json`.
