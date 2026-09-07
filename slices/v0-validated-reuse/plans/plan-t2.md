# plan-t2 (IR v0.1, reconstructed record — see ADAPTER-NOTE.md)

- objective: "Normalize tasks/t2-json/input.json to the canonical invoice schema with verified totals"
- inputs: {source: tasks/t2-json/input.json}
- outputs: {canonical: runs/t2/OUTPUT.json}
- acceptance: [checker tasks/check.py t2-json → SHIP]
- nodes:
  - id: solve (execution_class: deterministic, ref: runs/t2/solve_t2.py,
    memory_scope: run)
  - id: eval (execution_class: deterministic, ref: tasks/check.py,
    depends_on: [solve], memory_scope: run)
  - id: promote (execution_class: deterministic,
    ref: promotion rule (two shipped evals on distinct tasks),
    depends_on: [eval], memory_scope: run)
- memory: {workdir: runs/t2/ (fresh; no T1 artifacts), promotion: none yet}
- approval_gates: []
- capability_refs: [] (capability promoted BY this run, not used in it)
