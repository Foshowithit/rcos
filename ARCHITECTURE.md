# RCOS Architecture

This document maps each RCOS function to the open-source system that provides
it. RCOS itself is thin: interfaces, schemas, gates, and benchmarks. The heavy
machinery (models, agents, orchestration runtime) lives in Pi, DSH, and Archon,
which are **referenced, not vendored** — see INSTALL.md for the env-var wiring.

## 1. Cognitive control — DSH General

The entry point for intent. DSH General interprets the user's request, holds
conversation state, and decides whether a task routes to a workflow or is
handled inline. It does not execute multi-step work itself; it dispatches.

- Provides: intent parsing, routing decision, final receipt (`ship/fix/blocked`)
- Interface: task envelope `{task, context, constraints}` passed to the compiler

## 2. Procedural compiler — DSH Workflow Manager + workflow-engineer

The WM seat turns "actually do it" into a governed run. The `workflow-engineer`
role (plus router / builder / evaluator / verifier roles from the shared
agent-specs) compiles intent into an executable plan:

1. **Find** an existing certified workflow in the registry first.
2. **Compose** existing workflows into a DAG when one alone is close but inexact.
3. **Improve** a workflow when the gap is small (edit YAML, tighten a rubric).
4. **Build** new only when nothing fits — DAG design, node types
   (script vs model vs agent), schemas, validators, evaluators, repair loops,
   dry-run on a sealed fixture, then publish to the certification registry.
5. Ad-hoc agent work only when a workflow is overkill.

- Provides: plan DAG, node schemas, validators, repair loops
- Reuses: `~/.dsh/agent-specs/` roles (`router.md`, `builder.md`, `evaluator.md`,
  `verifier.md`, `workflow-engineer.md`, `PROMOTION.md`, `registry.json`)

## 3. Durable orchestration — Archon DAGs

Compiled plans execute as Archon workflows: durable, resumable, artifact-
producing DAGs. The live library (hundreds of YAMLs) already includes the eval
gate (`chow-eval-gate-v2`), the evals department (`chow-evals-dept-v1`), and a
capability estimator (`chow-capability-estimator-v1`) — RCOS treats these as the
execution substrate, not as code to copy.

- Provides: durable runs, per-node artifacts, run-scoped working directories,
  `EVAL.json` verdicts
- Interface: `archon workflow run <name> "<task>"`; results under run artifact dirs

## 4. Isolated execution — Pi AgentSpecs + code/model tiers

Leaf work happens in isolated tiers: Pi AgentSpecs (role configs with tools and
budgets), deterministic code/script nodes, and model-call nodes on configured
lanes (`~/.pi/agent/models.json`). Isolation matters: a capability under
evaluation must not leak state into, or read state from, unrelated runs except
through declared inputs.

- Provides: sandboxed step execution, lane selection, budget enforcement
- Reuses: `~/.pi/agent/agents/` (AgentSpecs), `~/.pi/agent/models.json` (lanes)

## 5. Memory isolation — scoped memory + run artifact dirs

Two layers, both append-only from the runner's perspective:

- **Layered memory:** global (human-curated, propose-never-rewrite), scoped
  (`roles/<name>.md`, `projects/<project>.md`, `workflows/<workflow>.md` with an
  `## inbox` for candidates vs `## standing` for promoted doctrine), and run
  memory (lives in the run artifact dir, referenced by run id, never copied).
- **Run artifact dirs:** every run gets its own directory; evaluators read from
  it, nothing else writes to it. Fresh-clone smoke tests rely on this property.

## 6. Promotion gate — registry.json + PROMOTION.md

The compounding mechanism. A capability (prompt template, script, model-node
config, agent team) enters the shared `capability-registry.json` only through
the gate:

- **Admit** after the eval gate returns `ship` **twice** on distinct tasks
  (the Fam-R pilot rule — see `prototype/promotion-gate.md`).
- **Reuse logging:** the router records every capability reuse per task, so
  compounding is measured, not assumed.
- **Retire** capabilities whose rolling eval scores decay below threshold or
  which go unused for N tasks. Promotion without retirement is hoarding.
- **Per-task metrics:** cost, latency, reuse count, verdict — logged by the
  task logger (`prototype/task-logger.md`), feeding the Fam-C decay curves.

## Data flow (one task's life)

```
intent → General → WM compiles DAG → Archon runs DAG → Pi/code/model executes
   → evaluator scores (ship/fix/blocked) → task logger records
   → ship ×2 → registry admits → router reuses → scores decay → retirement
```

## What RCOS does NOT do

- No model training, no fine-tuning, no weights in this repo.
- No vendored copies of Pi, DSH, or Archon — env-var pointers only.
- No secrets anywhere in the repo (enforced by CI grep + CONTRIBUTING rules).
- No hype claims: the overtaking hypothesis is tested by `benchmarks/`, and
  until Fam-C runs, it is a hypothesis.
