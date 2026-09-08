# fam04 T4 near-neighbor null
Surface: same DAG-validation shape. Flipped invariant: the graph has a
CYCLE (a→b→c→a), so it is not a valid DAG. Blind topological-sort-only
validation passes it; correct behavior reports invalid with the cycle.
Checker asserts `{"valid": false, "cycle": ["a", "b", "c", "a"]}` exactly.
