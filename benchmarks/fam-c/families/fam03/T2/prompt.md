# fam03-T2 — dedup JSON envelope by kind+target
Count events in `batch.json` (array under `events`). Identity =
(kind,target) pair. Emit `OUTPUT.json`: `{total, unique, removed}`.
