# Capability scaffold (fill every section, then propose)

Paste this into `capabilities/<id>/README.md` and fill it BEFORE writing code
or firing evals. The x2-ship gate promotes a *documented* capability, not a
vibe. Spec: docs/2026-09-17-scale-up-spec.md.

```markdown
# <Capability name>

## Contract
- Covers: <task contexts this capability applies to>
- Does NOT cover: <at least one adjacent context that should go elsewhere>
- Adapter: <how it runs — script path / skill / workflow command>

## Gates (EVAL.json, >=2, deterministic preferred)
- g1 (<deterministic|llm>): <the exact check>
- g2 (<deterministic|llm>): <the exact check>

## Attack case
- False-pass mode: <how this capability could appear to work while wrong>
- Caught by: <which gate catches it, and why that check cannot pass while wrong>

## Lineage
- <where it came from: which real task needed it, what preceded it>

## Eval log (append per ship; receipts live in evals/<run-id>/)
- (none yet — candidate)
```

Propose:

    rcos propose --id <id> --name "<name>" --kind <kind> --lineage "<one line>"

Then ship it twice on real tasks, submitting each eval with its trace:

    rcos eval-submit --id <id> --task <task-id> --verdict ship --run "<evidence note>" \
      --context "<what the task actually was>" --source reuse|synthesize --seconds <n>

Promote after two ships (EVAL.json must exist in the capability dir):

    rcos promote --id <id>
