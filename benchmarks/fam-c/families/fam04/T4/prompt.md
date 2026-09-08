# fam04-T4 — cyclic graph (near-neighbor null)
Read `graph.json`. Do NOT assume acyclicity: detect the cycle and write
`OUTPUT.json` `{"valid": false, "cycle": [...]}` tracing it back to start.
A bare topological sort that ignores the cycle is wrong.
