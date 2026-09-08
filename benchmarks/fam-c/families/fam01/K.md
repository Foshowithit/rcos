# fam01 capability contract (K)

Reusable core: record normalization — parse one record per row/section,
coerce USD to integer cents, split tag lists, emit canonical
`{id, name, amount_cents, tags}` preserving input order.

PRECONDITIONS (all must hold for K to be applicable):
1. Every data row/section is a record (no aggregates, headers-as-data ok).
2. Amounts are plain USD decimals (no currency mixtures, no unknown units).
3. Tags, when present, are delimiter-separated strings.
