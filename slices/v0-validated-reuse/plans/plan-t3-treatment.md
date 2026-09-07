# plan-t3-treatment (IR v0.1, reconstructed record — see ADAPTER-NOTE.md)

- objective: "Normalize tasks/t3-tsv/input.tsv by reusing promoted normalize-invoice-v1"
- inputs: {source: tasks/t3-tsv/input.tsv,
  capability: capabilities/normalize-invoice-v1 (impl sha256 cf62373d…)}
- outputs: {canonical: runs/t3-treatment/OUTPUT.json}
- acceptance: [checker tasks/check.py t3-tsv → SHIP]
- nodes:
  - id: route (execution_class: deterministic, ref: router.py,
    memory_scope: run)
  - id: adapt (execution_class: deterministic,
    ref: runs/t3-treatment/read_tsv.py + tsv_map.json (composed work),
    depends_on: [route], memory_scope: run)
  - id: execute-capability (execution_class: workflow,
    ref: normalize-invoice-v1 v1, depends_on: [adapt], memory_scope: run)
  - id: eval (execution_class: deterministic, ref: tasks/check.py,
    depends_on: [execute-capability], memory_scope: run)
- memory: {workdir: runs/t3-treatment/ (fresh; input + capability only)}
- approval_gates: []
- capability_refs:
  - {id: normalize-invoice-v1, version: 1, role: executed,
     invocation: t3-invocation-1}
  - {id: normalize-invoice-v1, version: 1, role: composed,
     invocation: t3-adapter (reader + field map)}
