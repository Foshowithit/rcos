#!/usr/bin/env python3
"""D3 independent checker: recompute the frozen predicate from raw artifacts.

WHY THIS FILE EXISTS
====================

The D3 harness (a12d3_counterfactual_provider_capability_controls.py) both RUNS
the arms and REPORTS the verdict.  A receipt produced that way is a self-report:
if the harness has a bug in how it reads a marker, or in which errno it binds, or
in the order in which it believes events occurred, the receipt will be internally
consistent and still wrong.  Recent history in this apparatus makes that concrete
rather than hypothetical -- an unconditional probe made every arm look identical,
a stale marker parser silently emptied the evidence list, and a marker reader
that returned TEXT errno values produced an empty errno set next to denials that
plainly occurred.

So this checker recomputes all fifteen conjuncts from the RAW on-disk artifacts
using its own parsers, and then compares its reconstruction against the harness's
claim.  It deliberately does NOT import the harness's evaluation code: sharing a
parser would share its bugs.  Importing the predicate module is safe and intended
-- the conjunct NAMES and the frozen text are the specification, not the
mechanism -- and the checker asserts the predicate text it recomputed against is
the frozen one.

WHAT IT CHECKS
==============

 1. The frozen predicate text is byte-identical to the spec in a12d3_d3_predicate.
 2. Per arm, recompute each conjunct from raw artifacts:
      - descriptor maps and their equality reconciliation (raw measurement.json)
      - the kernel's seccomp activation evidence (raw /proc-derived fields)
      - denied syscalls, by arm, from the raw strace text -- not from the
        harness's event summary
      - denial errnos from the LEG's own markers, coerced to int
      - honest completion from the leg's own LEG_COMPLETED marker
      - D1 ledger counts recomputed from the RAW jsonl records
 3. Ordered-timeline verification against SEQUENCE_STEPS, including rejection of
    FORBIDDEN_SEQUENCE (measure-before-install would open an unfiltered window).
 4. Arm verdicts against the frozen ARM_EXPECTATION.
 5. The two falsifier arms (D3-B, D3-E) MUST fail while D1 reports zero provider
    delta -- that is the D2-E falsifier requirement.
 6. Every failure code used must be in the frozen three-term vocabulary.

EXIT CODES
==========

  0  checker agreed with the harness on every arm and every conjunct
  1  a disagreement was found (the receipt is not trustworthy as written)
  2  a required raw artifact was missing or unreadable

A disagreement is not automatically a harness bug -- it is a contradiction that
must be resolved before the receipt can be believed.  The checker reports WHICH
side and WHICH conjunct, with the raw line, so the resolution is a reading rather
than a guess.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import a12d3_d3_predicate as predicate  # noqa: E402  (spec, not mechanism)

# The D2 count authority, restated here INDEPENDENTLY of the harness: the cell
# is entitled to exactly one authorized opportunity, so a populated boundary is
# 1/1/1.  A delta measured against anything else is not the same measurement.
EXPECTED_COUNTS = {"attempts": 1, "dispatches": 1, "receives": 1}

# The FALSIFIER arm's expected END state, and the delta that must be observed.
#
# These are transcribed from the FROZEN F1 text, which names this shape exactly:
# "baseline 1/1/1 -> inject a second REAL gate request but prevent the second
# dispatch -> final 2/1/1 -> delta {attempts:+1, dispatches:0, receives:0}".
# Transcribed rather than inferred from the harness's own numerics, because the
# harness's numerics are the thing under audit.
#
# F1b (the full-traverse variant, 2/2/1) is a SUPPLEMENTAL falsifier.  The gate
# ruled it must not be the contract-bearing one, so it is deliberately absent
# from the contract expectation below and is reported separately.
F1_FALSIFIER_EXPECTED_AFTER = {"attempts": 2, "dispatches": 1, "receives": 1}
F1_FALSIFIER_EXPECTED_DELTA = {"attempts": 1, "dispatches": 0, "receives": 0}
F1B_SUPPLEMENTAL_EXPECTED_AFTER = {"attempts": 2, "dispatches": 2, "receives": 1}
F1B_SUPPLEMENTAL_EXPECTED_DELTA = {"attempts": 1, "dispatches": 1, "receives": 0}

# Which arm carries the injected second opportunity.  `FALSIFIER_INJECTION_ARMS`
# lives in the HARNESS, not in the frozen predicate, so it cannot be imported
# without importing the thing under audit; it is transcribed here and the harness's
# own copy is cross-checked in main(), so a divergence is reported rather than
# absorbed.  (The frozen predicate's FALSIFIER_ARMS_REQUIRE_ZERO_PROVIDER_DELTA is
# a DIFFERENT set -- D3-B and D3-E, the arms that must fail while D1 reports zero
# delta.  Confusing the two would grade the wrong arms.)
FALSIFIER_ARMS = ("D3-X",)
import a12d3_d3_seccomp_policy as policy  # noqa: E402  (classifier groups)

CHECKER_VERSION = "D3_INDEPENDENT_CHECKER_v1.0"
WORK_ROOT = Path(os.environ.get("D3_WORK_ROOT", "/tmp/d3gen/d3run"))
STDIO_FDS = (0, 1, 2)

# The kernel's own record for a process under a seccomp filter.  Read externally
# from /proc/<pid>/status; "2" is SECCOMP_MODE_FILTER, the mode that enforces a
# BPF program.  Mode 1 (strict) is a different mechanism and is not what D3
# installs, so accepting either would weaken the check to "some seccomp is on".
SECCOMP_MODE_FILTER = "2"


# ---------------------------------------------------------------------------
# Raw readers.  Each returns plain data or raises, so a missing artifact is a
# hard failure rather than a silently-satisfied conjunct.
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text())


def read_leg_markers(path: Path) -> list[dict]:
    """Parse the leg's own marker file.

    Format, as emitted by d3_note():  <EVENT> wall=<sec>.<nsec> [k=v ...]

    The event name is FIRST.  Every subsequent key=value token is captured as
    TEXT, because the line is parsed generically and a token's type is not
    knowable from the line alone.  Numeric coercion is the caller's job -- here
    it is explicit, so a text "13" cannot silently fail an isinstance check.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))
    events: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        record: dict = {"marker": parts[0], "raw_line": line}
        for token in parts[1:]:
            if "=" not in token:
                continue
            key, _, value = token.partition("=")
            record[key] = value
        events.append(record)
    return events


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def recompute_descriptor_equality(measurement: dict, phase: str) -> dict:
    """Recompute descriptor-set EQUALITY independently of the harness.

    EQUALITY, not containment: the measured non-stdio descriptor set must be
    exactly the precommitted one.  Containment would let an arm hold an extra
    capability and still pass, which is precisely the D3-B/D3-E failure mode.

    An EMPTY or unverified measurement is MEASUREMENT_INVALID, never satisfied.
    A measurement that failed to observe anything must not be read as "observed
    nothing wrong".
    """
    descriptors = measurement.get("descriptors") or {}
    seccomp = measurement.get("seccomp") or {}
    measured = descriptors.get("descriptors") or []
    if not descriptors.get("measured") or not seccomp.get("target_verified"):
        return {"measurement_valid": False,
                "no_provider_capable_descriptor_inherited": False,
                "reason": "MEASUREMENT_INVALID",
                "measured_non_stdio_identities": []}

    measured_ids = sorted({d.get("identity") for d in measured
                           if d.get("fd") not in STDIO_FDS and d.get("identity")})
    declared = measurement.get("declared_descriptor_allowlist") or {}
    declared_ids = sorted({e.get("identity") for e in
                           (declared.get("entries") or [])
                           if e.get("identity")})
    undeclared = [i for i in measured_ids if i not in declared_ids]
    unmeasured = [i for i in declared_ids if i not in measured_ids]
    satisfied = not (undeclared or unmeasured)
    return {
        "measurement_valid": True,
        "no_provider_capable_descriptor_inherited": satisfied,
        "measured_non_stdio_identities": measured_ids,
        "declared_non_stdio_identities": declared_ids,
        "undeclared_but_measured": undeclared,
        "declared_but_unmeasured": unmeasured,
        "verdict": "EQUALITY_SATISFIED" if satisfied else "CAPABILITY_VIOLATION",
    }


# Denied syscalls as strace actually writes them: the syscall name is followed
# by arguments and a "= -1 EACCES (Permission denied)" tail.  The prefix carries
# an optional -ttt timestamp and pid; matching the syscall name anywhere is what
# the harness does, so the checker anchors on the call-and-result SHAPE instead,
# which is a genuinely independent reading.
_DENIED_RE = re.compile(
    r"(?P<nr>[a-z_0-9]+)\(.*\)\s*=\s*-1\s+(?P<errno>EACCES|EPERM)\b")

# A failure line whose errno is NAMED but is NOT an accepted denial errno:
#   ... = -1 ECHILD (No child processes)
# These must never be counted as denials.  The checker scans for them explicitly
# so that a harness which coerced the placeholder `-1` into errno 1 (EPERM) -- and
# thereby reported an ordinary supervisor `wait()` as a denied `wait4` -- is
# CAUGHT here rather than silently agreed with.  This is the independent side of
# that disagreement: the checker was right, and this keeps it provably so.
_NON_DENIAL_FAILURE_RE = re.compile(
    r"(?P<nr>[a-z_0-9]+)\(.*\)\s*=\s*-1\s+(?P<errno>[A-Z][A-Z0-9_]+)\b")
_ACCEPTED_DENIAL_NAMES = ("EACCES", "EPERM")


def read_denied_syscalls(trace_files: list[Path]) -> tuple[list[str], list[dict]]:
    """Extract denied syscalls from the RAW strace text.

    Returns (sorted unique syscall names, the matching records).  Kills are
    returned separately by the caller: a SIGSYS kill is a policy defect, not a
    denial, so it must never be folded into this set.
    """
    denied: set[str] = set()
    records: list[dict] = []
    for path in trace_files:
        if not path.exists():
            continue
        for line in path.read_text(errors="replace").splitlines():
            match = _DENIED_RE.search(line)
            if not match:
                continue
            name = match.group("nr")
            denied.add(name)
            records.append({"syscall": name, "errno_name": match.group("errno"),
                            "raw_line": line.strip(), "trace_file": str(path)})
    return sorted(denied), records


_KILL_RE = re.compile(r"killed by (SIGSYS|signal 31)", re.IGNORECASE)


def read_kill_events(trace_files: list[Path]) -> list[dict]:
    kills = []
    for path in trace_files:
        if not path.exists():
            continue
        for line in path.read_text(errors="replace").splitlines():
            if _KILL_RE.search(line):
                kills.append({"raw_line": line.strip(),
                              "trace_file": str(path)})
    return kills


def count_ledger_records(path: Path) -> int:
    """Count RAW records in a D1 ledger.

    Counted from the file itself, not from a summary line, because D1 is the
    provider-opportunity counting authority and the whole point of the falsifier
    arms is that they fail with this count at zero.  A count taken from the
    harness would be the harness confirming its own claim.
    """
    if not path.exists():
        return 0
    total = 0
    for line in path.read_text(errors="replace").splitlines():
        if line.strip():
            total += 1
    return total


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Ordered timeline, recomputed.
# ---------------------------------------------------------------------------

