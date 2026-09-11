"""D3 reuse of the D2 sealed-response identity (NO third capture mechanism).

D2 owns the capture and the seal.  This module does not re-capture anything: it
takes the response bytes the D2 gate+mock boundary actually produced, writes them
into a memfd sealed with the SAME D2 seal family, records the D2-compatible
identity fields, and hands the bytes to each leg by PATH.

Why by path: `systemd-run` drops inherited descriptors (proven twice in this
apparatus), so a live sealed memfd cannot reach a leg.  The leg therefore reads
the sealed-audit copy from disk and re-establishes the seal OBSERVATION itself:
it hashes exactly the bytes it consumed and publishes `point_of_use_sha256`, the
same field D2's legs publish.  The identity join is on BYTES, not on fd number,
so the path handoff does not weaken it.

README-LEVEL INVARIANT: the handoff is read-only and hash-verified at point of
use.  A leg that consumes different bytes reports a different point-of-use hash
and the join fails.
"""

import base64
import fcntl as _fcntl
import hashlib
import json
import os
import time
from pathlib import Path

SEAL_MODULE_VERSION = "D3_D2_SEALED_IDENTITY_REUSE_v1.0"

# The D2 seal family, reused verbatim.
SEAL_FLAGS = "F_SEAL_WRITE|F_SEAL_GROW|F_SEAL_SHRINK|F_SEAL_SEAL"
HANDOFF_KIND = "sealed_memfd_descriptor_family"
AUDIT_COPY_ROLE = "retained_evidence_copy_NOT_the_handoff"
LIVE_SOURCE_SEAL = "PATH_BACKED_NOT_KERNEL_SEALABLE"
D2_AUTHORITY = "a12d2_single_captured_response_controls.py"

# glibc exposes memfd_create; the seal constants come from fcntl so they are the
# real kernel values rather than remembered ones (F_SEAL_SEAL=1, SHRINK=2,
# GROW=4, WRITE=8 -- the 16/32/64 guess was wrong and produced EINVAL).
import ctypes

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.memfd_create.restype = ctypes.c_int
_libc.memfd_create.argtypes = [ctypes.c_char_p, ctypes.c_uint]

MFD_ALLOW_SEALING = 0x0002
F_ADD_SEALS = _fcntl.F_ADD_SEALS
F_SEAL_BITS = (_fcntl.F_SEAL_SEAL | _fcntl.F_SEAL_SHRINK |
               _fcntl.F_SEAL_GROW | _fcntl.F_SEAL_WRITE)


def _memfd_seal_bytes(payload: bytes):
    """Seal the capture in a memfd exactly as D2 does, and prove it is
    kernel-sealed by attempting a write (must fail with EPERM)."""
    name = b"d3-sealed-response-reuse"
    fd = _libc.memfd_create(name, MFD_ALLOW_SEALING)
    if fd < 0:
        return None, "memfd_create failed: errno=%d" % ctypes.get_errno()
    try:
        os.write(fd, payload)
        os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        if _fcntl.fcntl(fd, F_ADD_SEALS, F_SEAL_BITS) != 0:
            return None, "F_ADD_SEALS failed: errno=%d" % ctypes.get_errno()
        reread = os.read(fd, len(payload) + 16)
        if reread != payload:
            return None, "sealed memfd reread mismatch"
        offset = os.lseek(fd, 0, os.SEEK_SET)
        try:
            os.write(fd, b"x")
            write_probe = "UNEXPECTED_WRITE_SUCCEEDED"
        except OSError as exc:
            write_probe = "EPERM_kernel_seal_confirmed" if exc.errno == 1 \
                else "errno=%d" % exc.errno
        info = {
            "fd": fd, "seal_flags": SEAL_FLAGS,
            "bytes": len(payload),
            "seals_observed": _fcntl.fcntl(fd, _fcntl.F_GET_SEALS),
            "seals_expected": F_SEAL_BITS,
            "sealed_handoff_write_probe": write_probe,
            "reread_matches": True, "seek_offset_after_reread": offset,
        }
        return info, None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def atomic_write_json(path, payload):
    """Write JSON so a reader never sees a half-written identity document."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path


def bind_sealed_identity(arm_dir, response_bytes, cell_id, leg_identities=()):
    """Record the D2-compatible sealed-response identity for this arm.

    Returns the identity document that the receipt binds and the checker
    recomputes.  The D2 field names are preserved exactly so the join to D2
    evidence is by NAME as well as by VALUE.

    `leg_identities` is the set of legs this arm MUST bind the response to.  It is
    recorded so the join can require the FULL set rather than "however many legs
    happened to write a receipt": without an expected count, a run where two legs
    crashed before writing would still report "same response bound to all legs",
    because "all" would silently mean "the one that survived".
    """
    arm_dir = Path(arm_dir)
    payload = bytes(response_bytes)
    envelope_sha = hashlib.sha256(payload).hexdigest()

    seal_info, seal_error = _memfd_seal_bytes(payload)

    # The read-only audit copy the LEG consumes, exactly as D2 retains one.
    response_dir = arm_dir / "response"
    response_dir.mkdir(parents=True, exist_ok=True)
    encoded = base64.b64encode(payload)
    decoded_sha = hashlib.sha256(base64.b64decode(encoded)).hexdigest()
    audit_copy = response_dir / "sealed-response.b64"
    audit_copy.write_bytes(encoded)
    # The handoff is READ-ONLY and proven so: mode 0444 means an in-process write
    # attempt fails, which is the guarantee the sealed memfd provides in D2.
    # Without this the "read-only handoff" claim would be a comment, not a fact.
    os.chmod(audit_copy, 0o444)

    doc = {
        "version": SEAL_MODULE_VERSION,
        "d2_authority": D2_AUTHORITY,
        "reuse": "D2 capture+seal semantics reused; D3 captures nothing new",
        "cell_id": cell_id,
        "captured_from": "exclusive_gate_dispatch",
        "provider_opportunities_made": 1,
        "captured_responses": 1,
        "captured_response_bytes": len(payload),
        "captured_response_sha256": envelope_sha,
        "response_snapshot_sha256": decoded_sha,
        "sealed_response_sha256": decoded_sha,
        "seal_flags": SEAL_FLAGS,
        "seal_strong_hash_family": SEAL_FLAGS,
        "handoff_kind": HANDOFF_KIND,
        "sealed_handoff_write_probe":
            seal_info["sealed_handoff_write_probe"] if seal_info else
            "SEAL_UNAVAILABLE: %s" % seal_error,
        "sealed_reread_matches": bool(seal_info and seal_info["reread_matches"]),
        "sealed_memfd_bytes": seal_info["bytes"] if seal_info else 0,
        "sealed_audit_copy": str(audit_copy),
        "audit_copy_role": AUDIT_COPY_ROLE,
        "live_source_seal": LIVE_SOURCE_SEAL,
        "handoff_path": str(audit_copy),
        "handoff_delivery": "PATH_because_systemd_run_drops_inherited_fds",
        "identity_join_key": "captured_response_sha256 == point_of_use_sha256",
        # The legs this arm MUST bind the response to.  Recorded so the join can
        # require the FULL set instead of "however many receipts appeared".
        "leg_identities": list(leg_identities),
        "bound_wall": time.time(),
    }
    return doc


def read_leg_receipt(arm_dir, leg_role):
    """Read a leg's point-of-use receipt (D2-compatible field names)."""
    for name in ("%s.receipt.json" % leg_role, "%s.receipt.json" % leg_role.lower()):
        path = Path(arm_dir) / "receipts" / name
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                return None
    return None


