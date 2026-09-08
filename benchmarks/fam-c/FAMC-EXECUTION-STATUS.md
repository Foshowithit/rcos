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
- DONE: H2/H3 wiring attached to `run_arm_h1.py` (wired by default; `--no-wire`
  is the escape hatch). Every model call passes through `usage.recorded_call()`
  (usage receipts land in the run dir); every completed run emits
  `EVIDENCE-CHAIN.jsonl` (genesis binds frozen commit + run manifest →
  model-call → capability-event → evaluator → terminal grade) and re-audits
  clean before returning. Correct-arm loads go through
  `lock.load_artifact()` (locked-hash verified pre-execution) and write a
  `reuse_log` record; promotion via `lock.promote()` fires only on a ship
  verdict with an explicit `--promote`. Offline wiring compose-check:
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
`H1-P-fam05-T0` = ship); lane Q of that cell is externally blocked by the
provider's free-model daily quota, not by the harness. Correct-arm capability
runs await a real locked capability from a successful promotion. The frozen
instance package is unaffected.
