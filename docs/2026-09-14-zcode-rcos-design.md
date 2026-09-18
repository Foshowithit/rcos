# ZCode RCOS — the Mac cell

**Date:** 2026-09-14 · **Owner:** Adam · **Builder:** ZCode · **Status:** DESIGN — awaiting Adam's go

## 1. One paragraph

Chow has an organism on the Dell: DSH (face) → Archon workflows (habit engine) → RCOS capability registry (trophy case, eval-gated promotion). Adam's proposal: ZCode gets **its own organism on the Mac**, with **ZCode Desktop + GooeyPi** as the faces instead of DSH. This design defines that organism — the **Mac cell of RCOS** — using the exact public schema from `github.com/Foshowithit/rcos` so both cells speak the same language, while the habit engine is ZCode-native (skills, subagents, cron automations, idle-time runs) instead of a transplanted Archon.

## 2. Approaches considered

| | Approach | Verdict |
|---|---|---|
| **A** | **ZCode-native organism** — harness primitives as the engine + rcos-schema registry + eval gates + standing improve loop | **CHOSEN** — days to live, zero new daemons, runs on plan quota, schema-parity with chow |
| B | Archon transplant on Mac — run the Dell's engine locally | REJECTED — duplicates the Dell, another daemon on Adam's daily machine (past OOM pain), weeks of porting; Mac cell should complement chow, not clone it |
| C | Thin twin — registry + gate only, no loop | REJECTED — a filing cabinet, not an OS; "setup ur own rcos system" implies the recursion |

A ports B's **eval-gate conventions** (RECEIPT.json verdicts, EVAL.json gates, x2-ship promotion) so an engine swap later — if the organism ever outgrows session-bound runs — slots under the same registry without migration.

## 3. Mapping to chow's Dell stack

| Dell (chow) | Mac (ZCode) |
|---|---|
| DSH web UI — face, seats, sessions | **ZCode Desktop** (Adam ↔ ZCode) + **GooeyPi** (Pi / OMP / Prime worker lanes) |
| DSH General seat — cognitive control | ZCode sessions (me) |
| Archon — durable workflow DAGs | **Runbooks** (versioned md/yaml step-plans + acceptance gates) executed by subagents; recurrence via cron automations + idle-time runs; checkpointed by RECEIPT artifacts |
| chow-eval-gate-v1 | `rcos` CLI gate — deterministic gates first, LLM tiebreak, RECEIPT verdicts |
| capability registry (Dell) | `~/zcode-rcos/registry/capability-registry.json` — **same schema** (id/name/kind/version/status/admitted_after/evals/reuse_count/last_eval/retire_reason/retirement; `reuse_count` is a trace-derived cache, not independent truth) |
| Single-writer Dell | Mac cell never writes the Dell; Dell stays chow-only. Read-only comparison allowed later |

New `kind` values (schema-compatible — `kind` is a free string): `skill` · `subagent` · `script` · `runbook` · `automation`.

## 4. Components

Home: `~/zcode-rcos/` (own git repo; every registry mutation = a commit = the audit trail).

```
~/zcode-rcos/
  registry/capability-registry.json   # rcos-repo schema, two cells one schema
  capabilities/<id>/                  # README + impl pointer + EVAL.json + eval artifacts
  evals/<run-id>/                     # RECEIPT.json + metrics rows (eval-spec §5 schema)
  bin/rcos                            # THE ONE GUARDED PATH to the registry
  tests/                              # CLI contract tests (dsh-operator-ui check.js pattern)
  dashboard.html                      # `rcos render` — deterministic static view, opened for Adam
```