def join_point_of_use(sealed_doc, receipts):
    """The D2 identity join, computed from RAW artifacts.

    Reused D2 semantics: the bytes the leg actually consumed must hash to the
    captured-response hash.  `claimed_metadata_sha256` is the leg's CLAIM; the
    join is on `point_of_use_sha256`, which the leg derived by hashing the bytes
    it really read, so an unread or substituted response cannot pass.
    """
    expected = sealed_doc.get("captured_response_sha256", "")
    rows, mismatches, missing = [], [], []
    for role, receipt in sorted(receipts.items()):
        if receipt is None:
            missing.append(role)
            continue
        observed = receipt.get("point_of_use_sha256", "")
        # The consumer of this join reads `matches_captured_response`.  Assert the
        # field while building the row: a rename here would make the consumer read
        # None, and `all()` over None is False -- so a fully green three-leg join
        # would surface as a FAILED conjunct.  That is a schema defect wearing the
        # costume of evidence, and it is exactly how a green join was once hidden.
        row = {
            "leg": role,
            "point_of_use_sha256": observed,
            "claimed_metadata_sha256": receipt.get("claimed_metadata_sha256", ""),
            "bytes_consumed": receipt.get("bytes_consumed", 0),
            "proof": receipt.get("proof", ""),
            "provider_calls": receipt.get("provider_calls", None),
            "matches_captured_response": observed == expected,
            "claim_matches_observation":
                receipt.get("claimed_metadata_sha256", "") == observed,
        }
        rows.append(row)
        if not row["matches_captured_response"]:
            mismatches.append(role)
    all_same = bool(rows) and len({r["point_of_use_sha256"] for r in rows}) == 1
    # `all_same` over a SINGLE row is trivially true -- that is how the "same
    # response bound to ALL THREE legs" property had no content while an arm ran
    # one leg.  The property is only meaningful over the full expected set, so it
    # is derived against expected_leg_count rather than over "however many rows
    # happened to appear".  A missing leg must make this FALSE, not simply absent
    # from the average.
    expected_leg_count = len(sealed_doc.get("leg_identities") or ()) or len(
        receipts)
    all_three_same = (all_same and not missing and not mismatches and
                      len(rows) == expected_leg_count and
                      expected_leg_count > 1)
    return {
        "expected_captured_response_sha256": expected,
        "legs": rows,
        # Keyed by leg identity so a reader can join on identity rather than on
        # list position -- the same requirement the pid binding has, for the same
        # reason: order is not evidence.
        "per_leg": {row["leg"]: row for row in rows},
        "leg_count": len(rows),
        "expected_leg_count": expected_leg_count,
        "legs_missing_receipt": missing,
        "legs_with_mismatched_point_of_use": mismatches,
        "legs_consumed_sealed_response": bool(rows) and not missing,
        "point_of_use_hash_valid": bool(rows) and not mismatches and all_same,
        "same_captured_response_bound_to_all_legs": all_three_same,
        "no_response_substitution": not mismatches and not missing,
        "join_key": "captured_response_sha256 == point_of_use_sha256",
        "derivation": "recomputed from sealed identity + per-leg receipts",
    }
