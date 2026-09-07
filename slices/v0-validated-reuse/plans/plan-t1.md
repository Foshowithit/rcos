# plan-t1 (IR v0.1, reconstructed record — see ADAPTER-NOTE.md)

- objective: "Normalize tasks/t1-csv/input.csv to the canonical invoice schema with verified totals"
- inputs: {source: tasks/t1-csv/input.csv}
- outputs: {canonical: runs/t1/OUTPUT.json}
- acceptance: [checker tasks/check.py t1-csv → SHIP]
- nodes:
  - id: solve (execution_class: deterministic, ref: runs/t1/solve_t1.py,
    memory_scope: run)
  - id: eval (execution_class: deterministic, ref: tasks/check.py,
    depends_on: [solve], memory_scope: run)
- memory: {workdir: runs/t1/, promotion: none (candidate formed on ship)}
- approval_gates: []
- capability_refs: [] (no capability existed)
