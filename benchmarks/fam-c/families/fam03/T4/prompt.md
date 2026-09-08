# fam03-T4 — transitions are NOT duplicates (near-neighbor null)
Count lines in `events.txt`. Here repeated ids are legitimate STATE
TRANSITIONS (CREATED→PAID→SHIPPED), each line a distinct event: do NOT
deduplicate. Emit `OUTPUT.json`: `{total, unique, removed}`.
