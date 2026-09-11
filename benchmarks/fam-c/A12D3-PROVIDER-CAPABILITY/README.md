# A12D3 — PROVIDER-CAPABILITY DENIAL (counterfactual legs)

Status: **INTERESTING / NOT AUDITABLE UPSTREAM (now on a branch) / NOT YET SEALED**
Frozen contract: **D3 v1.0, 15 conjuncts, TEST-ONLY**
Branch: `a12-d3-provider-capability-denial`

---

## 1. NAME DISAMBIGUATION (permanent — read this before anything else)

There are **two unrelated experiments** in this workspace that both wore the `a12d3`/D3 label.
This directory is the **second** one only.

| | this directory | the other one |
|---|---|---|
| name | **A12D3 PROVIDER-CAPABILITY** | **A12d auditor slice D3** |
| subject | counterfactual provider-capability denial (seccomp / kernel audit) | consumer-manifest byte minimality (A12d.5) + order-derived readiness (A12d.6) |
| modules | `a12d3_d3_*.py`, `a12d3_counterfactual_*` | `a12d_d3_indep.py` |
| spec | `specs/D3_APPARATUS_REPAIR_RULING.md` | `benchmarks/fam-c/a12d_sliceD3.md` |
| in this repo? | **was not** — added by this branch | yes, pre-existing on `rcos-harness-readiness` |

The other experiment's name and history are **untouched** by this branch. Do not conflate the two
when reading any "D3" result from this workspace.

**The module filenames were deliberately NOT renamed.** They still read `a12d3_d3_*`. The frozen
source digests in `apparatus/SOURCE-FREEZE.sha256` are the binding identity of the bytes that were
actually measured, and renaming the files would break the only link between this branch and the
frozen freeze it was cut from — `git log -S a12d3_d3_provider_boundary` would return nothing against
the historical record, and the prerecorded digests would no longer verify. Disambiguation is
therefore carried by directory name (`A12D3-PROVIDER-CAPABILITY`), by this section, and by the
frozen predicate/module constants, which are already unambiguous. If you would rather have the
filename prefix changed to something like `a12d3pc_*`, say so and it will be done as a separate,
separately-hashed commit — it just should not be smuggled into the freeze commit.

## 2. The frozen contract

Predicate: `COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED` — 15 conjuncts, frozen order,
`conjunct_count: 15` asserted by both harness and checker.

    LEG_ENTRY_IDENTITIES_PRECOMMITTED          LEG_DESCRIPTOR_ALLOWLIST_PRECOMMITTED
    LEG_DESCRIPTOR_SET_MEASURED                NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED
    NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED
    NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY    PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY
    EXEC_DENIED_AFTER_LEG_ENTRY                KERNEL_DENIAL_POLICY_PRECOMMITTED
    KERNEL_DENIAL_POLICY_ACTIVE_AT_POINT_OF_USE
    HONEST_COUNTERFACTUAL_LEGS_COMPLETE        D1_PROVIDER_OPPORTUNITY_DELTA_ZERO
    TOTAL_MODEL_CELL_COUNT_UNCHANGED           ORDER_CELL_COUNT_UNCHANGED
    ALL_CAPABILITY_BINDINGS_RECONCILED

Failure vocabulary is closed to exactly three codes:
`PROVIDER_CAPABILITY_INHERITED`, `PROVIDER_CAPABILITY_ATTEMPT`, `PROVIDER_BROKER_REACHABLE`.

**Mechanism.** Each arm holds all three legs on a barrier while their real `/proc/<pid>/fd` sets are
measured from outside; only non-stdio fds that are exact apparatus necessities are permitted, and any
socket/IPC endpoint able to reach the gate, mock, provider, or a provider-capable broker is
forbidden. Denial is **kernel-enforced** (seccomp-BPF). A self-reported "sandbox enabled" boolean is
deliberately **not** load-bearing anywhere in the conjunct set.

Forbidden sequencing (`measure clean FDs → release leg → install seccomp`) is not merely avoided but
**inexpressible**: the legs rendezvous on a signal and hold no fd while held, so there is no instant
at which a leg is running business logic but unimpeded. Required order, enforced:

    install denial policy → entry barrier → externally measure /proc/<pid>/fd
      → establish activation → reconcile allowlists/capability bindings → release business logic

**Denial policy v1** (`D3_KERNEL_DENIAL_POLICY_v1.0`): 15 syscalls
`[41,42,43,44,46,49,50,53,56,57,58,59,288,322,435]`, `SECCOMP_RET_ERRNO|EACCES` (errno 13),
default ALLOW, arch guard denies ABI mismatch, no kill actions, `no_new_privs` required, installed
BEFORE the entry barrier. Filter: **21 insns / 168 bytes**,
sha256 `2d155ba65d4c584512235194d8359f9b0ec828e8b4d3062694526605c882b1fe` — unchanged across every
rebuild on record. `2cec76ef17f9db55270823b4b89db8a3f3f73236afe185d07b6e532437b83dbf` is
**superseded**; do not accept it.

