# fam04-T0 — validate DAG, emit topological order
Read `graph.json` ({nodes, edges}). The graph is promised acyclic:
verify that, then write `OUTPUT.json` `{"valid": true, "order": [...]}`.
If the input violates the acyclicity precondition, emit
`{"abstained": true, "reason": "...", "answer": ...}` with your best
independent answer instead.
