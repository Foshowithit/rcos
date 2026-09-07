# RCOS paper — 12-section skeleton (stubs)

> Stage 1 fills §§1–5 + §11 as definitions/protocol. §§6–10 await Fam-C/Fam-N
> data (stage 2). No section gets claims without linked evidence.

## 1. Introduction
STUB. Problem: single-shot agents plateau; per-task engineering does not
compound. Thesis: workflows first, capabilities as the compounding asset,
eval-driven promotion *and retirement*. Roadmap of the paper.

## 2. Related work
STUB. Workflow orchestration systems; agent role-spec frameworks (incl. Pi
AgentSpecs); skill-library and continual-learning agents (Voyager, FlowEvo,
AWM); eval-gated promotion / quality gates. For each: what RCOS reuses vs the
narrow novelty (heterogeneous executable capabilities under a workflow-first
control plane with promotion + retirement, tested longitudinally).

## 3. Definitions and system boundaries
STUB. Capability, workflow, eval gate, registry, promotion, retirement, reuse.
What RCOS is (thin wiring + gates + benchmarks) vs what it delegates to
Pi / DSH / Archon. Non-goals: no training, no weights, no vendoring.

## 4. Architecture
STUB. Control (DSH General) → compiler (WM + workflow-engineer) →
orchestration (Archon DAGs) → execution (Pi AgentSpecs + code/model tiers) →
evaluation → registry. Memory isolation (layered memory + run artifact dirs).
Mirrors ARCHITECTURE.md; figure: control-flow diagram.

## 5. Eval protocol (pre-registered)
STUB. Fam-R / Fam-C / Fam-N definitions; EVAL.json gate; ship/fix/blocked
semantics (blocked never counts against promotion); two-ship admission rule;
retirement rule; cost numeraire; control vs treatment design for Fam-C;
transfer + harm metrics for Fam-N.

## 6. Prototype implementation
STUB (stage 2). Registry schema, gate wiring, router reuse hook, task logger —
as built, with deviations from §5 logged explicitly.

## 7. Fam-R results
STUB (stage 2). Per-task verdicts table + logs link. Baseline sanity: tasks are
solvable, checkers sound.

## 8. Compounding experiment (core result)
STUB (stage 2). Fam-C cost-per-task curves, treatment vs control, reuse-rate
over time, retirement events. The overtaking figure — or its failure, reported
with equal prominence.

## 9. Generalization (Fam-N)
STUB (stage 2). Held-out transfer results, harm check outcomes, registry
snapshot id used.

## 10. Ablations and cost accounting
STUB (stage 2). Registry-off, retirement-off, reuse-logging-off; total compute
and subscription-only cost discipline.

## 11. Limitations and threats to validity
STUB (stage 1 draft, expanded stage 2). Single-machine lineage, lane
dependence, benchmark-distribution bias, registry-gaming risks, what would
falsify the thesis.

## 12. Conclusion
STUB. What was shown, what remains open, how to reproduce (repo + commit hash +
run dirs).