def recompute_timeline(events: list[dict], measurement: dict) -> dict:
    """Verify the mandated sequence by MERGING the two ordered raw sources.

    The sequence spans two observers, and neither one alone can attest to it:

      * The LEG's own markers (markers.txt) carry the leg-side steps, each with a
        wall timestamp: LEG_PROCESS_START, DENIAL_POLICY_INSTALLED,
        ENTRY_BARRIER_REACHING, BUSINESS_LOGIC_RELEASED.
      * Three steps are EXTERNAL observations made by the harness from outside
        the leg -- DESCRIPTOR_SET_MEASURED_EXTERNALLY, POLICY_ACTIVATION_EVIDENCED,
        DESCRIPTOR_ALLOWLIST_RECONCILED.  The leg cannot emit these about itself:
        if it did, "externally measured" would be a self-report, which is exactly
        the weakness D3 exists to avoid.  They are not in markers.txt at all.

    An earlier revision of this checker looked only at markers.txt and therefore
    reported all five arms as out of order -- a false alarm caused by reading one
    source for a two-source sequence.  The correction is to interleave them by
    timestamp: the external observation is placed at the measurement's own
    measured_wall, which is what proves it happened while the leg was parked.

    The forbidden sequence is measure-clean-FDs -> release-leg -> install
    seccomp, which opens a window in which the leg runs UNFILTERED between the
    measurement and the policy's activation.  D3 requires the policy installed
    BEFORE the leg reaches its entry barrier, so that order must never appear.
    """
    # Leg-side steps, in the leg's own recorded order.
    leg_steps: list[tuple[float, str]] = []
    for event in events:
        marker = event.get("marker")
        if marker == "ENTRY_BARRIER_REACHING":
            marker = "ENTRY_BARRIER_REACHED"
        if marker not in predicate.SEQUENCE_STEPS:
            continue
        try:
            wall = float(event.get("wall"))
        except (TypeError, ValueError):
            wall = None
        leg_steps.append((wall, marker))

    # External steps, timestamped at the moment the external observer measured.
    measured_wall = measurement.get("measured_wall")
    try:
        measured_wall = float(measured_wall)
    except (TypeError, ValueError):
        measured_wall = None
    external = [s for s in
                ("DESCRIPTOR_SET_MEASURED_EXTERNALLY",
                 "POLICY_ACTIVATION_EVIDENCED",
                 "DESCRIPTOR_ALLOWLIST_RECONCILED")
                if s in predicate.SEQUENCE_STEPS]

    merged: list[tuple[float, str]] = list(leg_steps)
    if measured_wall is not None:
        for step in external:
            merged.append((measured_wall, step))

    # Sort by timestamp; ties break deterministically on the expected order so
    # that a simultaneous external cluster does not read as an inversion.
    expected_index = {step: i for i, step in enumerate(predicate.SEQUENCE_STEPS)}
    merged.sort(key=lambda item: ((item[0] if item[0] is not None else -1.0),
                                  expected_index.get(item[1], 0)))

    observed: list[str] = []
    for _wall, marker in merged:
        if marker not in observed:
            observed.append(marker)

    expected = list(predicate.SEQUENCE_STEPS)
    missing = [step for step in expected if step not in observed]

    # Order inversions: index of each observed step must be increasing along the
    # expected order.  Computed as inversions in the permutation restricted to
    # the steps that both lists contain.
    common = [step for step in observed if step in expected]
    positions = [expected.index(step) for step in common]
    inversions = [(common[i], common[j])
                  for i in range(len(positions))
                  for j in range(i + 1, len(positions))
                  if positions[i] > positions[j]]

    forbidden = list(predicate.FORBIDDEN_SEQUENCE)
    # The forbidden sequence is present iff its steps appear as a SUBSEQUENCE of
    # the observed order (not necessarily adjacent) -- a window can span other
    # events and still exist.
    it = iter(observed)
    forbidden_observed = all(step in it for step in forbidden)

    return {
        "observed_order": observed,
        "expected_order": expected,
        "missing_steps": missing,
        "order_inversions": inversions,
        "order_respected": not missing and not inversions,
        "forbidden_sequence_observed": forbidden_observed,
        "no_forbidden_capability_window": not forbidden_observed,
    }


# ---------------------------------------------------------------------------
# Per-arm recomputation.
# ---------------------------------------------------------------------------

def _raw_ledger_state(path: Path) -> dict:
    """Read a raw JSONL ledger and return its bytes-level and record-level state.

    The point of reading RAW BYTES rather than a snapshot is that a snapshot is a
    C LAIM ABOUT a file.  The gate's D1 requirement is that the authority be the
    ledger bytes themselves: hash, byte offset, and decoded record count, so that
    neither a substitution of one ledger for another nor a retrospective
    reconstruction of a baseline can pass.
    """
    if not path.exists():
        return {"exists": False, "path": str(path), "bytes": 0, "sha256": "",
                "records": 0, "unparsable": 0, "byte_offsets": []}
    raw = path.read_bytes()
    records, unparsable, offsets = 0, 0, []
    offset = 0
    for line in raw.split(b"\n"):
        offset += len(line) + 1
        if not line.strip():
            continue
        try:
            json.loads(line.decode("utf-8", errors="replace"))
            records += 1
            offsets.append(offset)
        except (ValueError, TypeError):
            unparsable += 1
    return {
        "exists": True, "path": str(path), "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "records": records, "unparsable": unparsable,
        "byte_offsets": offsets,
        "final_record_end_offset": (offsets[-1] if offsets else 0),
    }


def _raw_sealed_state(sealed: bytes | None) -> dict:
    """Byte/record state of the SEALED pre-leg prefix (not of a live file).

    The sealed artifact is the authority for "what the boundary looked like before
    the leg was released".  Reading the live ledger at audit time would be a
    retrospective baseline: the file has grown by then, so the "before" would be
    the after.
    """
    if sealed is None:
        return {"exists": False, "bytes": 0, "sha256": "",
                "records": 0, "unparsable": 0, "byte_offsets": []}
    records, unparsable, offsets = 0, 0, []
    offset = 0
    for line in sealed.split(b"\n"):
        offset += len(line) + 1
        if not line.strip():
            continue
        try:
            json.loads(line.decode("utf-8", errors="replace"))
            records += 1
            offsets.append(offset)
        except (ValueError, TypeError):
            unparsable += 1
    return {"exists": True, "bytes": len(sealed),
            "sha256": hashlib.sha256(sealed).hexdigest(),
            "records": records, "unparsable": unparsable,
            "byte_offsets": offsets,
            "final_record_end_offset": (offsets[-1] if offsets else 0)}


def _resolve_ledger(arm_dir: Path, recorded_path: str) -> Path:
    """Resolve a recorded ledger path against THIS arm directory.

    The snapshot records an absolute path into the run root.  Resolving by
    basename instead of trusting the absolute string keeps the join valid when the
    run is audited at a different mount point -- and, more importantly, stops a
    snapshot from pointing the checker at a ledger in some OTHER arm's directory.
    """
    return arm_dir / Path(recorded_path or "").name


def _prefix_state(before_state: dict, after_state: dict,
                  sealed_prefix: bytes | None,
                  final_path: Path | None = None) -> dict:
    """Prove the pre-leg ledger bytes are an EXACT PREFIX of the final ledger.

    Three separate claims, each able to fail alone:

      * the sealed pre-leg byte length is <= the final byte length (monotone append)
      * the first `sealed_len` bytes of the final ledger equal the sealed bytes
        (the prefix was not rewritten, only appended to)
      * the final byte offsets are strictly increasing and the sealed record count
        is recoverable from the final bytes alone

    A mismatch is a FAILURE, never an absence: an arm whose ledger was truncated
    or rewritten has an unverifiable delta, which must not read as delta-zero.
    """
    if sealed_prefix is None:
        return {"prefix_verified": False,
                "prefix_reason": "SEALED_PRE_LEG_PREFIX_ABSENT"}
    sealed_len = len(sealed_prefix)
    sealed_sha = hashlib.sha256(sealed_prefix).hexdigest()
    final_len = after_state.get("bytes", 0)
    if not before_state.get("exists") or not after_state.get("exists"):
        return {"prefix_verified": False, "sealed_bytes": sealed_len,
                "sealed_sha256": sealed_sha,
                "prefix_reason": "LEDGER_ABSENT"}
    if final_len < sealed_len:
        return {"prefix_verified": False, "sealed_bytes": sealed_len,
                "sealed_sha256": sealed_sha, "final_bytes": final_len,
                "prefix_reason": "FINAL_LEDGER_SHORTER_THAN_SEALED_PREFIX"}
    final_path = Path(final_path or after_state.get("path") or "")
    if not str(final_path) or not final_path.exists():
        return {"prefix_verified": False, "sealed_bytes": sealed_len,
                "sealed_sha256": sealed_sha,
                "prefix_reason": "FINAL_LEDGER_UNREADABLE"}
    head = final_path.read_bytes()[:sealed_len]
    head_sha = hashlib.sha256(head).hexdigest()
    ok = (head_sha == sealed_sha)
    return {
        "prefix_verified": ok,
        "prefix_reason": None if ok else "PREFIX_BYTES_DIFFER",
        "sealed_bytes": sealed_len,
        "sealed_sha256": sealed_sha,
        "final_bytes": final_len,
        "final_prefix_sha256": head_sha,
        "appended_bytes": final_len - sealed_len,
    }


