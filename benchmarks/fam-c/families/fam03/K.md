# fam03 capability contract (K)

Reusable core: windowed dedup — count events, collapse repeats into
identity groups, emit {total, unique, removed}.

PRECONDITIONS (all must hold for K to be applicable):
1. Repeats are duplicates (same event observed twice), never distinct
   occurrences or state transitions.
2. Identity rule is fixed per task as stated in its prompt.
