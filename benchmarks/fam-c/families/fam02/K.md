# fam02 capability contract (K)

Reusable core: paginated acquisition — follow next-page tokens to
exhaustion with bounded retries, merge items, enforce latest-wins on
overlap only when the source declares versioning (it never does here).

PRECONDITIONS (all must hold for K to be applicable):
1. Pages are disjoint (no id appears on two pages with different values).
2. Page shapes are stable within a task (one envelope per task).
3. Faults, if any, are transient and declared in faults.json.
