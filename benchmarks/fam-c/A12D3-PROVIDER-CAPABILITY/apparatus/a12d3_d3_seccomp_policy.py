#!/usr/bin/env python3
"""A12D3 / D3 TEST-ONLY kernel denial policy builder and verifier.

THIS FILE IS NOT A13 CODE AND AWARDS NO ELIGIBILITY.

It has exactly three jobs, all of which must be independently re-derivable by an
auditor from the bytes on disk:

  1. BUILD the seccomp-bpf policy SPEC as deterministic bytes, and hash it BEFORE
     any leg is launched.  The hash is what is precommitted; the legs are checked
     against it, so "which policy ran" is answered by bytes, not by a claim.

  2. VERIFY activation from KERNEL-REPORTED state.  A harness boolean saying
     "sandbox enabled" is deliberately NOT load-bearing anywhere in D3.  The only
     accepted activation evidence is the `Seccomp:` line the kernel emits in
     /proc/<pid>/status, read externally while the leg is held at its entry
     barrier -- see a12d3_d3_descriptor_inspector.py.

  3. CLASSIFY a raw strace syscall line into an externally observed denial event.
     The denial must be a RETURNED ERRNO (EACCES/EPERM), never a process kill: a
     killed leg could not complete honestly, and D3-A requires honest completion.

WHY THE FILTER RETURNS ERRNO RATHER THAN KILLING
------------------------------------------------
SECCOMP_RET_KILL_* would make the offending leg die.  D3's predicate requires
HONEST_COUNTERFACTUAL_LEGS_COMPLETE, i.e. the clean legs consume the sealed
response and complete normally while the *same* policy is active.  So the policy
must be a pure capability restriction that a correct program never notices, and a
denial must survive as an observable syscall result.

WHY THE ARCH CHECK IS LOAD-BEARING
----------------------------------
A seccomp filter that matches only on syscall NUMBER is bypassable on a process
that can be induced to run foreign-ABI code (x32/i386 syscall numbers differ).
The guard is emitted first, and on an arch mismatch it returns ERRNO|EACCES --
it must NEVER return ALLOW.  The "canonical" idiom of allowing on mismatch, on
the reasoning that a foreign number is not comparable to the local deny list, is
WRONG and was measured wrong here: a native 64-bit process issuing `int $0x80`
with the i386 socket number (359) created a real socket under the policy, got no
audit record at all, while its native syscall=41/57/59 attempts were denied with
code=0x50000 in the same pid.  The kernel reported arch=40000003
(AUDIT_ARCH_I386), compat=1 for the escaping calls.  Denying the mismatch closes
network, process-creation and exec on the foreign path at once.  See
check_foreign_abi_cannot_escape() for the guard that keeps this fixed.
"""

from __future__ import annotations

import hashlib
import json
import struct
import time
from pathlib import Path

POLICY_VERSION = "D3_KERNEL_DENIAL_POLICY_v1.0"

# ---------------------------------------------------------------------------
# BPF constants (linux/bpf_common.h + linux/filter.h); spelled out so this file
# has no C headers and can be executed by a pure-Python auditor.
# ---------------------------------------------------------------------------

BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_K = 0x00
BPF_RET = 0x06

SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_KILL_THREAD = 0x00000000
SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO = 0x00050000

AUDIT_ARCH_X86_64 = 0xC000003E
AUDIT_ARCH_I386 = 0x40000003
# BPF_JGE lives in linux/bpf_common.h, not linux/filter.h
BPF_JGE = 0x30

# Struct offsets inside `struct seccomp_data` (linux/seccomp.h), confirmed
# against the host ABI this session:
#   int   nr;            /* offset 0 */
#   __u32 arch;          /* offset 4 */
#   __u64 instruction_pointer;  /* offset 8 */
struct_seccomp_data_nr = 0
struct_seccomp_data_arch = 4

# ---------------------------------------------------------------------------
# Syscall numbers (asm/unistd_64.h).  Hard-coded so the policy spec bytes are
# reproducible on any machine without importing the local headers.
# ---------------------------------------------------------------------------

X86_64_SYSCALLS = {
    "read": 0, "write": 1, "open": 2, "close": 3, "stat": 4, "fstat": 5,
    "lstat": 6, "poll": 7, "lseek": 8, "mmap": 9, "mprotect": 10, "munmap": 11,
    "brk": 12, "rt_sigaction": 13, "rt_sigprocmask": 14, "rt_sigreturn": 15,
    "ioctl": 16, "pread64": 17, "pwrite64": 18, "readv": 19, "writev": 20,
    "access": 21, "pipe": 22, "select": 23, "sched_yield": 24, "mremap": 25,
    "msync": 26, "mincore": 27, "madvise": 28, "shmget": 29, "shmat": 30,
    "dup": 32, "dup2": 33, "pause": 34, "nanosleep": 35, "getitimer": 36,
    "alarm": 37, "setitimer": 38, "getpid": 39, "sendfile": 40,
    "socket": 41, "connect": 42, "accept": 43, "sendto": 44, "recvfrom": 45,
    "sendmsg": 46, "recvmsg": 47, "shutdown": 48, "bind": 49, "listen": 50,
    "getsockname": 51, "getpeername": 52, "socketpair": 53, "setsockopt": 54,
    "getsockopt": 55, "clone": 56, "fork": 57, "vfork": 58, "execve": 59,
    "exit": 60, "wait4": 61, "kill": 62, "uname": 63, "fcntl": 72,
    "fsync": 74, "fdatasync": 75, "truncate": 76, "ftruncate": 77,
    "getcwd": 79, "chdir": 80, "rename": 82, "mkdir": 83, "rmdir": 84,
    "creat": 85, "link": 86, "unlink": 87, "readlink": 89, "chmod": 90,
    "fchmod": 91, "getuid": 102, "getgid": 104, "setuid": 105, "setgid": 106,
    "geteuid": 107, "getegid": 108, "getppid": 110, "setpgid": 109,
    "getgroups": 115, "getpgid": 121, "getsid": 124, "capget": 125,
    "capset": 126, "rt_sigpending": 127, "rt_sigtimedwait": 128,
    "rt_sigqueueinfo": 129, "rt_sigsuspend": 130, "sigaltstack": 131,
    "statfs": 137, "fstatfs": 138, "prctl": 157, "arch_prctl": 158,
    "gettid": 186, "futex": 202, "getdents64": 217, "set_tid_address": 218,
    "clock_gettime": 228, "clock_getres": 229, "exit_group": 231,
    "epoll_wait": 232, "epoll_ctl": 233, "openat": 257, "mkdirat": 258,
    "newfstatat": 262, "unlinkat": 263, "readlinkat": 267, "fchmodat": 268,
    "faccessat": 269, "pselect6": 270, "ppoll": 271, "set_robust_list": 273,
    "splice": 275, "tee": 276, "sync_file_range": 277, "vmsplice": 278,
    "utimensat": 280, "epoll_pwait": 281, "signalfd": 282, "eventfd": 284,
    "fallocate": 285, "accept4": 288, "signalfd4": 289, "eventfd2": 290,
    "epoll_create1": 291, "dup3": 292, "pipe2": 293, "prlimit64": 302,
    "getrandom": 318, "memfd_create": 319, "execveat": 322, "statx": 332,
    "rseq": 334, "clone3": 435, "close_range": 436,
    "openat2": 437, "faccessat2": 439, "epoll_pwait2": 441,
}

# ---------------------------------------------------------------------------
# The two denial groups.  These names are FROZEN: the predicate conjuncts
# NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY, PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY
# and EXEC_DENIED_AFTER_LEG_ENTRY are each bound to exactly one group below, and
# the independent checker re-derives membership from this module (never from a
# harness summary line).
# ---------------------------------------------------------------------------

NETWORK_CREATION_SYSCALLS = (
    "socket", "socketpair", "connect", "bind", "listen", "accept", "accept4",
    "sendto", "sendmsg",
)

PROCESS_CREATION_SYSCALLS = (
    "fork", "vfork", "clone", "clone3",
)

EXEC_SYSCALLS = (
    "execve", "execveat",
)

