# zcode-rcos — the Mac cell

ZCode's own organism on the Mac: this repo is the trophy case (capability
registry), `bin/rcos` is the one guarded path to it, and the standing
weekly sweep (curator) + judge loop is the habit engine. Faces are ZCode
Desktop + GooeyPi. Chow's Dell cell stays chow-only; both cells speak the
same registry schema (`github.com/Foshowithit/rcos`).

Design: `docs/2026-09-14-zcode-rcos-design.md` (copy of the approved spec).

## Commands

- `bin/rcos query [--status S] [--kind K] [--json]`
- `bin/rcos propose --id <id> --name <name> --kind <kind> [--version x.y.z] [--lineage <text>]`
- `bin/rcos eval-submit --id <id> --task <task> --verdict ship|fix|blocked --run <run> [--date YYYY-MM-DD]`
- `bin/rcos promote --id <id>` (x2-ship gate enforced)
- `bin/rcos retire --id <id> --reason <text>`
- `bin/rcos reuse-log --id <id> --task <task> --run <run> --verdict ship|fix|blocked [--context <text>] [--seconds <n>]`
- `bin/rcos sync [--force] [--json]` (re-derive the reuse cache from the trace log)
- `bin/rcos audit [--json]`
- `bin/rcos render [--out <path>]`

## Integrity rules

1. Verdict = oracle + RECEIPT, never prose.
2. Promotion needs 2 shipped evals **on 2 distinct task ids** — same-task
   repeats do not count (the point is transfer, not memorization), and every
   ship eval carries a run id (no run id, no admission). The CLI refuses
   otherwise.
3. `reuse_count` is a **cache of the trace log**, not independent truth.
   There is no manual increment path: `reuse-log` appends a `source=reuse`
   trace first and then re-derives the number, and `audit` warns when the
   stored value drifts from the derived one. Backfilled traces never count —
   they were reconstructed *from* the registry, so counting them would let the
   registry certify itself.
4. Retirement is **armed at admission**, never later — promotion without
   retirement is hoarding, and the registry must shrink as well as grow. The
   armed policy is `rcos-retire/1` with thresholds deliberately `null` until
   pilot data calibrates them.
5. Every mutation via the CLI, then a git commit.
