# plan-t3-control (IR v0.1, reconstructed record — see ADAPTER-NOTE.md)

- objective: "Normalize tasks/t3-tsv/input.tsv with the registry disabled (fresh-solve control)"
- inputs: {source: tasks/t3-tsv/input.tsv}
- outputs: {canonical: runs/t3-control/OUTPUT.json}
- acceptance: [checker tasks/check.py t3-tsv → SHIP]
- nodes:
  - id: solve (execution_class: deterministic, ref: runs/t3-control/solve_t3.py,
    memory_scope: run)
  - id: eval (execution_class: deterministic, ref: tasks/check.py,
    depends_on: [solve], memory_scope: run)
- memory: {workdir: runs/t3-control/ (fresh; input only, no capability)}
- approval_gates: []
- capability_refs: [] (registry disabled by design)