def recompute_provider_delta(arm_dir: Path, arm_completed: bool,
                            expected_after: dict | None = None,
                            expected_delta: dict | None = None) -> dict:
    """Recompute the D1 delta conjunct from the RAW before/after snapshots.

    Fail-closed rule, in three parts.  The original defect was a conjunct that
    read `records == 0` on files nothing ever wrote, so "the apparatus is absent"
    and "no provider opportunity occurred" produced the SAME true value.  So:

      1. If the arm claims a completed run and a snapshot is missing, that is
         MEASUREMENT_INVALID -- never a quiet zero.
      2. The before-snapshot must be POPULATED (matches the D2 authority 1/1/1).
         An empty boundary cannot evidence "no delta" because there was nothing
         to move.
      3. after == before == expected.
    """
    # A missing snapshot is a RESULT (fail closed), not an exception: if this
    # raised, a checker could crash on exactly the malformed arm it exists to
    # catch, and a crash is not a verdict.
    def _opt(name):
        path = arm_dir / name
        return _load_json(path) if path.exists() else {}

    before = _opt("provider-before.json")
    after = _opt("provider-after.json")
    out = {
        "before_present": bool(before), "after_present": bool(after),
        "before": (before or {}).get("counts"),
        "after": (after or {}).get("counts"),
        "expected": expected_after or EXPECTED_COUNTS,
        "expected_is_falsifier_shape": bool(expected_after),
        "falsifier_arm": bool((before or {}).get("falsifier_arm")),
        # Published by the harness when the conjunct went false; the checker
        # confirms the evidence exists rather than trusting the flag.
        "offenders_present": (arm_dir / "delta-offenders.json").exists(),
        "falsifier_injection_present": (arm_dir / "falsifier-injection.json").exists(),
    }

    missing = [n for n in ("before_present", "after_present") if not out[n]]
    if missing and arm_completed:
        out.update({
            "conjunct_value": False,
            "fail_closed": True,
            "invalid_reason": "COMPLETED_RUN_WITHOUT_%s" %
                              "_AND_".join(m.upper() for m in missing),
        })
        return out

    if not before or not after:
        # No completed run and no snapshots: the delta was never measured, which
        # must NOT read the same as a measured zero.
        out.update({"conjunct_value": False, "fail_closed": True,
                    "invalid_reason": "DELTA_NEVER_MEASURED"})
        return out

    before_counts = {n: int(before.get("counts", {}).get(n, {}).get("records", 0))
                     for n in EXPECTED_COUNTS}
    after_counts = {n: int(after.get("counts", {}).get(n, {}).get("records", 0))
                    for n in EXPECTED_COUNTS}
    populated_before = before_counts == EXPECTED_COUNTS
    delta = {n: after_counts[n] - before_counts[n] for n in EXPECTED_COUNTS}

    # ── The authority is the RAW LEDGER BYTES, not the snapshot ────────────────
    #
    # Everything above reads `provider-before.json` / `provider-after.json`, which
    # are SNAPSHOTS -- claims about ledger files.  Under snapshot-only authority
    # the substitution attack is constructible: repoint a snapshot at a different
    # ledger, or synthesise both snapshots to agree, and the conjunct reports
    # "zero delta" while the real ledgers moved.  So each ledger is now read from
    # its raw bytes, and the three joins below are required to hold:
    #
    #   (i)   the recorded path resolves to THIS arm's directory
    #   (ii)  snapshot.bytes and snapshot.sha256 match the raw bytes on disk
    #   (iii) the pre-leg sealed bytes are an exact prefix of the final bytes
    #
    # Only then are the before/after counts derived from those bytes.
    raw_rows, raw_ok, raw_notes = {}, True, []
    for name in EXPECTED_COUNTS:
        recorded = (before.get("counts") or {}).get(name) or {}
        path = _resolve_ledger(arm_dir, recorded.get("path", ""))
        # (i) the ledger must live in this arm directory
        if path.parent.resolve() != arm_dir.resolve():
            raw_ok = False
            raw_notes.append("%s: ledger resolves outside the arm directory" % name)
        stated_side = (after.get("counts") or {}).get(name) or {}
        path_after = _resolve_ledger(arm_dir, stated_side.get("path", ""))
        if path_after != path:
            raw_ok = False
            raw_notes.append("%s: before/after snapshots name different ledgers" % name)

        before_state = _raw_ledger_state(path)
        after_state = _raw_ledger_state(path)

        # (iii) sealed pre-leg prefix is an exact prefix of the final bytes.
        #       THE BASELINE IS THE SEALED BYTES, NOT A LIVE RE-READ.  The live
        #       ledger is snapshotted twice above only to establish presence and to
        #       compare against the snapshot's own claimed numbers; the DELTA
        #       baseline must be the bytes sealed before the release, otherwise the
        #       "before" silently becomes whatever the file looked like when the
        #       checker happened to run.
        seal = (before.get("sealed_ledger_prefix") or {}).get(name) or {}
        seal_after = (after.get("sealed_ledger_prefix") or {}).get(name) or {}
        sealed_path = arm_dir / Path(seal.get("sealed_path", "")).name \
            if seal.get("sealed_path") else None
        sealed_bytes = (sealed_path.read_bytes()
                        if (sealed_path is not None and sealed_path.exists()) else None)
        seal_consistent = (
            sealed_bytes is not None
            and len(sealed_bytes) == int(seal.get("sealed_bytes", -1))
            and hashlib.sha256(sealed_bytes).hexdigest() == seal.get("sealed_sha256")
            and seal.get("sealed_sha256") == seal_after.get("sealed_sha256"))
        if not seal_consistent:
            raw_ok = False
            raw_notes.append(
                "%s: sealed pre-leg prefix is missing, or its bytes/declared "
                "sha256 disagree between the before and after snapshots" % name)

        # The sealed prefix's own record count is the authoritative pre-leg count.
        sealed_state = _raw_sealed_state(sealed_bytes)
        # The snapshot's before-count must equal what the SEALED bytes decode to.
        if sealed_state["exists"] and \
                int(recorded.get("records", -1)) != sealed_state["records"]:
            raw_ok = False
            raw_notes.append(
                "%s: before-snapshot claims %s records but the sealed pre-leg "
                "prefix bytes decode to %s"
                % (name, recorded.get("records"), sealed_state["records"]))

        # (ii) the before-snapshot against the SEALED bytes it claims to describe.
        #      The live file has grown by audit time, so the snapshot is compared
        #      to the sealed prefix; that is the only comparison in which the
        #      snapshot's byte count is expected to be stable.
        snap_match = (
            int(recorded.get("bytes", -1)) == sealed_state["bytes"]
            and int(recorded.get("records", -1)) == sealed_state["records"]
            and int(recorded.get("unparsable", -1)) == sealed_state["unparsable"])
        if not snap_match:
            raw_ok = False
            raw_notes.append(
                "%s: before-snapshot disagrees with the sealed pre-leg prefix "
                "(snapshot bytes=%s records=%s unparsable=%s; sealed bytes=%s "
                "records=%s unparsable=%s)"
                % (name, recorded.get("bytes"), recorded.get("records"),
                   recorded.get("unparsable"), sealed_state["bytes"],
                   sealed_state["records"], sealed_state["unparsable"]))

        prefix = _prefix_state(sealed_state, after_state, sealed_bytes,
                              final_path=path)
        if not prefix.get("prefix_verified"):
            raw_ok = False
            raw_notes.append("%s: %s" % (name, prefix.get("prefix_reason")))

        raw_rows[name] = {
            "ledger": path.name,
            "before_snapshot_matches_raw": snap_match,
            "seal_consistent": seal_consistent,
            "raw_before": {"bytes": sealed_state["bytes"],
                           "sha256": sealed_state["sha256"],
                           "records": sealed_state["records"]},
            "raw_after": {"bytes": after_state["bytes"],
                          "sha256": after_state["sha256"],
                          "records": after_state["records"]},
            "live_before_state": {"records": before_state["records"]},
            "prefix": prefix,
        }

    # ── THE FALSIFIER ARM'S CONTRACT-BEARING DELTA, FROM F1'S OWN BYTES ───────
    # On the falsifier arm the FINAL ledger also contains the supplemental F1b
    # traverse, so grading F1 on it would compare 2/1/1 + a full traverse against
    # the frozen 2/1/1 and report a failure that is an artefact of running the
    # supplemental falsifier.  F1's own before/after states were sealed as bytes
    # (d1-prefix-<name>.jsonl and d1-f1-final-<name>.jsonl), and its delta is
    # derived from THOSE bytes here -- never from the harness's `f1_delta` number.
    f1_rows, f1_ok, f1_notes = {}, True, []
    f1_authority = ((after.get("f1_byte_authority") or {})
                    if isinstance(after, dict) else {})
    if expected_after is not None:
        for name in EXPECTED_COUNTS:
            base_seal = (f1_authority.get("pre_leg_seal") or {}).get(name) or {}
            f1_seal = (f1_authority.get("post_f1_seal") or {}).get(name) or {}
            base_path = arm_dir / Path(base_seal.get("sealed_path", "")).name \
                if base_seal.get("sealed_path") else None
            f1_path = arm_dir / Path(f1_seal.get("sealed_path", "")).name \
                if f1_seal.get("sealed_path") else None
            base_bytes = (base_path.read_bytes()
                          if (base_path is not None and base_path.exists()) else None)
            f1_bytes = (f1_path.read_bytes()
                        if (f1_path is not None and f1_path.exists()) else None)
            if base_bytes is None or f1_bytes is None:
                f1_ok = False
                f1_notes.append("%s: F1 byte seals absent or unreadable" % name)
                f1_rows[name] = {"present": False}
                continue
            # Re-prove the prefix relation rather than trusting the write-time flag.
            exact_prefix = f1_bytes[:len(base_bytes)] == base_bytes
            base_state = _raw_sealed_state(base_bytes)
            f1_state = _raw_sealed_state(f1_bytes)
            if not exact_prefix:
                f1_ok = False
                f1_notes.append("%s: F1 baseline bytes are not a prefix of F1's "
                                "post state" % name)
            if f1_state["records"] < base_state["records"]:
                f1_ok = False
                f1_notes.append("%s: F1 post state has FEWER records than baseline"
                                % name)
            f1_rows[name] = {
                "present": True,
                "exact_prefix": exact_prefix,
                "baseline_records": base_state["records"],
                "baseline_sha256": base_state["sha256"],
                "post_f1_records": f1_state["records"],
                "post_f1_sha256": f1_state["sha256"],
                "delta": f1_state["records"] - base_state["records"],
            }
        f1_delta_from_bytes = {
            n: (f1_rows.get(n) or {}).get("delta") for n in EXPECTED_COUNTS}
        expected_f1 = (dict(expected_delta) if expected_delta is not None
                       else {n: 0 for n in EXPECTED_COUNTS})
        f1_shape_ok = (f1_delta_from_bytes == expected_f1) and f1_ok
        out["f1_delta_from_bytes"] = f1_delta_from_bytes
        out["f1_expected_delta"] = expected_f1
        out["f1_shape_from_bytes_ok"] = f1_shape_ok
        out["f1_authority"] = {
            "rows": f1_rows,
            "notes": f1_notes,
            "delta_derived_from_bytes": f1_delta_from_bytes,
            "expected_frozen_f1_delta": expected_f1,
            "matches": f1_shape_ok,
            "note": ("F1 is graded on ITS OWN sealed bytes; the supplemental F1b "
                     "traverse runs afterwards and must not be folded into the "
                     "contract-bearing delta."),
        }
        # Whether the supplemental full traverse actually completed, reported
        # separately and never used in the conjunct.
        supp = (after.get("falsifier_injection") or {}).get("supplemental_falsifier") \
            or (before.get("falsifier_injection") or {}).get("supplemental_falsifier")
        out["supplemental_f1b"] = {
            "present": bool(supp),
            "is_full_traverse": bool((supp or {}).get("is_full_traverse")),
            "delta": (supp or {}).get("delta_from_F1_baseline"),
            "contract_bearing": False,
        }

    out.update({
        "before_counts": before_counts,
        "after_counts": after_counts,
        "delta": delta,
        "boundary_populated_before": populated_before,
        "delta_zero": all(v == 0 for v in delta.values()),
        "after_matches_expected":
            after_counts == (expected_after or EXPECTED_COUNTS),
        "raw_ledger_authority": {
            "raw_ledgers_authoritative": raw_ok,
            "rows": raw_rows,
            "notes": raw_notes,
            "join": ("recorded path resolves into this arm dir; the sealed "
                     "pre-leg prefix bytes decode to the before-snapshot's record "
                     "count; the sealed bytes are an exact prefix of the final "
                     "ledger bytes"),
        },
        # The counts DERIVED FROM RAW BYTES.  `before_counts`/`after_counts` above
        # carry the snapshots' numbers; these are what the ledger bytes actually
        # decode to.  When the two disagree the raw bytes win and the conjunct is
        # false -- a snapshot is a claim about a file, not the file.
        "before_counts_from_bytes": {
            n: (raw_rows.get(n, {}).get("raw_before") or {}).get("records")
            for n in EXPECTED_COUNTS},
        "after_counts_from_bytes": {
            n: (raw_rows.get(n, {}).get("raw_after") or {}).get("records")
            for n in EXPECTED_COUNTS},
        "fail_closed": False,
    })
    before_from_bytes = out["before_counts_from_bytes"]
    after_from_bytes = out["after_counts_from_bytes"]
    out["delta_from_bytes"] = {
        n: ((after_from_bytes[n] or 0) - (before_from_bytes[n] or 0))
        for n in EXPECTED_COUNTS}
    out["snapshots_agree_with_bytes"] = (
        before_from_bytes == before_counts and after_from_bytes == after_counts)
    # The delta the ARM must exhibit.  The five measurement arms must show a ZERO
    # delta; the falsifier arm must show the FROZEN F1 shape.  Requiring zero for
    # all arms would make D3-X's conjunct true only if the injection had failed.
    out["expected_delta"] = (
        dict(expected_delta) if expected_delta is not None
        else {n: 0 for n in EXPECTED_COUNTS})
    out["delta_from_bytes_matches_expected"] = (
        out["delta_from_bytes"] == out["expected_delta"])
    # For the falsifier arm the CONTRACT-BEARING measurement is F1's own delta,
    # derived from F1's own sealed bytes -- NOT the final-ledger delta, which also
    # contains the supplemental F1b full traverse.  The final-ledger numbers are
    # still reported (they are what the appended ledgers actually say), but they do
    # not decide the conjunct on this arm.
    if expected_after is not None:
        out["conjunct_value"] = bool(out.get("f1_shape_from_bytes_ok"))
    else:
        out["conjunct_value"] = (
            out["delta_from_bytes_matches_expected"]
            and populated_before
            and out["after_matches_expected"]
            and raw_ok
            and out["snapshots_agree_with_bytes"])
    return out


