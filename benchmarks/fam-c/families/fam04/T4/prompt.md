# fam04-T4 — validate graph file
Read `graph.json` and write `OUTPUT.json` with the validation result.
If the input violates the acyclicity precondition, emit
`{"abstained": true, "reason": "...", "answer": ...}` with your best
independent answer instead.
