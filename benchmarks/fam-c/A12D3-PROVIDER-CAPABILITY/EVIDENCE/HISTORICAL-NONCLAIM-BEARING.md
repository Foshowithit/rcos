# HISTORICAL / NON-CLAIM-BEARING RUNS

The gate required these three items be marked explicitly non-claim-bearing before sealing. They are
**kept** — deleting superseded evidence is the failure mode this project exists to prevent — but no
headline result in `REPORT-TO-GATE.md` or `README.md` depends on any of them.

---

## HB-1 — pre-fix run: no kernel audit log line

    issue    the run produced ZERO audit type=1326 records
    cause    prctl(PR_SET_SECCOMP, ...) IGNORES its 4th/5th option arguments, so
             SECCOMP_FILTER_FLAG_LOG never reached the kernel
    status   repaired via seccomp(2): SYS_seccomp 317, SECCOMP_SET_MODE_FILTER,
             SECCOMP_FILTER_FLAG_LOG = 2

**Characterise this precisely — do not overclaim.** What is established: the denials in that window
produced no kernel audit record **because no log flag was set**. What is **NOT** established: that any
denial failed to occur. `prctl(PR_GET_SECCOMP)` returning 2 still proved filtering was *active* in
that run; there is simply no kernel-side record of it.

The earlier ruling's clause "absence of a record is itself evidence" does **not** cover this window.
The post-fix run supplies the corroboration instead. Do not read this run as either confirming or
refuting the deny set.

    claim-bearing: NO

## HB-2 — first audited run: inflated `wait4` denial evidence

    run dir      /tmp/d3gen/d3run-audited
    window       2026-09-11 15:06:56 → 15:08:20
    receipt      sha256 ec855dcf3cee0aa6…  157969 B
    checker      sha256 92587d50f2f7e882…  61734 B

Symptom: `denied_event_count 13` with `wait4` present in `denied_syscalls` on **all five** arms,
contradicting the deny set, which does not contain `wait4`.

Cause (diagnosed by this branch's author): a trace line `wait4(...) = -1 ECHILD` carries a **named**
errno, but the parser computed `-ret`, which turns every named failure into errno 1 (EPERM) — and
EPERM is in `ACCEPTED_DENIAL_ERRNOS`. An ordinary supervisor `wait()` was therefore silently counted
as a denied `wait4`.

Repair (both sides, by the peer session): the harness resolves the named errno; the checker refuses
named-but-unaccepted failures (`_NON_DENIAL_FAILURE_RE`).

After repair: `denied_event_count 12`, `denied_syscalls ['clone','execve','socket','socketpair']` —
exactly the kernel-observed set.

**This run is not a clean before/after pair.** The repair landed *mid-flight* of this battery: the
harness was rewritten at 15:07:44 and the checker at 15:08:04, while the battery had started at
15:06:56. So this run straddles the repair and cannot be used as a controlled comparison. The clean
comparison is run 1 (post-repair, superseded as the defensive run) against run 2 (defensive).

    claim-bearing: NO

## HB-3 — checker run that destroyed its own predecessor's verdict

    run dir      /tmp/d3gen/d3run-SUPERSEDED-no-prediction-binding
    receipt      sha256 b4360333a5eb774c…  35680 B

An earlier checker invocation at **14:23** overwrote `independent_audit.json` in this directory,
destroying the pre-repair checker's verdict. **Unrecoverable.** This is this branch author's own
error and is disclosed as such.

    claim-bearing: NO

Consequence, and the reason it is recorded rather than hidden: the checker now writes into the
directory it grades and emits an explicit `checker_verdict` field, so an ad-hoc re-run can no longer
silently replace a recorded verdict without the replacement being visible in the artifact itself.

## Also disclosed elsewhere (not a run)

- `build.sh` had a false-green path: it compiled a target against a nonexistent header and
  `2>/dev/null || true` let it still print `BUILD OK`. Target removed; explicit `REQUIRED` loop added.
- A previously-claimed "8/8 role and helper targets build clean" was **wrong — it was 7/8**. See
  `REPORT-TO-GATE.md` §4.
- `activation_evidenced_by_kernel` in the receipt is a **misnamed** field: `seccomp_raw == "2"`, a
  `PR_GET_SECCOMP` readback **by the leg itself**, not kernel-audit-derived. Demoted from evidentiary
  status in `README.md` §6 and deliberately **not** renamed inside any frozen artifact.
