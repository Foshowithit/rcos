#!/usr/bin/env python3
"""Deterministically apply the seccomp(2) audit-log install to a legs.c copy.

Why a script instead of an in-place edit: the apparatus directory is written by a
concurrent session, so a hand-edited frozen file can be silently overwritten (it
was, at 15:03).  A patch that reports BEFORE/AFTER digests and refuses to apply
twice is re-runnable and self-verifying.

Usage: apply_seccomp_log_patch.py <path-to-a12d3_d3_legs.c>
"""
import hashlib
import re
import sys
from pathlib import Path

OLD_CALL = """    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog, 0, 0) != 0) {
        d3_note("DENIAL_POLICY_INSTALL_FAILED", "stage=set_seccomp errno=%d",
                errno);
        return -1;
    }"""

NEW_CALL = """    /*
     * Install through the seccomp(2) SYSCALL, not prctl(PR_SET_SECCOMP, ...).
     *
     * PR_SET_SECCOMP IGNORES prctl's 4th and 5th arguments: prctl always reaches
     * the kernel's seccomp_set_mode_filter() with flags = 0.  SECCOMP_FILTER_FLAG_LOG
     * therefore CANNOT be set through prctl, and without that flag the kernel
     * writes no `type=1326` audit record for a denial.
     *
     * Measured consequence (2026-09-11): the battery ran green while the journal
     * held ZERO `type=1326` records for its window, leaving every denial witnessed
     * only by the leg's OWN self-reported errno=13 marker -- the class of evidence
     * this contract says must not carry the argument alone.
     *
     * With the flag honoured the same run emits one record per denied attempt
     * (`sig=0 ... code=0x50000`, i.e. SECCOMP_RET_ERRNO returned, not a kill).
     * Filter BYTES are unchanged: deny set, errno and ALLOW default are identical;
     * only whether the kernel ALSO logs changes.
     */
    if (syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER,
                (unsigned int)SECCOMP_FILTER_FLAG_LOG, &prog) != 0) {
        d3_note("DENIAL_POLICY_INSTALL_FAILED", "stage=set_seccomp errno=%d",
                errno);
        return -1;
    }"""

OLD_HEADER = " *   2. PR_SET_SECCOMP(SECCOMP_MODE_FILTER, ...)  -- the filter itself."
NEW_HEADER = """ *   2. seccomp(2) with SECCOMP_FILTER_FLAG_LOG -- the filter itself, AND the
 *      kernel-side audit record for every denial it returns.
 *
 * Step 2 uses the seccomp(2) SYSCALL, not prctl(PR_SET_SECCOMP, ...).  See the
 * comment at the install site: prctl cannot carry the LOG flag, and without it
 * a denial is witnessed only by the denying process's own marker."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_seccomp_log_patch.py <a12d3_d3_legs.c>")
        return 2
    path = Path(sys.argv[1])
    src = path.read_text()
    before = digest(src)
    print(f"BEFORE sha256 {before}")

    if "SECCOMP_FILTER_FLAG_LOG" in src:
        print("REFUSED: patch already present; refusing to apply twice")
        return 3
    if OLD_CALL not in src:
        print("REFUSED: install call not found verbatim -- source moved, do not force")
        return 4
    if OLD_HEADER not in src:
        print("REFUSED: installer doc header not found verbatim -- source moved")
        return 5

    src = src.replace(OLD_CALL, NEW_CALL, 1)
    src = src.replace(OLD_HEADER, NEW_HEADER, 1)

    # The install must now be the syscall form and only once.
    if src.count("syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER") != 1:
        print("REFUSED: expected exactly one seccomp() install site after patch")
        return 6
    # A surviving INSTALL through prctl would make the patch partial.  Match the
    # call at a LINE START, not a bare substring: the compiler cannot execute a
    # prctl install that does not begin a statement, whereas the explanatory
    # comment above deliberately names prctl(PR_SET_SECCOMP, ...) and a naive
    # substring test counts that comment and reports a false failure.
    if re.search(r"^\s*(if\s*\(\s*)?prctl\(\s*PR_SET_SECCOMP", src, re.M):
        print("REFUSED: a prctl install site survives -- patch would be partial")
        return 7

    path.write_text(src)
    after = digest(path.read_text())
    print(f"AFTER  sha256 {after}")
    print(f"APPLIED ok -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
