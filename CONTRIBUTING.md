# Contributing to RCOS

## Ground rules

- **Small, reviewable PRs.** One capability, one benchmark family, or one paper
  section per PR. Large PRs are closed with a request to split.
- **Verify, don't assert.** Every behavioral PR includes artifact evidence:
  checker logs, `EVAL.json` verdicts, or fresh-clone smoke output. Presence of a
  file is not success.
- **No vendoring.** PRs that copy Pi, DSH, or Archon source into this repo are
  rejected. Reference via env vars (`PI_CHECKOUT`, `DSH_CHECKOUT`,
  `ARCHON_CHECKOUT`) and document the interface instead.
- **No hype in the paper.** Conservative claims only; numbers need benchmark logs.

## Security hygiene (merge requirement)

- **Never commit:** API keys, tokens, credentials files, `auth.json`, vault
  contents (`.agent-vault/`), filled `.env` files, private keys.
- `.env.example` carries **placeholders only**.
- CI runs a secret-grep on every PR. If it flags your diff, the PR is blocked
  until history is clean (rebase/squash the secret out — deleting it in a later
  commit is not enough).
- **Report vulnerabilities privately.** See [SECURITY.md](SECURITY.md). A public
  issue that describes a live sandbox escape or a leaked credential *is* the
  incident — report it privately rather than opening an issue.
- Before pushing, run the same check locally:

```bash
git grep -n -i -E '(^|[^A-Za-z0-9])sk-[A-Za-z0-9]{8,}|(^|[^A-Za-z0-9])gh[op]_[A-Za-z0-9]+|api[_-]?key[[:space:]]*[:=][[:space:]]*["A-Za-z0-9/+_=-]{8,}|bearer [A-Za-z0-9_.-]{8,}|BEGIN (RSA )?PRIVATE KEY' -- . ':!.git' || echo "CLEAN"
```

## Commit hygiene

- `main` is the trunk; branch per PR (`feat/...`, `bench/...`, `paper/...`, `fix/...`).
- Messages: imperative, scoped — e.g. `bench(fam-r): add fix-loop task r09`.
- Keep commits small with clear messages; rebase before merge.

## Benchmark contributions

- New Fam-R tasks: one dir per task under `benchmarks/fam-r/tasks/<id>/` with
  `prompt.md`, `check.sh` (exit 0 = pass), and `EVAL.json` (gate thresholds).
- Register the task in `benchmarks/fam-r/tasks.json` and run
  `python3 benchmarks/schema_check.py` plus the task's own checker before opening the PR.

## Running the smoke tests

The harness smoke suite is `harness/tests/` — 37 standalone scripts, one per
boundary, each runnable on its own and exiting non-zero on failure:

```bash
for f in harness/tests/smoke_*.py; do
  python3 "$f" > "/tmp/$(basename "$f" .py).log" 2>&1
  echo "$(basename "$f" .py) rc=$?"
done
```

Run it from a checkout that contains **both** `harness/` and `benchmarks/`. The
scripts import harness modules and build benchmark fixtures, so a partial
checkout fails on missing prerequisites rather than on defects — that reads
like a broken test but is not one. Nine of them exercise the Docker sandbox
(`harness/dockersandbox.py`), so they need a working `docker`.

The suite takes roughly 12 minutes end to end, dominated by
`smoke_h25_readiness` and `smoke_h27_d5` at a few minutes each; give the
per-test timeout headroom. Quote the sweep summary — `TOTAL=n ZERO=n` — in a PR
that touches `harness/`, rather than asserting that a file exists.

## Capability proposals

- Open an issue with the **capability-proposal** template first. New registry
  entries require two shipped evals on distinct tasks (see
  `prototype/promotion-gate.md`) — proposals without eval evidence stay open as
  drafts.

## Conduct

Be decent — [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Assume good faith, critique
the work, and keep discussion technical.
