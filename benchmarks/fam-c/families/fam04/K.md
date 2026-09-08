# fam04 capability contract (K)

Reusable core: DAG validation — parse a graph, verify acyclicity,
emit a topological order.

PRECONDITIONS (all must hold for K to be applicable):
1. The input is promised acyclic (validation confirms, never discovers).
2. Edge semantics are "must-precede".
