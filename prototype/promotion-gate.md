# Promotion gate

Admit a capability to `capability-registry.json` **only** when all of these hold:

1. **Two shipped evals on distinct tasks.** The eval gate (equivalent of
   `chow-eval-gate-v2`: deterministic checks + rubric scoring → `ship/fix/blocked`)
   returns `ship` for this capability on two different task ids. Same-task
   repeats do not count — the point is transfer, not memorization.
2. **Evals are recorded.** Both verdicts appear in the capability's `evals`
   array with `task_id`, `verdict: ship`, and the `run_id` pointing at the run
   artifact dir. No run id, no admission.
3. **Router reuse is wired.** The router logs every selection of this capability
   (see `router-reuse-hook.md`) so `reuse_count` moves after admission.
4. **Retirement is armed.** At admission, the capability gets a decay policy:
   retire when the rolling mean of its last 5 eval scores drops below the
   `EVAL.json` gate threshold, or after N consecutive tasks where it was
   eligible but never selected (default N=20). Promotion without retirement is
   hoarding — the registry must shrink as well as grow.

## Status values

- `candidate` — proposed, fewer than 2 shipped evals.
- `promoted` — admitted through the gate above.
- `retired` — decayed or unused; kept as a tombstone with `retire_reason`
  (history matters for the paper's trajectory analysis).

## TODO (pilot landing)

- [ ] Land live `capability-registry.json` with the Fam-R pilot's first entries
- [ ] Confirm the two-ship rule against actual pilot eval logs
- [ ] Settle the retirement N and decay threshold from pilot data