- **`rcos` CLI** — `query / propose / eval-submit / promote / retire / reuse-log / sync / audit / render`. Schema-validating; enforces the x2-ship gate mechanically (promotion with <2 SHIP receipts on 2 distinct task ids is refused); no keys ever stored.
- **ZCode skill `rcos`** (`~/.zcode/skills/rcos/SKILL.md`) — the protocol in my own hands: when to propose, how to eval, how to log reuse.
- **Subagents (separation of duties — builder ≠ judge, per Adam's doctrine):**
  - `zcode-rcos-curator` — weekly sweep: mine real work (git status across project dirs, ledgers, memory diff) for 3+ recurrences → propose candidates; runs decay audit.
  - `zcode-rcos-judge` — evaluates candidates against their EVAL.json; deterministic gates first, LLM tiebreak only on genuine ambiguity; ties count against.
- **Cron automations (the daemons):** weekly curator sweep; weekly registry audit. Heavy passes → idle-time runs (off-peak, no plan-quota cost).
- **GooeyPi extension `rcos-tools`** — registers registry tools (query / reuse-log / eval-submit) into the Pi/OMP agents GooeyPi fronts, all calling the same `bin/rcos`. GooeyPi becomes the operator window onto the Mac cell's worker lanes.

## 5. The loop (what makes it recursive)

```
real work happens (any face)
  → curator spots a 3+ recurrence  →  candidate registered (kind, impl pointer, EVAL.json)
  → judge runs evals               →  RECEIPT verdicts: ship | fix | blocked   (never prose)
  → 2nd SHIP, distinct task id     →  PROMOTED (admitted_after recorded, retirement armed)
  → promoted caps get reused (each reuse = a trace line via reuse-log;
    reuse_count is DERIVED from the append-only trace log, never hand-incremented)
  → rolling evals decay            →  RETIRED (reason recorded)
```

**Amended 2026-09-17 (invariant repair):** `reuse_count` was a mutable counter
in the first build; the 09-17 repair made it a cache of the trace log with no
manual increment path (see the 2026-09-17 evidence bundle), and promotion now
requires 2 distinct task ids and arms retirement at admission.

Worked example: Adam asks in ZCode Desktop for a weekly Shop-OS demo video. I register candidate `shopos-weekly-demo` (kind=automation, impl=CronCreate id + runbook + EVAL gates incl. Dell-side render receipt). Weekly runs emit RECEIPTs. Second SHIP → promoted, visible on GooeyPi lanes and `dashboard.html`. If quality decays two evals running → retired with reason.

## 6. Integrity rules (inherited, encoded)

1. **Verdict = oracle + RECEIPT, never prose** (the 09-04 chow-wrapper lesson).
2. **x2-ship promotion gate** — mechanically enforced by the CLI.
3. **Planted-bad integrity test** — 3 known-bad capabilities must be BLOCKED; one promoted bad = integrity fail, all wins that cycle void (eval-spec §6.3).
4. **Oracle hygiene** — oracles live outside task worktrees.
5. **Honest seeding** — proven past capabilities enter as `candidate` unless backed by ≥2 real past ship receipts; never retro-claim `promoted`.
6. **No keys in the registry. No Dell writes. No paid lanes** (MAKE-DONT-BUY). No deterministic LLM-routing — the CLI is tooling; judgment stays with models.
7. **Derived over editable** (added 09-17): anything the evidence can compute, the registry must not store as independent truth. `reuse_count` is derived from the append-only trace log; backfilled traces never count; `sync` repairs drift and refuses to zero an unverifiable cache.
8. **Retirement armed at admission** (added 09-17): promotion without retirement is hoarding. The armed policy (`rcos-retire/1`) carries `null` thresholds until pilot data calibrates them — an invented threshold is a check that cannot fail.

## 7. Day-one seeding (honest, from ZCode's proven work)

Candidates (real lineage exists, most with only 1 formal receipt → start as candidate): filmstrip video verification protocol · muse-image lane recipe · Dell GPU render/encode dispatch runbook · browser-verify web artifacts · QR-camo embed · chalk-explainer capture recipe · hog-crankers QA suite pattern · dsh-operator-ui contract-test pattern.

## 8. Phasing

| Phase | Ships | Gate |
|---|---|---|
| 1 | repo + CLI + registry schema + skill + seed inventory + contract tests | tests green, Adam sees dashboard |
| 2 | curator + judge subagents + sweep cron + **first real promotion** (dogfood) | one capability reaches promoted honestly |
| 3 | GooeyPi extension + `rcos render` dashboard polish | OMP agent queries registry live from GooeyPi |
| 4 (later) | `zcode` lane added to the RCOS-EVAL-SPEC program; cross-cell comparison with chow | separate spec amendment |

**Out of scope for v1:** Archon-on-Mac, builder-building-builder, benchmark program runs, any federation that writes across machines.

## 9. Open items to verify at build time (not blockers)

- GooeyPi user-level extension dir (bundled `extensions/` won't survive app updates; verify supported load path — else load via the hosted harness's own extension loader).
- Cron automations bind to this workspace — confirm sweep prompts fire with the right session context.
- Local model server stays disabled (standing rule); sweeps are text-light and swap-guard safe.