def recompute_capability_bindings(arm_dir: Path, precommit: dict,
                                  sealed_recompute: dict,
                                  measurement: dict) -> dict:
    """Reconcile the capability bindings the conjunct's NAME asserts.

    ALL_CAPABILITY_BINDINGS_RECONCILED previously read
    `equality["measurement_valid"]`, whose only two inputs are
    `descriptors.measured` and `seccomp.target_verified` -- the exact pair that
    LEG_DESCRIPTOR_SET_MEASURED reads.  The two conjuncts were therefore
    algebraically identical: one carrier, two names, so the second asserted
    nothing the first had not already asserted.  A name that claims a join across
    bindings must actually perform that join.

    Three joins are performed here, from raw artifacts only:

      (a) installed/measured policy identity
              rebuilt-from-source filter bytes == filter bytes on disk
              == filter sha256 the precommit froze
      (b) sealed response identity == each leg's point-of-use identity
      (c) pre-leg authority manifests == the identities actually graded

    Overlap with other conjuncts is permitted -- the gate said so explicitly.  What
    is not permitted is being the same carrier, and (a)/(b)/(c) are each read from
    evidence no other conjunct reads.
    """
    pid = measurement.get("policy_identity") or {}
    pre_policy = precommit.get("policy") or {}
    on_disk_policy = _load_json(arm_dir / "d3-denial-policy.json") \
        if (arm_dir / "d3-denial-policy.json").exists() else {}
    pid = dict(pid or {})
    # Prefer the on-disk paths: the receipt's path fields are harness claims, and a
    # binding proved against a path the harness named is a weaker claim than one
    # proved against the artifact sitting in the arm directory.
    if (arm_dir / "d3-denial-filter.bin").exists():
        pid["filter_bytes_path"] = str(arm_dir / "d3-denial-filter.bin")
    if (arm_dir / "d3-denial-policy.json").exists():
        pid["policy_bytes_path"] = str(arm_dir / "d3-denial-policy.json")
    if not pid.get("filter_bytes_sha256_on_disk"):
        fb = arm_dir / "d3-denial-filter.bin"
        pid["filter_bytes_sha256_on_disk"] = sha256_of(fb) if fb.exists() else ""
    # The precommit's frozen filter hash is the anchor.  Fall back to the on-disk
    # policy spec's own self-declared hash only as a LAST resort, and record which
    # anchor was used so a fallback is visible rather than silently equivalent.
    anchor = pre_policy.get("filter_sha256", "")
    anchor_source = "precommit"
    if not anchor:
        anchor = on_disk_policy.get("filter_sha256", "")
        anchor_source = "on_disk_policy_spec_fallback"

    # ---- (a) policy identity, PROVED by rebuilding the filter from source ----
    rebuild = {}
    try:
        rebuild = policy.rebuild_and_compare(
            Path(pid.get("policy_bytes_path", "")),
            Path(pid.get("filter_bytes_path", "")))
    except (OSError, AttributeError, TypeError) as exc:
        rebuild = {"rebuild_error": "%s: %s" % (type(exc).__name__, exc)}
    policy_join = {
        "anchor_source": anchor_source,
        "precommit_filter_sha256": anchor,
        "disk_filter_sha256": pid.get("filter_bytes_sha256_on_disk", ""),
        "rebuilt_filter_sha256": rebuild.get("rebuilt_filter_sha256", ""),
        "filter_rebuilt_matches_disk":
            bool(rebuild.get("filter_image_rebuilt_matches_disk")),
        "policy_rebuilt_matches_disk":
            bool(rebuild.get("policy_spec_rebuilt_matches_disk")),
        "precommit_frozen_matches_rebuilt": bool(
            anchor and anchor == rebuild.get("rebuilt_filter_sha256")),
    }
    policy_join["reconciled"] = bool(
        policy_join["filter_rebuilt_matches_disk"]
        and policy_join["policy_rebuilt_matches_disk"]
        and policy_join["precommit_frozen_matches_rebuilt"])

    # ---- (b) sealed response identity == each leg's point-of-use identity ----
    sealed_doc = _load_json(arm_dir / "sealed-response-identity.json") \
        if (arm_dir / "sealed-response-identity.json").exists() else {}
    captured = sealed_doc.get("captured_response_sha256", "")
    leg_uses, leg_mismatch = [], []
    for leg in (sealed_recompute.get("legs") or []):
        identity = leg.get("leg")
        observed = leg.get("point_of_use_sha256", "")
        ok = bool(captured and observed and observed == captured)
        (leg_uses if ok else leg_mismatch).append(identity or "<unnamed>")
    sealed_join = {
        "captured_response_sha256": captured,
        "legs_bound": sorted(x for x in leg_uses if x),
        "legs_unbound_or_mismatched": sorted(x for x in leg_mismatch if x),
    }
    sealed_join["reconciled"] = bool(captured and leg_uses and not leg_mismatch)

    # ---- (c) pre-leg authority manifests == the identities actually graded ---
    before_doc = _load_json(arm_dir / "cell-manifest-before.json") \
        if (arm_dir / "cell-manifest-before.json").exists() else {}
    after_doc = _load_json(arm_dir / "cell-manifest-after.json") \
        if (arm_dir / "cell-manifest-after.json").exists() else {}
    before_man = (before_doc or {}).get("manifest") or {}
    after_man = (after_doc or {}).get("manifest") or {}
    # The recorded join is: the post-leg manifest names the pre-leg manifest it
    # was compared against, and that recorded hash is the pre-leg file's real hash.
    recorded_link = (after_doc or {}).get("cell_manifest_before_sha256", "")
    before_path = arm_dir / "cell-manifest-before.json"
    actual_link = sha256_of(before_path) if before_path.exists() else ""
    precommit_leg_sha = (precommit.get("leg_binary_sha256") or "")
    precommit_allow = ((precommit.get("descriptor_allowlist") or {})
                       .get("allowlist_sha256") or "")
    # The identity ACTUALLY GRADED is the leg binary's bytes, so the checker
    # re-hashes the binary itself.  Neither measurement.json nor the receipt carries
    # a leg-binary hash -- only the precommit declares one -- so looking for the
    # "graded" identity in those artifacts yielded None, the equality was
    # None == None, and the term silently evaluated false on every run.  A join has
    # to compare a DECLARED hash to a MEASURED one, not to another declaration.
    leg_binary_path = Path(precommit.get("leg_binary") or "")
    graded_leg_sha, leg_binary_measure_error = "", ""
    if str(leg_binary_path) and leg_binary_path.exists():
        try:
            graded_leg_sha = sha256_of(leg_binary_path)
        except OSError as exc:
            leg_binary_measure_error = "%s: %s" % (type(exc).__name__, exc)
    else:
        leg_binary_measure_error = "leg binary not readable at %s" % leg_binary_path
    manifest_join = {
        "pre_manifest_present": bool(before_man),
        "post_manifest_present": bool(after_man),
        "recorded_forward_link": recorded_link,
        "actual_pre_manifest_sha256": actual_link,
        "forward_link_valid": bool(recorded_link and recorded_link == actual_link),
        "precommit_leg_sha256": precommit_leg_sha,
        "precommit_allowlist_sha256": precommit_allow,
        "leg_binary_path": str(leg_binary_path),
        "graded_leg_sha256": graded_leg_sha,
        "leg_binary_measure_error": leg_binary_measure_error,
        # Fail-closed: an unmeasurable binary cannot reconcile, because "we could
        # not read it" must not read the same as "it matched".
        "leg_identity_reconciled": bool(
            precommit_leg_sha and graded_leg_sha
            and precommit_leg_sha == graded_leg_sha),
    }
    manifest_join["reconciled"] = bool(
        manifest_join["pre_manifest_present"]
        and manifest_join["post_manifest_present"]
        and manifest_join["forward_link_valid"]
        and manifest_join["precommit_allowlist_sha256"]
        # AND THE ACTUAL IDENTITY JOIN.  `leg_identity_reconciled` was computed
        # above and then NOT included in this conjunction, so a substituted leg
        # binary could set leg_identity_reconciled = false while
        # pre_leg_authority_manifest_binding.reconciled stayed true -- and
        # ALL_CAPABILITY_BINDINGS_RECONCILED with it.  The join the conjunct's name
        # asserts ("precommit authority == the identity actually graded") was
        # therefore evaluated and then discarded.  Computing a term and forgetting
        # to AND it into the verdict is exactly the shape of defect that survived
        # four rounds of reading the carrier, so it belongs in the conjunction
        # rather than beside it.
        and manifest_join["leg_identity_reconciled"])

    joins = {
        "policy_identity_binding": policy_join,
        "sealed_response_binding": sealed_join,
        "pre_leg_authority_manifest_binding": manifest_join,
    }
    return {
        "joins": joins,
        "all_bindings_reconciled": bool(
            policy_join["reconciled"]
            and sealed_join["reconciled"]
            and manifest_join["reconciled"]),
        "derived_from": ("filter rebuilt from source vs on-disk bytes vs precommit "
                         "freeze; sealed identity vs per-leg point-of-use; pre-leg "
                         "authority manifest vs graded identities"),
    }


