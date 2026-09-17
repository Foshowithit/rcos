# Operator-error attempt — preserved, not deleted

What: PQ/fam05/T0/C (cell 3122872f) was executed on lane P by operator error.
In block PQ the C universe is the Q-lane (reciprocal producer) acquisition;
the authorized lane is Q.

What the machinery did (fail-closed, correctly):
- the P-lane manifest was refused by the state authority: INADMISSIBLE
  (manifest lane P != authorized Q) — the order did NOT advance on it;
- the correct-lane re-run was refused CHAIN-TERMINAL (a final grade may not
  be appended over).

Disposition: the attempt is preserved byte-for-byte here, out of the ordered
derived path, so the authorized Q-lane cell can execute. This attempt is NOT
estimand evidence and must not be reclassified as such.
