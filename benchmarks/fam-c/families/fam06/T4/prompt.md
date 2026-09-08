# fam06-T4 — reconcile two sources
Match `a.csv` against `b.csv` by id per the usual contract
(`{matched, missing_in_b, missing_in_a, conflicts}`).
Entries that cannot be compared on one consistent basis go under a
top-level `unreconcilable` list instead of being forced into a verdict.
Write `OUTPUT.json`.
