# PROVENANCE — A12D3 PROVIDER-CAPABILITY

Source freeze → build → run → checker → kernel corroboration. Every hash below was recomputed at
branch-creation time (2026-09-11) from the artifacts on disk; none is copied from a worker summary.

---

## 1. Parent

    repository   Foshowithit/rcos
    branch cut   a12-d3-provider-capability-denial
    parent       origin/rcos-harness-readiness
    parent tip   8ba9df78fc072ec72feece4fee0a95486388e40c
                 "Item B dependency: receipt builder accepts and forwards the
                  26-slot temporal schema isolation"

Cut from a **clean clone**, not from the working tree. The live checkout
`/home/chow/chow-work/rcos` was deliberately not used: it carried uncommitted modifications to
`benchmarks/fam-c/EXECUTION-LOCK.json`, `benchmarks/fam-c/harness-run/run_arm_h1.py` and
`harness/adaptation.py`, plus an untracked `harness/seal_canonical.py`, from a session operating a
different lane. Committing this apparatus into that dirty tree would have mixed unrelated
work-in-progress into the freeze commit. `rcos-harness-readiness` itself is untouched by this branch.

## 2. Source freeze

    origin       /tmp/d3gen/frozen-150201
    frozen       2026-09-11 15:09  (re-frozen a 3rd time)
    manifest     /tmp/d3gen/frozen-150201/MANIFEST.sha256
                 sha256 55e8fccff8d3372c0911c914fab4e5ef67304abd15d6688482bcd5f51a6d596f
    copied to    apparatus/   (verbatim; digest set reproduced in apparatus/SOURCE-FREEZE.sha256)

The freeze exists because the live apparatus dir `/home/chow/rcos-verify/apparatus-final/` was being
written **concurrently** by another session throughout this work — it replaced `/tmp/d3gen/build`
wholesale at 14:46:15, rewrote the harness at 15:00:04, the checker at 15:02:19, the harness trace
parser at 15:07:44, the checker again at 15:08:04, and the checker a further time at 15:20:43 (after
the freeze). There is no version control over that tree, so a digest set is the only binding
identity available. **The bytes in `apparatus/` are the freeze, not the live tree, and they are what
was measured.**

The `seccomp(2)` LOG install patch is applied **in this freeze**, not in the live tree. Patch identity:

    a12d3_d3_legs.c  patched   4c3fb3dcc21a63e28896beff4544d6d939aeb5d0686447a9d7e4973851d8ea12
    a12d3_d3_legs.c  pristine  5a9396b0e45dab1af1486fffc9208b3decdc6104605b27e5cd8ffa877bc68892

This changes the **install entry point**, which is part of the precommitted identity of the thing D3
measures. Same filter bytes, same deny set, same errno, same default: only whether the kernel also
writes a log line changed. It was authorized by the operator and is disclosed to the gate in §4 of
`REPORT-TO-GATE.md`; it is not a silent re-freeze.

## 3. Build

    build dir    /tmp/d3gen/build-audit2
    builder      apparatus/build-pinned.sh  (parameterised; not build.sh)

`build.sh` as originally written was **not reproducible** — `SRC` and `B` were hardcoded to the live
tree, so a receipt did not bind to frozen source. `build-pinned.sh` reimplements its logic unmodified
(identity x injection matrix, explicit `REQUIRED` target enumeration, preprocessor-axis assertion,
honest-legs injection-0 assertion) with all paths parameterised. Verified: two independent rebuilds
→ **19 identical, 0 differing**.

Key build artifacts:

    2d155ba65d4c584512235194d8359f9b0ec828e8b4d3062694526605c882b1fe  d3-denial-filter.bin   168 B
    98c21329a3507f78...                                              d3-denial-policy.json  1693 B
    d623f1468db10979...                                              d3-leg-on             21824 B

`d3-denial-filter.bin` is **21 insns / 168 bytes**, `sha256 2d155ba6…` = ACCEPTED. Unchanged across
every rebuild on record. `2cec76ef17f9db55270823b4b89db8a3f3f73236afe185d07b6e532437b83dbf` is
**SUPERSEDED** — reject it.

`policy_self_check` from the run receipt (all asserted true):

    instruction_count 21 (= expected_instruction_count)   deny_site_index 20
    deny_site_count 2                                     allow_site_count 1
    denied_syscall_count 15    deny_errno 13              kill_instructions 0
    default_action_is_allow true                          no_kill_instructions true
    arch_guard_present true    arch_guard_denies_mismatch true    arch_guard_deny_index 2
    all_comparisons_target_deny_site true
    deny_sites_confined_to_guard_and_terminal true
    denied_syscalls_have_numbers true    missing_from_number_table []