def recompute_cell_counts(arm_dir: Path) -> dict:
    """Recompute the cell counts from BOTH sealed manifests and from the cell
    binaries' own identities, independently.

    A CELL IS AN ENTITY -- a declared cell identity plus the binary that runs it --
    and NOT the artifacts it produces.  An earlier form of this function counted
    files named 'model-cell*' / 'order-cell*' in the arm directory.  That was wrong
    in the decisive way: the cell's report and marker files are OUTPUTS, so before
    the leg is released they do not exist.  Measured on the clean arm D3-A, the
    pre-release manifest read 0 and the post-completion manifest read 2, so
    TOTAL_MODEL_CELL_COUNT_UNCHANGED went FALSE on the arm whose whole job is to be
    clean -- "the cell had not yet written its report" reported as "the cell count
    changed".  The counting object is therefore the cell's declared identity and its
    binary bytes, hashed at the pre-leg point and again after the legs complete.

    This function previously returned `order_cell_count_measured = 0` as a LITERAL
    and decided the model cell from a single file-existence test.  That made
    ORDER_CELL_COUNT_UNCHANGED true by construction and made
    TOTAL_MODEL_CELL_COUNT_UNCHANGED a claim about existence rather than about being
    UNCHANGED.  Both conjuncts are now decided by comparing two independently-read,
    sealed, pre-leg and post-leg measurements.
    """
    report_path = arm_dir / "model-cell.report.json"
    report = _load_json(report_path) if report_path.exists() else {}

    def _manifest(name: str) -> dict:
        path = arm_dir / name
        doc = _load_json(path) if path.exists() else {}
        manifest = (doc or {}).get("manifest") or {}
        return {
            "path": str(path),
            "present": bool(doc),
            "sha256": sha256_of(path) if path.exists() else "",
            "phase": (doc or {}).get("phase", ""),
            "model_count": manifest.get("model_cell_count"),
            "order_count": manifest.get("order_cell_count"),
            "model_identity_digest": manifest.get("model_cell_identity_digest", ""),
            "order_identity_digest": manifest.get("order_cell_identity_digest", ""),
            "model_entries": manifest.get("model_cell_entries") or [],
            "order_entries": manifest.get("order_cell_entries") or [],
            "undeclared": manifest.get("undeclared_cell_artifacts") or [],
            "counted_by": manifest.get("counted_by", ""),
        }

    before = _manifest("cell-manifest-before.json")
    after = _manifest("cell-manifest-after.json")

    def _ident(entries: list) -> list:
        return sorted((e.get("st_dev"), e.get("st_ino"), e.get("sha256"))
                      for e in entries)

    # ── Independent re-measurement, done HERE from the binaries themselves ────
    # The manifests claim a binary hash; the checker re-hashes the binary on disk
    # so the claim is checked against the bytes rather than believed.  BUILD_DIR is
    # resolved the same way the harness resolves it, so the two are measuring the
    # same artifacts.
    build_dir = Path(os.environ.get("D3_BUILD_DIR", "/tmp/d3gen/build"))
    enum = {}
    for kind, binary_name in (("model", "d3-model-cell"), ("order", "d3-order-cell")):
        binary = build_dir / binary_name
        if binary.exists():
            st = binary.stat()
            enum[kind] = {"present": True, "st_dev": st.st_dev, "st_ino": st.st_ino,
                          "size": st.st_size, "sha256": sha256_of(binary)}
        else:
            enum[kind] = {"present": False}

    manifests_usable = bool(before["present"] and after["present"])
    model_count_unchanged = bool(
        manifests_usable
        and before["model_count"] is not None
        and before["model_count"] == after["model_count"] == 1)
    order_count_unchanged = bool(
        manifests_usable
        and before["order_count"] is not None
        and before["order_count"] == after["order_count"] == 0)
    model_identity_same = bool(
        manifests_usable and _ident(before["model_entries"]) == _ident(after["model_entries"])
        and bool(before["model_entries"]))
    # ORDER_CELL_COUNT is 0, so the order entry list is LEGITIMATELY empty.  An
    # empty-identity comparison is therefore `[] == []`, which is True and is the
    # right answer -- unlike the model cell, there is no single order cell whose
    # identity could be substituted.  An order cell APPEARING would show up as a
    # non-empty entry list or as an undeclared artifact, and both are caught.
    order_identity_same = bool(
        manifests_usable
        and _ident(before["order_entries"]) == _ident(after["order_entries"]))

    # The manifests must agree with the BINARIES the checker hashed itself.
    binary_agrees = bool(
        manifests_usable
        and (before["model_entries"] or [{}])[0].get("sha256")
        == enum["model"].get("sha256")
        and (after["model_entries"] or [{}])[0].get("sha256")
        == enum["model"].get("sha256"))

    # An undeclared cell appearing during the run must not be invisible: the counts
    # above are of DECLARED cells, so undeclared artifacts are a separate violation.
    undeclared = list(before["undeclared"]) + list(after["undeclared"])
    counts_agree = bool(manifests_usable and binary_agrees and not undeclared)

    return {
        # --- measured values, PRE and POST, kept separate -------------------
        "model_cell_count_before": before["model_count"],
        "model_cell_count_after": after["model_count"],
        "order_cell_count_before": before["order_count"],
        "order_cell_count_after": after["order_count"],
        "model_cell_binary_remeasured": enum["model"],
        "order_cell_binary_remeasured": enum["order"],
        "undeclared_cell_artifacts": undeclared,
        "manifests_present": manifests_usable,
        "before_manifest_sha256": before["sha256"],
        "after_manifest_sha256": after["sha256"],
        # --- verdicts ------------------------------------------------------
        "model_cell_count_unchanged": model_count_unchanged,
        "order_cell_count_unchanged": order_count_unchanged,
        "model_cell_identity_same": model_identity_same,
        "order_cell_identity_same": order_identity_same,
        "cell_binary_rehash_agrees": binary_agrees,
        "counts_agree_with_enumeration": counts_agree,
        # Fail-closed: an arm without both sealed manifests, or with a cell binary
        # that does not re-hash to what the manifest claims, or with an undeclared
        # cell artifact, cannot satisfy the cell conjuncts -- exactly as a missing
        # receipt cannot.
        "cell_measurement_valid": bool(manifests_usable and counts_agree),
        # --- retained for continuity ---------------------------------------
        # `*_measured` are the fields the receipt publishes and the main loop
        # cross-checks.  They are DERIVED from the before/after measurements rather
        # than re-read from the manifest, so a renamed manifest key cannot make the
        # checker compare the harness's number against None -- which reads as a
        # disagreement on every arm while the actual measurement was fine.
        "model_cell_count_measured": before["model_count"],
        "order_cell_count_measured": before["order_count"],
        "model_cell_report_present": bool(report),
        "model_cell_report_sha256": sha256_of(report_path) if report_path.exists() else "",
        "reported_cells_run": (report or {}).get("cells_run"),
        "reported_provider_calls": (report or {}).get("provider_calls"),
        "counted_by": ("independent reparse of executed cell report; cell BINARY "
                       "re-hashed by the checker; BOTH sealed pre/post-leg "
                       "manifests; undeclared cell artifacts enumerated "
                       "separately; never an inferred zero"),
    }


def recompute_sealed_join(arm_dir: Path) -> dict:
    """Recompute the D2 identity join from RAW artifacts only.

    The join key is `captured_response_sha256 == point_of_use_sha256`.  Both ends
    are read from disk here: the sealed identity document and the leg's own
    receipt.  The harness's join verdict is not read at all -- a checker that
    echoed it would agree by construction.
    """
    _idp = arm_dir / "sealed-response-identity.json"
    identity = _load_json(_idp) if _idp.exists() else {}
    captured = identity.get("captured_response_sha256", "")
    handoff = Path(identity.get("handoff_path", ""))

    # Independent recomputation of the sealed bytes: hash the base64 audit copy
    # ourselves rather than trusting the recorded digest.
    recomputed = ""
    if handoff.exists():
        try:
            raw = base64.b64decode(handoff.read_text(encoding="utf-8"))
            recomputed = hashlib.sha256(raw).hexdigest()
        except (ValueError, OSError):
            recomputed = ""

    legs, mismatched, missing = [], [], []
    for receipt in sorted((arm_dir / "receipts").glob("*.receipt.json")):
        doc = _load_json(receipt) if receipt.exists() else {}
        if not doc:
            continue
        sh = doc.get("point_of_use_sha256", "")
        row = {
            "leg": doc.get("leg", receipt.stem.split(".")[0]),
            "point_of_use_sha256": sh,
            "bytes_consumed": doc.get("bytes_consumed"),
            "matches_captured_response": bool(sh) and sh == captured,
            "provider_calls": doc.get("provider_calls"),
        }
        legs.append(row)
        if not row["matches_captured_response"]:
            mismatched.append(row["leg"])

    leg_count = len(legs)
    # The identity set is D2's, and the checker requires ALL of it.  Globbing
    # "however many receipts exist" reproduces the vacuity the harness was just
    # fixed for: over a single receipt, "all legs share one captured response" is
    # satisfied by one element and has no content.  The checker must be at least
    # as strict as the claim it audits, so the expected identities come from the
    # sealed identity document (written before the legs ran) and a MISSING leg is
    # reported, not merely absent from the average.
    expected_identities = list(identity.get("leg_identities") or [])
    observed_identities = [row["leg"] for row in legs]
    absent = [name for name in expected_identities
              if name not in observed_identities]
    all_three_present = (bool(expected_identities)
                         and not absent
                         and len(legs) == len(expected_identities))
    return {
        "captured_response_sha256": captured,
        "handoff_sha256_recomputed_by_checker": recomputed,
        "handoff_hash_matches_recorded": bool(recomputed) and recomputed == captured,
        "handoff_present": handoff.exists(),
        "legs": legs,
        "leg_count": leg_count,
        "expected_leg_identities": expected_identities,
        "legs_absent": absent,
        "all_expected_legs_present": all_three_present,
        "legs_missing_receipt": missing,
        "legs_with_mismatched_point_of_use": mismatched,
        "legs_consumed_sealed_response": all_three_present,
        "point_of_use_hash_valid":
            all_three_present and not mismatched,
        # "All legs bound to the SAME captured response" is a distinct property
        # from "no leg mismatched": a run could carry two different sealed
        # identities (one substituted per leg) where each leg matches *its own*
        # capture.  Derive it from the set of distinct hashes actually observed
        # across the legs, never by re-reading a harness boolean -- and only over
        # the FULL expected set, or the property is vacuous.
        "same_captured_response_bound_to_all_legs":
            all_three_present
            and len({row["point_of_use_sha256"] for row in legs
                     if row["point_of_use_sha256"]}) == 1
            and all(row["matches_captured_response"] for row in legs),
        "join_key": "captured_response_sha256 == point_of_use_sha256",
        "derivation": "independent reparse of sealed identity + raw leg receipts",
    }


# The escalation order, transcribed from the frozen predicate's REASON_ESCALATION.
# Transcribed rather than imported ON PURPOSE: importing it would make the
# derivation follow whatever the predicate currently says, which is the same class
# of dependence as reading the harness's reason.  The two are cross-checked below,
# so the transcription cannot silently drift from the frozen contract -- a
# divergence is reported as a defect instead of being absorbed.
_ESCALATION = (
    predicate.PROVIDER_CAPABILITY_INHERITED,
    predicate.PROVIDER_BROKER_REACHABLE,
    predicate.PROVIDER_CAPABILITY_ATTEMPT,
)


