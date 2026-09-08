# fam02 capability contract (K)

Reusable core: paginated acquisition — follow next-page tokens to
exhaustion with bounded retries, merge items latest-wins ONLY where a
task-declared duplicate policy says so.

PRECONDITIONS (all must hold for K to be applicable):
1. Pages are disjoint unless a declared POLICY states otherwise.
2. One envelope shape per task; pagination field stable within a task.
3. Faults, if any, are transient and declared.
