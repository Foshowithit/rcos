# Router reuse hook

The router must prefer promoted capabilities when they fit — and record every
decision so compounding is **measured, not assumed**.

## Interface

On every task, the router emits one JSONL record per capability considered:

```json
{"task_id": "r07", "capability_id": "jsonl-log-writer", "decision": "reused|rejected|inapplicable", "reason": "fits log-writing step", "run_id": "<run>"}
```

- `reused` — capability selected for (part of) this task.
- `rejected` — eligible but passed over (why belongs in `reason`).
- `inapplicable` — task outside the capability's scope.

## Rules

1. Records append to the run artifact dir's `reuse-log.jsonl` (see
   `task-logger.md`) — never to a global mutable file during the run.
2. After the run, a merge step increments `reuse_count` in
   `capability-registry.json` for each `reused` record.
3. Rejection reasons are first-class data: the Fam-C analysis reads them to
   distinguish "registry ignored" from "registry irrelevant".

## TODO (pilot landing)

- [ ] Land the hook implementation against the pilot's actual router
- [ ] Confirm the JSONL schema against real pilot logs
- [ ] Wire the merge step into the pilot's post-run flow
