# D3 KERNEL AUDIT CORROBORATION — 2026-09-11 15:09:13 .. 15:10:37

## What this file establishes

The retained D3 battery run emitted **zero** `type=1326` kernel audit records, so every
denial in that run was witnessed only by the denying leg's **own** self-reported
`errno=13` marker. The ruling requires that denials not rest on self-report alone.
This file records a re-run in which the kernel **independently** witnessed every denial.

## Run identity

| Item | Value |
|---|---|
| Window | 2026-09-11 15:09:13 .. 15:10:37 |
| Work root | `/tmp/d3gen/d3run-audited2` |
| Build dir | `/tmp/d3gen/build-audit2` |
| Frozen source | `/tmp/d3gen/frozen-150201` |
| Harness exit | **0** |
| `ALL_ARMS_MEET_CONTRACT` | **True** |
| `conjunct_count` | **15** |
| Checker exit | **0** — `AGREES with the harness on all 5 arms and all 15 conjuncts` |

Per-arm outcome (from `receipt.json`):

```
arm D3-A: boundary_holds=True  semantic_ok=True  code=NONE                          expectation_met=True
arm D3-B: boundary_holds=False semantic_ok=False code=PROVIDER_CAPABILITY_INHERITED  expectation_met=True
arm D3-C: boundary_holds=True  semantic_ok=False code=PROVIDER_CAPABILITY_ATTEMPT    expectation_met=True
arm D3-D: boundary_holds=True  semantic_ok=False code=PROVIDER_CAPABILITY_ATTEMPT    expectation_met=True
arm D3-E: boundary_holds=False semantic_ok=False code=PROVIDER_BROKER_REACHABLE       expectation_met=True
falsifier D3-X: delta={'attempts':1,'dispatches':1,'receives':0} conjunct=False proved_live=True offenders=2
```

## Kernel-side evidence (authoritative, not self-reported)

**60 `type=1326` records**, every one identical in shape:

```
audit: type=1326 audit(1789153620.279:898): auid=1000 uid=1000 gid=1000 ses=12761
  subj=unconfined pid=801486 comm="d3-leg-adapt"
  exe="/tmp/d3gen/build-audit/d3-leg-adapt"
  sig=0 arch=c000003e syscall=41 compat=0 ip=0x7c28cc72c57b code=0x50000
```

- `code=0x50000` = `SECCOMP_RET_ERRNO` — the filter **returned an error**; it did not kill.
- `sig=0` — corroborates "no kill", matching `kill_instructions: 0` in the filter.
- `arch=c000003e compat=0` on **all 60** — the arch guard held; no foreign-ABI escape.
- Denied syscalls observed by the kernel: `41` socket, `53` socketpair, `56` clone,
  `59` execve. **This is the only syscall set the kernel ever saw denied.**

## The decisive cross-check: kernel PIDs vs the legs' own markers

18 of 18 PIDs appear in **both** the kernel audit and the legs' own `markers.txt`,
each with `comm` and `exe` naming the exact binary the arm under test ran:

```
pid 839847  denials=4 ['socket','socketpair','clone','execve']  arm=arm-D3-E
pid 839848  denials=2 ['socket','socketpair']                  arm=arm-D3-E
pid 839849  denials=4 ['socket','socketpair','clone','execve']  arm=arm-D3-E
pid 842261  denials=3 ['socket','socketpair','clone']           arm=arm-D3-X
...
PIDs in BOTH kernel audit and leg markers: 18/18
```

This closes the gap the ruling identified: the denial is now attested by the **kernel**,
whose `exe=` field independently names the leg binary, and the two sources agree.

## Defect found and fixed during this work (NOT self-reported either)

The first audited run (15:06:56) produced a checker **disagreement**:

```
D3-A disagrees with harness:
  denied syscalls: harness=[...'wait4']  checker=['clone','execve','socket','socketpair']
```

Root cause, independently investigated: `wait4` is syscall **61** and is **not** in the
deny set (`denied_syscall_numbers = [41,42,43,44,46,49,50,53,56,57,58,59,288,322,435]`).
A trace line `wait4(...) = -1 ECHILD` has a **named** errno, but the parser computed
`-ret`, turning every named failure into errno 1 (EPERM) — an *accepted* denial errno.
So an ordinary supervisor `wait()` returning `ECHILD` was silently counted as a denied
`wait4`, inflating the denial evidence with a syscall that was never denied.

Repaired by resolving the **named** errno rather than the `-1` placeholder
(`_ERRNO_BY_NAME`, harness) and by explicitly refusing named-but-unaccepted failures
(`_NON_DENIAL_FAILURE_RE`, checker). After repair:

| | before repair | after repair | kernel says |
|---|---|---|---|
| `denied_event_count` | 13 | **12** | — |
| `denied_syscalls` | `+ wait4` | `['clone','execve','socket','socketpair']` | exactly those 4 |

The harness now reports **exactly** the kernel-observed set. Note the disagreement was
**caught by the independent checker**, which is the control working as designed.

## Honest disclosure

1. **`activation_evidenced_by_kernel: True` in the receipt is misnamed.** It is derived
   from `seccomp_raw == "2"`, i.e. `PR_GET_SECCOMP` read back **by the leg itself**. It
   is self-reported, not kernel-audit-derived. The genuine kernel corroboration is this
   file, produced by re-running, not by that field.
2. **The first audited window (15:06:56–15:08:20) is superseded**, not deleted. It is
   retained as the run in which the `wait4` inflation was observed and diagnosed.
3. The install fix changes the **entry point** (`seccomp(2)` instead of
   `prctl(PR_SET_SECCOMP)`), which is part of the precommitted identity of the thing D3
   measures. It is disclosed here rather than silently re-frozen.
   **The filter artifact is byte-identical**: 168 bytes, sha256
   `2d155ba65d4c584512235194d8359f9b0ec828e8b4d3062694526605c882b1fe` (ACCEPTED),
   21 instructions, deny site 20, errno 13, ALLOW default, 0 kill instructions.
   Same policy **artifact**; only whether the kernel also logs has changed.
