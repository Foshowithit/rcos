# evals/

Two layers, deliberately separate:

- `evals/<eval-id>/` — a **definition**. What to run and what must hold.
- `runs/<run-id>/` — an **execution**. What actually happened, hashed.

## A definition (`evals/<eval-id>/`)

```
evals/<eval-id>/
  eval.json        schema rcos-eval/1: eval_id, capability_id, adapter, fixtures, gates
  fixtures/        inputs the adapter copies into its work dir
  adapter/run.js   produces evidence; forms no opinion
  gates/check.js   reads the evidence; returns pass/fail per gate
```

A package is any directory here that contains an `eval.json` — `rcos evals`
lists only those. Two things are refused at load time: a fixture listed in
`eval.json` but missing on disk, and a definition in which **no gate is
required**. An eval where nothing must pass cannot ship; the schema will not
let you write one.

Gates encode the subject's *own stated policy*, not the behaviour observed
while writing the package — otherwise a gate is just a snapshot of a bug.

## An execution (`runs/<run-id>/`)

```
runs/<run-id>/
  manifest.json    eval_id, capability_id, run id, timing, adapter spec
  input.json       what the run was given (fixture hashes)
  output.json      what the adapter reported
  evidence/        the raw artifacts the adapter produced
  checks.json      each gate's argv, exit code, stdout, duration, status
  receipt.json     hashes of everything above — written last, hashes nothing of itself
```

Run ids look like `20260917T211412Z-92c41a`: sortable, collision-resistant.
A run directory is **immutable**. Reusing a run id is refused rather than
overwriting, and `rcos eval-verify --run <id>` re-hashes every artifact and
also fails on a file that is present in the run but absent from the receipt.

## Running

```
rcos eval-run --eval <eval-id> [--task <task>] [--submit]
rcos eval-verify --run <run-id>
```

The adapter and each gate run with their cwd set to the run's `work/`
directory. Any argv element starting with `./` resolves against the **eval
package** directory, so `["node", "./adapter/run.js"]` means the package's own
adapter. Children get `RCOS_HOME`, `RCOS_RUN_DIR`, `RCOS_WORK_DIR`,
`RCOS_EVIDENCE_DIR`, `RCOS_EVAL_DIR` and `RCOS_BIN` in the environment.

The verdict comes from exit codes, and only from exit codes: all required gates
pass → `ship`; a required gate fails while the execution itself was valid →
`fix`; the evaluation cannot establish a result because a prerequisite is
unavailable → `blocked`. `eval-run` exits 0, 3, 4 to match.

`--submit` records the eval against the registry with `provenance: executed`
and requires the capability to already exist there — checked before the run is
spent. Without `--submit` a package still runs and still writes its evidence
to `runs/`; that is how kernel-invariant evals (which name no registered
capability) are exercised. An eval run is not a reuse: the trace is appended
with `source: null` and `reuse_count` does not move.

## Legacy directories

The `study-round*` / `dogfood-check-*` directories here predate the runner and
hold a bare `RECEIPT.json` written by hand. They are **not** packages — no
`eval.json` — so they are invisible to `rcos evals` and nothing rewrites them.
Their receipts are assertions; the registry labels them that way. They are left
in place as history rather than backfilled, because retro-fitting a provenance
label onto evidence nobody re-ran would be a lie with extra steps.
