RCOS A12-D / **D3 (counterfactual provider-capability denial)** — report for gate. TEST-ONLY: no real provider or model call was made at any point. Calibration unspent.

## 0. Verdict claimed, and what it does NOT claim

Claimed: **D3-A..E meet the frozen 15-conjunct v1.0 contract, and the failure arms fail for the right reason.** Harness exit 0, `all_arms_meet_contract: true`, `conjunct_count: 15`.

Not claimed: that any of this is upstream-visible. It is not. See §5 — that is a governance question for you before you spend any audit effort.

## 1. What was run

    run dir   /tmp/d3gen/d3run-audited2   (2026-09-11 15:09:13 -> 15:10:37, wall 84 s)
    build     /tmp/d3gen/build-audit2     (rebuilt from frozen source, not the live tree)
    freeze    /tmp/d3gen/frozen-150201/src  (10 files + MANIFEST.sha256, 24 lines)

    receipt                exit 0   all_arms_meet_contract: true
    independent checker    exit 0   verdict AGREES, disagreements []
                                    (checker recomputes all 15 conjuncts from raw
                                     artifacts and re-runs the same frozen functions;
                                     it does not read a harness summary line)

Arms (all `expectation_met: true`):

    D3-A  clean closed legs           boundary_holds true   semantic_ok true   code NONE
    D3-B  inherited provider channel  boundary_holds false  semantic_ok false  PROVIDER_CAPABILITY_INHERITED
    D3-C  direct network attempt      boundary_holds true   semantic_ok false  PROVIDER_CAPABILITY_ATTEMPT
    D3-D  child/exec escape           boundary_holds true   semantic_ok false  PROVIDER_CAPABILITY_ATTEMPT
    D3-E  provider broker             boundary_holds false  semantic_ok false  PROVIDER_BROKER_REACHABLE
    D3-X  falsifier (injects a real
          extra provider attempt)     conjunct_value false  proved_live true  offenders 2
                                        delta after {attempts 2, dispatches 2, receives 1}

The D3-B/D3-E distinction you asked for is preserved: those two fail from **capability possession**, not from a second provider call actually happening. D3-C/D record an *attempted denied syscall* as experimental evidence, and the honest legs still complete under the same policy — the attempt is not an infrastructure failure.

## 2. The dishonest sequencing was impossible, not merely avoided

Required order, enforced: install denial policy → entry barrier → externally measure `/proc/<pid>/fd` → establish activation → reconcile allowlists → release business logic.

The forbidden shortcut (measure clean FDs → release leg → install seccomp) cannot be expressed: the leg blocks on a signal rendezvous (`rendezvous=signal mode=no_held_fd`, `sigsuspend`) and holds no fd while held, so there is no point at which the leg is running business logic but unimpeded. `PROCESS_CREATION / NETWORK_CREATION / EXEC` denials are kernel-enforced by seccomp — a self-reported "sandbox enabled" boolean is deliberately not load-bearing anywhere in the conjunct set.

Denial policy v1.0: 15 syscalls `[41,42,43,44,46,49,50,53,56,57,58,59,288,322,435]`, `SECCOMP_RET_ERRNO|EACCES` (13), default ALLOW, arch-guard denies ABI mismatch, no kill actions, `no_new_privs` required, installed BEFORE the entry barrier. Filter is **21 insns / 168 bytes**, sha256 `2d155ba65d4c584512235194d8359f9b0ec828e8b4d3062694526605c882b1fe`. That digest is unchanged across every rebuild I have run.

## 3. Kernel corroboration

The pre-fix run produced **zero** `type=1326` audit records. Root cause: `prctl(PR_SET_SECCOMP, ...)` **ignores its 4th/5th option arguments**, so `SECCOMP_FILTER_FLAG_LOG` never reached the kernel. `prctl(PR_GET_SECCOMP)` returning 2 still proved filtering was *active*, but nothing was logged.

Repaired by installing via `seccomp(2)` (`SYS_seccomp` 317, `SECCOMP_SET_MODE_FILTER`, `SECCOMP_FILTER_FLAG_LOG`=2). Same filter bytes, same deny set, same errno, same default — **only whether the kernel also writes a log line changed.** Post-fix runs emit 60 records each.

In-window, from `journalctl -k` (run 2, the defensive run): **60 `type=1326` records**, `syscall=41`×18, `53`×18, `56`×17, `59`×7 — all `code=0x50000` (`SECCOMP_RET_ERRNO`), all `sig=0` (error returned, not killed), all `arch=c000003e compat=0`. Kernel-observed denied set is exactly `{41 socket, 53 socketpair, 56 clone, 59 execve}`. Run 1's window shows the same 60 records and the same set but a slightly different retry distribution (`56`×16, `59`×8) — the set is what the conjunct requires, not the counts; I am flagging the difference rather than quoting one run's numbers as if they were both.

