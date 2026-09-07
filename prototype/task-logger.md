# Per-task logger

Every evaluated task produces one metrics record. These records are the raw
material for the Fam-C cost-decay curves and the paper's compounding figure.

## Record schema (JSONL, one line per task)

```json
{
  "task_id": "r07",
  "family": "R",
  "run_id": "<run artifact dir id>",
  "verdict": "ship",
  "latency_s": 42.5,
  "cost_units": 1.0,
  "capabilities_reused": ["jsonl-log-writer"],
  "capabilities_proposed": [],
  "timestamp": "2026-09-07T00:00:00Z"
}
```

| Field | Meaning |
|---|---|
| `cost_units` | Normalized cost (tokens, seconds, or API units — one numeraire per experiment, declared in the run's `EVAL.json`) |
| `capabilities_reused` | Registry ids actually selected this task |
| `capabilities_proposed` | New candidates surfaced this task (promotion pipeline input) |

## Rules

1. The logger writes into the **run artifact dir** (`task-metrics.jsonl`), never
   into `benchmarks/` or `prototype/` directly.
2. Aggregation scripts read across run dirs to build Fam-C curves — runs stay
   immutable, analysis is a pure function of them.
3. `cost_units` numeraire must be fixed before an experiment starts and recorded
   alongside it; switching numeraires mid-trajectory invalidates the curve.

## TODO (pilot landing)

- [ ] Land the logger implementation from the pilot
- [ ] Fix the `cost_units` numeraire for the first Fam-C run
- [ ] Add the aggregation script (`benchmarks/fam-c/aggregate.py`, staged)
