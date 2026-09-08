# fam04 T4 design (auditor-facing; agents never see this file)

Null mechanism: the graph is cyclic, so DAG-topological K does not
apply; correct behavior reports the cycle. A solver that assumes
acyclicity (bare topo sort) claims valid and fails. Rejection of K is
recorded in the run trace, never in the output shape.
