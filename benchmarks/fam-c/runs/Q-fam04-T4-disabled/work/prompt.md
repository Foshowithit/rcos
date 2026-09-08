# fam04-T4 — validate graph file
Read `graph.json` and write `OUTPUT.json` with the validation result:
`{"valid": true, "order": [...]}` for a DAG, or `{"valid": false,
"cycle": [...]}` tracing any directed cycle back to its start.
