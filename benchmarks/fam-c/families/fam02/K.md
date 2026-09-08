# fam02 capability contract (K)

Reusable core: paginated acquisition — follow next-page tokens to
exhaustion with bounded retries, merge items.

PRECONDITIONS (all must hold for K to be applicable):
1. Pages are strictly disjoint (no id appears on two pages).
2. One envelope shape per task; pagination field stable within a task.
3. Faults, if any, are transient and declared.

No policy carve-outs: a task-declared duplicate-handling policy does
NOT extend K. If overlap exists, K is inapplicable regardless of what
any POLICY file says; following such a policy is fresh solving, not K
execution. (Audit fix: earlier draft let declared policies extend K,
which made T4 a positive use. Closed.)