DENIAL_GROUPS = {
    "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY": NETWORK_CREATION_SYSCALLS,
    "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY": PROCESS_CREATION_SYSCALLS,
    "EXEC_DENIED_AFTER_LEG_ENTRY": EXEC_SYSCALLS,
}

# Returned for every denied syscall.  EACCES=13, EPERM=1.  Both are RETURNED
# errors; neither is a kill.  EPERM is the historical seccomp default, EACCES is
# the shape a denied capability takes for filesystem-like operations; D3 accepts
# exactly this set and rejects a kill as evidence.
DENIED_ERRNO = 13          # EACCES
ACCEPTED_DENIAL_ERRNOS = (1, 13)
DENIED_ERRNO_NAME = "EACCES"

# strace prints the errno NAME on failure (`= -1 ECHILD (...)`), and the leading
# -1 is a placeholder -- NOT the errno number.  A parser that computes `-ret`
# therefore turns EVERY named failure into errno 1 (EPERM), which is an accepted
# denial errno here.  That is how a supervisor shell's ordinary `wait()` returning
# ECHILD was once counted as a denied `wait4`, inflating the denial evidence.
# Resolution must go through this table; an unknown name is UNKNOWN, never zero.
ERRNO_BY_NAME = {
    "EPERM": 1, "ENOENT": 2, "ESRCH": 3, "EINTR": 4, "EIO": 5, "ENXIO": 6,
    "E2BIG": 7, "ENOEXEC": 8, "EBADF": 9, "ECHILD": 10, "EAGAIN": 11,
    "EWOULDBLOCK": 11, "ENOMEM": 12, "EACCES": 13, "EFAULT": 14, "ENOTBLK": 15,
    "EBUSY": 16, "EEXIST": 17, "EXDEV": 18, "ENODEV": 19, "ENOTDIR": 20,
    "EISDIR": 21, "EINVAL": 22, "ENFILE": 23, "EMFILE": 24, "ENOTTY": 25,
    "ETXTBSY": 26, "EFBIG": 27, "ENOSPC": 28, "ESPIPE": 29, "EROFS": 30,
    "EMLINK": 31, "EPIPE": 32, "EDOM": 33, "ERANGE": 34, "EDEADLK": 35,
    "ENAMETOOLONG": 36, "ENOLCK": 37, "ENOSYS": 38, "ENOTEMPTY": 39,
    "ELOOP": 40, "ENOMSG": 42, "EIDRM": 43, "ECHRNG": 44, "EL2NSYNC": 45,
    "EL3HLT": 46, "EL3RST": 47, "ELNRNG": 48, "EUNATCH": 49, "ENOCSI": 50,
    "EL2HLT": 51, "EBADE": 52, "EBADR": 53, "EXFULL": 54, "ENOANO": 55,
    "EBADRQC": 56, "EBADSLT": 57, "EBFONT": 59, "ENOSTR": 60, "ENODATA": 61,
    "ETIME": 62, "ENOSR": 63, "ENONET": 64, "ENOPKG": 65, "EREMOTE": 66,
    "ENOLINK": 67, "EADV": 68, "ESRMNT": 69, "ECOMM": 70, "EPROTO": 71,
    "EMULTIHOP": 72, "EDOTDOT": 73, "EBADMSG": 74, "EOVERFLOW": 75,
    "ENOTUNIQ": 76, "EBADFD": 77, "EREMCHG": 78, "ELIBACC": 79,
    "ELIBBAD": 80, "ELIBSCN": 81, "ELIBMAX": 82, "ELIBEXEC": 83,
    "EILSEQ": 84, "ERESTART": 85, "ESTRPIPE": 86, "EUSERS": 87,
    "ENOTSOCK": 88, "EDESTADDRREQ": 89, "EMSGSIZE": 90, "EPROTOTYPE": 91,
    "ENOPROTOOPT": 92, "EPROTONOSUPPORT": 93, "ESOCKTNOSUPPORT": 94,
    "EOPNOTSUPP": 95, "ENOTSUP": 95, "EPFNOSUPPORT": 96, "EAFNOSUPPORT": 97,
    "EADDRINUSE": 98, "EADDRNOTAVAIL": 99, "ENETDOWN": 100, "ENETUNREACH": 101,
    "ENETRESET": 102, "ECONNABORTED": 103, "ECONNRESET": 104, "ENOBUFS": 105,
    "EISCONN": 106, "ENOTCONN": 107, "ESHUTDOWN": 108, "ETOOMANYREFS": 109,
    "ETIMEDOUT": 110, "ECONNREFUSED": 111, "EHOSTDOWN": 112,
    "EHOSTUNREACH": 113, "EALREADY": 114, "EINPROGRESS": 115, "ESTALE": 116,
    "EUCLEAN": 117, "ENOTNAM": 118, "ENAVAIL": 119, "EISNAM": 120,
    "EREMOTEIO": 121, "EDQUOT": 122, "ENOMEDIUM": 123, "EMEDIUMTYPE": 124,
    "ECANCELED": 125, "ENOKEY": 126, "EKEYEXPIRED": 127,
    "EKEYREVOKED": 128, "EKEYREJECTED": 129, "EOWNERDEAD": 130,
    "ENOTRECOVERABLE": 131, "ERFKILL": 132, "EHWPOISON": 133,
}


def denial_syscall_names() -> list[str]:
    """Every syscall name the policy denies, in stable order."""
    ordered: list[str] = []
    for group in ("NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY",
                  "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY",
                  "EXEC_DENIED_AFTER_LEG_ENTRY"):
        for name in DENIAL_GROUPS[group]:
            if name not in ordered:
                ordered.append(name)
    return ordered


def denial_syscall_numbers() -> list[int]:
    return sorted(X86_64_SYSCALLS[name] for name in denial_syscall_names())


# ---------------------------------------------------------------------------
# Policy spec
# ---------------------------------------------------------------------------

def policy_spec() -> dict:
    """The complete, deterministic policy description.

    Everything the filter does is declared here as data.  build_filter() is a
    mechanical expansion of this spec, and the independent checker rebuilds the
    byte stream from the spec and compares it to the precommitted hash -- so
    the filter cannot silently diverge from the declared policy.
    """
    return {
        "schema": POLICY_VERSION,
        "architecture": "x86_64",
        "audit_arch": AUDIT_ARCH_X86_64,
        "arch_guard": "DENY_ABI_MISMATCH_BY_ERRNO_SHORT_CIRCUIT",
        "arch_guard_effect": (
            "if seccomp_data.arch != AUDIT_ARCH_X86_64 the filter RETURNS "
            "ERRNO|EACCES without comparing syscall numbers.  It must NOT return "
            "ALLOW: an earlier revision did, on the reasoning that numbers from a "
            "foreign ABI are not comparable, and that was a live escape.  Measured "
            "on this host, a native 64-bit process issuing int $0x80 with the i386 "
            "socket number created a socket under the policy, because the kernel "
            "reports seccomp_data.arch = AUDIT_ARCH_I386 for it, the guard "
            "short-circuited to ALLOW, and no audit record (type=1326) was emitted "
            "at all -- while the native syscall=41/57/59 attempts in the same "
            "process were denied with code=0x50000.  Denying the mismatch closes "
            "network, process-creation and exec on the foreign path at once."
        ),
        "default_action": "ALLOW",
        "denied_syscalls": {
            group: [X86_64_SYSCALLS[name] for name in names]
            for group, names in DENIAL_GROUPS.items()
        },
        "denied_syscall_names": denial_syscall_names(),
        "denied_syscall_numbers": denial_syscall_numbers(),
        "denial_action": "SECCOMP_RET_ERRNO|EACCES",
        "denial_errno": DENIED_ERRNO,
        "kill_actions_used": False,
        "ret_kill_permitted": False,
        "no_new_privs_required": True,
        "policy_installed_relative_to_entry_barrier": "BEFORE",
        "notes": (
            "Returned-errno denial only. No SECCOMP_RET_KILL_* is emitted, so a "
            "denied leg observes EACCES and remains able to complete honestly."
        ),
    }


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def policy_spec_sha256() -> tuple[str, bytes]:
    payload = canonical_bytes(policy_spec())
    return hashlib.sha256(payload).hexdigest(), payload


