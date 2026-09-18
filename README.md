# zcode-rcos — the Mac cell

ZCode's own organism on the Mac: this repo is the trophy case (capability
registry), `bin/rcos` is the one guarded path to it, and the standing
weekly sweep (curator) + judge loop is the habit engine. Faces are ZCode
Desktop + GooeyPi. Chow's Dell cell stays chow-only; both cells speak the
same registry schema (`github.com/Foshowithit/rcos`).

Design: `docs/2026-09-14-zcode-rcos-design.md` (copy of the approved spec).

## Commands

- `bin/rcos query [--status S] [--kind K] [--json]`
- `bin/rcos evals [--json]` (list eval packages; a package is a dir with an `eval.json`)
- `bin/rcos runs [--json]` (list executed runs and their verdicts)
- `bin/rcos eval-run --eval <eval-id> [--task <task>] [--submit]` (execute a package; exit 0 = ship, 3 = fix, 4 = blocked)
- `bin/rcos eval-verify --run <run-id>` (re-hash a run's receipt and its artifacts)
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
6. The **runner owns the verdict**. `deriveVerdict(adapterResult, gateResults)`
   is the only thing that writes one: adapters return evidence, gates return
   pass/fail, and neither can write a verdict. All required gates pass → `ship`;
   a required gate fails while the execution itself was valid → `fix`; the
   evaluation cannot establish a result because a prerequisite is unavailable
   → `blocked` (adapter exit 4, any other non-zero adapter exit, or a gate that
   crashes — a crashed gate is `blocked`, not `fix`). `eval-run`'s own exit code
   mirrors the verdict: 0, 3, 4.
7. A run directory is **written once**. An existing run id is refused, never
   rewritten. The receipt is written last, hashes every other artifact, and does
   not hash itself. `eval-verify` re-hashes all of it and fails on both a
   mismatch and a file present in the run but absent from the receipt — so an
   edited or planted artifact is detectable after the fact.
8. An eval entry's `provenance` is `executed` only when a runner run produced
   it, `asserted` otherwise — and absent means `asserted`, so every eval
   recorded before the runner is honestly labelled. Nothing is backfilled.
   `audit` warns (never errors) while promoted capabilities rest entirely on
   asserted evals. An eval run is **not** a reuse: `eval-run --submit` appends a
   trace with `source: null`, so `reuse_count` does not move.
9. `--submit` requires the capability to already exist in the registry, and that
   is checked *before* the run is spent. A kernel-invariant eval that names no
   registered capability still runs and still writes its evidence to `runs/` —
   it just cannot be submitted.
