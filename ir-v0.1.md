# RCOS IR v0.1 (change-controlled — tiny by design)

The neutral plan format between cognitive control (DSH Workflow Manager,
backend #1) and procedural runtime (Archon DAGs, backend #1). A plan document
conforming to this schema compiles to exactly one executable DAG via a
backend adapter. Nothing above the IR may assume Archon, Pi, or DSH.

Status: v0.1, frozen for the first vertical slice. If the running loop proves
a deficiency, apply the smallest documented patch. No v0.2, adapter
framework, or conformance suite until one promoted capability is reused
through this schema and logged.

## Schema (fields)

- `objective` (string, required) — pinned goal, single sentence.
- `inputs` / `outputs` (maps, required) — named artifacts with shapes;
  outputs must name concrete paths or schemas, never "a report."
- `acceptance` (list, required) — criteria the eval gate checks; each maps
  to at least one gate, defined before the run.
- `nodes` (list, required) — each node:
  - `id` (string, required)
  - `execution_class` (required): `deterministic` | `model` | `agent` | `workflow`
  - `ref` — command/path for deterministic, model lane + prompt for model,
    AgentSpec name for agent, workflow name + inputs for workflow
  - `depends_on` (list of node ids; empty = entry node)
  - `memory_scope` — `turn` | `run` | `workflow` | `workflow-role`
- `dependencies` — implied by node `depends_on`; no separate edge list.
- `memory` — run-scoped working dir + promotion rule (inbox → standing).
- `approval_gates` (list) — human checkpoints; each names its node boundary
  and its approve/reject/rework decisions.
- `capability_refs` (list) — registry `capability_id/version` pairs this plan
  reuses; empty on a first-solve plan, non-empty on a reuse plan. Each entry
  carries `role: executed | composed | dependency` and an `invocation_id`.
  The reuse claim of any run is verified against the trace, never
  self-certified: the runtime must prove the resolved implementation
  (immutable hash) executed and its output artifact was consumed by a
  downstream node or the eval. `selected ≠ executed ≠ consumed` — only the
  last counts as reuse. (v0.1 patch, slice-0 proven need.)

## Tier rule (authoring time)

A node that can be `deterministic` must be. Bounded single judgments may be
`model`. Open-ended multi-step tool use may be `agent`. Composition of
existing certified behavior must be `workflow`. The class is chosen when the
plan is written, never guessed at runtime.

## Minimal example (reuse plan — the shape Task 3 must take)

```yaml
objective: "Reconcile ledger-A against statement-B using cap:reconcile-v3"
inputs:
  ledger: fixtures/ledger.json
  statement: fixtures/statement.json
outputs:
  report: artifacts/RECONCILIATION.json
acceptance:
  - reconciled totals match to the cent
  - every unmatched line cited with id + amount
nodes:
  - id: reconcile
    execution_class: deterministic
    ref: tools/reconcile.py
    memory_scope: run
  - id: review-gate
    execution_class: model
    ref: {lane: TO-FILL, prompt: "confirm no unmatched line lacks a citation"}
    depends_on: [reconcile]
    memory_scope: run
dependencies: []
memory: {workdir: run-artifacts/<run-id>/, promotion: inbox-then-standing}
approval_gates: []
capability_refs: [{id: reconcile-v3, version: 2, role: executed,
  invocation: run-041-invocation-1}]
```