# ---------------------------------------------------------------------------
# Filter construction
# ---------------------------------------------------------------------------

def build_filter() -> list[tuple[int, int, int, int]]:
    """Return the classic-BPF program as (code, jt, jf, k) tuples.

    Program layout -- EVERY syscall number comparison is a 1-instruction
    conditional jump to the shared DENY block, so the program length is
    O(number of denied syscalls) and there is exactly ONE deny site.  One deny
    site is deliberate: it makes "the policy denied X" a single, auditable
    instruction rather than one duplicated return per syscall.

        0: A = seccomp_data.arch
        1: if A == AUDIT_ARCH_X86_64 -> 3 else 2
        2: return ERRNO|EACCES          (foreign ABI: DENY, never allow)
        3: A = seccomp_data.nr
        4..: if A == <denied nr> -> JUMP TO deny_site, else next
        N:   return ALLOW               (default)
        N+1: return ERRNO|EACCES        (deny_site)

    Jump threading: there is exactly ONE deny site, the last instruction.  Every
    comparison makes its TRUE branch jump FORWARD to it (`jf` is always 0, i.e.
    a non-matching syscall number falls through to the next comparison and
    finally to the default ALLOW).  A duplicated per-syscall return would work
    but would make "the policy denied X" 15 separate instructions instead of one
    auditable site.

    `jt` SEMANTICS (pinned here after a self-inflicted near-regression).
    In classic BPF a jump offset counts instructions AFTER the instruction that
    FOLLOWS the jump: from index i, `jt = n` lands on index i + 1 + n.  So the
    offset that reaches the deny site at D is exactly `D - i - 1`.
    Do not "simplify" this to `D - i - 2`: that lands on the default-ALLOW
    instruction instead, which silently makes the whole deny list inert (every
    denied syscall returns ALLOW).  That variant was committed and caught only
    because `check_filter_denies_exactly` simulates the encoded image over the
    deny set at build time; without it a filter that denies NOTHING would have
    gone out behind a receipt that still bound the policy hash.

    Contract note: execve/execveat belong in the deny set.  The D3 contract says
    the policy must prevent "new network/provider IPC plus fork / clone / vfork
    and execve / execveat after the leg reaches its measured entrypoint", so a
    denied execve(59) is required behaviour, not an over-broad denial.
    """
    numbers = denial_syscall_numbers()
    program: list[tuple[int, int, int, int]] = []
    program.append((BPF_LD | BPF_W | BPF_ABS, 0, 0, struct_seccomp_data_arch))
    program.append((BPF_JMP | BPF_JEQ | BPF_K, 1, 0, AUDIT_ARCH_X86_64))
    # ABI MISMATCH -> ERRNO(EACCES), never ALLOW.  See the arch-guard note above:
    # an ALLOW here is a live capability escape, because seccomp_data.nr is then
    # interpreted in a foreign number space the deny list does not cover.
    program.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO | DENIED_ERRNO))
    program.append((BPF_LD | BPF_W | BPF_ABS, 0, 0, struct_seccomp_data_nr))
    # The default ALLOW lands at 4 + len(numbers); the deny site is the
    # instruction after it, and every comparison's TRUE branch jumps to it.
    default_allow_index = 4 + len(numbers)
    deny_site_index = default_allow_index + 1
    for offset, number in enumerate(numbers):
        comparison_index = 4 + offset
        jump = deny_site_index - comparison_index - 1
        assert 0 <= jump <= 255, "jump offset out of range"
        program.append((BPF_JMP | BPF_JEQ | BPF_K, jump, 0, number))
    # NOTE -- x32 range is deliberately NOT guarded by an instruction.  A guard
    # (JGE 0x40000000 -> deny site) was implemented and MEASURED as unreachable
    # on this host, so it was removed rather than shipped as an unexercised
    # instruction that a receipt would report as enforced.  Evidence: probes on
    # 0x40000000, 0x40000029 and 0x400001ff returned ENOSYS (errno 38) with ZERO
    # type=1326 audit records, while every in-deny-set syscall in the same pid
    # produced one -- i.e. the kernel rejects x32-range numbers before seccomp
    # evaluates the filter.  See D3-POLICY-002 for the carrier condition under
    # which this residual becomes live.
    program.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ALLOW))
    program.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO | DENIED_ERRNO))
    check_filter_denies_exactly(program, numbers)
    return program


