# RCOS — conservative abstract (draft, stage 1)

Single-shot language-model agents plateau: each task starts from scratch, and
engineering effort spent on one task rarely transfers to the next. We describe
RCOS, a Recursive Capability Operating System that treats durable workflows —
not individual agent runs — as the primary abstraction. In RCOS, a cognitive
control surface compiles intent into procedures, a durable orchestration layer
executes them, isolated execution tiers carry out steps, and every execution is
scored by an evaluator. Behavior that ships repeatedly is promoted into a
shared capability registry through an eval gate requiring two shipped results
on distinct tasks; behavior whose scores decay is retired. Capabilities are
heterogeneous — prompt templates, scripts, model-node configurations, agent
teams, whole workflows — and reuse is logged per task so compounding is
measured rather than assumed.

We do not claim that any component is novel in isolation: workflow
orchestration, agent role specifications, and eval-gated promotion each have
established literatures, which we survey. The hypothesis under test is
longitudinal and falsifiable: an RCOS instance should start no better than a
fixed-harness baseline, then overtake it on cost-per-task as its registry
accumulates, and transfer part of that advantage to held-out tasks. We
pre-register the benchmark families (Fam-R reproducible, Fam-C compounding,
Fam-N novelty), the promotion rule, the retirement rule, and the cost
numeraire before running the experiment. Results will be reported in the
stage-2 empirical paper; this preprint locks the definitions, boundaries, and
protocol.