**18/18 kernel PIDs appear in both the kernel audit and the arms' own `markers.txt`**, with `comm`/`exe` naming the exact leg binary. Full artifact at `/tmp/d3gen/KERNEL_AUDIT_CORROBORATION.md`.

## 4. Two defects and one required disclosure

**(a) `wait4` denial-evidence inflation — found, fixed, disclosed.** The first audited run reported `denied_event_count 13` with `wait4` in `denied_syscalls` on all five arms, contradicting the deny set. Cause: a trace line `wait4(...) = -1 ECHILD` carries a *named* errno, but the parser computed `-ret`, turning every named failure into errno 1 (EPERM) — which is in `ACCEPTED_DENIAL_ERRNOS`. So an ordinary supervisor `wait()` was silently counted as a denied `wait4`. Repaired on both sides (harness resolves the named errno; checker refuses named-but-unaccepted failures). After repair: `denied_event_count 12`, `denied_syscalls ['clone','execve','socket','socketpair']` — exactly the kernel-observed set. Both runs are retained; the first is kept as superseded, not deleted. Note the repair landed mid-flight of that battery, so run 1 is not a clean before/after pair.

**(b) `activation_evidenced_by_kernel` is a MISNAMED field.** Traced to source: it is `seccomp_raw == "2"`, i.e. `PR_GET_SECCOMP` read back **by the leg itself** — self-reported, not kernel-audit-derived. It appears in the receipt and I am not defending it. The genuine kernel corroboration is §3, which is external to the leg. Treat that field as noise; I have not silently renamed it inside a frozen artifact.

**(c) Self-inflicted evidence loss — disclosed.** An earlier checker run at 14:23 overwrote `independent_audit.json` in `d3run-SUPERSEDED-no-prediction-binding`, destroying the pre-repair checker's verdict. Unrecoverable. My error, and it is why the checker now writes into the directory it grades with an explicit verdict field rather than being re-run ad hoc.

Also disclosed: `build.sh` as written was **not reproducible** — `SRC` and `B` were hardcoded to the live tree, so a receipt was not meaningful. Fixed by a parameterized builder; two independent rebuilds now give 19 identical / 0 differing outputs. And `build.sh` had a false-green path (`2>/dev/null || true` let it print `BUILD OK` for a target compiled against a nonexistent header); that target is removed and an explicit REQUIRED loop added. Correction to something I said earlier: 7 role/helper targets built clean, not 8.

## 5. Two things I need from you before this is worth your time

**(1) Not in the repository.** As of now `Foshowithit/rcos` has **never** contained the boundary-series modules in any ref: `git log --all -S a12d3_counterfactual_provider_capability_controls` is empty, and likewise for `a12d1_*`/`a12d2_*`. The apparatus lives only in `/home/chow/rcos-verify/apparatus-final/` and `/tmp/d3gen/`, which is **not a git repo at all**. Your connector cannot see it. Every prior D-series post gave you a branch, tip and `rev-list 0`; this one cannot, and I would rather say so than dress it up.

So: **do you want this apparatus in `Foshowithit/rcos` on a branch before you audit it** — and if so, on `rcos-harness-readiness`, or a separate branch? I am not committing it into the live tree unprompted: a concurrent session is actively writing that same tree (it rewrote the checker again at 15:20:43, after my freeze), and the tree currently has uncommitted modifications.

**(2) A name collision you should rule on.** There are two unrelated D3s in this workspace, both wearing the `a12d` prefix:

    a12d_d3_indep.py / a12d_sliceD3.md   -> A12d auditor slice D3: consumer-manifest byte
                                            minimality (A12d.5) + order-derived readiness (A12d.6)
                                            IN the repo, on rcos-harness-readiness
    a12d3_d3_*.py (this report)          -> counterfactual provider-capability denial, seccomp
                                            NOT in the repo

If you have been holding a mental "D3" for this A12 lane, tell me which one it is; if you have never seen the provider-capability D3 contract text, then this report is arriving cold and you should tell me so rather than infer it from the other D3.

## 6. Attribution

Mine: the B1 guard repair (self-exec guard compared path text, so a hardlinked copy of the leg passed and re-exec'd 30,228 times in 18.5 s — fixed with `os.path.samefile()`), the `build.sh` false-green repair, the parameterized reproducible builder, the patch tooling, the kernel-audit root cause and the `seccomp()` fix, the clean-leg analysis, and the `wait4` inflation *diagnosis*. Not mine: the B2 one-line typo repair, and the `wait4` inflation *repair* on both sides.

Every number above is from a primary artifact in `/tmp/d3gen/`. If you want a different slice of raw output, name it and I will produce it rather than summarise.
