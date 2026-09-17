# HOG QA headless suite pattern

## Contract
- Covers: pre-ship QA of the HOG CRANKERS game (and any `game-fleet/` web
  build served on localhost) — automated Playwright passes across the 5
  canonical scenarios (phone portrait gate, phone landscape ride, desktop
  ride crank, desktop pause/mute, tablet landscape ride) plus the
  hog-eyes sighted judge pass, before any wave ships.
- Does NOT cover: visual taste calls (the judge/Adam gates own those —
  this suite proves the game RUNS and holds fps, not that it looks good);
  non-web builds; load/soak testing; real-device testing (headless Chrome
  with `--use-angle=metal` only approximates a phone).
- Adapter: `game-fleet/qa/run-local.mjs` (node, playwright chromium
  channel:'chrome' headless, `--use-angle=metal`); optional scenario ids as
  args. Requires the game served at `http://localhost:8180/`.

## Gates (EVAL.json, >=2)
- g1 (`five-of-five`, deterministic): all 5 scenarios report `pass: true`,
  `fails: []`, and SUITE_PASS=true; fps >= 30 on ride scenarios.
- g2 (`judge-ship`, llm): sighted muse pass on the captured scenario frames
  returns a ship verdict (no broken geometry, no unreadable HUD).

## Attack case
- False-pass mode: the suite passes while the game is actually broken —
  e.g. a stale server serves an old build that passes last wave's checks,
  or a scenario silently no-ops (asserts removed) while still reporting
  `pass: true`.
- Caught by: g1 re-runs the real browser against the live server fresh each
  time (no cached report reuse; REPORT_DIR is timestamped per run), and
  console-error capture makes silent no-ops loud: any page error fails its
  scenario. A stale build still has to physically render, ride, and hold
  30+ fps in THIS run to pass.

## Lineage
- `game-fleet/qa/`; every shipped HOG CRANKERS wave went through it since
  the wave harness was stood up (09-12+). Headless first, eyes second,
  taste last — in that order, every wave.

## Eval log (append per ship; receipts live in evals/<run-id>/)
- 2026-09-17 eval-1 ship: full suite 5/5, 61fps ride scenarios, 44.9s wall.
  Evidence: `evidence/hog-qa-suite/eval-1/`.
- 2026-09-17 eval-2 ship: full suite 5/5 re-run, 61fps, 44.9s wall.
  Evidence: `evidence/hog-qa-suite/eval-2/`.
