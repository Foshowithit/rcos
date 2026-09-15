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
> proposal), log reuses for existing capabilities, advance the sweep marker
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
