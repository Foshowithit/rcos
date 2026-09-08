# fam06-T4 — reconcile two sources
Match `a.csv` against `b.csv` by id per the usual contract
(`{matched, missing_in_b, missing_in_a, conflicts}`).
If the sources cannot be reconciled under one consistent unit basis,
emit `{"abstained": true, "reason": "...", "answer": ...}` with your
best independent answer instead.
