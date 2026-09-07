# benchmarks/

Three families, one contract: every task has a **prompt**, a **checker**
(exit 0 = pass), and an **`EVAL.json`** gate. Verdicts are `ship/fix/blocked`.

## Fam-R — reproducible (runnable today)

15 deterministic tasks across three kinds:

| Kind | Ids | What they test |
|---|---|---|
| file-ops | r01–r05 | create/transform/validate files with exact expected bytes |
| repo-scan | r06–r10 | answer structural questions about a fixture repo |
| fix-loop | r11–r15 | repair a broken fixture so the checker passes |

Each task: `benchmarks/fam-r/tasks/<id>/{prompt.md, check.sh, EVAL.json}`.
Run: `python3 benchmarks/fam-r/run_checker.py --tasks r01,r02` (smoke) or
`--all`. Per-task `EVAL.json` results land under `runs/` (git-ignored), never
in `benchmarks/`. Task registry: `benchmarks/fam-r/tasks.json`.

## Fam-C — compounding (STAGED)

Repeated-task families measuring reuse rate and cost-per-task decay as the
registry fills. **Schema defined, tasks TODO** — content lands after the pilot.

- Design: each Fam-C series replays a task family with seeded variations;
  the router may reuse promoted capabilities; the logger records
  `cost_units` + `capabilities_reused` per task.
- Success criterion (the paper's core claim): RCOS cost-per-task decays below
  the fixed-harness baseline over the series. See `fam-c/STAGED.md`.

## Fam-N — novelty / generalization (STAGED)

Held-out tasks measuring transfer of promoted capabilities to unseen problems.
**Schema defined, tasks TODO.**

- Design: tasks drawn from outside the Fam-R/C distribution; scored by whether
  reused capabilities help or hurt vs a no-registry control. See
  `fam-n/STAGED.md`.

## EVAL.json gate (all families)

```json
{
  "task_id": "r01",
  "family": "R",
  "pass_threshold": 1.0,
  "verdict_map": {"pass": "ship", "fail": "fix", "error": "blocked"},
  "cost_numeraire": "wall_seconds"
}
```

`ship` = checker passed at/above threshold; `fix` = failed but retryable;
`blocked` = infrastructure error (not a capability failure — never counted
against promotion).