## 4. Run

    harness_version  D3_COUNTERFACTUAL_PROVIDER_CAPABILITY_CONTROLS_v1.0
    predicate        COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED
    conjunct_count   15
    run dir          /tmp/d3gen/d3run-audited2
    window           2026-09-11 15:09:13 → 15:10:37  (wall 84 s)
    generated_wall   1789153837.1329331

    receipt              sha256 c57dfb67692da006…  157948 B   exit 0
                         all_arms_meet_contract true

Run preconditions are fail-closed: the harness refuses without `D3_EXECUTE=1` (exit 2) and refuses
to wipe an existing arm dir without `D3_ALLOW_WIPE=1`.

## 5. Independent checker

    checker_version  D3_INDEPENDENT_CHECKER_v1.0
    artifact         /tmp/d3gen/d3run-audited2/independent_audit.json
                     sha256 0031b6d652034dea…  60230 B   exit 0

    checker_verdict            AGREES
    checker_agrees_with_harness true
    disagreements              []
    conjunct_count             15
    failure_vocabulary         [PROVIDER_CAPABILITY_INHERITED,
                                PROVIDER_CAPABILITY_ATTEMPT,
                                PROVIDER_BROKER_REACHABLE]

The checker recomputes all 15 conjuncts from raw artifacts and re-runs the same frozen functions; it
does not read a harness summary line. It writes into the directory it grades with an explicit
verdict field. Exit codes: 0 agrees / 1 disagrees / 2 missing receipt.

## 6. Kernel corroboration

    source      journalctl -k, audit type=1326
    run 2 window 2026-09-11 15:09:13 → 15:10:37   (AUDITED2_WINDOW)
    run 1 window 2026-09-11 15:06:56 → 15:08:20   (AUDITED_WINDOW)

Run 2: **60 records**, `syscall=41`×18, `53`×18, `56`×17, `59`×7, **all** `code=0x50000`
(`SECCOMP_RET_ERRNO`), **all** `sig=0` (error returned, not killed), all `arch=c000003e compat=0`,
`auid=1000 uid=1000 gid=1000 ses=12761 subj=unconfined`.

Run 1: same 60 records and same denied set, different retry distribution (`56`×16, `59`×8). The
**set** `{41 socket, 53 socketpair, 56 clone, 59 execve}` is what the conjunct requires and is
identical in both; the counts are not, and are not quoted as if they were.

Raw sample record:

    Sep 11 15:09:17 chow kernel: audit: type=1326 audit(1789153757.074:970):
      auid=1000 uid=1000 gid=1000 ses=12761 subj=unconfined
      pid=827823 comm="d3-leg-adapt" exe="/tmp/d3gen/build-audit2/d3-leg-adapt"
      sig=0 arch=c000003e syscall=41 compat=0 ip=0x7bb7f372c57b code=0x50000

**18/18 kernel PIDs appear in both the kernel audit and the arms' own `markers.txt`**, with `comm`/
`exe` naming the exact leg binary. Full artifact: `EVIDENCE/KERNEL_AUDIT_CORROBORATION.md`.

Kernel facts relied on: `CONFIG_IA32_EMULATION=y`, `# CONFIG_X86_X32_ABI is not set`, kernel
`7.0.0-31-generic`, `AUDIT_ARCH_X86_64 = 0xC000003E`, `AUDIT_ARCH_I386 = 0x40000003`. `auditd`
userspace was **not** running (no `audit=` boot param, `auditctl` not installed); the records arrive
via the kernel audit subsystem's own emission, which is why `SECCOMP_FILTER_FLAG_LOG` was necessary.
`CapEff` was `0000000000000000` (unprivileged uid 1000) throughout.

## 7. What is NOT in this branch

    raw run dirs          /tmp/d3gen/d3run-*        (receipt alone ~158 KB; not committed)
    build tree            /tmp/d3gen/build-audit2   (binary artifacts; not committed)
    freeze                /tmp/d3gen/frozen-150201  (reproduced in apparatus/)

Digests for all of the above are in `EVIDENCE/EVIDENCE-DIGESTS.sha256`, so substitution can be
detected. The bytes are available on request, in full, rather than summarised.
