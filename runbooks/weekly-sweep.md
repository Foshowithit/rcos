# Weekly curator sweep

The habit engine of the Mac cell. Every Monday 09:00 local, the curator
sweep fires; every Sunday 18:00 local, the registry audit fires. Heavy
follow-up passes go to idle-time runs (off-peak queue, no plan-quota cost).

## Sweep (Monday 09:00)

Invoke the `zcode-rcos-curator` agent with this runbook path. It mines the
week's real work for 3+ recurrences (git histories, new memory files since
the sweep marker, ledger diffs), proposes candidates through `bin/rcos`
with lineage, writes README + EVAL.json per proposal, and updates the
sweep marker. Full protocol lives in the curator agent file — this runbook
is the schedule + handoff, not a duplicate.

Sweep marker: `runbooks/.sweep-marker` (contains the last-sweep date
`YYYY-MM-DD`; the curator advances it each run; committed with the sweep).

## Audit (Sunday 18:00)

Run `bin/rcos audit` in `/Users/adam26/zcode-rcos`. If WARNs decay toward
retirement (rolling failures, >90d stale), invoke `zcode-rcos-curator`
for a decay recommendation; the operator retires via `rcos retire --reason`.
Commit the audit result.

## Cron prompts (exact texts registered via CronCreate)

### Sweep prompt (weekly, Monday 09:00 local)

> RCOS Mac-cell weekly curator sweep. Invoke the `zcode-rcos-curator`
> agent with runbook `/Users/adam26/zcode-rcos/runbooks/weekly-sweep.md`:
> mine this week's real work across project dirs for behaviors that recurred
> 3+ times with a stable shape, propose candidates through
> `/Users/adam26/zcode-rcos/bin/rcos` with lineage (README + EVAL.json per
> proposal), log reuses for existing capabilities via
> `bin/rcos reuse-log --id <id> --task <task> --run <run> --verdict ship|fix|blocked`
> (a reuse is a trace, never a manual counter bump), advance the sweep marker
> in `runbooks/.sweep-marker`, run `bin/rcos audit`, and commit one batch.
> Curator proposes only — never evals, never promotes. Verdict = oracle +
> RECEIPT, never prose. No keys in the repo. No Dell writes. No paid lanes.

### Audit prompt (weekly, Sunday 18:00 local)

> RCOS Mac-cell weekly registry audit. In `/Users/adam26/zcode-rcos` run
> `bin/rcos audit`; if decay WARNs point at retirement, invoke the
> `zcode-rcos-curator` agent for a decay recommendation, then retire only
> via `bin/rcos retire --id <id> --reason <text>` with the reason recorded.
> Commit the audit result. No keys in the repo. No Dell writes.

## Automation ids

- Sweep: `automation-f62e750b-e22a-486a-a32f-f8efaa4c57e3` (registered 2026-09-15)
- Audit: `PENDING — register from a fresh session (CronCreate allowed only one creation in the build session); exact prompt preserved in the "Cron prompts" section above`

## Reuse triggers

Log reuses immediately when the real work happens — a reuse is a **trace**, not
a counter bump. From `/Users/adam26/zcode-rcos`:

```
bin/rcos reuse-log --id <id> --task <what the task actually was> \
  --run <run id or receipt path> --verdict ship|fix|blocked [--context <text>]
```

`--task` and `--run` are the evidence: the number moves only because a trace
line exists behind it. Then a git commit. The registry's `reuse_count` is a
cache of the trace log — `bin/rcos sync` re-derives it and `bin/rcos audit`
warns if it drifts.

| capability | reuse event | command |
|---|---|---|
| `operator-ui-contract-test` | after every real `node scripts/check.js` pre-push run in dsh-operator-ui | `bin/rcos reuse-log --id operator-ui-contract-test --task <repo+what was checked> --run <check.js output or commit> --verdict ship` |
| `filmstrip-verify` | after every real 6-frame video verification | `bin/rcos reuse-log --id filmstrip-verify --task <film+6 frames verified> --run <filmstrip path> --verdict ship` |
| `browser-verify-artifacts` | after every real archived browser proof | `bin/rcos reuse-log --id browser-verify-artifacts --task <what was verified in-browser> --run <archive path> --verdict ship` |
| `muse-image-lane` | after every real lane image delivery | `bin/rcos reuse-log --id muse-image-lane --task <prompt/subject> --run <image path> --verdict ship` |
| `dell-gpu-dispatch` | after every real Dell render dispatch | `bin/rcos reuse-log --id dell-gpu-dispatch --task <render dispatched> --run <Dell job/output path> --verdict ship` |
| `qr-camo-embed` | after each real QR camo embed use | `bin/rcos reuse-log --id qr-camo-embed --task <target image> --run <output path> --verdict ship` |
| `chalk-capture-recipe` | after each real chalk capture use | `bin/rcos reuse-log --id chalk-capture-recipe --task <scene captured> --run <capture path> --verdict ship` |
| `hog-qa-suite` | after each real HOG QA suite run | `bin/rcos reuse-log --id hog-qa-suite --task <suite run> --run <suite output> --verdict ship` |
