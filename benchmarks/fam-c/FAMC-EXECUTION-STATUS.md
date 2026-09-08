# Fam-C Pilot Execution Status — QUARANTINED / NOT GRADABLE

Date: 2026-09-08. This is a status boundary, not a result claim.

## Why execution is paused

The partial P/Q runs committed under this branch were launched by the
ad-hoc `harness-run/run_arm.py` helper, which called the provider endpoints
directly and did **not** yet execute model steps through the sealed H1
DockerSandbox boundary (`harness/dockersandbox.py`). H1 itself is sealed
and its 33/33 smoke is green, but the Fam-C runner has not integrated it.
Therefore these runs are preserved as evidence but are **not gradable Fam-C
estimand data**: do not use their success, cost, or reuse outcomes in a
headline.

## Preserved evidence

All existing `runs/` artifacts remain committed and untouched. They include
raw responses, prompts for later runner revisions, lane records, usage blocks,
solver arrivals, mechanical checker outcomes, and capability locks where a
capability was created. The branch history carries partial fam01/fam02/fam03/
fam04/fam05/fam06 work; malformed arrivals and model failures are retained,
not retried into a prettier record.

A direct tally currently contains partial records for 5 families; it is an
inventory only. Fam02 and Fam06 capability promotion attempts already
returned `fix` (the generated capability did not satisfy the frozen checker
contract), so no correct-arm lock exists for those families. This is an
experimental outcome, not an infrastructure invalidation.

## Run classification (Round-1 audit P0 #1) — H1 runs are HARNESS-VALIDATION

`harness/admissibility.py` classifies every `runs/` dir (read-only, no
relabeling): **H1-* runs are EXCLUDED as harness-validation** — they prove the
harness works end-to-end, they are never estimand data. The admissibility
command returns, for the current `runs/` inventory, `estimand-grade = 0`:
every dir is EXCLUDED (the two H1-* dirs as harness-validation; all legacy
`P-*`/`Q-*` dirs as pre-harness ad-hoc evidence with no run manifest), because
no dir satisfies the estimand evidence gate (provider-side `identity.json`,
instance-freeze anchor `== FREEZE.json freeze_commit`, wired run manifest,
intact `EVIDENCE-CHAIN.jsonl`). For the paper: these dirs are **PILOT-GRADE
harness-validation evidence only** — cite them for what they prove about the
harness, never in an estimand headline; claim-grade estimand results require
fresh replication on unseen families behind the EXECUTION-LOCK after the
Round-2 audit closes.

## Lane/failover boundary

The P/Q direct probes used the frozen P/Q endpoints in their lane records at
the time of the calls, but a separate model failover warning appeared in the
session. Any call whose provider/model identity cannot be established from
its committed lane/usage receipt is excluded from future tallies under the
frozen invalid-run taxonomy. No relabeling by behavior is allowed.

## Required next implementation before resuming

- DONE: H1-integrated runner `harness-run/run_arm_h1.py` now stages work under
  the trusted root (`/tmp/rcos-runs/famc-<id>`), mounts `/work:rw`+`/task:ro`,
  executes arrivals inside `--network none` digest-pinned containers, and
  copies OUTPUT back for host-side evaluation. Model calls stay harness-side.
  First validation run `H1-P-fam01-T0` = ship (json-envelope, container rc0).
- P/Q lane identity re-probed live and confirmed distinct: P=`MiniMax-M3`
  (router9/v1), Q=`agnes-2-0-flash:free` (kenari.id/v1). Both reachable.
- DONE: H2/H3 wiring attached to `run_arm_h1.py` (wired by default; Round-1
  audit P0 #19: unwired execution is REFUSED on the estimand surface —
  `--no-wire` is banned; the only unwired escape is `--dev-unwired-outdir DIR`
  outside the Fam-C tree, stamped `dev_mode=true` in the manifest). Every
  model call passes through `usage.recorded_call()` (usage receipts land in
  the run dir); every completed run emits `EVIDENCE-CHAIN.jsonl` (genesis
  binds the **instance freeze commit from `FREEZE.json`
  (`d1292434…`) — never an execution HEAD masquerading as the freeze** — +
  run manifest → model-call → capability-event → evaluator → terminal grade)
  and re-audits clean before returning. Dual anchors (Round-1 audit P0 #4):
  each manifest records `instance_freeze_commit`/`instance_freeze_tree`
  (FREEZE.json) alongside `execution_harness_commit` (git HEAD at run time)
  and `execution_harness_manifest_sha256` (sha over the executed harness
  modules + runner), and the runner refuses to START unless the executed
  instance subtree is byte-identical to `FREEZE-HASHES.sha256`
  (`verify_instance_frozen`, fail-closed on drift/extras). Correct-arm loads
  go through `lock.load_artifact()` (locked-hash verified pre-execution) and
  write a `reuse_log` record; promotion via `lock.promote()` fires only on a
  ship verdict with an explicit `--promote`. Offline wiring compose-check:
  `run_arm_h1.py --selfcheck-wire` = ok (fixture, not a run).
- First frozen-order wired run: `H1-P-fam05-T0` = ship (json-envelope,
  container rc0; manifest verdict `ship`; chain audit intact).
  `H1-Q-fam05-T0` blocked externally: kenari free-model daily quota exhausted
  (`429 free_quota_daily`, resets 00:00 UTC) — endpoint reachable, lane has no
  completions budget today. Correct-arm CAPABILITY_LOCK/ledger path is
  implemented + offline-proven but has no real locked capability yet (prior
  fam02/fam06 promotion attempts returned `fix`), so no correct-arm run is
  claim-grade until a real lock exists.
- REMAINING (to resume): re-run the frozen sequence from the next family cell
  (new runs only via `run_arm_h1.py`; prior ad-hoc runs stay quarantined);
  retry lane Q after the kenari daily-quota reset (00:00 UTC).

## Verdict

`IN-PROGRESS — estimand lock proven on lane P`: new runs emit H2+H3-linked
manifests and audit-intact chains through `run_arm_h1.py` (validated on
`H1-P-fam05-T0` = ship — harness-validation, not estimand data); lane Q of
that cell is externally blocked by the provider's free-model daily quota, not
by the harness. Correct-arm capability runs await a real locked capability
from a successful promotion. Status wording (Round-1 audit correction #2):
locked capability reuse is **promotion + locked reuse under workflow
control**, never "retirement" — a promoted capability remains reusable by
correct-arm runs exactly as `lock.load_artifact()` enforces. The frozen
instance package is unaffected; execution stays STOPPED for estimand-grade
runs (admissibility: `estimand-grade = 0`) until the Round-2 audit closes and
the EXECUTION-LOCK is applied.
