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
- `bin/rcos reuse --id <id>`
- `bin/rcos audit [--json]`
- `bin/rcos render [--out <path>]`

## Integrity rules

1. Verdict = oracle + RECEIPT, never prose.
2. Promotion needs 2 shipped evals — the CLI refuses otherwise.
3. Every mutation via the CLI, then a git commit.
