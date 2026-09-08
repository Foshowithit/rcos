# fam04-T0 — validate DAG, emit topological order
Read `graph.json` ({nodes, edges}). Verify acyclicity, then write
`OUTPUT.json` `{"valid": true, "order": [...]}` with a valid
topological order. If cyclic, write `{"valid": false, "cycle": [...]}`
tracing the cycle back to its start.
