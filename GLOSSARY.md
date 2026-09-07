# RCOS Glossary (frozen v1 — repo canonical)

Eight concepts. Everything else in this repo is defined in terms of these.
Quoted grounding points at the doc that owns each meaning.

- **Capability** — a reusable, versioned, eval-gated unit of behavior: a prompt
  template, script, model-node config, agent team, or workflow. Lives in
  `capability-registry.json` with lineage (derived_from, created_by_run,
  supersedes), eval history, usage counters (eligible, reused, rejected),
  economics (expected cost/latency), and lifecycle state. (ARCHITECTURE.md §6)
- **Workflow** — a durable, resumable DAG of typed nodes executed by the
  procedural runtime (Archon backend #1). Nodes are deterministic code, bounded
  model calls, stateful agents, or child workflows. (ARCHITECTURE.md §3)
- **AgentSpec** — a reusable specialist configuration consumed by agent nodes:
  runtime, role/prompt, model, tool allowlist (fail-closed), lazy skills,
  fail-closed permissions, context policy, memory scope, session persistence,
  compaction policy, pinned objective + completion criteria. (ARCHITECTURE.md §4)
- **Eval** — a deterministic check suite plus rubric scoring over one execution,
  returning `ship` / `fix` / `blocked`. Gates are defined BEFORE the run; every
  run emits a verdict with quoted artifact evidence. (ARCHITECTURE.md §3, §6)
- **Promotion** — admission of a `candidate` capability to the shared registry.
  Pilot rule: eval gate returns `ship` on two distinct tasks, both verdicts
  recorded with run ids, router reuse wired, retirement policy armed at
  admission. Statuses: `candidate` → `promoted` → `retired` (tombstoned with
  reason). (prototype/promotion-gate.md)
- **Reuse** — a router selecting a promoted capability for a new task and
  executing it, logged per task with the selected/rejected decision. Reuse
  that is measured, not assumed, is what compounding claims rest on.
  (prototype/router-reuse-hook.md)
- **Retirement** — removal of a live capability from eligibility when its
  rolling eval mean decays below threshold or it goes N tasks eligible but
  unselected. Promotion without retirement is hoarding. (ARCHITECTURE.md §6)
- **RCOS IR** — the neutral intermediate representation between cognitive
  control and procedural runtime. Defined in `ir-v0.1.md`. Backends compile
  from it; nothing above it may assume a specific backend.

Change rule: these definitions are frozen for the vertical slice. Corrections
require a documented reason and the smallest edit that fixes the deficiency.
