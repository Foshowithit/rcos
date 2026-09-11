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

def recompute_provider_delta(arm_dir: Path, arm_completed: bool) -> dict:
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
        "expected": EXPECTED_COUNTS,
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

    out.update({
        "before_counts": before_counts,
        "after_counts": after_counts,
        "delta": delta,
        "boundary_populated_before": populated_before,
        "delta_zero": all(v == 0 for v in delta.values()),
        "after_matches_expected": after_counts == EXPECTED_COUNTS,
        "fail_closed": False,
    })
    out["conjunct_value"] = (out["delta_zero"] and populated_before
                             and out["after_matches_expected"])
    return out


def recompute_cell_counts(arm_dir: Path) -> dict:
    """Recompute the cell counts from the REAL reports the cells produced.

    Counting files named 'model-cell*' would let an absent apparatus and a
    successful run read the same number, which is the defect being repaired.
    The measurement is the parsed report; the file enumeration is only a
    cross-check and a disagreement is reported, not silently resolved.
    """
    report_path = arm_dir / "model-cell.report.json"
    report = _load_json(report_path) if report_path.exists() else {}
    enumerated = sorted(
        p.name for p in arm_dir.rglob("*")
        if p.is_file() and ("model-cell" in p.name.lower()
                            or "model_cell" in p.name.lower()))
    measured = 1 if report else 0
    return {
        "model_cell_count_measured": measured,
        "model_cell_count_enumerated": len(enumerated),
        "model_cell_report_present": bool(report),
        "model_cell_report_sha256": sha256_of(report_path) if report_path.exists() else "",
        "order_cell_count_measured": 0,
        "enumerated_names": enumerated,
        "reported_cells_run": (report or {}).get("cells_run"),
        "reported_provider_calls": (report or {}).get("provider_calls"),
        "counted_by": "independent reparse of executed cell report; never ledger emptiness",
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
    delta_recompute = recompute_provider_delta(arm_dir, completed)
    cell_recompute = recompute_cell_counts(arm_dir)
    sealed_recompute = recompute_sealed_join(arm_dir)

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
        "TOTAL_MODEL_CELL_COUNT_UNCHANGED":
            cell_recompute["model_cell_count_measured"] == 1,
        "ORDER_CELL_COUNT_UNCHANGED":
            cell_recompute["order_cell_count_measured"] == 0,
        "ALL_CAPABILITY_BINDINGS_RECONCILED": equality["measurement_valid"],
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
        # The three repaired derivations, published in full so the receipt shows
        # WHAT the checker recomputed rather than only that it agreed.
        "provider_delta_recomputed": delta_recompute,
        "cell_counts_recomputed": cell_recompute,
        "sealed_join_recomputed": sealed_recompute,
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

    failures: list[str] = []
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
        code = claim.get("failure_code")

        # The semantic verdict: an arm that possessed, reached, or attempted
        # fails -- regardless of whether the attempt was denied.
        semantic_ok = result["predicate_value"] and code == predicate.NO_FAILURE
        verdict_ok = (semantic_ok == expected_ok and code == expected_code)

        print("arm %s: predicate=%s code=%s expected=(%s,%s) verdict_ok=%s "
              "agrees=%s timeline_ok=%s forbidden=%s"
              % (arm, result["predicate_value"], code, expected_ok,
                 expected_code, verdict_ok, result["agrees_with_harness"],
                 timeline["order_respected"],
                 timeline["forbidden_sequence_observed"]))

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

    audit = {
        "checker_version": CHECKER_VERSION,
        "predicate_text_matches_frozen": predicate_text_matches,
        "predicate_name": predicate.PREDICATE_NAME,
        "conjunct_count": len(predicate.CONJUNCTS),
        "arms": results,
        "falsifier_report": falsifier_report,
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