## 3. Controls

    D3-A  clean closed legs            PASS  boundary_holds true   semantic_ok true   code NONE
    D3-B  inherited provider channel   FAIL  boundary_holds false  semantic_ok false  PROVIDER_CAPABILITY_INHERITED
    D3-C  direct network attempt       FAIL  boundary_holds true   semantic_ok false  PROVIDER_CAPABILITY_ATTEMPT
    D3-D  child/exec escape            FAIL  boundary_holds true   semantic_ok false  PROVIDER_CAPABILITY_ATTEMPT
    D3-E  provider broker              FAIL  boundary_holds false  semantic_ok false  PROVIDER_BROKER_REACHABLE
    D3-X  falsifier (injects a real extra provider attempt)
                                       conjunct_value false, proved_live true, offenders 2
                                       delta after {attempts 2, dispatches 2, receives 1}

**B/E and C/D are different causal failure modes and must not be collapsed:**

    B / E : fail because a prohibited capability EXISTS or is REACHABLE
            (capability possession, not a second provider call actually happening)
    C / D : capability use is ATTEMPTED; the kernel policy DENIES the attempt;
            honest business logic still proceeds under the same policy
            (the denied syscall is experimental evidence, not infrastructure failure)

## 4. Reproducing the build and the run

    # 1. verify the frozen bytes
    cd apparatus && sha256sum -c SOURCE-FREEZE.sha256

    # 2. rebuild all binaries from frozen source (never from the live tree)
    ./build-pinned.sh <source-file> <build-dir> <policy-module-dir>

`build-pinned.sh` reimplements `build.sh`'s logic unmodified — identity x injection matrix, explicit
`REQUIRED` target enumeration, preprocessor-axis assertion, honest-legs injection-0 assertion — but
with all paths parameterised. **`build.sh` as originally written was not reproducible**: `SRC` and `B`
were hardcoded to the live tree, so a build receipt did not actually bind to frozen source. Two
independent rebuilds through `build-pinned.sh` produced **19 identical / 0 differing** outputs.

Two further build defects, both repaired and disclosed: `build.sh` compiled one target against a
nonexistent header and `2>/dev/null || true` let it still print `BUILD OK` (target removed; explicit
`REQUIRED` loop added), and a previously-claimed "8/8 role and helper targets build clean" was wrong
— it was **7/8**.

Run, from a clean work root:

    D3_EXECUTE=1 D3_ALLOW_WIPE=1 \
    D3_WORK_ROOT=<run-dir> D3_BUILD_DIR=<build-dir> \
    python3 apparatus/a12d3_counterfactual_provider_capability_controls.py

The harness refuses to run without `D3_EXECUTE=1` (exit 2) and refuses to wipe an existing arm dir
without `D3_ALLOW_WIPE=1`. The checker is invoked separately and exits 0 = agrees, 1 = disagrees,
2 = missing receipt; it recomputes all 15 conjuncts from raw artifacts and re-runs the same frozen
functions rather than reading any harness summary line. It writes `independent_audit.json` **into the
directory it grades**, with an explicit `checker_verdict` field.

## 5. Claim boundary — what this does NOT establish

This does **not** establish that a real provider/model call was denied under production conditions.
Zero calibration was spent and no provider/model call was made: the provider path is a mock boundary.
The claim is the narrow one the gate stated:

> the test apparatus can distinguish clean execution, inherited provider capability, denied
> provider-capability attempts, child/exec attempts, and broker reachability under the frozen
> 15-conjunct contract, with an independently recomputed checker and external kernel corroboration.

## 6. `activation_evidenced_by_kernel` is a LEGACY / MISNAMED field

    activation_evidenced_by_kernel:
        legacy/misnamed receipt field
        source = PR_GET_SECCOMP readback by the leg itself
        NOT used as kernel-audit corroboration

It is `seccomp_raw == "2"` — self-reported by the leg, not derived from the kernel audit. It appears
in `receipt.json` and in historical artifacts and is **not silently renamed**; the historical record
keeps its original bytes and this note is the correction. The real external corroboration is the
`journalctl -k` `type=1326` evidence in `EVIDENCE/KERNEL_AUDIT_CORROBORATION.md`.

## 7. Evidence

| file | what it is |
|---|---|
| `REPORT-TO-GATE.md` | the report posted to the gate, verbatim |
| `specs/D3_APPARATUS_REPAIR_RULING.md` | the external gate's frozen D3 apparatus-repair ruling |
| `EVIDENCE/KERNEL_AUDIT_CORROBORATION.md` | kernel-side corroboration, raw `type=1326` record, 18/18 PID cross-check |
| `EVIDENCE/PROVENANCE.md` | source freeze → build → run → checker → kernel corroboration chain |
| `EVIDENCE/EVIDENCE-DIGESTS.sha256` | digests of every run/build artifact named in the report |
| `EVIDENCE/HISTORICAL-NONCLAIM-BEARING.md` | the three superseded/defective runs, kept but non-claim-bearing |

Raw run directories are **not** committed here (the graded receipt alone is ~158 KB, and the evidence
loss disclosed in §6 of the report means one of them is partly unrecoverable). They live at
`/tmp/d3gen/` and will be published in full on request — say which run and it will be produced rather
than summarised.

## 8. Attribution

Mine: the B1 guard repair (self-exec guard compared path **text**, so a hardlinked copy of the leg
passed and re-exec'd 30,228 times in 18.5 s — fixed with `os.path.samefile()`), the `build.sh`
false-green repair, `build-pinned.sh`, the patch tooling, the clean-leg analysis, the kernel-audit
root cause and the `seccomp(2)` fix, and the `wait4` inflation **diagnosis**. Not mine: the B2
one-line typo repair, and the `wait4` inflation **repair** on both sides.
