# RCOS Install

RCOS is a wiring project: it connects **your own checkouts** of Pi, DSH, and
Archon. This repo contains no copies of those systems and no credentials.

## Prereqs

| Tool | Check | Notes |
|---|---|---|
| `git` | `git --version` (≥ 2.30) | |
| `gh` | `gh auth status` | only needed to fork / open PRs |
| `python3` | `python3 --version` (≥ 3.10) | runs checkers + schema validation |
| `node` / `pnpm` | `node --version` | only if you touch web artifacts |

No paid services, no CI minutes, no API keys are required for the dry run.

## 1. Clone

```bash
git clone https://github.com/Foshowithit/rcos.git
cd rcos
```

## 2. Point RCOS at your stack

```bash
cp .env.example .env
```

Edit `.env` and set paths to **your own** checkouts (placeholders shown — the
file is git-ignored and must never be committed):

| Variable | Meaning |
|---|---|
| `PI_CHECKOUT` | Path to your Pi checkout (AgentSpecs, `models.json` lanes) |
| `DSH_CHECKOUT` | Path to your DSH checkout (`settings.yaml`, `agent-specs/`) |
| `ARCHON_CHECKOUT` | Path to your Archon checkout |
| `ARCHON_WORKFLOWS` | Path to your Archon workflow library (YAMLs) |
| `RCOS_RUN_DIR` | Where run artifact dirs go (default `./runs`, git-ignored) |
| `RCOS_MODEL` | `provider/model` lane id for model nodes (must be subscription/funded — never add paid keys to fund it) |

RCOS reads these at runtime and shells out / imports across the boundary.
Vendoring any of these trees into this repo (or into a PR) will be rejected in
review — see CONTRIBUTING.md.

## 3. Dry-run smoke (~5 min, no keys, no network beyond clone)

```bash
# 1. Validate every registry/benchmark schema in the repo
python3 benchmarks/schema_check.py

# 2. Run the Fam-R checker smoke on 2 sample tasks (pure local file ops)
python3 benchmarks/fam-r/run_checker.py --tasks r01,r02
```

Expected: `schema_check.py` prints `ALL SCHEMAS OK`, and each smoke task prints
`verdict: ship`. If either fails, open an issue with the `bug` template —
paste the full log, not a paraphrase.

## 4. Full Fam-R suite (optional, still local)

```bash
python3 benchmarks/fam-r/run_checker.py --all
```

All 15 tasks run their `check.sh` against fixture inputs; per-task `EVAL.json`
files are written under `runs/` (git-ignored), never into `benchmarks/`.

## 5. What is NOT set up here (staged TODOs)

- **Fam-C / Fam-N tasks** — schemas are defined in `benchmarks/`; task content
  lands after the pilot.
- **Live promotion loop** — `prototype/` holds the registry schema, gate wiring,
  reuse hook, and logger interfaces; the running pilot plugs in per
  `prototype/README.md`.
- **Paper draft** — `paper/` holds the outline + abstract + section stubs.

## Troubleshooting

- `schema_check.py` fails on JSON: run `python3 -m json.tool <file>` to locate it.
- `run_checker.py --tasks r01,r02` fails: confirm you run from the repo root and
  that `bash` is available for `check.sh` scripts.
- Anything mentioning Pi/DSH/Archon paths: those are *your* checkouts — this repo
  cannot fix a missing path. Verify each `*_CHECKOUT` dir exists first.
