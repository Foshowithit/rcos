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

1. Integrate `DockerSandbox` into the P/Q runner; the runner must construct
   exactly `/work:rw` + `/task:ro`, verify the staged snapshot, and execute
   arrivals inside `--network none` containers.
2. Add the H2 `recorded_call`/identity/reuse records to each run and bind
   normalizer IDs to the frozen lane identity.
3. Add the H3 Chain + CAPABILITY_LOCK + replacement ledger records, with a
   terminal grade only after the graph checks pass.
4. Run the full H1/H2/H3 smoke suite from the runner; only then resume from
   the next frozen family/order position. Existing partial evidence remains
   quarantined and is not silently upgraded.

## Verdict

`BLOCKED` for Fam-C grading until the runner is H1-integrated and the lane
failover boundary is resolved per the frozen protocol. The frozen instance
package is unaffected; this is an execution-harness integration block.
