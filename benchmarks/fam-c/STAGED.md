# Fam-C — compounding series (STAGED TODO)

**Status:** schema defined, no tasks yet. Task content lands after the Fam-R
pilot + promotion loop are live, because Fam-C measures the loop, not fixtures.

## Planned design

- **Series:** replay a task family (e.g. log-wrangling, config repair) with
  seeded variations, 20–50 tasks per series.
- **Treatment:** router with the live promotion registry.
  **Control:** fixed harness (no registry, same models/lanes).
- **Logged per task** (see `prototype/task-logger.md`): `cost_units`,
  `capabilities_reused`, `verdict`.
- **Claim under test:** treatment cost-per-task decays below control over the
  series (the README's figure). Pre-register the numeraire (`cost_units` —
  wall-seconds or token counts, fixed before the run) and the decay statistic
  (e.g. mean of last-10 vs first-10) before running.

## TODO

- [ ] Pilot lands → promotion loop live
- [ ] Fix `cost_units` numeraire for series 1
- [ ] Write series task generator + `aggregate.py` (reads run dirs, emits curve CSV)
- [ ] Pre-register control vs treatment protocol in `paper/`