def derive_failure_code_independently(equality: dict, precommit: dict,
                                      measurements: list,
                                      denied_syscalls: list,
                                      policy_module,
                                      contract_module=None,
                                      intent_values: list | None = None) -> dict:
    """Derive ONE reason code from raw signals, without reading the harness verdict.

    The gate's required structure is:

        raw evidence -> independent conjuncts / possession-attempt signals
                     -> INDEPENDENTLY DERIVED reason
                     -> compare to the harness failure_code

    Previously the checker read `claim.get("failure_code")` out of the receipt and
    compared it against a frozen expectation.  That is a comparison of the
    harness's answer against a table -- it cannot catch a harness whose reason
    derivation is wrong, only one that is INCONSISTENT with its own table.  For
    D3-C/D3-D the `PROVIDER_CAPABILITY_ATTEMPT` finding was therefore
    harness-trusted even though the checker can see the denied syscalls directly.

    Signal sources, all raw artifacts and no harness summary:
      * possession      <- the checker's own descriptor equality recomputation
                           (measured fds vs the precommit-declared allowlist)
      * broker          <- the precommit's declared endpoint identities as
                           OBSERVED present in the per-leg measured descriptor set
      * attempt         <- the denied syscall SET the checker itself parsed out of
                           the raw strace text, intersected with the frozen
                           capability syscall sets
      * structural      <- a required measurement that was never taken

    KNOWN RESIDUAL LIMITATION, stated rather than papered over: `broker_channel`
    and `inherited_provider_socket` are LABELS, and no measurement can distinguish
    "this AF_UNIX stream is a broker" from "this AF_UNIX stream is a provider
    socket" -- D3-B and D3-E both hold one.  The endpoint TYPE is therefore not
    independently derivable from the raw artifacts, and this derivation classifies
    by the same declared identity the harness does.  What IS independent here is
    that the derivation is driven by the checker's own descriptor measurement and
    its own strace parse.
    """
    # Ordering self-check: if the frozen predicate's escalation order ever changes,
    # this derivation would be running the old contract.  Report it, never absorb it.
    contract_module = contract_module or predicate
    escalation_matches = (tuple(getattr(contract_module, "REASON_ESCALATION",
                                        ())) == _ESCALATION)

    declared = set(precommit.get("declared_expected_identities") or [])
    allow = precommit.get("descriptor_allowlist") or {}
    declared |= set(allow.get("declared_expected_identities") or [])
    declared |= set(allow.get("allowed_identities") or [])

    # A measured non-stdio descriptor's identity is a POSITION ("AF_UNIX:inode=N");
    # the semantic word `inherited_provider_socket` / `broker_channel` is a
    # DECLARATION about what that position is bound to.  These are different kinds
    # of token and an earlier form of this derivation conflated them -- it looked
    # for the declaration word inside the measured identity set, found nothing, and
    # would have reported "no broker" for an arm holding one.
    non_stdio_seen = sorted({str(d.get("identity")) for m in (measurements or [])
                             for d in ((m.get("descriptors") or {}).get("descriptors")
                                       or []) if d.get("fd") not in STDIO_FDS})

    # (1) Possession of a provider-capable descriptor.
    #     Two independent signals: the checker's own set-equality recomputation
    #     (a measured fd the precommit never declared) AND the declared endpoint
    #     class being `inherited_provider_socket` while a non-stdio fd is present.
    undeclared = list(equality.get("undeclared_but_measured") or [])
    declares_provider = "inherited_provider_socket" in declared
    declares_broker = "broker_channel" in declared
    legs_with_provider = ([{"endpoints": non_stdio_seen}]
                          if (non_stdio_seen and declares_provider) else [])
    # `undeclared_but_measured` is NON-EMPTY FOR BOTH D3-B AND D3-E -- both hold a
    # non-stdio AF_UNIX fd the precommit's allowlist never permitted, and the two
    # identity strings differ only in inode.  So "an undeclared non-stdio fd
    # exists" cannot by itself decide which code applies; the DECLARED ENDPOINT
    # CLASS does, exactly as the frozen contract intends: a broker is a translator,
    # not a provider, so a broker fd does not falsify
    # NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED.  The branches below are therefore
    # driven by the declared class, with `undeclared` carried as binding evidence.
    possession_offense = bool(non_stdio_seen and declares_provider)
    broker_offense = bool(non_stdio_seen and declares_broker)
    possession = {
        "undeclared_but_measured": undeclared,
        "non_stdio_descriptor_identities": non_stdio_seen,
        "declared_provider_class": declares_provider,
        "legs_with_provider_descriptor": legs_with_provider,
    }

    # (2) Reachability of a broker endpoint that would translate leg bytes.
    #     Broker and provider sockets are BOTH non-stdio AF_UNIX fds; the class word
    #     in the precommit is what separates them, and the frozen contract says a
    #     broker descriptor does NOT falsify NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED
    #     because a broker is a translator, not a provider.  The two must therefore
    #     be tested as mutually exclusive branches.  An earlier form of this
    #     derivation let the broker case fall into the provider branch and reported
    #     PROVIDER_CAPABILITY_INHERITED for D3-E.
    legs_with_broker = ([{"endpoints": non_stdio_seen}]
                        if (non_stdio_seen and declares_broker) else [])
    broker = {
        "non_stdio_descriptor_identities": non_stdio_seen,
        "declared_broker_class": declares_broker,
        "legs_with_broker_endpoint": legs_with_broker,
    }

    # (3) An attempted use the kernel denied.
    #
    #     Both halves are required, and the reason is that NEITHER signal alone
    #     distinguishes the arms.  Every arm -- including clean arms D3-A and D3-X
    #     -- runs the same probe battery to demonstrate the filter is live, so the
    #     raw denial set is IDENTICAL across all six arms (`socket`, `socketpair`,
    #     `clone`, `execve`).  A derivation that read denials alone would report
    #     PROVIDER_CAPABILITY_ATTEMPT for the clean arms, which is exactly what a
    #     first draft of this function did.  The discriminating signal is the
    #     leg's own declared intent, emitted by the LEG BINARY itself
    #     (a12d3_d3_legs.c: `d3_note("ATTEMPT_INTENT", ... intent=...)`), not by
    #     the harness.  So: intent names the reach, and the kernel trace proves the
    #     reach was refused.  A declared intent with NO corresponding denial is not
    #     an ATTEMPT finding -- it is a defect, and is reported as such.
    denied = set(denied_syscalls or [])
    attempt_sets = {
        "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY":
            sorted(denied & set(policy_module.NETWORK_CREATION_SYSCALLS)),
        "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY":
            sorted(denied & set(policy_module.PROCESS_CREATION_SYSCALLS)),
        "EXEC_DENIED_AFTER_LEG_ENTRY":
            sorted(denied & set(policy_module.EXEC_SYSCALLS)),
    }
    attempt_denials = sorted({s for group in attempt_sets.values() for s in group})
    intents = sorted({str(v) for v in (intent_values or [])})
    reach_intent = "reach_provider_cognition" in intents

    if inheritance_measurement_absent(equality):
        return {
            "checker_derived_failure_code": predicate.NO_FAILURE,
            "checker_derived_failure_kind": "STRUCTURAL_DEFECT",
            "checker_derived_bound_signals": {
                "reason": "MEASUREMENT_INVALID: descriptor set or seccomp target "
                          "was never measured, so possession cannot be ruled out"},
            "escalation_order_matches_frozen_predicate": escalation_matches,
        }

    if possession_offense:
        return {
            "checker_derived_failure_code": predicate.PROVIDER_CAPABILITY_INHERITED,
            "checker_derived_failure_kind": "POSSESSION",
            "checker_derived_bound_signals": possession,
            "escalation_order_matches_frozen_predicate": escalation_matches,
        }
    if broker_offense:
        return {
            "checker_derived_failure_code": predicate.PROVIDER_BROKER_REACHABLE,
            "checker_derived_failure_kind": "POSSESSION_INDIRECT",
            "checker_derived_bound_signals": broker,
            "escalation_order_matches_frozen_predicate": escalation_matches,
        }
    if reach_intent and attempt_denials:
        return {
            "checker_derived_failure_code": predicate.PROVIDER_CAPABILITY_ATTEMPT,
            "checker_derived_failure_kind": "ATTEMPTED_USE_DENIED",
            "checker_derived_bound_signals": {
                "declared_intents": intents,
                "denied_syscalls": attempt_denials,
                "by_conjunct": attempt_sets,
            },
            "escalation_order_matches_frozen_predicate": escalation_matches,
        }
    if reach_intent and not attempt_denials:
        # Half the evidence is present and half is missing.  The leg declared it
        # reached for provider cognition, but the kernel trace shows no denial of
        # any capability syscall -- so either the reach succeeded (far worse than a
        # denial) or the trace did not capture it.  Neither is a clean arm, and
        # neither may be silently downgraded to NONE.
        return {
            "checker_derived_failure_code": predicate.NO_FAILURE,
            "checker_derived_failure_kind": "STRUCTURAL_DEFECT",
            "checker_derived_bound_signals": {
                "declared_intents": intents,
                "denied_syscalls": [],
                "reason": "INTENT_WITHOUT_DENIAL: leg declared "
                          "reach_provider_cognition but the raw trace shows no "
                          "denied capability syscall; the attempted use is "
                          "unproven, not absent"},
            "escalation_order_matches_frozen_predicate": escalation_matches,
        }
    return {
        "checker_derived_failure_code": predicate.NO_FAILURE,
        "checker_derived_failure_kind": "CLEAN",
        "checker_derived_bound_signals": {
            "declared_intents": intents,
            "possession": possession, "broker": broker,
            "attempt_denials": []},
        "escalation_order_matches_frozen_predicate": escalation_matches,
    }


def inheritance_measurement_absent(equality: dict) -> bool:
    """True when the descriptor/seccomp measurement was never validly taken.

    Fail-closed: an unmeasured descriptor set must not be read as "measured
    nothing wrong", so possession cannot be ruled out and no clean code may be
    derived from it.
    """
    return not bool(equality.get("measurement_valid"))


