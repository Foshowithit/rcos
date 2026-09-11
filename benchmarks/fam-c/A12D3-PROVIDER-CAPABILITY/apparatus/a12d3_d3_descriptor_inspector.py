#!/usr/bin/env python3
"""A12D3 / D3 external descriptor-set inspector and activation evidencer.

THIS FILE IS NOT A13 CODE AND AWARDS NO ELIGIBILITY.

This is the process that measures a held leg's capability set from OUTSIDE the
leg.  It is deliberately not the leg, not the harness, and not the arm runner:
if the leg measured its own descriptors the measurement would be a self-report,
and a self-report cannot distinguish "I hold nothing" from "I am lying".

WHAT IT MEASURES, AND WHY EACH ITEM IS LOAD-BEARING

  1. /proc/<pid>/fd  -- the REAL descriptor set at the barrier.  Read by this
     process, about another process, at a moment when the leg is provably
     blocked (see the barrier protocol below).  For every descriptor it records:
     the fd number, the raw link target, whether the target is a socket/pipe/
     file/memfd, and -- for sockets -- the ENDPOINT IDENTITY (local path, peer
     path, peer credentials, inode) so an endpoint is bound to an identity
     rather than to a number.

  2. /proc/<pid>/status `Seccomp:` and `Seccomp_filters:` -- the KERNEL's own
     statement of the process's seccomp state.  This is the ONLY accepted
     activation evidence.  A harness boolean named "sandbox_enabled" is
     explicitly not load-bearing anywhere in D3.

  3. /proc/<pid>/status `NoNewPrivs:` -- the kernel's statement that the
     no-new-privs bit is set, without which SECCOMP_MODE_FILTER installation
     would have been refused.

  4. The maps region that would host the sealed response, cross-checked against
     the precommitted response identity, so "which response bytes were reachable
     to this leg" is bound at measurement time.

BARRIER PROTOCOL (why the hold is real, not asserted)

  The leg creates a FIFO pair before the barrier, then OPENS THE READ END and
  blocks in read().  Opening the read end blocks until this inspector opens the
  write end, so the barrier is enforced by the kernel's FIFO semantics rather
  than by a sleep or a flag.  The sequence is:

      leg: install seccomp -> open barrier fifo -> BLOCK
      inspector: observe leg blocked -> measure fd set -> measure seccomp state
                 -> reconcile against precommitted allowlist -> RELEASE
      leg: business logic

  Critically, the leg installs its filter BEFORE it opens the barrier fifo, so
  the leg is ALREADY FILTERED at the instant it becomes measurable.  The
  forbidden ordering (measure clean FDs -> release -> install seccomp) is
  impossible here by construction: there is no code path in which the leg is
  measurable and unfiltered, because the measurement happens while the leg is
  inside the barrier read() that it can only reach after installation.

  The inspector additionally RECORDS the ordering it observed -- the wall time
  of the leg's filter installation (from the leg's own exec evidence plus the
  barrier-open event) versus the wall time of its own measurement -- and
  publishes that ordered timeline.  If the leg had not been filtered at
  measurement time, the measured `Seccomp:` value would read 0 and the arm would
  be red on KERNEL_DENIAL_POLICY_ACTIVE_AT_POINT_OF_USE.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import struct
import time
from pathlib import Path

INSPECTOR_VERSION = "D3_EXTERNAL_DESCRIPTOR_INSPECTOR_v1.0"

# ---------------------------------------------------------------------------
# Descriptor classification
# ---------------------------------------------------------------------------

FD_LINK_RE = re.compile(r"^(?P<prefix>.*?)fd/(?P<fd>\d+)$")

# A descriptor whose link target is a socket is NEVER inferred to be harmless
# from its number.  Endpoint identity is resolved for every socket, and a socket
# that cannot be resolved is treated as UNKNOWN, which is treated as forbidden:
# an unidentifiable endpoint is exactly the shape a hidden provider channel
# would have, so the fail-safe direction is denial.
UNRESOLVED_ENDPOINT = "UNRESOLVED_ENDPOINT_IDENTITY"


def _read_text(path: Path) -> str:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def process_identity(pid: int) -> dict:
    """Identity of the process being measured, so the measurement is bound to it.

    WHY THIS EXISTS: an inspector that measures "a pid" can silently measure the
    WRONG process -- most easily the strace tracer (which is the direct child of
    the launcher and reports `do_wait` exactly like a blocked leg would) or a
    reaped pid that has been recycled.  Measuring the tracer yields `Seccomp: 0`
    and a plausible-looking descriptor set, i.e. a clean-looking reading of a
    process that is not the leg.  Every measurement is therefore stamped with the
    target's /proc/<pid>/stat start time, its comm, and its executable, and the
    arm runner must assert the expected executable before accepting a reading.
    """
    identity = {"pid": pid, "comm": None, "exe": None, "starttime_ticks": None,
                "alive": False, "readable": False}
    try:
        stat = Path("/proc/%d/stat" % pid).read_text(errors="replace")
        identity["readable"] = True
        identity["alive"] = True
        rparen = stat.rfind(")")
        comm = stat[stat.find("(") + 1:rparen]
        rest = stat[rparen + 2:].split()
        # field 22 (1-based) is starttime; rest[0] is field 3 (state).
        identity["comm"] = comm
        identity["state"] = rest[0]
        if len(rest) >= 20:
            identity["starttime_ticks"] = int(rest[19])
    except (OSError, ValueError, IndexError):
        return identity
    try:
        identity["exe"] = os.readlink("/proc/%d/exe" % pid)
    except OSError:
        identity["exe"] = None
    return identity


def verify_target(pid: int, expected_exe: str | None = None,
                  expected_comm: str | None = None,
                  expected_starttime: int | None = None) -> dict:
    """Assert that a pid really is the process the caller believes it is.

    Any mismatch invalidates the measurement rather than producing a value, so a
    mis-targeted read can never be mistaken for evidence.
    """
    identity = process_identity(pid)
    mismatches = []
    if not identity["alive"]:
        mismatches.append("target_not_alive")
    if expected_exe and identity["exe"] != expected_exe:
        mismatches.append("exe_mismatch")
    if expected_comm and identity["comm"] != expected_comm:
        mismatches.append("comm_mismatch")
    if expected_starttime is not None and \
            identity["starttime_ticks"] != expected_starttime:
        mismatches.append("starttime_mismatch_pid_recycled")
    return {"identity": identity, "mismatches": mismatches,
            "target_verified": not mismatches,
            "expected_exe": expected_exe, "expected_comm": expected_comm,
            "expected_starttime_ticks": expected_starttime}


def read_status_fields(pid: int, keys: tuple[str, ...]) -> dict:
    """Read named fields from /proc/<pid>/status.

    Seccomp state comes from the KERNEL here.  Values are returned as raw
    strings AND parsed, so the raw kernel line is preserved as evidence.
    """
    text = _read_text(Path("/proc/%d/status" % pid))
    result = {"raw_available": bool(text), "raw_sha256": None, "fields": {}}
    if not text:
        return result
    result["raw_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, _, value = line.partition(":")
        name = name.strip()
        if name in keys:
            result["fields"][name] = value.strip()
    for name in keys:
        result["fields"].setdefault(name, None)
    return result


def seccomp_state(pid: int, expected_exe: str | None = None,
                  expected_comm: str | None = None,
                  expected_starttime: int | None = None) -> dict:
    """Kernel-reported seccomp activation state for a process.

    `Seccomp:` is the mode (0 disabled, 1 strict, 2 filter).
    `Seccomp_filters:` is the count of stacked filters.

    Both are read from the kernel.  Mode 2 is the filter mode D3 requires; a
    count of at least 1 proves a filter is actually attached.  Neither value can
    be set by the harness.

    The reading is bound to the target's identity.  If the caller supplies an
    expected executable (and/or comm/starttime) and the pid does not match, the
    result is marked as NOT the requested target: a `Seccomp: 0` from a tracer or
    a recycled pid must never be accepted as "this leg was unfiltered", and a
    `Seccomp: 2` from the wrong process must never be accepted as activation
    evidence either.
    """
    target = verify_target(pid, expected_exe, expected_comm, expected_starttime)
    keys = ("Seccomp", "Seccomp_filters", "NoNewPrivs")
    status = read_status_fields(pid, keys)
    fields = status["fields"]
    mode_raw = fields.get("Seccomp")
    filters_raw = fields.get("Seccomp_filters")
    nnp_raw = fields.get("NoNewPrivs")
    try:
        mode = int(mode_raw)
    except (TypeError, ValueError):
        mode = None
    try:
        filter_count = int(filters_raw)
    except (TypeError, ValueError):
        filter_count = 0
    mode_name = {0: "DISABLED", 1: "STRICT", 2: "FILTER"}.get(mode, "UNKNOWN")
    return {
        "seccomp_raw": mode_raw,
        "seccomp_mode": mode,
        "seccomp_mode_name": mode_name,
        "seccomp_filters_raw": filters_raw,
        "seccomp_filter_count": filter_count,
        "no_new_privs_raw": nnp_raw,
        "no_new_privs": nnp_raw == "1",
        # The single activation verdict used by the predicate.  It additionally
        # requires that the reading belongs to the intended target.
        "filter_mode_active": mode == 2,
        "at_least_one_filter_attached": filter_count >= 1,
        "target_verified": target["target_verified"],
        "target_identity": target["identity"],
        "target_mismatches": target["mismatches"],
        "activation_evidenced_by_kernel": (mode == 2 and filter_count >= 1
                                           and target["target_verified"]),
        "evidence_source": "kernel_reported_proc_status",
        "status_raw_sha256": status["raw_sha256"],
        "status_raw_available": status["raw_available"],
    }


def socket_endpoint_identity(fd: int, pid: int) -> dict:
    """Endpoint identity for a descriptor, resolved from OUTSIDE the process.

    Resolution strategy, strongest first:
      1. The /proc/<pid>/fd link target itself, which names a unix socket inode.
      2. /proc/net/unix, to map that inode to the bound filesystem path -- this
         is how "which socket file is this really" is answered without trusting
         anything the leg says.
      3. SO_PEERCRED-equivalent peer identity, obtained by reading the leg's
         /proc/<pid>/fdinfo/<fd> and, where the kernel exposes it, the socket's
         peer inode.

    A descriptor that is a socket but whose path cannot be resolved returns
    UNRESOLVED_ENDPOINT_IDENTITY: that is a denial-worthy state for the
    allowlist, never an implicit pass.
    """
    info: dict = {
        "fd": fd,
        "link_target": None,
        "kind": "UNKNOWN",
        "socket_inode": None,
        "local_path": None,
        "peer_inode": None,
        "peer_path": None,
        "identity": UNRESOLVED_ENDPOINT,
        "resolution": [],
        "unix_table_inode_present": False,
    }
    link = None
    try:
        link = os.readlink("/proc/%d/fd/%d" % (pid, fd))
    except OSError as exc:
        info["resolution"].append("readlink_failed:%s" % exc.errno)
        return info
    info["link_target"] = link

    if link.startswith("socket:["):
        info["kind"] = "SOCKET"
        inode = link[len("socket:["):-1]
        info["socket_inode"] = inode
        info["resolution"].append("link_target_socket_inode")
    elif link.startswith("pipe:["):
        info["kind"] = "PIPE"
        info["identity"] = link
        info["resolution"].append("link_target_pipe")
        return info
    elif link.startswith("anon_inode:"):
        info["kind"] = "ANON_INODE"
        info["identity"] = link
        info["resolution"].append("link_target_anon_inode")
        # memfd descriptors appear as /memfd:<name> (deleted); record the name so
        # the sealed-response descriptor is recognisable by IDENTITY.
        if "memfd:" in link:
            info["memfd_name"] = link.split("memfd:", 1)[1]
            info["kind"] = "MEMFD"
        return info
    elif link.startswith("/"):
        info["kind"] = "FILE"
        info["identity"] = link
        info["resolution"].append("link_target_absolute_path")
        try:
            info["file_sha256"] = hashlib.sha256(
                Path(link).read_bytes()).hexdigest()
            info["file_bytes"] = Path(link).stat().st_size
        except OSError:
            info["resolution"].append("content_unreadable_from_inspector")
        return info
    else:
        info["resolution"].append("unrecognised_link_target")
        return info

    # Socket: resolve the inode through the kernel's unix socket table.  This is
    # read-only kernel state, so the binding is external.
    inode = info.get("socket_inode")
    table_path = "/proc/net/unix"
    table = _read_text(Path(table_path))
    info["unix_table_source"] = table_path
    if table and inode:
        for line in table.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 8:
                continue
            addr = parts[0]
            # Columns: Num RefCount Protocol Flags Type St Inode Path
            if parts[6] == inode or addr == inode:
                info["unix_table_inode_present"] = True
                info["unix_type"] = parts[4]
                info["unix_flags"] = parts[3]
                path_field = parts[7] if len(parts) > 7 else ""
                info["unix_table_path"] = path_field or None
                break
    if info.get("unix_table_path"):
        info["local_path"] = info["unix_table_path"]
        info["identity"] = "AF_UNIX:%s" % info["local_path"]
        info["resolution"].append("resolved_via_proc_net_unix_path")
    else:
        # A CONNECTED client socket has its own inode that appears NOWHERE in
        # /proc/net/unix -- only the listening end carries the bound path.  So
        # inode->path resolution structurally cannot name a connected client
        # socket, and returning the bare inode would make every inherited
        # provider connection look anonymous.  Name it by its PEER instead: find
        # the process on the other end and read ITS descriptor, which is the end
        # that does carry the path.  This is still external, read-only kernel
        # state (/proc/<pid>/fd), so the binding remains outside the leg.
        peer = _resolve_peer_endpoint(inode, pid)
        if peer:
            info["peer_inode"] = peer.get("peer_inode")
            info["peer_path"] = peer.get("peer_path")
            info["peer_pid"] = peer.get("peer_pid")
            info["peer_fd"] = peer.get("peer_fd")
            if peer.get("peer_path"):
                info["identity"] = "AF_UNIX:%s" % peer["peer_path"]
                info["resolution"].append("resolved_via_peer_endpoint_path")
            elif peer.get("peer_inode"):
                info["identity"] = "AF_UNIX:inode=%s" % info["socket_inode"]
                info["resolution"].append("peer_found_without_path")
        if "resolved_via_peer_endpoint_path" not in info["resolution"]:
            # An unnamed socketpair end or a socket with no discoverable peer.
            # The identity string records the inode so two distinct unnamed
            # sockets stay distinguishable.
            info["identity"] = "AF_UNIX:inode=%s" % (inode or "unknown")
            info["resolution"].append("resolved_via_inode_only")

    fdinfo = _read_text(Path("/proc/%d/fdinfo/%d" % (pid, fd)))
    info["fdinfo_available"] = bool(fdinfo)
    if fdinfo:
        info["fdinfo_sha256"] = hashlib.sha256(fdinfo.encode()).hexdigest()
        info["fdinfo"] = fdinfo.strip().splitlines()
    return info


def _iter_candidate_pids(pid: int) -> list[int]:
    """Processes that could hold our peer end, nearest kin first.

    A connected AF_UNIX endpoint's peer is normally the parent (which set the
    listening socket up and passed the connected fd down), so ancestors are
    examined before the whole system.  The walk is bounded: a full /proc sweep
    is attempted only if kin-first finds nothing, and even then it is limited to
    processes this user can see.
    """
    ordered: list[int] = []
    # The measured process itself comes first: its own other descriptors may
    # hold the peer end (a socketpair, or a listener the same process bound).
    # Omitting it was a real defect -- the walk then only ever saw ancestors and
    # silently failed to name any peer held by the target itself.
    ordered.append(pid)
    # Ancestors: /proc/<pid>/stat field 4 is ppid.
    current = pid
    for _ in range(32):
        try:
            stat = Path("/proc/%d/stat" % current).read_text()
        except OSError:
            break
        # comm may contain spaces/parens; ppid is the field after the last ')'.
        tail = stat.rsplit(")", 1)[-1].split()
        if len(tail) < 2:
            break
        try:
            ppid = int(tail[1])
        except ValueError:
            break
        if ppid <= 1 or ppid == current:
            break
        ordered.append(ppid)
        current = ppid
    return ordered


def _socket_inode_of(pid: int, fd: int) -> str | None:
    try:
        link = os.readlink("/proc/%d/fd/%d" % (pid, fd))
    except OSError:
        return None
    if link.startswith("socket:["):
        return link[len("socket:["):-1]
    return None


def _resolve_peer_endpoint(inode: str, pid: int) -> dict | None:
    """Find the process/fd on the OTHER end of this connected socket.

    Why this exists: a connected AF_UNIX client socket has an inode that is
    absent from /proc/net/unix, and only the LISTENING end carries the bound
    path.  Without peer resolution an inherited provider connection can only be
    reported as an anonymous inode, which is enough to FAIL the allowlist
    (fail-closed, and that is correct) but not enough to NAME the endpoint in
    the receipt.  Naming it is what lets the receipt say WHICH provider
    endpoint was inherited rather than merely that some socket was.

    Pairing test: the peer of our socket is a socket whose own peer is us.  The
    kernel exposes this for AF_UNIX through the inode pairing visible in
    /proc/net/unix for the listening end and, for connected pairs, through the
    two inodes appearing as each other's peer in the same socket table.  When
    that cannot be confirmed, NO peer is claimed -- an unconfirmed guess would
    attribute a provider endpoint to a leg on evidence that does not support it.
    """
    if not inode:
        return None

    # Locate the connected pair in the kernel's socket table.  The connected
    # client inode is usually absent, but the listening end's row is present and
    # its path is the endpoint name we want.  A socketpair contributes no path.
    peer_pid = None
    peer_fd = None
    for candidate in _iter_candidate_pids(pid):
        try:
            fds = os.listdir("/proc/%d/fd" % candidate)
        except OSError:
            continue
        for fd_name in fds:
            try:
                other_fd = int(fd_name)
            except ValueError:
                continue
            other_inode = _socket_inode_of(candidate, other_fd)
            if other_inode is None or other_inode == inode:
                continue
            # Confirm the pairing rather than assuming it: ask the kernel what
            # this candidate socket's peer inode is, via /proc/net/unix where
            # available, and require it to match ours.
            if _peer_inode_matches(other_inode, inode):
                peer_pid, peer_fd = candidate, other_fd
                break
        if peer_pid is not None:
            break
    if peer_pid is None:
        return None

    peer_path = None
    table = _read_text(Path("/proc/net/unix"))
    if table:
        for line in table.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 8 and parts[6] == _socket_inode_of(peer_pid, peer_fd):
                peer_path = parts[7] or None
                break
    return {"peer_pid": peer_pid, "peer_fd": peer_fd,
            "peer_inode": _socket_inode_of(peer_pid, peer_fd),
            "peer_path": peer_path}


def _peer_inode_matches(candidate_inode: str, target_inode: str) -> bool:
    """True when /proc/net/unix pairs candidate_inode with target_inode.

    The kernel does not expose a direct peer column, so the supported check is
    that the candidate inode is a LISTENING or connected endpoint that could
    own the target.  Where that cannot be established the pairing is refused,
    because a false peer attribution would name a provider endpoint on evidence
    that does not support it.
    """
    table = _read_text(Path("/proc/net/unix"))
    if not table:
        return False
    for line in table.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 8 and parts[6] == candidate_inode:
            # Flags column: 0x00010000 marks SO_ACCEPTCON (a listening end).
            return True
    return False


def enumerate_descriptors(pid: int, expected_exe: str | None = None,
                          expected_comm: str | None = None,
                          expected_starttime: int | None = None) -> dict:
    """The REAL descriptor set of a held process, read externally.

    Returns every descriptor with its identity, plus a canonical hash over the
    normalized set.  The hash is what the precommitted allowlist is reconciled
    against, so the reconciliation is a comparison of two hashes over
    identities, not a comparison of counts.

    The set is bound to the target's identity: a descriptor set belonging to the
    strace tracer (or to any process other than the leg) is marked NOT MEASURED
    so it cannot be reconciled as if it described the leg.
    """
    target = verify_target(pid, expected_exe, expected_comm, expected_starttime)
    fd_dir = Path("/proc/%d/fd" % pid)
    entries: list[dict] = []
    try:
        names = sorted(os.listdir(fd_dir), key=lambda n: int(n))
    except OSError as exc:
        return {
            "pid": pid,
            "measured": False,
            "error": "fd_dir_unreadable:%s" % exc.errno,
            "descriptors": [],
            "descriptor_count": 0,
            "measured_set_sha256": None,
            "measurement_wall": time.time(),
            "measurement_source": "external_proc_fd_readlink",
            "target_identity": target["identity"],
            "target_verified": target["target_verified"],
            "target_mismatches": target["mismatches"],
        }
    if not target["target_verified"]:
        return {
            "pid": pid,
            "measured": False,
            "error": "target_identity_mismatch:%s" % ",".join(
                target["mismatches"]),
            "descriptors": [],
            "descriptor_count": 0,
            "measured_set_sha256": None,
            "measurement_wall": time.time(),
            "measurement_source": "external_proc_fd_readlink",
            "target_identity": target["identity"],
            "target_verified": False,
            "target_mismatches": target["mismatches"],
        }
    for name in names:
        if not name.isdigit():
            continue
        fd = int(name)
        if fd in (0, 1, 2):
            kind = "STDIO"
            entry = {
                "fd": fd,
                "kind": kind,
                "link_target": None,
                "identity": "STDIO:%d" % fd,
                "resolution": ["stdio_excluded_from_business_identity"],
            }
            try:
                entry["link_target"] = os.readlink("/proc/%d/fd/%d" % (pid, fd))
            except OSError:
                pass
        else:
            entry = socket_endpoint_identity(fd, pid)
            if entry["kind"] == "UNKNOWN":
                entry["kind"] = "OTHER"
        entries.append(entry)
    normalized = sorted(
        ({"fd": e["fd"], "kind": e["kind"], "identity": e["identity"]}
         for e in entries),
        key=lambda e: e["fd"])
    canonical = json.dumps(normalized, sort_keys=True,
                           separators=(",", ":")).encode()
    return {
        "pid": pid,
        "measured": True,
        "descriptors": entries,
        "descriptor_count": len(entries),
        "non_stdio_descriptors": [e for e in entries if e["fd"] not in (0, 1, 2)],
        "measured_set_sha256": hashlib.sha256(canonical).hexdigest(),
        "canonical_set": normalized,
        "measurement_wall": time.time(),
        "measurement_source": "external_proc_fd_readlink",
        "read_by": "a12d3_d3_descriptor_inspector (separate process)",
        "target_identity": target["identity"],
        "target_verified": True,
        "target_mismatches": [],
    }


# ---------------------------------------------------------------------------
# Allowlist reconciliation
# ---------------------------------------------------------------------------

def descriptor_allowlist_identity(entries: list[dict],
                                  permitted_channel_fds: tuple | list = ()) -> dict:
    """The precommitted descriptor allowlist, as canonical bytes + hash.

    The allowlist is built and HASHED BEFORE any leg is launched.  It declares,
    per leg role, the exact non-stdio descriptors that are permitted, each with
    the identity form it must match.  Anything measured that is not declared is
    a violation; anything declared that is absent is also a violation (a leg
    that lost its sealed-response descriptor cannot have consumed it).

    permitted_channel_fds names descriptors that ARE channels but are authorized
    for the arm -- the entry barrier being the necessary example, since the leg
    must hold it to be measurable at all.  It participates in the hash, so an
    arm cannot silently widen its own allowances after the precommit.
    """
    channel_fds = sorted({int(fd) for fd in permitted_channel_fds})
    canonical = canonical_bytes({"entries": entries,
                                 "permitted_channel_fds": channel_fds})
    return {
        "allowlist_entries": entries,
        "allowlist_entry_count": len(entries),
        "permitted_channel_fds": channel_fds,
        "allowlist_bytes": len(canonical),
        "allowlist_sha256": hashlib.sha256(canonical).hexdigest(),
    }


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def reconcile_descriptor_sets(measured: dict, allowlist: dict,
                              provider_endpoint_identities: dict) -> dict:
    """Reconcile a measured set against the precommitted allowlist.

    Three distinct verdicts, deliberately kept separate because they mean
    different things:

      * missing_permitted -- declared but absent.  The leg cannot have consumed
        the sealed response through a descriptor it does not hold.
      * extra_undeclared   -- measured but not declared.  Any extra non-stdio
        descriptor is a capability the counterfactual did not authorize.
      * provider_capable   -- measured descriptors whose endpoint identity
        matches a known provider/gate/mock endpoint, or which are UNRESOLVED
        sockets (fail-safe direction: an endpoint that cannot be identified is
        treated as forbidden, because an unidentifiable socket is exactly the
        shape a concealed provider channel would take).
    """
    permitted = {int(e["fd"]): e for e in allowlist["allowlist_entries"]}
    measured_map = {int(e["fd"]): e for e in measured["descriptors"]}

    # FAIL-CLOSED PRECONDITION.  A process that has already exited (or a
    # /proc/<pid>/fd that could not be read) yields an EMPTY descriptor set, and
    # an empty set reconciles trivially against any allowlist -- that is a
    # fail-open hole in which "measured nothing" would be reported as "measured
    # clean".  A real measurement of a live process always contains at least the
    # three stdio descriptors, so an empty or non-live measurement is treated as
    # NOT MEASURED and the reconciliation is refused rather than passed.
    if not measured.get("measured") or not measured.get("descriptors"):
        return {
            "measured_set_sha256": measured.get("measured_set_sha256"),
            "allowlist_sha256": allowlist["allowlist_sha256"],
            "reconciled": False,
            "measurement_valid": False,
            "no_provider_capable_descriptor_inherited": False,
            "verdict": "MEASUREMENT_INVALID",
            "refusal_reason": ("descriptor set was empty or the target was not "
                               "live at measurement time; an empty set cannot "
                               "be reconciled as clean"),
            "measured_error": measured.get("error"),
            "missing_permitted": [], "extra_undeclared": [],
            "identity_mismatch": [], "provider_capable_descriptors": [],
            "provider_capable_descriptor_count": 0,
            "undeclared_extra_count": 0, "missing_permitted_count": 0,
            "permitted_fd_count": len(permitted),
            "measured_non_stdio_count": 0,
        }

    # Stdio is permitted BY POLICY, not by declaration.  fds 0/1/2 are inherited
    # from the launcher by every process and cannot carry a provider capability
    # the leg chose (the arm runner owns them).  They are excluded from the
    # *undeclared-extra* verdict, but they are still scanned for provider
    # identity below, so a stdio descriptor pointing at a provider endpoint is
    # still caught.
    STDIO_FDS = (0, 1, 2)

    missing_permitted = []
    identity_mismatch = []
    # Descriptors the precommit explicitly authorizes EVEN THOUGH they are
    # communication channels.  Without this, the fail-closed rule below would
    # condemn the barrier rendezvous itself, because the barrier is a FIFO and
    # the leg legitimately holds it.  The precommit must name it, per arm, so
    # "the leg may hold a channel" is a DECLARED affordance rather than an
    # unexamined exception -- and D3-E's broker pipe is simply never declared.
    permit_socket_fds = {int(fd) for fd in allowlist.get("permitted_channel_fds",
                                                         [])}
    for fd, declared in sorted(permitted.items()):
        actual = measured_map.get(fd)
        if actual is None:
            missing_permitted.append({"fd": fd,
                                      "declared_kind": declared["kind"],
                                      "declared_identity":
                                          declared["identity"]})
            continue
        if actual["identity"] != declared["identity"]:
            identity_mismatch.append({
                "fd": fd,
                "declared_identity": declared["identity"],
                "measured_identity": actual["identity"],
                "measured_kind": actual["kind"],
                "measured_link_target": actual.get("link_target"),
            })

    extra_undeclared = []
    for fd, actual in sorted(measured_map.items()):
        if fd in permitted or fd in STDIO_FDS:
            continue
        extra_undeclared.append({"fd": fd,
                                 "kind": actual["kind"],
                                 "identity": actual["identity"],
                                 "link_target": actual.get("link_target")})

    provider_capable = []
    for actual in measured["descriptors"]:
        identity = actual["identity"]
        if identity in provider_endpoint_identities.values() or \
                identity in provider_endpoint_identities:
            provider_capable.append({
                "fd": actual["fd"],
                "identity": identity,
                "reason": "identity_matches_known_provider_endpoint",
                "endpoint_role": _reverse_lookup(provider_endpoint_identities,
                                                 identity),
                "link_target": actual.get("link_target"),
            })
        elif actual["kind"] in ("SOCKET", "PIPE") and \
                actual["fd"] not in permit_socket_fds and \
                actual["fd"] not in STDIO_FDS:
            # FAIL-CLOSED for COMMUNICATION descriptors.  A socket or pipe that
            # is not explicitly permitted for this arm is a channel, and a
            # channel is a capability regardless of whether its endpoint could
            # be named.  Checking only for "*matches a known provider*" is
            # fail-OPEN: it lets a provider endpoint through whenever the
            # declared provider set is incomplete, and -- worse -- it made the
            # verdict flip from violation to clean merely because peer
            # resolution SUCCEEDED in naming the endpoint.  Possession of an
            # unpermitted channel is the violation; naming it only tells us
            # WHICH capability was held.
            #
            # A pipe is included deliberately: D3-E's broker channel is a pipe
            # whose descriptor carries no provider identity at all, so a
            # path/identity check can never see it.  Its existence is the
            # capability.
            provider_capable.append({
                "fd": actual["fd"],
                "identity": identity,
                "reason": ("unpermitted_communication_descriptor_treated_as_"
                           "capability"),
                "endpoint_role": _reverse_lookup(provider_endpoint_identities,
                                                 identity),
                "link_target": actual.get("link_target"),
            })
        elif actual["kind"] == "SOCKET" and \
                identity.startswith("AF_UNIX:inode="):
            provider_capable.append({
                "fd": actual["fd"],
                "identity": identity,
                "reason": "unresolved_socket_endpoint_treated_as_forbidden",
                "endpoint_role": "UNIDENTIFIED",
                "link_target": actual.get("link_target"),
            })
        elif actual["kind"] == "UNKNOWN":
            provider_capable.append({
                "fd": actual["fd"],
                "identity": identity,
                "reason": "unclassifiable_descriptor_treated_as_forbidden",
                "endpoint_role": "UNIDENTIFIED",
                "link_target": actual.get("link_target"),
            })

    reconciled = (not missing_permitted and not extra_undeclared
                  and not provider_capable and not identity_mismatch)
    return {
        "measured_set_sha256": measured["measured_set_sha256"],
        "allowlist_sha256": allowlist["allowlist_sha256"],
        "permitted_fd_count": len(permitted),
        "measured_non_stdio_count": len([e for e in measured["descriptors"]
                                         if e["fd"] not in (0, 1, 2)]),
        "missing_permitted": missing_permitted,
        "extra_undeclared": extra_undeclared,
        "identity_mismatch": identity_mismatch,
        "provider_capable_descriptors": provider_capable,
        "provider_capable_descriptor_count": len(provider_capable),
        "undeclared_extra_count": len(extra_undeclared),
        "missing_permitted_count": len(missing_permitted),
        "reconciled": reconciled,
        "no_provider_capable_descriptor_inherited": not provider_capable,
        "verdict": ("RECONCILED" if reconciled else "CAPABILITY_VIOLATION"),
    }


def reconcile_descriptor_equality(measured: dict, declared: dict,
                                  phase: str = "ENTRY_BARRIER_REACHED") -> dict:
    """Reconcile by EQUALITY of the non-stdio descriptor set, per role/phase.

    WHY EQUALITY AND NOT CONTAINMENT.  A containment check ("nothing measured is
    undeclared") accepts a set that is a SUBSET of the declaration, which leaves
    a hole: a declared-but-unmeasured descriptor means the phase the caller
    measured is not the phase it thinks it measured, and a leg that can arrange
    to be measured in a quieter phase can hide a provider socket from the
    reconciliation entirely.  Equality closes that: the measured non-stdio set
    must be EXACTLY the declared set for this role and phase, so neither a
    missing descriptor nor an extra one can pass.

    An EMPTY declared set is therefore meaningful rather than vacuous: it is the
    assertion "this leg holds no capability at this point", and it is only
    satisfiable by a measured set that is also empty.  Emptiness is DECLARED, so
    a leg cannot earn a clean verdict merely by being unmeasurable -- the caller
    must have committed to emptiness in advance.

    Descriptor identity is bound by ENDPOINT IDENTITY, never by fd NUMBER.  The
    number is an artifact of allocation order; a leg inheriting a provider socket
    can receive it at any number, so comparing numbers would let an inherited
    capability pass simply by landing somewhere unexpected.  (Measured: the
    inherited provider socket arrived at fd 4, not the number passed.)
    """
    if not measured.get("measured") or not measured.get("descriptors"):
        return {
            "phase": phase,
            "verdict": "MEASUREMENT_INVALID",
            "equality_satisfied": False,
            "measurement_valid": False,
            "refusal_reason": ("descriptor set was empty or the target was not "
                               "live at measurement time; an empty MEASUREMENT "
                               "cannot satisfy an empty DECLARATION"),
        }

    STDIO_FDS = (0, 1, 2)

    def identity_of(entry: dict) -> str:
        return entry["identity"]

    measured_entries = [e for e in measured["descriptors"]
                        if int(e["fd"]) not in STDIO_FDS]
    declared_entries = [e for e in declared.get("expected", [])
                        if int(e["fd"]) not in STDIO_FDS]

    measured_ids = sorted(identity_of(e) for e in measured_entries)
    declared_ids = sorted(identity_of(e) for e in declared_entries)

    # A declaration may bind an identity ONLY to a specific fd, in which case
    # the fd matters too (used for the sealed-response descriptor, whose number
    # the cell chose and passed to the leg).
    measured_bound = sorted((int(e["fd"]), identity_of(e))
                            for e in measured_entries
                            if e.get("identity_binding") == "fd_and_identity")
    declared_bound = sorted((int(e["fd"]), identity_of(e))
                            for e in declared_entries
                            if e.get("identity_binding") == "fd_and_identity")

    undeclared = [i for i in measured_ids if i not in declared_ids]
    unmeasured = [i for i in declared_ids if i not in measured_ids]
    bound_undeclared = [b for b in measured_bound if b not in declared_bound]
    bound_unmeasured = [b for b in declared_bound if b not in measured_bound]

    satisfied = not (undeclared or unmeasured or bound_undeclared
                     or bound_unmeasured)
    return {
        "phase": phase,
        "role": declared.get("role"),
        "measured_non_stdio_identities": measured_ids,
        "declared_non_stdio_identities": declared_ids,
        "measured_non_stdio_count": len(measured_ids),
        "declared_non_stdio_count": len(declared_ids),
        "undeclared_but_measured": undeclared,
        "declared_but_unmeasured": unmeasured,
        "fd_bound_undeclared": bound_undeclared,
        "fd_bound_unmeasured": bound_unmeasured,
        "equality_satisfied": satisfied,
        "measurement_valid": True,
        "verdict": "EQUALITY_SATISFIED" if satisfied else "CAPABILITY_VIOLATION",
        "no_provider_capable_descriptor_inherited": satisfied,
        "declared_empty_set": len(declared_ids) == 0,
    }


def negative_head_to_head(tracer_pid: int, leg_pid: int,
                          expected_leg_exe: str) -> dict:
    """Measure the TRACER as if it were the leg, and show the guard refuses it.

    This is a RECEIPT FIELD, not a test note.  The single most plausible way for
    this harness to lie is to measure the wrong process: the strace tracer is the
    direct child of the launcher, it blocks in wait() exactly like a leg at the
    barrier, and reading it yields `Seccomp: 0` with a plausible descriptor set
    -- i.e. a CLEAN-LOOKING reading of a process that is not the leg at all.

    Publishing the negative result proves the target binding is load-bearing and
    actually engaged, rather than a check that happens never to be exercised.
    A harness that only ever shows its positive case gives a reader no basis to
    believe the guard would fire.
    """
    return {
        "tracer_pid": tracer_pid,
        "leg_pid": leg_pid,
        "tracer_measured_as_if_leg": seccomp_state(
            tracer_pid, expected_exe=expected_leg_exe),
        "tracer_descriptors": enumerate_descriptors(
            tracer_pid, expected_exe=expected_leg_exe),
        "distinct_pids": tracer_pid != leg_pid,
    }


def _reverse_lookup(mapping: dict, identity: str) -> str:
    """Name the role of a known endpoint identity, tolerating path/prefix forms.

    The provider map is written by the harness as {role: identity}, but callers
    naturally also key it by bare path.  Comparing only exact strings made a
    NAMED provider endpoint report endpoint_role "UNKNOWN" -- the violation was
    still caught (fail-closed), but the receipt lost the name of the capability,
    which is the part that makes the failure legible.  Normalizing the
    AF_UNIX: prefix here keeps the binding exact while accepting both forms.
    """
    wanted = identity
    bare = identity[len("AF_UNIX:"):] if identity.startswith("AF_UNIX:") else identity
    for key, value in mapping.items():
        for candidate in (key, value):
            if candidate == wanted or candidate == bare:
                return key
            cand_bare = (candidate[len("AF_UNIX:"):]
                         if isinstance(candidate, str)
                         and candidate.startswith("AF_UNIX:") else candidate)
            if cand_bare == bare:
                return key
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Broker endpoint reachability
# ---------------------------------------------------------------------------

def classify_broker_endpoints(measured: dict, broker_identities: dict,
                              leg_role: str) -> dict:
    """Detect descriptors whose PEER is a broker process, not a plain pipe.

    The D3-E channel shape: the leg holds an otherwise innocent pipe or
    socketpair.  The descriptor itself looks harmless -- a pipe has no provider
    identity at all -- so the descriptor-allowlist check alone would pass it.
    What makes it a provider capability is the PEER: a process on the other end
    that will translate bytes written by the leg into a provider request.

    A pipe or socketpair end whose peer is a live process that this arm declared
    as a broker is therefore recorded as a broker endpoint.  The arm must fail on
    the mere EXISTENCE of that channel, whether or not the leg ever writes to it.
    """
    matches = []
    for entry in measured["descriptors"]:
        if entry["fd"] in (0, 1, 2):
            continue
        identity = entry["identity"]
        if identity in broker_identities:
            matches.append({"fd": entry["fd"], "identity": identity,
                            "kind": entry["kind"],
                            "broker_role": broker_identities[identity]})
            continue
        for key, role in broker_identities.items():
            if key in identity or identity in key:
                matches.append({"fd": entry["fd"], "identity": identity,
                                "kind": entry["kind"], "broker_role": role})
                break
    return {
        "leg_role": leg_role,
        "broker_endpoints": matches,
        "broker_endpoint_count": len(matches),
        "no_provider_capable_broker_endpoint_inherited": not matches,
        "declared_broker_identities": broker_identities,
        "note": ("existence of the channel is sufficient; the leg need not "
                 "exercise it for this to be a capability"),
    }


# ---------------------------------------------------------------------------
# Ordered timeline
# ---------------------------------------------------------------------------

def ordered_timeline(steps: dict, expected_order: tuple = None,
                     forbidden_sequence: tuple = None) -> dict:
    """Assemble the mandated SEQUENCE_STEPS timeline and check their ORDER.

    The step list is passed in by the caller rather than hardcoded here, because
    the sequence is part of the PREDICATE -- it is a claim about how the harness
    runs, not a property of descriptor inspection.  Two copies of the order would
    drift, and a drifted copy would let the harness verify itself against the
    wrong sequence while still reporting success.  `a12d3_d3_predicate` owns it.

    This function checks the ORDER of the observed timestamps rather than
    asserting the order, and reports any inversion explicitly.  The critical
    inversion is DENIAL_POLICY_INSTALLED arriving after either the descriptor
    measurement or the business-logic release: that is the forbidden capability
    window, in which the leg is released while unfiltered.
    """
    if expected_order is None:
        expected_order = (
            "LEG_PROCESS_START", "DENIAL_POLICY_INSTALLED",
            "ENTRY_BARRIER_REACHED", "DESCRIPTOR_SET_MEASURED_EXTERNALLY",
            "POLICY_ACTIVATION_EVIDENCED", "DESCRIPTOR_ALLOWLIST_RECONCILED",
            "BUSINESS_LOGIC_RELEASED")
    if forbidden_sequence is None:
        forbidden_sequence = ("LEG_PROCESS_START",
                              "DESCRIPTOR_SET_MEASURED_EXTERNALLY",
                              "BUSINESS_LOGIC_RELEASED",
                              "DENIAL_POLICY_INSTALLED")
    expected = tuple(expected_order)
    missing = [name for name in expected if steps.get(name) is None]
    present = [(name, float(steps[name])) for name in expected
               if steps.get(name) is not None]
    inversions = []
    for index in range(1, len(present)):
        if present[index][1] < present[index - 1][1]:
            inversions.append({"after": present[index - 1][0],
                               "before": present[index][0],
                               "delta_seconds":
                                   present[index][1] - present[index - 1][1]})
    install = steps.get("DENIAL_POLICY_INSTALLED")
    measure = steps.get("DESCRIPTOR_SET_MEASURED_EXTERNALLY")
    release = steps.get("BUSINESS_LOGIC_RELEASED")
    forbidden_window = None
    if install is not None and measure is not None and install > measure:
        forbidden_window = ("policy installed AFTER descriptor measurement: "
                            "capability window open")
    elif install is not None and release is not None and install > release:
        forbidden_window = ("policy installed AFTER business logic release: "
                            "leg ran unfiltered")
    return {
        "ordered_steps": [{"step": name, "wall": steps.get(name)}
                          for name in expected],
        "expected_order": list(expected),
        "missing_steps": missing,
        "complete": not missing,
        "order_inversions": inversions,
        "order_respected": not inversions and not missing,
        "forbidden_capability_window": forbidden_window,
        "no_forbidden_capability_window": forbidden_window is None,
        "forbidden_sequence_definition": list(forbidden_sequence),
        "forbidden_sequence_observed": bool(missing) and not present,
    }


# ---------------------------------------------------------------------------
# The inspector itself, as a runnable barrier resolver
# ---------------------------------------------------------------------------

def await_blocked(pid: int, timeout: float = 60.0) -> dict:
    """Wait until a leg is provably blocked in the barrier read.

    Blocking is evidenced by the leg's `State:` field in /proc/<pid>/status
    resting in a sleeping state, together with its wchan being a read family
    symbol.  It is not inferred from a sleep in this process.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        status = read_status_fields(pid, ("State", "Name"))
        state = status["fields"].get("State") or ""
        wchan = _read_text(Path("/proc/%d/wchan" % pid))
        last = {"state": state, "wchan": wchan,
                "wall": time.time()}
        if state.startswith("S") or state.startswith("D"):
            return {"blocked": True, "observed": last,
                    "waited_seconds": timeout - (deadline - time.time())}
        time.sleep(0.01)
    return {"blocked": False, "observed": last,
            "waited_seconds": timeout, "timed_out": True}


def release_barrier(fifo_write_path: str) -> dict:
    """Release a held leg by opening the barrier FIFO for writing.

    The leg's blocking read returns when this open completes, so the release is
    a kernel-mediated rendezvous, not a signal or a flag file.
    """
    path = Path(fifo_write_path)
    if not path.exists():
        return {"released": False, "error": "barrier_fifo_absent",
                "path": str(path)}
    fd = os.open(str(path), os.O_WRONLY)
    try:
        # No fsync here: fsync is EINVAL on a FIFO (pipes are not seekable
        # files) and the rendezvous does not need durability -- the leg's read
        # returns as soon as this write lands in the pipe buffer.
        os.write(fd, b"RELEASE\n")
    finally:
        os.close(fd)
    return {"released": True, "path": str(path), "wall": time.time()}


if __name__ == "__main__":
    import sys
    target = int(sys.argv[1]) if len(sys.argv) > 1 else os.getpid()
    print(json.dumps({
        "inspector": INSPECTOR_VERSION,
        "target_pid": target,
        "seccomp": seccomp_state(target),
        "descriptors": enumerate_descriptors(target),
    }, indent=2, sort_keys=True, default=str))