def check_filter_denies_exactly(program, numbers) -> dict:
    """Simulate the encoded program over the deny set and over allowed numbers.

    This is an internal consistency proof, not a substitute for the kernel: the
    authoritative evidence is the kernel's own denial/audit record.  It exists to
    make a jump offset that denies the wrong set -- including a filter that
    denies NOTHING -- a hard failure at build time rather than a silent receipt
    bound to an inert policy.

    Returns a report; raises AssertionError on any mismatch.
    """
    image = encode_filter(program)
    insns = [struct.unpack_from("=HBBI", image, i * 8) for i in range(len(image) // 8)]
    denied = set(numbers)
    deny_tail = SECCOMP_RET_ERRNO | DENIED_ERRNO
    report: dict = {"program_len": len(program), "deny_site_action": hex(deny_tail)}

    def run(nr: int) -> int:
        a = 0
        pc = 0
        for _ in range(64):
            code, jt, jf, k = insns[pc]
            if code == (BPF_LD | BPF_W | BPF_ABS):
                a = AUDIT_ARCH_X86_64 if k == struct_seccomp_data_arch else nr
                pc += 1
            elif code == (BPF_JMP | BPF_JEQ | BPF_K):
                pc = pc + 1 + (jt if a == k else jf)
            elif code == (BPF_JMP | BPF_JGE | BPF_K):
                pc = pc + 1 + (jt if (a & 0xFFFFFFFF) >= (k & 0xFFFFFFFF) else jf)
            elif code == (BPF_RET | BPF_K):
                return k
            else:
                raise AssertionError("unexpected opcode %#x" % code)
        raise AssertionError("filter did not return within 64 instructions")

    # 1. every denied number must reach the deny site
    simulated_denied = {}
    for nr in sorted(denied):
        ret = run(nr)
        simulated_denied[nr] = ret
        assert ret == deny_tail, (
            "syscall %d must reach the deny site (%#x) but got %#x -- a jump offset "
            "is wrong, and a filter that denies nothing is inert while still being "
            "bound into the receipt by its hash" % (nr, deny_tail, ret))
    assert simulated_denied, "deny set is empty; the policy would deny nothing"
    # the deny site must be the LAST instruction and be reachable, not dead code
    assert insns[-1][0] == (BPF_RET | BPF_K) and insns[-1][3] == deny_tail, (
        "the deny site is not the final instruction returning the deny action")

    # 2. ordinary syscalls a correct program needs must survive.  0x3fffffff is
    #    the top of the non-x32 number space: it proves the x32 guard is not
    #    swallowing ordinary numbers.
    must_allow = [0, 1, 2, 3, 9, 13, 14, 60, 202, 231, 262, 0x3FFFFFFF]
    simulated_allowed = {}
    for nr in must_allow:
        ret = run(nr)
        simulated_allowed[nr] = ret
        assert ret == SECCOMP_RET_ALLOW, (
            "nr=%d must be ALLOWed (%#x) but got %#x -- the deny set is too broad"
            % (nr, SECCOMP_RET_ALLOW, ret))

    report["simulated_denied"] = sorted(simulated_denied)
    report["simulated_allowed"] = sorted(simulated_allowed)
    report["deny_tail"] = deny_tail
    report["insns"] = len(program)
    return report


def simulate_filter(program, arch: int, nr: int) -> int:
    """Simulate the encoded program for an explicit (seccomp_data.arch, nr) pair.

    Unlike check_filter_denies_exactly this makes the architecture an *input*,
    so the foreign-ABI path can be tested directly instead of being assumed.
    """
    image = encode_filter(program)
    insns = [struct.unpack_from("=HBBI", image, i * 8) for i in range(len(image) // 8)]
    a = 0
    pc = 0
    for _ in range(64):
        code, jt, jf, k = insns[pc]
        if code == (BPF_LD | BPF_W | BPF_ABS):
            a = arch if k == struct_seccomp_data_arch else nr
            pc += 1
        elif code == (BPF_JMP | BPF_JEQ | BPF_K):
            pc = pc + 1 + (jt if a == k else jf)
        elif code == (BPF_JMP | BPF_JGE | BPF_K):
            pc = pc + 1 + (jt if (a & 0xFFFFFFFF) >= (k & 0xFFFFFFFF) else jf)
        elif code == (BPF_RET | BPF_K):
            return k
        else:
            raise AssertionError("unexpected opcode %#x" % code)
    raise AssertionError("filter did not return within 64 instructions")


def check_foreign_abi_cannot_escape(program) -> dict:
    """A foreign-ABI syscall must be DENIED, not allowed by an arch short circuit.

    Load-bearing history (measured on the target host, not reasoned about):
    an earlier revision returned SECCOMP_RET_ALLOW when seccomp_data.arch was
    not AUDIT_ARCH_X86_64.  A native 64-bit process issuing `int $0x80` with
    the i386 socket number therefore created a real socket under the policy,
    and emitted NO audit record at all -- while its native syscall=41/57/59
    attempts in the same process were denied with code=0x50000.  The kernel
    reports arch=40000003 (AUDIT_ARCH_I386), compat=1 for those calls, so the
    ABI mismatch is observable and must be treated as hostile, not as "numbers
    are not comparable, so allow".
    """
    mismatch = SECCOMP_RET_ERRNO | DENIED_ERRNO
    report = {"foreign_arch_probe": {}, "native_arch_probe": {}}
    # Foreign numbers to probe: the i386 number space is unrelated to the
    # x86_64 deny set, so probe a wide span rather than only known meanings.
    for nr in (1, 2, 4, 11, 20, 41, 57, 59, 102, 120, 359, 435):
        ret = simulate_filter(program, AUDIT_ARCH_I386, nr)
        report["foreign_arch_probe"][nr] = hex(ret)
        assert ret == mismatch, (
            "foreign-ABI syscall nr=%d reached action %#x, expected ERRNO|EACCES "
            "(%#x).  An arch short circuit that returns ALLOW here is a live "
            "capability escape: the i386 network/clone/exec numbers are not "
            "covered by the x86_64 deny list." % (nr, ret, mismatch))
    # x32 numbers occupy the 0x40000000 range; the arch word for x32 is also
    # not AUDIT_ARCH_X86_64, so the same guard must deny them.
    # x32 range: recorded expectation, NOT an assertion.  The filter's default
    # ALLOW does cover these numbers, so no instruction denies them; the kernel
    # is what makes them harmless here by rejecting x32-range numbers before
    # seccomp runs (measured: ENOSYS, no audit record).  Asserting a denial here
    # would be asserting a property the program does not have -- that mistake
    # would hide the residual instead of documenting it.
    for nr in (0x40000000 | 41, 0x40000000 | 39, 0x4000019b, 0x7FFFFFFF):
        ret = simulate_filter(program, AUDIT_ARCH_X86_64, nr)
        report["native_arch_probe"][nr] = hex(ret)
        assert ret == SECCOMP_RET_ALLOW, (
            "nr=%#x is in the x32 range and this program is NOT expected to deny "
            "it; if it is now denied, the policy gained an unmeasured instruction"
            % nr)
    report["x32_range"] = ("NOT_DENIED_BY_PROGRAM: covered only by the host kernel "
                           "rejecting x32 numbers before seccomp (observed ENOSYS, "
                           "no type=1326 record). Live only if CONFIG_X86_X32_ABI "
                           "is enabled -- see D3-POLICY-002")
    # boundary: one below the x32 range must still be reachable by the normal
    # number comparisons, i.e. the guard must not swallow ordinary numbers.
    below = 0x3FFFFFFF
    assert simulate_filter(program, AUDIT_ARCH_X86_64, below) == SECCOMP_RET_ALLOW, (
        "the x32 guard is too broad: nr=%#x (below the x32 range) was denied, "
        "which would break ordinary syscalls" % below)
    report["x32_boundary_below_range"] = hex(below) + " -> ALLOW (correct)"
    # And the native arch word must still deny the whole deny set.
    report["denied_native"] = sorted(denial_syscall_numbers())
    return report

    for nr in denied:
        got = run(nr)
        assert got == deny_tail, (
            "syscall %d must reach the deny site (ret %#x) but got %#x" % (nr, deny_tail, got))
    # Ordinary syscalls an honest leg needs must survive; nothing outside the
    # declared deny set may be denied.
    must_allow = [0, 1, 2, 3, 9, 13, 14, 60, 202, 231, 262]
    for nr in must_allow:
        got = run(nr)
        assert got == SECCOMP_RET_ALLOW, (
            "syscall %d must be ALLOWED but the filter returned %#x" % (nr, got))
    # Discrimination proof: the deny set must be non-empty and the filter must
    # actually have a reachable deny site (guards against an inert policy).
    assert denied, "deny set must not be empty"
    assert run(sorted(denied)[0]) == deny_tail, "deny site unreachable"
    return {"simulated_denied": sorted(denied), "simulated_allowed": must_allow,
            "deny_tail": deny_tail, "insns": len(insns)}


def encode_filter(program: list[tuple[int, int, int, int]]) -> bytes:
    """Encode the program as the exact `struct sock_filter[]` byte image."""
    out = bytearray()
    for code, jt, jf, k in program:
        # struct sock_filter { __u16 code; __u8 jt; __u8 jf; __u32 k; }
        out += struct.pack("=HBBI", code & 0xFFFF, jt & 0xFF, jf & 0xFF,
                           k & 0xFFFFFFFF)
    return bytes(out)


def filter_sha256() -> tuple[str, bytes]:
    """Hash of the exact BPF byte image the legs install."""
    image = encode_filter(build_filter())
    return hashlib.sha256(image).hexdigest(), image


def denial_policy_identity() -> dict:
    """The full precommitted policy identity: spec + serialized filter bytes.

    `policy_sha256` covers the SPEC (declarative: which syscalls, which action,
    which errno).  `filter_sha256` covers the BYTE IMAGE actually handed to the
    kernel.  `policy_bytes_path` / `filter_bytes_path` let an auditor hash both
    from disk after the run and compare to these digests.
    """
    spec_hash, spec_bytes = policy_spec_sha256()
    filter_hash, filter_image = filter_sha256()
    program = build_filter()
    return {
        "schema": POLICY_VERSION,
        "policy_sha256": spec_hash,
        "policy_bytes": len(spec_bytes),
        "policy_spec": policy_spec(),
        "filter_sha256": filter_hash,
        "filter_bytes": len(filter_image),
        "filter_instructions": len(program),
        "deny_sites": 1,
        "denied_syscall_count": len(denial_syscall_numbers()),
        "denied_errno": DENIED_ERRNO,
        "denied_errno_name": DENIED_ERRNO_NAME,
        "accepted_denial_errnos": list(ACCEPTED_DENIAL_ERRNOS),
    }


# ---------------------------------------------------------------------------
# GATE-MANDATED APPLICABILITY AND IDENTITY MECHANISMS (GPT D3 pre-report ruling)
#
# Three conditions were imposed before the D3-A..D3-E battery may run:
#   1. X32_ROUTE_UNAVAILABLE must be MECHANICAL, not prose -- and the unfiltered
#      arm is required, because it is what distinguishes "this host has no x32
#      syscall route" from "something about the installed filter produced ENOSYS".
#   2. A PERMANENT NEGATIVE CONTROL for the self-check: because the old
#      check_filter_denies_exactly() had passed vacuously (D3-POLICY-T01),
#      showing the repaired check passes a good filter is NOT sufficient.  A
#      deliberately broken filter must make it FAIL.
#   3. The independent checker must FAIL CLOSED on mixed identities: five named
#      policy-hash sites must all agree, and one mismatch invalidates the arm.
# ---------------------------------------------------------------------------

#: The accepted policy artifact for D3.  Every accepted D3 result must bind this
#: and not the superseded 2cec76ef... , which remains valid ONLY as historical
#: falsifier evidence that D3-POLICY-001 was real.
ACCEPTED_FILTER_SHA256 = (
    "2d155ba65d4c584512235194d8359f9b0ec828e8b4d3062694526605c882b1fe")

SUPERSEDED_FILTER_SHA256 = (
    "2cec76ef17f9db55270823b4b89db8a3f3f73236afe185d07b6e532437b83dbf")

#: The five independent sites that must all carry the same policy identity.
#: GPT naming correction: the site is the hash of the bytes SUBMITTED by the
#: install path, NOT a kernel readback.  Linux gives no way to read back the
#: installed BPF program: PR_GET_SECCOMP == 2 proves filtering is ACTIVE, and the
#: install path plus the bound bytes prove WHICH program was submitted.  Those are
#: two separate facts and must never be merged into "the kernel proved these exact
#: 168 bytes are installed".
POLICY_IDENTITY_SITES = (
    "precommit_expected_sha256",   # frozen before any leg launches
    "submitted_filter_sha256",     # bytes handed to the kernel by the install path
    "leg_receipt_filter_sha256",   # hash written into the leg's own receipt
    "observer_filter_sha256",      # hash recorded by the external observer/audit
    "checker_expected_sha256",     # hash the independent checker demands
)


def check_policy_identity_sites(observed: dict) -> dict:
    """Fail closed unless all five identity sites carry the accepted hash.

    This is the mechanism for GPT's rule: "precommit policy hash / runtime
    installed filter hash / leg receipt policy hash / audit observer policy hash
    / independent-checker expected hash must all equal 2d155ba6...  One mismatch
    invalidates that arm."

    Raises AssertionError naming every offending site -- a checker that reports
    only "mismatch" forces a re-run to find out which copy drifted.
    """
    problems = []
    for site in POLICY_IDENTITY_SITES:
        if site not in observed:
            problems.append("%s=MISSING (fail closed: an absent site is not a match)"
                            % site)
            continue
        got = observed[site]
        if got is None:
            problems.append("%s=None" % site)
        elif got == SUPERSEDED_FILTER_SHA256:
            problems.append("%s=%s (SUPERSEDED policy; invalid for D3 evidence)"
                            % (site, got[:12]))
        elif got != ACCEPTED_FILTER_SHA256:
            problems.append("%s=%s (expected %s)"
                            % (site, got[:12], ACCEPTED_FILTER_SHA256[:12]))
    assert not problems, (
        "POLICY IDENTITY MISMATCH -- arm invalid. Offending sites: %s"
        % "; ".join(problems))
    return {"schema": POLICY_VERSION, "identity_ok": True, "sites": list(POLICY_IDENTITY_SITES),
            "accepted_filter_sha256": ACCEPTED_FILTER_SHA256}


def kernel_x32_abi_enabled(config_paths=("/proc/config.gz",)) -> dict:
    """Was the kernel built with an x32 syscall route at all?

    FAILS CLOSED: an unreadable configuration returns established=False, so the
    apparatus refuses rather than silently running a 21-instruction policy that
    cannot deny the x32 number space (the D3-POLICY-002 residual).
    """
    import gzip
    import platform
    release = platform.release()
    candidates = list(config_paths) + [
        "/boot/config-%s" % release, "/boot/config", "/usr/lib/modules/%s/config" % release]
    for path in candidates:
        opener = gzip.open if path.endswith(".gz") else open
        try:
            with opener(path, "rt", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if line.startswith("# CONFIG_X86_X32_ABI is not set"):
                        return {"established": True, "enabled": False, "source": path,
                                "line": line,
                                "reading": "kernel built without an x32 ABI route"}
                    if line.startswith("CONFIG_X86_X32_ABI="):
                        value = line.split("=", 1)[1].strip()
                        enabled = value not in ("n", "N", "")
                        return {"established": True, "enabled": enabled, "source": path,
                                "line": line,
                                "reading": "x32 ABI %s" % ("ENABLED" if enabled else "disabled")}
        except OSError:
            continue
    return {"established": False, "enabled": None, "source": None, "line": None,
            "reading": "no readable kernel config among %r -- cannot establish" % (candidates,)}


def x32_route_unavailable(evidence: dict) -> dict:
    """X32_ROUTE_UNAVAILABLE, exactly as frozen by GPT.

        X32_ROUTE_UNAVAILABLE := CONFIG_X86_X32_ABI is not enabled
                               AND unfiltered x32 __NR_socket attempt returns ENOSYS
                               AND filtered   x32 __NR_socket attempt returns ENOSYS
                               AND no socket descriptor is created

    `evidence` is produced by executing the compiled control (/tmp/a12d3_x32_control
    --raw and --policy); nothing here is inferred from the policy's own behaviour,
    because the whole point is to separate the HOST property from a FILTER artifact.
    """
    need = {
        "config_enabled",                          # bool, from kernel_x32_abi_enabled()
        "raw_x32_socket_ret", "raw_descriptor_delta",
        "filtered_x32_socket_ret", "filtered_descriptor_delta",
        "policy_state_seen_by_parent",             # e.g. "Seccomp:\t2"
    }
    missing = sorted(need - set(evidence))
    assert not missing, (
        "X32 precondition cannot be established absent %r -- APPARATUS-MISMATCH / REFUSE. "
        "Never silently run the 21-instruction policy without it." % missing)

    claims = {
        "config_x32_not_enabled": evidence["config_enabled"] is False,
        "unfiltered_x32_socket_is_enosys": evidence["raw_x32_socket_ret"] == -38,
        "filtered_x32_socket_is_enosys": evidence["filtered_x32_socket_ret"] == -38,
        "no_descriptor_from_x32_raw": evidence["raw_descriptor_delta"] == 0,
        "no_descriptor_from_x32_filtered": evidence["filtered_descriptor_delta"] == 0,
    }
    established = all(claims.values())
    assert established, (
        "X32 CARRIER PRESENT OR CANNOT BE ESTABLISHED ABSENT -> APPARATUS-MISMATCH. "
        "Refusing to run. Detail: %s" % json.dumps(claims, sort_keys=True))
    return {"schema": POLICY_VERSION, "predicate": "X32_ROUTE_UNAVAILABLE",
            "established": True, "claims": claims,
            "policy_state_seen_by_parent": evidence["policy_state_seen_by_parent"],
            "note": ("host-conditioned residual: the 21-instruction filter denies no "
                     "x32-range number, and is admissible only while no x32 route exists. "
                     "This policy is NOT claimed to be generally x86 ABI-complete; on an "
                     "x32-enabled kernel the guard must be reinstated and independently "
                     "exercised.")}


def _t01_self_check_rejects(program, numbers) -> tuple[bool, str]:
    """Run the repaired checks against `program`; return (implausible, reason).

    A wrong jump offset can drive the simulator off the end of the program; a
    malformed filter must be REJECTED by the check, so an IndexError is a
    rejection (with its own reason), never an unhandled crash that could be
    mistaken for an infrastructure failure.
    """
    try:
        check_filter_denies_exactly(program, numbers)
    except AssertionError as exc:
        return True, str(exc).split("\n")[0][:200]
    except IndexError:
        return True, ("simulator ran off the end of the program: a jump offset "
                      "leaves the instruction list")
    # The simulator only ever models seccomp_data.arch == AUDIT_ARCH_X86_64, so it
    # is structurally blind to the arch guard.  D3-POLICY-001 lived exactly there,
    # which is why the structural self-check must be driven too -- otherwise this
    # negative control would certify a check that cannot see the regression it
    # exists to catch.
    structural = policy_self_check(program)
    failed = sorted(k for k, v in structural.items()
                    if isinstance(v, bool) and not v)
    if failed:
        return True, "structural self-check failed: %s" % ", ".join(failed)
    return False, "accepted (NO FAILURE RAISED)"


def t01_negative_control() -> dict:
    """Prove the repaired self-check FAILS on a deliberately inert/broken filter.

    GPT: "Since the self-check previously passed vacuously, deliberately mutate a
    jump/deny action so the deny set becomes inert and prove the rebuilt
    self-check fails. Do not merely show the repaired self-check passes the good
    filter."  The acceptance pair is good->PASS with broken->FAIL, and a broken
    filter must not be able to enter the battery.
    """
    numbers = denial_syscall_numbers()
    good = build_filter()
    report = check_filter_denies_exactly(good, numbers)      # arm 1: must PASS
    assert report["simulated_denied"] == sorted(numbers)

    mutations = []
    for name, mutate, why in [
        ("comparison_lands_past_deny_site",
         lambda p: p[:4] + [(p[4][0], p[4][1] + 1, p[4][2], p[4][3])] + p[5:],
         "off-by-one jump: every comparison overshoots the deny site, so the deny "
         "list is INERT while the receipt still binds the policy hash"),
        ("deny_action_weakened_to_allow",
         lambda p: p[:-1] + [(p[-1][0], p[-1][1], p[-1][2], SECCOMP_RET_ALLOW)],
         "deny site returns ALLOW: the policy denies nothing at all"),
        ("deny_errno_changed",
         lambda p: p[:-1] + [(p[-1][0], p[-1][1], p[-1][2], SECCOMP_RET_ERRNO | 1)],
         "deny site returns a different errno than the frozen action"),
        ("arch_guard_allows_mismatch",
         lambda p: p[:2] + [(p[2][0], p[2][1], p[2][2], SECCOMP_RET_ALLOW)] + p[3:],
         "the D3-POLICY-001 regression itself: foreign ABI returned ALLOW"),
        ("jump_forward_far_past_deny_site",
         lambda p: p[:4] + [(p[4][0], p[4][1] + 5, p[4][2], p[4][3])] + p[5:],
         "grossly wrong offset: comparison lands beyond the program tail"),
    ]:
        broken = mutate(good)
        assert broken != good, "%s did not change the program" % name
        rejected, reason = _t01_self_check_rejects(broken, numbers)
        assert rejected, (
            "T01 NEGATIVE CONTROL FAILED: mutation %r was ACCEPTED by the repaired "
            "self-check -- the check is still vacuous for this defect class" % name)
        mutations.append({"mutation": name, "intent": why, "self_check": "FAIL (correct)",
                          "reason": reason})

    return {"schema": POLICY_VERSION,
            "acceptance_pair": {"good_filter": "PASS", "broken_filter": "FAIL"},
            "good_filter_sha256": filter_sha256()[0],
            "good_filter_instructions": len(good),
            "mutations": mutations,
            "mutations_rejected": len(mutations),
            "battery_entry_allowed": True}


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reconcile_identity_sites_from_disk(directory) -> dict:
    """Read the FIVE identity sites from their real locations and reconcile them.

    This is what makes check_policy_identity_sites() non-circular: the precommit
    and runtime-installed sites are hashed from BYTES ON DISK, so a leg that
    installed a different filter than the receipt claims is caught here rather
    than by comparing a value to a copy of itself.

    FAILS CLOSED: a site whose artifact is absent is recorded as None (i.e.
    MISSING) rather than being silently skipped -- "no evidence" is not "match".
    """
    directory = Path(directory)
    precommit = directory / "d3-policy-precommit.json"
    filter_bin = directory / "d3-denial-filter.bin"
    header = directory / "d3_denial_filter.h"
    checker_expected = directory / "d3-checker-expected.json"

    observed: dict = {}
    observed["precommit_expected_sha256"] = None
    if precommit.is_file():
        try:
            observed["precommit_expected_sha256"] = (
                json.loads(precommit.read_text()).get("policy", {}).get("filter_sha256"))
        except (OSError, ValueError):
            observed["precommit_expected_sha256"] = None
    # submitted, not "installed": this is the byte image the install path hands to
    # the kernel.  It is exact identity evidence for the SUBMISSION, and activation
    # is established separately by PR_GET_SECCOMP / the parent-visible Seccomp line.
    observed["submitted_filter_sha256"] = sha256_file(filter_bin) if filter_bin.is_file() else None
    # the leg receipt / observer / checker-expected files are produced by the
    # battery; until then they are honestly MISSING, not assumed equal.
    observed["leg_receipt_filter_sha256"] = None
    observed["observer_filter_sha256"] = None
    observed["checker_expected_sha256"] = None
    if checker_expected.is_file():
        try:
            observed["checker_expected_sha256"] = json.loads(
                checker_expected.read_text()).get("filter_sha256")
        except (OSError, ValueError):
            observed["checker_expected_sha256"] = None

    report = {"directory": str(directory), "observed": observed,
              "header_present": header.is_file(),
              "filter_bin_present": filter_bin.is_file(),
              "precommit_present": precommit.is_file()}
    # The byte image on disk must equal the in-process build, or the artifact the
    # legs install has drifted from the policy this module reasons about.
    built = filter_sha256()[0]
    report["in_process_filter_sha256"] = built
    report["disk_matches_build"] = (observed["submitted_filter_sha256"] == built)
    # GPT-required distinction, published explicitly so no reader can mistake
    # activation evidence for an imaginary BPF readback.
    report["policy_submitted_sha256"] = observed["submitted_filter_sha256"]
    report["kernel_seccomp_mode"] = None          # filled from the leg's PR_GET_SECCOMP
    report["kernel_policy_active"] = None         # filled from PR_GET_SECCOMP == 2
    report["exact_policy_identity_binding"] = ("precommit_expected / submitted / leg_receipt / "
                                               "observer / checker_expected reconciliation")
    report["kernel_readback_available"] = False   # Linux offers no way to read back the BPF program
    return report


def precommit_policy(directory) -> dict:
    """Freeze the policy BEFORE any leg runs, so it cannot be written after the
    fact to match whatever was observed."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    identity = denial_policy_identity()
    precommit = {
        "schema": POLICY_VERSION,
        "precommitted_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "policy": {"policy_sha256": identity["policy_sha256"],
                   "filter_sha256": identity["filter_sha256"],
                   "filter_instructions": identity["filter_instructions"],
                   "denied_errno": identity["denied_errno"]},
        "applicability": {"requires": "X32_ROUTE_UNAVAILABLE",
                          "refusal": "APPARATUS-MISMATCH if a x32 carrier is present or "
                                     "cannot be established absent"},
        "claim_boundary": ("not generally x86 ABI-complete; host-conditioned (D3-POLICY-002)"),
    }
    (directory / "d3-policy-precommit.json").write_text(
        json.dumps(precommit, indent=2, sort_keys=True) + "\n")
    (directory / "d3-checker-expected.json").write_text(
        json.dumps({"schema": POLICY_VERSION,
                    "filter_sha256": identity["filter_sha256"],
                    "identity_sites": list(POLICY_IDENTITY_SITES)},
                   indent=2, sort_keys=True) + "\n")
    return precommit


def write_policy_artifacts(directory: Path) -> dict:
    """Write the policy spec + filter byte image as immutable, hashed files.

    These are written BEFORE any leg is launched and chmod 0444, so the policy
    that ran is recoverable from disk and cannot be edited afterwards.  The
    filter image is ALSO emitted as a C header of the identical byte image, so
    the compiled leg and the Python spec cannot drift apart without the hash
    check below failing.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    identity = denial_policy_identity()
    spec_hash, spec_bytes = policy_spec_sha256()
    filter_hash, filter_image = filter_sha256()

    # The artifacts are chmod 0444 so they cannot be edited after the run, which
    # means a plain write_text() on a SECOND emit fails with EACCES and leaves
    # the generator unable to regenerate its own output -- it could produce the
    # policy once and never again.  Unlink first (this needs write permission on
    # the DIRECTORY, not the file) so regeneration is always possible while the
    # immutable-after-write property is preserved.
    def _replace(path: Path, data: bytes) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        path.write_bytes(data)
        path.chmod(0o444)

    spec_path = directory / "d3-denial-policy.json"
    _replace(spec_path, spec_bytes)

    filter_path = directory / "d3-denial-filter.bin"
    _replace(filter_path, filter_image)

    program = build_filter()
    header = directory / "d3_denial_filter.h"
    lines = [
        "/* GENERATED by a12d3_d3_seccomp_policy.py -- DO NOT EDIT.",
        " * The BPF byte image below is asserted to equal filter_sha256",
        " * %s" % filter_hash,
        " * and is emitted so the compiled leg installs exactly this policy. */",
        "#ifndef D3_DENIAL_FILTER_H",
        "#define D3_DENIAL_FILTER_H",
        "#define D3_DENIAL_POLICY_SHA256 \"%s\"" % spec_hash,
        "#define D3_DENIAL_FILTER_SHA256 \"%s\"" % filter_hash,
        "#define D3_DENIAL_INSTRUCTION_COUNT %d" % len(program),
        "#define D3_DENIAL_ERRNO %d" % DENIED_ERRNO,
        "static const struct sock_filter d3_denial_filter_program[] = {",
    ]
    for code, jt, jf, k in program:
        lines.append("    { 0x%04x, %d, %d, 0x%08xu }," % (code, jt, jf, k))
    lines.append("};")
    lines.append("")
    lines.append("static const unsigned short d3_denial_filter_length = %d;"
                 % len(program))
    lines.append("#endif")
    header_path = directory / "d3_denial_filter.h"
    _replace(header_path, ("\n".join(lines) + "\n").encode("utf-8"))

    identity["policy_bytes_path"] = str(spec_path)
    identity["filter_bytes_path"] = str(filter_path)
    identity["filter_header_path"] = str(header_path)
    identity["policy_bytes_sha256_on_disk"] = hashlib.sha256(
        spec_path.read_bytes()).hexdigest()
    identity["filter_bytes_sha256_on_disk"] = hashlib.sha256(
        filter_path.read_bytes()).hexdigest()
    identity["spec_bytes_match"] = (
        identity["policy_bytes_sha256_on_disk"] == spec_hash)
    identity["filter_bytes_match"] = (
        identity["filter_bytes_sha256_on_disk"] == filter_hash)
    return identity


# ---------------------------------------------------------------------------
# Independent re-derivation (used by the checker, NOT by the harness)
# ---------------------------------------------------------------------------

def rebuild_and_compare(policy_bytes_path: Path,
                        filter_bytes_path: Path) -> dict:
    """Rebuild spec+filter from THIS FILE and compare to the on-disk artifacts.

    The checker calls this so "the precommitted policy matches the declared
    policy" is proved by recomputation from source, not by trusting the
    precommit's own numbers.
    """
    expected_spec = canonical_bytes(policy_spec())
    expected_filter = encode_filter(build_filter())
    spec_on_disk = Path(policy_bytes_path).read_bytes() if \
        Path(policy_bytes_path).exists() else None
    filter_on_disk = Path(filter_bytes_path).read_bytes() if \
        Path(filter_bytes_path).exists() else None
    return {
        "policy_spec_rebuilt_matches_disk": spec_on_disk == expected_spec,
        "filter_image_rebuilt_matches_disk": filter_on_disk == expected_filter,
        "rebuilt_policy_sha256": hashlib.sha256(expected_spec).hexdigest(),
        "rebuilt_filter_sha256": hashlib.sha256(expected_filter).hexdigest(),
        "disk_policy_sha256": (hashlib.sha256(spec_on_disk).hexdigest()
                               if spec_on_disk is not None else None),
        "disk_filter_sha256": (hashlib.sha256(filter_on_disk).hexdigest()
                               if filter_on_disk is not None else None),
        "rebuilt_filter_instructions": len(build_filter()),
        "kill_actions_in_filter": sum(
            1 for code, _jt, _jf, k in build_filter()
            if code == (BPF_RET | BPF_K)
            and k in (SECCOMP_RET_KILL_PROCESS, SECCOMP_RET_KILL_THREAD)),
        "deny_sites_in_filter": sum(
            1 for code, _jt, _jf, k in build_filter()
            if code == (BPF_RET | BPF_K)
            and (k & 0xFFFF0000) == SECCOMP_RET_ERRNO),
    }


# ---------------------------------------------------------------------------
# Raw-strace denial classification (no harness summary lines)
# ---------------------------------------------------------------------------

# strace renders a seccomp denial either as the plain syscall line
#   socket(AF_UNIX, SOCK_STREAM, 0) = -1 EACCES (Permission denied)
# or, with -f and the `seccomp` decoder, as
#   socket(AF_UNIX, SOCK_STREAM, 0) = -1 EACCES (Permission denied)
#   --- SIGSYS ... ---            (only for KILL/TRAP, which this policy never emits)
# Both are matched from the RAW line; the parser never consults a JSON summary.

DENIAL_PATTERN = None  # set below; imported lazily to keep this module stdlib-only


def _denial_regex():
    global DENIAL_PATTERN
    if DENIAL_PATTERN is None:
        import re
        names = "|".join(denial_syscall_names())
        # strace is invoked with -ttt, so every line begins with a wall-clock
        # timestamp, and with -f a pid column may follow.  An anchored
        # "^syscall(" therefore matches NOTHING and silently yields zero
        # denials -- a false negative that would make a genuinely filtered leg
        # look like an unfiltered one.  The optional prefix below is required
        # for the pattern to ever fire on real strace output.
        DENIAL_PATTERN = re.compile(
            r"^(?:(?P<ts>\d+\.\d+)\s+)?"
            r"(?:\[pid\s+(?P<pid>\d+)\]\s+)?"
            r"(?P<nr>%s)\((?P<args>.*)\)\s+=\s+-1\s+(?P<errno>EACCES|EPERM)"
            r"\s+\((?P<text>[^)]*)\)\s*$" % names)
    return DENIAL_PATTERN


def normalize_raw_lines(raw_lines: list) -> list[dict]:
    """Accept either structured records or bare strace text lines.

    The checker reads RAW strace files, where the natural unit is a text line,
    while the arm runner already has {"owner","line","path"} records.  Both are
    legitimate inputs, so they are normalized here rather than at every call
    site -- and deliberately WITHOUT stripping anything from the line, because
    the line as written by strace is the evidence.
    """
    normalized: list[dict] = []
    for item in raw_lines:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, (str, bytes)):
            text = item.decode("utf-8", "replace") if isinstance(item, bytes) \
                else item
            normalized.append({"owner": -1, "line": text, "path": None})
        else:
            raise TypeError("raw strace record must be a dict or a text line, "
                            "got %r" % type(item).__name__)
    return normalized


def classify_denial_events(raw_lines: list) -> dict:
    """Classify denial events from RAW strace records.

    Each input record is {"owner": int, "line": str, "path": str}; bare text
    lines are also accepted (see normalize_raw_lines).  A record counts as an
    externally observed denial only if it names a syscall the policy denies AND
    returns -1 with EACCES/EPERM.  A kill-shaped outcome (SIGSYS, "+++ killed by
    SIGSYS") is recorded SEPARATELY as a policy defect, because a kill would
    violate the returned-errno contract.
    """
    raw_lines = normalize_raw_lines(raw_lines)
    pattern = _denial_regex()
    network = set(NETWORK_CREATION_SYSCALLS)
    process = set(PROCESS_CREATION_SYSCALLS)
    execc = set(EXEC_SYSCALLS)
    events: list[dict] = []
    kills: list[dict] = []
    for record in raw_lines:
        line = record.get("line", "")
        stripped = line.strip()
        match = pattern.match(stripped)
        if match:
            name = match.group("nr")
            errno_name = match.group("errno")
            errno_value = {"EACCES": 13, "EPERM": 1}[errno_name]
            if name in network:
                group = "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY"
            elif name in process:
                group = "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY"
            elif name in execc:
                group = "EXEC_DENIED_AFTER_LEG_ENTRY"
            else:
                group = "UNCLASSIFIED"
            events.append({
                "syscall": name,
                "syscall_number": X86_64_SYSCALLS[name],
                "group": group,
                "errno_name": errno_name,
                "errno_value": errno_value,
                "errno_accepted": errno_value in ACCEPTED_DENIAL_ERRNOS,
                "observed_pid": (record.get("owner") if record.get("owner", -1) != -1
                                 else (int(match.group("pid")) if match.group("pid")
                                       else -1)),
                "timestamp": (record.get("timestamp")
                              if record.get("timestamp") is not None
                              else (float(match.group("ts"))
                                    if match.group("ts") else None)),
                "trace_file": record.get("path"),
                "raw_line": line,
                "witness_kind": "externally_observed_denied_syscall",
            })
            continue
        low = stripped.lower()
        if ("killed by sigsys" in low or "sig_sys" in low
                or "killed by signal 31" in low or "+++ killed by" in low):
            kills.append({"observed_pid": record.get("owner"),
                          "trace_file": record.get("path"),
                          "raw_line": line})
    by_group: dict[str, list[dict]] = {}
    for event in events:
        by_group.setdefault(event["group"], []).append(event)
    return {
        "denial_events": events,
        "denial_event_count": len(events),
        "kill_shaped_events": kills,
        "kill_shaped_event_count": len(kills),
        "kill_action_observed": bool(kills),
        "observed_pids": sorted({int(e["observed_pid"]) for e in events
                                 if e.get("observed_pid") is not None}),
        "observed_syscalls": sorted({e["syscall"] for e in events}),
        "observed_groups": sorted(by_group),
        "denial_by_group": {group: [e["syscall"] for e in group_events]
                            for group, group_events in sorted(by_group.items())},
        "all_denials_are_returned_errno": all(
            e["errno_accepted"] for e in events),
        "classification_source": "raw_strace_lines_only",
    }


def policy_self_check(program=None) -> dict:
    """Cheap structural assertions; failure means the policy is malformed.

    `program` defaults to the real build_filter().  It is injectable ONLY so the
    T01 negative control can drive this same structural check with a deliberately
    broken filter: a mutation the structural check cannot see is exactly how
    D3-POLICY-001 stayed invisible while the simulator-only check passed.
    """
    program = build_filter() if program is None else program
    numbers = denial_syscall_numbers()
    # Layout: arch guard (LD, JEQ, RET-deny) + nr load, then one comparison per
    # denied syscall, then the default ALLOW, then the deny site.
    #
    # The arch guard's mismatch branch is itself a RET-deny, so this program has
    # TWO deny sites by design -- the foreign-ABI guard and the syscall deny
    # list.  They are distinguished below rather than counted together, because
    # "how many deny sites" is not the invariant that matters; "which syscalls
    # are denied" is, and that is proven by check_filter_denies_exactly() at
    # build time and by the kernel's own record at run time.
    expected_length = 4 + len(numbers) + 1 + 1
    deny_sites = [i for i, (code, _jt, _jf, k) in enumerate(program)
                  if code == (BPF_RET | BPF_K)
                  and (k & 0xFFFF0000) == SECCOMP_RET_ERRNO]
    # SECCOMP_RET_KILL_THREAD is 0x00000000, which is indistinguishable from an
    # unused operand field when only `k` is inspected.  A kill can only be
    # emitted by a RET instruction, so match on the opcode FIRST and then on the
    # action bits; SECCOMP_RET_ALLOW/KILL_PROCESS have the high bit set and
    # KILL_THREAD is the all-zero action code.
    kills = [i for i, (code, _jt, _jf, k) in enumerate(program)
             if code == (BPF_RET | BPF_K)
             and k in (SECCOMP_RET_KILL_PROCESS, SECCOMP_RET_KILL_THREAD)]
    allow_sites = [i for i, (code, _jt, _jf, k) in enumerate(program)
                   if code == (BPF_RET | BPF_K) and k == SECCOMP_RET_ALLOW]
    missing = [name for name in denial_syscall_names()
               if name not in X86_64_SYSCALLS]
    return {
        "instruction_count": len(program),
        "expected_instruction_count": expected_length,
        "instruction_count_ok": len(program) == expected_length,
        "deny_site_count": len(deny_sites),
        # The LAST deny site is the syscall deny list: the arch guard's deny
        # precedes the comparisons, and the default-ALLOW/comparison block
        # follows it.  The terminal RET is therefore the deny list, and every
        # comparison must jump to it.
        "deny_site_index": deny_sites[-1] if deny_sites else None,
        "arch_guard_deny_index": deny_sites[0] if deny_sites else None,
        "deny_sites_confined_to_guard_and_terminal": (
            deny_sites == [2, len(program) - 1] if deny_sites else False),
        "kill_instructions": len(kills),
        "no_kill_instructions": not kills,
        "allow_site_count": len(allow_sites),
        "denied_syscall_count": len(numbers),
        "denied_syscalls_have_numbers": not missing,
        "missing_from_number_table": missing,
        # The guard is present iff it loads seccomp_data.arch, compares it
        # against the native ABI, and DENIES on mismatch.  An ALLOW on mismatch
        # would be a live escape: seccomp_data.nr would then be interpreted in a
        # foreign number space the deny list never names, so a denylist filter
        # cannot cover it by enumeration.  Denying the foreign ABI outright is
        # the only closed form.
        "arch_guard_present": program[0][3] == struct_seccomp_data_arch
        and program[1][3] == AUDIT_ARCH_X86_64
        and program[2][3] == (SECCOMP_RET_ERRNO | DENIED_ERRNO),
        "arch_guard_denies_mismatch": program[2][3] ==
        (SECCOMP_RET_ERRNO | DENIED_ERRNO),
        "default_action_is_allow": program[-2][3] == SECCOMP_RET_ALLOW,
        "all_comparisons_target_deny_site": all(
            program[4 + offset][0] == (BPF_JMP | BPF_JEQ | BPF_K)
            and program[4 + offset][1] == len(program) - 1 - (4 + offset) - 1
            and program[4 + offset][2] == 0
            for offset in range(len(numbers))),
        "deny_errno": DENIED_ERRNO,
    }


def battery_entry_gate(evidence: dict, identity_sites: dict) -> dict:
    """The single precondition D3-A..D3-E may not start without.

    GPT: "run D3-A..D3-E only after those applicability/self-check controls are
    green."  Any failure here is APPARATUS-MISMATCH -- the battery is not run, and
    the 21-instruction policy is never silently used on an unsuitable host.
    """
    result: dict = {"schema": POLICY_VERSION}
    # 1. X32 applicability (mechanical, includes the UNFILTERED arm)
    result["x32_route_unavailable"] = x32_route_unavailable(evidence)
    # 2. the permanent T01 negative control (good PASS / broken FAIL)
    result["t01_negative_control"] = t01_negative_control()
    # 3. five-site policy identity, fail closed
    result["policy_identity"] = check_policy_identity_sites(identity_sites)
    result["battery_entry"] = "ALLOWED"
    return result


if __name__ == "__main__":
    import sys
    check = policy_self_check()
    identity = denial_policy_identity()
    payload = {"self_check": check,
               "policy_sha256": identity["policy_sha256"],
               "filter_sha256": identity["filter_sha256"],
               "filter_instructions": identity["filter_instructions"],
               "denied_syscalls": identity["policy_spec"][
                   "denied_syscall_names"]}
    ok = all([
        check["instruction_count_ok"],
        check["deny_sites_confined_to_guard_and_terminal"],
        check["no_kill_instructions"], check["denied_syscalls_have_numbers"],
        check["arch_guard_present"], check["arch_guard_denies_mismatch"],
        check["default_action_is_allow"],
        check["all_comparisons_target_deny_site"]])

    if "--gate" in sys.argv:
        # battery-entry gate: consumes the MEASURED x32 control evidence
        evidence_path = Path("/tmp/a12d3_x32_evidence.json")
        if not evidence_path.is_file():
            print(json.dumps({"battery_entry": "REFUSED",
                              "reason": "missing %s -- run /tmp/a12d3_x32_control "
                                        "--raw and --policy first" % evidence_path},
                             indent=2, sort_keys=True))
            raise SystemExit(2)
        evidence = json.loads(evidence_path.read_text())
        sites = {s: identity["filter_sha256"] for s in POLICY_IDENTITY_SITES}
        try:
            gate = battery_entry_gate(evidence, sites)
        except AssertionError as exc:
            print(json.dumps({"battery_entry": "REFUSED",
                              "reason": str(exc)}, indent=2, sort_keys=True))
            raise SystemExit(3)
        payload["battery_entry_gate"] = gate
        payload["battery_entry"] = "ALLOWED"
        print(json.dumps(payload, indent=2, sort_keys=True))
        raise SystemExit(0 if ok else 1)

    print(json.dumps(payload, indent=2, sort_keys=True))
    raise SystemExit(0 if ok else 1)