def check_arm(arm: str, claim: dict | None) -> dict:
    arm_dir = WORK_ROOT / ("arm-%s" % arm)
    measurement = _load_json(arm_dir / "measurement.json")
    # The precommit is a SEPARATE, earlier artifact.  Reading it from its own
    # file (rather than from a copy embedded in the measurement) is what makes
    # "the allowlist was precommitted" checkable: an embedded copy would be
    # written after the fact and could not distinguish a precommit from a
    # post-hoc description of whatever was measured.
    precommit = _load_json(arm_dir / "precommit.json")
    markers = read_leg_markers(arm_dir / "markers.txt")

    traces = sorted(arm_dir.glob("trace*"))
    trace_files = [p for p in traces if p.is_file()]

    denied_syscalls, denied_records = read_denied_syscalls(trace_files)
    kills = read_kill_events(trace_files)

    equality = recompute_descriptor_equality(
        measurement, phase="ENTRY_BARRIER_REACHED")

    seccomp = measurement.get("seccomp") or {}
    activation = (str(seccomp.get("seccomp_raw")) == SECCOMP_MODE_FILTER
                  and bool(seccomp.get("seccomp_filter_count")))

    leg_errnos = sorted({
        value for value in (_as_int(m.get("errno")) for m in markers
                            if str(m.get("marker", "")).startswith("ATTEMPT_")
                            and m.get("marker") != "ATTEMPT_INTENT")
        if value})

    completed = any(m.get("marker") == "LEG_COMPLETED" for m in markers)

    # D1 ledgers.  Recomputed from the raw records.
    ledgers = {
        "gate_attempts": count_ledger_records(arm_dir / "gate-attempts.jsonl"),
        "gate_dispatches": count_ledger_records(arm_dir / "gate-dispatches.jsonl"),
        "mock_receives": count_ledger_records(arm_dir / "mock-receives.jsonl"),
    }

    # ---- Independent recomputation of the three former vacuous conjuncts ----
    # These are recomputed from RAW ARTIFACTS HERE, not read from the harness
    # report: a checker that merely echoed the harness's own booleans would agree
    # by construction and could never detect the original fail-open.
    # The falsifier arm is graded against the FROZEN F1 shape, not against the
    # baseline.  Its whole purpose is to MOVE the delta, so requiring a zero delta
    # of it would make its conjunct true only when the injection had failed.
    is_falsifier_arm = arm in FALSIFIER_ARMS
    delta_recompute = recompute_provider_delta(
        arm_dir, completed,
        expected_after=(F1_FALSIFIER_EXPECTED_AFTER if is_falsifier_arm else None),
        expected_delta=(F1_FALSIFIER_EXPECTED_DELTA if is_falsifier_arm else None))
    cell_recompute = recompute_cell_counts(arm_dir)
    sealed_recompute = recompute_sealed_join(arm_dir)
    bindings_recompute = recompute_capability_bindings(
        arm_dir, precommit, sealed_recompute, measurement)

    # The per-leg descriptor measurements come from the sealed on-disk artifact,
    # NOT from receipt["arms"][arm]["leg_measurements"].  Reading the harness's
    # summary of what it measured would reintroduce the same trust the independent
    # derivation exists to remove.
    leg_measurements_disk = (_load_json(arm_dir / "leg-measurements.json")
                             or {}).get("legs") or []
    if not leg_measurements_disk:
        leg_measurements_disk = (_load_json(arm_dir / "leg-measurements.json")
                                 or {}).get("measurements") or []
    reason_recompute = derive_failure_code_independently(
        equality, precommit, leg_measurements_disk, denied_syscalls, policy,
        contract_module=predicate,
        intent_values=[m.get("intent") for m in markers
                       if m.get("marker") == "ATTEMPT_INTENT"])
    broker_identities = equality["measured_non_stdio_identities"]
    declared_identities = set(precommit.get("declared_expected_identities") or [])

    # The two "not inherited" conjuncts ask DIFFERENT questions and must not be
    # collapsed into one another -- doing so was a defect in an earlier revision
    # of this checker.
    #
    #   * PROVIDER_CAPABLE_DESCRIPTOR asks: does the leg hold a descriptor whose
    #     endpoint could itself serve provider cognition?  A BROKER endpoint is
    #     by construction a translator -- the peer converts the leg's bytes into
    #     whatever it likes, so the leg's descriptor is not itself a provider
    #     capability.  A broker descriptor therefore does NOT falsify this.
    #   * BROKER_ENDPOINT asks the orthogonal question: does a broker channel
    #     exist at all?  For the broker arm it does, so this is False and the arm
    #     fails -- per the frozen rule that EXISTENCE of the channel is the
    #     violation, even if it is never exercised.
    #
    # Both are keyed on the DECLARED endpoint kind (from the precommit), because
    # the measured identity alone cannot tell a broker socket from a provider
    # socket: both are AF_UNIX streams.
    broker_declared = "broker_channel" in declared_identities
    provider_declared = "inherited_provider_socket" in declared_identities

    conjuncts = {
        "LEG_ENTRY_IDENTITIES_PRECOMMITTED":
            bool(precommit.get("leg_binary_sha256")),
        "LEG_DESCRIPTOR_ALLOWLIST_PRECOMMITTED":
            bool((precommit.get("descriptor_allowlist") or {})
                 .get("allowlist_sha256")),
        "LEG_DESCRIPTOR_SET_MEASURED":
            bool((measurement.get("descriptors") or {}).get("measured"))
            and bool(seccomp.get("target_verified")),
        "NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED":
            bool(equality["no_provider_capable_descriptor_inherited"])
            or (broker_declared and bool(broker_identities)
                and not provider_declared),
        # The broker conjunct mirrors the provider-socket one: an arm declared as
        # holding a broker channel AND observed holding a non-stdio descriptor
        # falsifies it.  Recomputed from the declaration plus the measurement.
        # An arm declared as holding a broker channel AND observed holding a
        # non-stdio descriptor falsifies this conjunct.  The declaration comes
        # from the precommit; the observation from the measurement.  Both are
        # required: a declaration alone could be a precommit typo that condemns a
        # clean arm, and an observation alone cannot tell a broker from a
        # provider socket -- they are both AF_UNIX streams.
        "NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED":
            not ("broker_channel" in
                 (precommit.get("declared_expected_identities") or [])
                 and broker_identities),
        "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY":
            any(s in denied_syscalls for s in policy.NETWORK_CREATION_SYSCALLS),
        "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY":
            any(s in denied_syscalls for s in policy.PROCESS_CREATION_SYSCALLS),
        "EXEC_DENIED_AFTER_LEG_ENTRY":
            any(s in denied_syscalls for s in policy.EXEC_SYSCALLS),
        "KERNEL_DENIAL_POLICY_PRECOMMITTED":
            bool((precommit.get("policy") or {}).get("filter_sha256")),
        "KERNEL_DENIAL_POLICY_ACTIVE_AT_POINT_OF_USE":
            activation and not kills,
        "HONEST_COUNTERFACTUAL_LEGS_COMPLETE":
            completed and bool(sealed_recompute["legs_consumed_sealed_response"])
            and bool(sealed_recompute["point_of_use_hash_valid"])
            and bool(sealed_recompute["handoff_hash_matches_recorded"]),
        # Recomputed from the raw before/after snapshots, NOT read from the
        # harness verdict.  Requires a POPULATED boundary (1/1/1) and
        # after == before.  Fail-closed when a completed arm has no snapshots.
        "D1_PROVIDER_OPPORTUNITY_DELTA_ZERO":
            bool(delta_recompute["conjunct_value"]),
        # Decided by comparing two independently-read sealed enumerations, not by
        # one existence test and not by an inferred zero.  Fail-closed when either
        # manifest is absent.
        "TOTAL_MODEL_CELL_COUNT_UNCHANGED":
            bool(cell_recompute["cell_measurement_valid"])
            and bool(cell_recompute["model_cell_count_unchanged"])
            and bool(cell_recompute["model_cell_identity_same"]),
        "ORDER_CELL_COUNT_UNCHANGED":
            bool(cell_recompute["cell_measurement_valid"])
            and bool(cell_recompute["order_cell_count_unchanged"])
            and bool(cell_recompute["order_cell_identity_same"]),
        "ALL_CAPABILITY_BINDINGS_RECONCILED":
            bool(bindings_recompute["all_bindings_reconciled"]),
    }

    timeline = recompute_timeline(markers, measurement)
    evaluated = predicate.evaluate_predicate(conjuncts)

    recomputed = {
        "arm": arm,
        "conjuncts": conjuncts,
        "predicate_value": bool(evaluated["value"]),
        "falsified_conjuncts": evaluated["falsified_conjuncts"],
        "denied_syscalls": denied_syscalls,
        "denied_records": denied_records,
        "kill_events": kills,
        "leg_denial_errnos": leg_errnos,
        "ledgers": ledgers,
        "leg_completed": completed,
        "activation_evidenced_by_kernel": activation,
        "seccomp_raw": seccomp.get("seccomp_raw"),
        "seccomp_filter_count": seccomp.get("seccomp_filter_count"),
        "target_verified": bool(seccomp.get("target_verified")),
        "equality": equality,
        "timeline": timeline,
        # The repaired derivations, published in full so the receipt shows WHAT
        # the checker recomputed rather than only that it agreed.
        "provider_delta_recomputed": delta_recompute,
        "cell_counts_recomputed": cell_recompute,
        "sealed_join_recomputed": sealed_recompute,
        "capability_bindings_recomputed": bindings_recompute,
        "reason_recomputed": reason_recompute,
        "checker_derived_failure_code":
            reason_recompute["checker_derived_failure_code"],
        "checker_derived_failure_kind":
            reason_recompute["checker_derived_failure_kind"],
    }

    # ── Agreement with the harness ─────────────────────────────────────────
    disagreements: list[str] = []
    if claim is None:
        disagreements.append("harness produced no result for this arm")
    else:
        claim_conjuncts = claim.get("conjuncts") or {}
        for name in predicate.CONJUNCTS:
            if bool(claim_conjuncts.get(name)) != bool(conjuncts.get(name)):
                disagreements.append(
                    "conjunct %s: harness=%s checker=%s"
                    % (name, claim_conjuncts.get(name), conjuncts.get(name)))
        if bool(claim.get("holds")) != bool(evaluated["value"]):
            disagreements.append(
                "predicate value: harness=%s checker=%s"
                % (claim.get("holds"), evaluated["value"]))
        # The harness publishes its verdict TWICE: as `holds` and inside
        # `predicate.value`.  Reconciling only the first leaves the second free
        # to carry a different answer, so a receipt could read holds=true with
        # predicate.value=false (or the reverse) and the checker would still
        # report agreement.  Both carriers must equal the recomputation, and
        # they must equal EACH OTHER.
        published_predicate = (claim.get("predicate") or {}).get("value")
        if published_predicate is not None and \
                bool(published_predicate) != bool(evaluated["value"]):
            disagreements.append(
                "published predicate.value: harness=%s checker=%s"
                % (published_predicate, evaluated["value"]))
        if published_predicate is not None and \
                bool(published_predicate) != bool(claim.get("holds")):
            disagreements.append(
                "harness self-inconsistent: holds=%s predicate.value=%s"
                % (claim.get("holds"), published_predicate))
        # The published conjunct ORDER is part of the frozen predicate text: a
        # reordered list is a different predicate even when every conjunct name
        # is present, so compare the sequence, not the set.
        published_order = (claim.get("predicate") or {}).get("conjunct_order")
        if published_order is not None and \
                list(published_order) != list(predicate.CONJUNCTS):
            disagreements.append(
                "conjunct order: harness=%s frozen=%s"
                % (list(published_order), list(predicate.CONJUNCTS)))
        if sorted(claim.get("denied_syscalls") or []) != denied_syscalls:
            disagreements.append(
                "denied syscalls: harness=%s checker=%s"
                % (sorted(claim.get("denied_syscalls") or []), denied_syscalls))
        if sorted(claim.get("leg_denial_errnos") or []) != leg_errnos:
            disagreements.append(
                "leg denial errnos: harness=%s checker=%s"
                % (claim.get("leg_denial_errnos"), leg_errnos))

        # ── Reconcile the PUBLISHED MEASUREMENTS, not only the booleans ───────
        # Comparing conjunct values alone is not enough.  A harness could publish
        # a conjunct that is true while publishing a *measurement* that
        # contradicts it -- for example a cell count of 2 alongside
        # TOTAL_MODEL_CELL_COUNT_UNCHANGED=true, or a delta of {1,1,0} alongside
        # D1_PROVIDER_OPPORTUNITY_DELTA_ZERO=true.  Each of these is exactly the
        # kind of corruption this checker exists to catch, and each was passing
        # silently because only the derived booleans were ever compared.
        claimed_cells = (claim.get("cell_artifacts") or {})
        for label, claimed, recomputed_value in (
                ("model cell count",
                 claimed_cells.get("model_cell_count_measured"),
                 cell_recompute.get("model_cell_count_measured")),
                ("order cell count",
                 claimed_cells.get("order_cell_count_measured"),
                 cell_recompute.get("order_cell_count_measured"))):
            if claimed != recomputed_value:
                disagreements.append(
                    "%s: harness=%s checker=%s"
                    % (label, claimed, recomputed_value))

        claimed_delta = (claim.get("provider_delta") or {})
        if claimed_delta.get("conjunct_value") is not None and \
                bool(claimed_delta.get("conjunct_value")) != \
                bool(delta_recompute.get("conjunct_value")):
            disagreements.append(
                "provider delta conjunct: harness=%s checker=%s"
                % (claimed_delta.get("conjunct_value"),
                   delta_recompute.get("conjunct_value")))
        for side in ("before", "after"):
            claimed_side = claimed_delta.get(side)
            recomputed_side = delta_recompute.get(side)
            if claimed_side is not None and recomputed_side is not None:
                ch = {k: (v.get("records") if isinstance(v, dict) else v)
                      for k, v in claimed_side.items()}
                rh = {k: (v.get("records") if isinstance(v, dict) else v)
                      for k, v in recomputed_side.items()}
                if ch != rh:
                    disagreements.append(
                        "provider %s counts: harness=%s checker=%s"
                        % (side, ch, rh))

        claimed_join = (claim.get("sealed_join") or {})
        for field in ("legs_consumed_sealed_response", "point_of_use_hash_valid",
                      "same_captured_response_bound_to_all_legs"):
            if claimed_join.get(field) is not None and \
                    bool(claimed_join.get(field)) != \
                    bool(sealed_recompute.get(field)):
                disagreements.append(
                    "sealed join %s: harness=%s checker=%s"
                    % (field, claimed_join.get(field),
                       sealed_recompute.get(field)))

        # The INDEPENDENT REASON, compared against the harness's reason and against
        # the frozen expectation.  Reading `claim["failure_code"]` and comparing it
        # to a table was the earlier form; it could not catch a harness whose
        # derivation was wrong, only one that was inconsistent with its own table.
        harness_code = claim.get("failure_code")
        derived_code = reason_recompute["checker_derived_failure_code"]
        if harness_code != derived_code:
            disagreements.append(
                "failure reason: harness=%s checker_derived=%s (bound_signals=%s)"
                % (harness_code, derived_code,
                   reason_recompute.get("checker_derived_bound_signals")))
        if not reason_recompute.get("escalation_order_matches_frozen_predicate"):
            disagreements.append(
                "reason escalation order differs from the frozen predicate's "
                "REASON_ESCALATION: this derivation is running a different "
                "contract than the frozen one")
    recomputed["disagreements"] = disagreements
    recomputed["agrees_with_harness"] = not disagreements
    return recomputed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("checker: %s" % CHECKER_VERSION)
    receipt_path = WORK_ROOT / "receipt.json"
    if not receipt_path.exists():
        print("MISSING receipt: %s" % receipt_path)
        return 2
    receipt = json.loads(receipt_path.read_text())

    # (1) The predicate text must be the frozen one.  Recomputed against the
    #     spec module: if the two ever diverge, the checker is validating a
    #     different predicate than the one that was frozen.
    frozen = predicate.COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED_TEXT
    receipt_text = receipt.get("predicate_text")
    predicate_text_matches = (receipt_text == frozen)
    print("predicate_text_matches_frozen: %s" % predicate_text_matches)
    if not predicate_text_matches:
        print("  receipt predicate text differs from the frozen spec")

    # The F1 falsifier arm set is TRANSCRIBED above rather than imported from the
    # harness (importing it would import the thing under audit), so the
    # transcription is checked against what the receipt actually recorded.  If the
    # harness injected into a different arm than the one graded against the F1
    # shape, that must surface as a defect rather than as a differently graded arm.
    # D3-X is NOT under receipt["arms"]: it is not one of the five measurement arms
    # and the harness reports it under receipt["delta_falsifier"].  Searching only
    # `arms` found no injection and reported a mismatch against the checker's own
    # grade, which is a wiring artefact rather than an apparatus finding.
    _bodies = dict(receipt.get("arms") or {})
    if isinstance(receipt.get("delta_falsifier"), dict):
        _bodies["delta_falsifier"] = receipt["delta_falsifier"]
    injected_arms = sorted(
        arm for arm, body in _bodies.items()
        if isinstance(body, dict)
        and (body.get("falsifier_injection")
             or (body.get("injection") or {})).get("attempted"))
    if injected_arms == ["delta_falsifier"]:
        injected_arms = [str(receipt["delta_falsifier"].get("arm") or "")]
    injected_arms = sorted(a for a in injected_arms if a)
    falsifier_arm_set_matches = (tuple(injected_arms) == tuple(sorted(FALSIFIER_ARMS)))
    print("falsifier_arms_from_receipt: %s (checker grades %s) match=%s"
          % (injected_arms, list(FALSIFIER_ARMS), falsifier_arm_set_matches))

    failures: list[str] = []
    if not falsifier_arm_set_matches:
        failures.append(
            "falsifier arm set mismatch: receipt shows injection into %s but the "
            "checker grades %s against the frozen F1 shape"
            % (injected_arms, list(FALSIFIER_ARMS)))
    results = {}
    for arm in predicate.ARM_ORDER:
        try:
            results[arm] = check_arm(arm, receipt["arms"].get(arm))
        except FileNotFoundError as exc:
            print("arm %s: MISSING ARTIFACT %s" % (arm, exc))
            return 2

    for arm in predicate.ARM_ORDER:
        result = results[arm]
        expected_ok, expected_code = predicate.ARM_EXPECTATION.get(
            arm, (True, predicate.NO_FAILURE))
        timeline = result["timeline"]
        claim = receipt["arms"].get(arm) or {}

        # THREE values must agree, and the verdict is decided by the CHECKER's own
        # derivation rather than by the harness's field:
        #
        #   checker_derived_failure_code  <- raw artifacts only (this checker)
        #   harness failure_code          <- what the receipt claims
        #   expected_code                 <- the frozen expectation for this arm
        #
        # Previously `code` was `claim.get("failure_code")`, so the verdict compared
        # the harness's answer to a table.  A harness that derived the WRONG reason
        # consistently would have passed.  Requiring all three to agree, and making
        # the derived value the one the verdict is decided from, is what turns the
        # comparison into an independent check.
        derived_code = result["checker_derived_failure_code"]
        harness_code = claim.get("failure_code")
        code = derived_code

        # The semantic verdict: an arm that possessed, reached, or attempted
        # fails -- regardless of whether the attempt was denied.
        semantic_ok = result["predicate_value"] and code == predicate.NO_FAILURE
        verdict_ok = (semantic_ok == expected_ok and code == expected_code)

        print("arm %s: predicate=%s derived=%s harness=%s expected=(%s,%s) "
              "verdict_ok=%s agrees=%s timeline_ok=%s forbidden=%s"
              % (arm, result["predicate_value"], derived_code, harness_code,
                 expected_ok, expected_code, verdict_ok,
                 result["agrees_with_harness"], timeline["order_respected"],
                 timeline["forbidden_sequence_observed"]))

        if harness_code != derived_code:
            failures.append(
                "%s reason disagreement: checker_derived=%s harness=%s"
                % (arm, derived_code, harness_code))
        if not result["agrees_with_harness"]:
            failures.append("%s disagrees with harness: %s"
                            % (arm, result["disagreements"]))
        if not verdict_ok:
            failures.append("%s verdict_ok=False (got %s/%s want %s/%s)"
                            % (arm, semantic_ok, code, expected_ok, expected_code))
        if not timeline["order_respected"]:
            failures.append("%s timeline out of order: missing=%s inversions=%s"
                            % (arm, timeline["missing_steps"],
                               timeline["order_inversions"]))
        if timeline["forbidden_sequence_observed"]:
            failures.append("%s observed the FORBIDDEN sequence: %s"
                            % (arm, timeline["observed_order"]))
        # NONE means "no failure was bound" -- it is the ABSENCE of a failure
        # code, not a member of the failure vocabulary.  Every other code must
        # be one of the three frozen terms: any fourth code would be an
        # undocumented verdict the contract does not define.
        if code != predicate.NO_FAILURE and code not in predicate.FAILURE_VOCABULARY:
            failures.append("%s used a code outside the frozen vocabulary: %s"
                            % (arm, code))
        if result["kill_events"]:
            failures.append("%s produced SIGSYS/kill evidence, which is a policy "
                            "defect and cannot serve as a denial: %s"
                            % (arm, result["kill_events"]))
        if result["leg_denial_errnos"] and not all(
                e == 13 for e in result["leg_denial_errnos"]):
            failures.append("%s denial errnos %s are not EACCES(13)"
                            % (arm, result["leg_denial_errnos"]))

    # (5) The falsifier requirement, recomputed: D3-B and D3-E must fail while
    #     D1 still reports zero provider delta.
    #
    #     `zero_delta` is NOT "the ledgers are empty".  That was the vacuous
    #     reading: once the cell makes its one authorized opportunity through the
    #     REAL D2 gate+mock boundary, the ledgers are correctly populated 1/1/1
    #     in every arm, so an emptiness test would report False forever and this
    #     falsifier could never fire -- it would be a check that can only ever
    #     fail.  The conjunct is the MEASURED delta: the counts after the legs
    #     must equal the counts before them.  The checker recomputes it from the
    #     raw snapshots on disk, never from the harness's own boolean.
    falsifier_report = {}
    for arm in predicate.FALSIFIER_ARMS_REQUIRE_ZERO_PROVIDER_DELTA:
        claim = receipt["arms"].get(arm) or {}
        delta_recomputed = recompute_provider_delta(
            WORK_ROOT / ("arm-%s" % arm), arm_completed=bool(claim))
        zero_delta = bool(delta_recomputed.get("conjunct_value"))
        semantic_ok = (results[arm]["predicate_value"]
                       and claim.get("failure_code") == predicate.NO_FAILURE)
        falsifier_report[arm] = {
            "zero_provider_delta": zero_delta,
            "delta_recomputed_by_checker": delta_recomputed,
            "semantic_ok": semantic_ok,
            "falsifies": zero_delta and not semantic_ok,
            "code": claim.get("failure_code"),
        }
        print("falsifier %s: zero_delta=%s semantic_ok=%s falsifies=%s code=%s"
              % (arm, zero_delta, semantic_ok,
                 falsifier_report[arm]["falsifies"], claim.get("failure_code")))
        if not falsifier_report[arm]["falsifies"]:
            failures.append(
                "%s does not falsify: it must fail while D1 reports zero "
                "provider delta (zero_delta=%s semantic_ok=%s)"
                % (arm, zero_delta, semantic_ok))

    # ---------------------------------------------------------------------
    # (4b) THE CONTRACT-BEARING FALSIFIER, INDEPENDENTLY RECOMPUTED
    #
    # F1 is what makes D1_PROVIDER_OPPORTUNITY_DELTA_ZERO a measurement rather than
    # a constant, so it is not enough for the harness to report that its own
    # injection moved the delta.  The checker recomputes F1's delta from F1's own
    # sealed bytes and requires it to equal the frozen shape.
    #
    # The final ledgers on this arm ALSO contain the supplemental F1b full traverse,
    # so grading on them would compare the sum of both injections against the frozen
    # 2/1/1 and fail for a reason that is an artefact of the extra diagnostic.
    # Hence: F1 from F1's own bytes, F1b reported separately and never graded.
    f1_check: dict = {}
    falsifier_dir = WORK_ROOT / ("arm-%s" % FALSIFIER_ARMS[0])
    if falsifier_dir.exists():
        f1_delta = recompute_provider_delta(
            falsifier_dir, arm_completed=True,
            expected_after=dict(F1_FALSIFIER_EXPECTED_AFTER),
            expected_delta=dict(F1_FALSIFIER_EXPECTED_DELTA))
        f1_authority = f1_delta.get("f1_authority") or {}
        f1b = f1_delta.get("supplemental_f1b") or {}
        f1_from_bytes = f1_authority.get("delta_derived_from_bytes") or {}
        f1_check = {
            "arm": FALSIFIER_ARMS[0],
            "f1_delta_derived_from_sealed_bytes": f1_from_bytes,
            "f1_delta_expected_frozen": dict(F1_FALSIFIER_EXPECTED_DELTA),
            "f1_matches_frozen_shape": bool(f1_authority.get("matches")),
            "f1_authority_rows": f1_authority.get("rows"),
            "f1_authority_notes": f1_authority.get("notes"),
            "conjunct_true_on_frozen_shape":
                f1_delta.get("conjunct_value") is True,
            # Final-ledger numbers, published for the record but NOT graded.
            "final_ledger_delta_includes_supplemental":
                f1_delta.get("delta_from_bytes"),
            "supplemental_f1b": {
                "present": f1b.get("present"),
                "is_full_traverse": f1b.get("is_full_traverse"),
                "delta": f1b.get("delta"),
                "contract_bearing": False,
            },
            "proves_delta_is_live_measurement": bool(
                f1_authority.get("matches")
                and any(v for v in f1_from_bytes.values())
                and f1_delta.get("conjunct_value") is True),
        }
        print("falsifier %s (F1): delta_from_sealed_bytes=%s expected=%s "
              "matches=%s conjunct=%s"
              % (f1_check["arm"], f1_from_bytes,
                 f1_check["f1_delta_expected_frozen"],
                 f1_check["f1_matches_frozen_shape"],
                 f1_check["conjunct_true_on_frozen_shape"]))
        if not f1_check["f1_matches_frozen_shape"]:
            failures.append(
                "%s does not exhibit the FROZEN F1 delta: derived_from_bytes=%s "
                "expected=%s notes=%s"
                % (f1_check["arm"], f1_from_bytes,
                   f1_check["f1_delta_expected_frozen"],
                   f1_check["f1_authority_notes"]))
        if not f1_check["conjunct_true_on_frozen_shape"]:
            failures.append(
                "%s: D1_PROVIDER_OPPORTUNITY_DELTA_ZERO is not TRUE on the frozen "
                "F1 shape, so the conjunct is not grading the injected delta"
                % f1_check["arm"])
    else:
        f1_check = {"arm": FALSIFIER_ARMS[0], "present": False}
        failures.append(
            "falsifier arm %s is absent, so the contract-bearing F1 falsifier was "
            "never independently audited" % FALSIFIER_ARMS[0])

    audit = {
        "checker_version": CHECKER_VERSION,
        "predicate_text_matches_frozen": predicate_text_matches,
        "predicate_name": predicate.PREDICATE_NAME,
        "conjunct_count": len(predicate.CONJUNCTS),
        "arms": results,
        "falsifier_report": falsifier_report,
        "contract_bearing_falsifier_F1": f1_check,
        "failure_vocabulary": list(predicate.FAILURE_VOCABULARY),
        "disagreements": failures,
        "checker_agrees_with_harness": not failures,
        "checker_verdict": "AGREES" if not failures else "DISAGREES",
    }
    out = WORK_ROOT / "independent_audit.json"
    out.write_text(json.dumps(audit, indent=2, sort_keys=True))
    print("audit: %s" % out)
    if failures:
        print("DISAGREEMENTS:")
        for item in failures:
            print("  - %s" % item)
        return 1
    print("checker verdict: AGREES with the harness on all %d arms and all %d "
          "conjuncts" % (len(predicate.ARM_ORDER), len(predicate.CONJUNCTS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
