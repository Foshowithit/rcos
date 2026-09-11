#!/usr/bin/env python3
"""D3 -- counterfactual provider-capability controls (TEST-ONLY harness).

WHAT THIS ESTABLISHES
---------------------
D1 established that the counterfactual legs created ZERO extra provider
opportunity.  D2 established that known provider artifacts were not STATICALLY
reachable from the leg entrypoints.  Neither of those excludes a leg that
*holds* a usable provider-cognition capability and simply did not happen to
exercise it.  D3 measures the missing boundary:

    the legs did not POSSESS a usable provider-cognition capability, even if
    their code had attempted to exercise one.

The predicate proved is `COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED` (see
a12d3_d3_predicate.py -- the text and conjunct list live there and are not
restated here, so there is exactly one authority for the claim).

AUTHORITY REUSE (deliberate, and required)
------------------------------------------
D1 is the provider-opportunity COUNTING authority and D2 is the captured-response
IDENTITY authority.  This harness REUSES both and invents neither:
  * provider opportunities are read from D1's own ledger files with D1's outcome
    vocabulary (gate-attempts / gate-dispatches / mock-receives), recomputed from
    RAW records rather than trusting any summary;
  * the captured-response identity, its sealing construction, and its descriptor
    handoff semantics are D2's (sealed memfd, F_SEAL_WRITE|GROW|SHRINK|SEAL).
A third counting mechanism would make the two results incomparable, which is why
none exists here.

THE ONE CONSTRAINT THAT SHAPES THE WHOLE DESIGN
-----------------------------------------------
For D3 to be non-vacuous, the "no provider capability" result must be produced by
a leg that COULD have attempted provider cognition.  A leg that is incapable of
trying proves nothing.  So every leg:

  1. starts (externally observed by strace, before anything else),
  2. has the kernel denial policy INSTALLED (seccomp),
  3. reaches the entry barrier and blocks WITHOUT HOLDING ANY DESCRIPTOR,
  4. is measured from OUTSIDE (descriptor set + kernel-reported Seccomp state),
  5. is released only after the measurement is sealed,
  6. and ONLY THEN runs business logic that actively attempts network creation,
     process creation, and exec.

Step 3 holds no descriptor on purpose.  An earlier revision blocked in
open(FIFO, O_RDONLY), which means the leg acquires an fd AFTER the filter is
installed and holds it ACROSS the measurement window -- so the measured set
depends on when the measurement is taken, and the allowlist needs a timing
caveat to explain away a descriptor that is genuinely present.  That caveat is
precisely the seam through which a real capability could hide.  Blocking in
sigsuspend() removes the seam rather than documenting it.

The sequence "measure clean descriptors -> release the leg -> install the
policy" is FORBIDDEN and is published as forbidden: it opens a capability window
in which the leg is released while unfiltered.  a12d3_d3_predicate.py carries
FORBIDDEN_SEQUENCE as data, and the independent checker rejects it.

TEST-ONLY SCOPE
---------------
These stand-in legs are NOT A13.  Nothing here is eligibility-bearing, and no
real provider or model is ever contacted.  The "provider" endpoints are local
AF_UNIX fixtures; the "broker" is a stand-in with no provider credential.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a12d3_d3_descriptor_inspector as inspector      # noqa: E402
import a12d3_d3_predicate as predicate                 # noqa: E402
import a12d3_d3_seccomp_policy as policy               # noqa: E402
import a12d3_d3_provider_boundary as boundary_module   # noqa: E402
import a12d3_d3_sealed_identity as sealed_identity     # noqa: E402

# The D2 cell cardinalities, reused as the authority for C.  D2 declares
# MODEL_CELL_COUNT = 1 and ORDER_CELL_COUNT = 0; D3 counts the real artifacts on
# disk and compares, instead of inferring them from ledger emptiness.
MODEL_CELL_COUNT = 1
ORDER_CELL_COUNT = 0

# The falsifier for the delta conjunct.  D3-X is NOT one of the five
# measurement arms: it proves that D1_PROVIDER_OPPORTUNITY_DELTA_ZERO is a real
# measurement by making a SECOND provider opportunity at the same real D2
# boundary and requiring the conjunct to flip FALSE with the offending record
# published.  If it cannot be made false by a real extra opportunity, it is not
# a measurement.
#
# TWO FALSIFIERS, and the distinction is the gate's ruling, not a preference:
#
#   F1  -- THE FROZEN, CONTRACT-BEARING FALSIFIER.  Baseline 1/1/1; inject a
#          second REAL gate attempt; PREVENT the second dispatch; final 2/1/1;
#          delta {attempts:+1, dispatches:0, receives:0}.  This is the shape the
#          frozen text names, so it is the shape D3-X must produce.  Its purpose
#          is to prove the apparatus detects an extra opportunity AT THE GATE
#          BOUNDARY even when downstream dispatch never occurs.
#
#   F1b -- SUPPLEMENTAL, SEPARATELY NAMED.  The full traverse: the second
#          opportunity IS dispatched, ending 2/2/1.  Strictly stronger evidence,
#          and it is what the apparatus originally produced.  The gate explicitly
#          forbade relabelling that pre-existing 2/2/1 result as F1 after the
#          fact, so it is carried under its own name and is reported as
#          supplemental -- it does NOT bear the contract.
FALSIFIER_INJECTION_ARMS = ("D3-X",)
SUPPLEMENTAL_FALSIFIER_ARMS = ("D3-X",)

# The FROZEN F1 delta, transcribed from the frozen text: "baseline 1/1/1 -> inject
# a second REAL gate request but prevent the second dispatch -> final 2/1/1 ->
# delta {attempts:+1, dispatches:0, receives:0}".  Declared here so the falsifier's
# "did the delta move to exactly the frozen shape" test has an explicit authority
# rather than an inline literal.
F1_FROZEN_DELTA = {"attempts": 1, "dispatches": 0, "receives": 0}
F1_FROZEN_AFTER = {"attempts": 2, "dispatches": 1, "receives": 1}

# Which leg roles consume the sealed response, per arm role.  EVERY arm that
# runs a leg consumes it: HONEST_COUNTERFACTUAL_LEGS_COMPLETE must have content,
# so a leg that never read the response cannot claim honest completion.
#
# These are the legs' OWN role labels -- the string compiled into each leg as
# D3_LEG_ROLE, which is the name it writes its receipt under
# (receipts/<role>.receipt.json).  The short binary suffixes ("c", "d", "b",
# "e") are NOT receipt names: using them here made every arm except D3-A report
# legs_missing_receipt and a zero-length leg set, so the read looked like "the
# leg never consumed the response" when in fact it had consumed it correctly.
# Only "clean" passed, because for that one role the two names coincide.
# ---------------------------------------------------------------------------
# THE THREE D2 LEGS, AND THE ONE INJECTION PER ARM
# ---------------------------------------------------------------------------
# IDENTITY is D2's vocabulary and D3 adds none of it: the same three legs D2
# binds a single captured response to.  Reusing D2's names means the identity
# join below is a statement about the SAME three legs D2 certified, not about a
# D3-specific trio that happens to have the same size.
D2_LEG_IDENTITIES = ("ON", "OFF_NOOP", "ADAPTER_ONLY_PASS_THROUGH")

# Which leg each arm injects its offending capability into.  Every other leg in
# that arm is built with injection NONE and is an honest control.
#
# WHY ONE INJECTION PER ARM IS THE POINT.  An arm with a single leg that fails
# proves the harness can stop a counterfactual executable; it does not show the
# boundary distinguishes a possessed capability from an ordinary leg, because no
# ordinary leg ran in that arm.  With all three legs present -- two honest, one
# offending, all under the same policy hash -- an arm that fails while its honest
# siblings complete is evidence about the BOUNDARY.
#
# The offender lands on ON in the negative arms.  ON is the leg that would
# actually be reaching a provider, so an injected capability there is the
# strongest form of the test; planting it on OFF_NOOP would let a critic argue
# the arm failed on a leg that never intended to do anything.
OFFENDER_LEG = {
    predicate.ARM_A: None,          # clean: no injection at all
    predicate.ARM_B: "ON",          # inherited provider-capable socket, never used
    predicate.ARM_C: "ON",          # direct network attempt, denied by policy
    predicate.ARM_D: "ON",          # process/exec escape attempt, denied by policy
    predicate.ARM_E: "ON",          # broker channel whose peer would translate bytes
    "D3-X": None,                   # delta falsifier reuses the clean leg set
}

# Injection KIND per arm, matching the LEG_ROLES vocabulary the C source uses.
ARM_INJECTION = {
    predicate.ARM_A: "none",
    predicate.ARM_B: "inherited-provider-socket",
    predicate.ARM_C: "direct-network-attempt",
    predicate.ARM_D: "process-exec-escape",
    predicate.ARM_E: "broker-channel",
    "D3-X": "none",
}

# Binary suffix per (identity, injection).  Honest legs are the SAME three
# binaries in every arm -- an arm cannot quietly run a different "honest" leg
# than another arm, because there is only one such binary per identity.
_LEG_BIN = {
    ("ON", "none"): "d3-leg-on",
    ("OFF_NOOP", "none"): "d3-leg-off",
    ("ADAPTER_ONLY_PASS_THROUGH", "none"): "d3-leg-adapt",
    ("ON", "inherited-provider-socket"): "d3-leg-on-prov",
    ("ON", "broker-channel"): "d3-leg-on-brok",
    ("ON", "direct-network-attempt"): "d3-leg-on-net",
    ("ON", "process-exec-escape"): "d3-leg-on-exec",
}


def arm_leg_plan(arm: str) -> list:
    """Return the three (identity, injection, binary) triples this arm runs.

    Order is D2_LEG_IDENTITIES order so the timeline and the join are directly
    comparable across arms -- an arm that ran its legs in a different order would
    make the per-arm timelines non-diffable for no benefit.
    """
    offender = OFFENDER_LEG[arm]
    injection_for_arm = ARM_INJECTION[arm]
    plan = []
    for identity in D2_LEG_IDENTITIES:
        injection = injection_for_arm if identity == offender else "none"
        plan.append((identity, injection, _LEG_BIN[(identity, injection)]))
    return plan


# Retained for the precommit schema and any external reader expecting a
# one-injection summary.  Derived from the table above, never hand-kept.
LEG_ROLES = {
    arm: (OFFENDER_LEG[arm] or "none") for arm in list(predicate.ARM_ORDER) + ["D3-X"]
}
LEG_BINARIES = {
    arm: _LEG_BIN[(OFFENDER_LEG[arm] or "ON", ARM_INJECTION[arm])]
    for arm in list(predicate.ARM_ORDER) + ["D3-X"]
}

HARNESS_VERSION = "D3_COUNTERFACTUAL_PROVIDER_CAPABILITY_CONTROLS_v1.0"
BUILD_DIR = Path(os.environ.get("D3_BUILD_DIR", "/tmp/d3gen/build"))
WORK_ROOT = Path(os.environ.get("D3_WORK_ROOT", "/tmp/d3gen/d3run"))
SYSTEMD_RUN = shutil.which("systemd-run") or "/usr/bin/systemd-run"
STRACE = shutil.which("strace") or "/usr/bin/strace"
# Arm naming, ordering, and expectations are OWNED BY THE PREDICATE MODULE.
# Keeping a second copy here would let the two drift, and a drift would mean the
# harness runs arms the predicate does not know about (or, worse, grades them
# against stale expectations).  So this file derives its arm table from
# a12d3_d3_predicate and adds only the build artifacts the arms need.


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def atomic_write_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(json.dumps(value, indent=2, sort_keys=True,
                               default=str).encode() + b"\n")
    os.replace(tmp, path)


def artifact_record(path: Path) -> dict:
    """SHA-256 / bytes / lines for one artifact, so a receipt can bind it."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"path": str(path), "present": False, "error": str(exc)}
    return {"path": str(path), "present": True, "bytes": len(data),
            "lines": data.count(b"\n"),
            "sha256": hashlib.sha256(data).hexdigest()}


# ---------------------------------------------------------------------------
# The scaffold: one gate fixture (D1/D2 ledger vocabulary), one provider
# endpoint, one broker peer.
# ---------------------------------------------------------------------------

def empty_ledgers(arm_dir: Path) -> dict:
    """D1's ledger files, created EMPTY.

    Reused verbatim in name and vocabulary so D1's counting authority applies
    unchanged: `gate-attempts.jsonl` (an attempt happened), `gate-dispatches`
    (an attempt reached the gate), `mock-receives` (bytes reached the mock).
    D3 does not add a fourth file and does not reinterpret these.
    """
    paths = {"attempts": arm_dir / "gate-attempts.jsonl",
             "dispatches": arm_dir / "gate-dispatches.jsonl",
             "receives": arm_dir / "mock-receives.jsonl"}
    for path in paths.values():
        path.touch(mode=0o600)
    return paths


def count_ledger(path: Path) -> dict:
    """Count RAW records, ignoring anything unparsable rather than guessing."""
    records, unparsable = 0, 0
    for line in Path(path).read_text(encoding="utf-8",
                                     errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            unparsable += 1
            continue
        records += 1
    data = Path(path).read_bytes()
    return {"records": records, "unparsable": unparsable,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def make_provider_endpoint(arm_dir: Path, name: str = "provider-gate.sock"
                           ) -> tuple[socket.socket, str]:
    """A local AF_UNIX listener standing in for a provider-capable endpoint.

    Deliberately NOT a network socket and NOT a real provider: D3 proves that a
    leg cannot reach provider cognition, and using a real endpoint would make the
    test depend on the network it is supposed to be independent of.

    The listener is bound BEFORE the leg exists and owned by the FIXTURE, never
    by the leg.  The leg's only involvement is to hold a connection to it -- and
    that connection must be established before the denial policy is installed,
    because the policy denies socket() and would refuse it afterwards.  That
    ordering is what makes the resulting descriptor an INHERITED capability
    rather than something the leg could have manufactured on demand.

    Binding by PATH (rather than passing an fd) is deliberate.  The launcher
    cannot carry an inherited descriptor across its own exec -- measured twice on
    this host: a systemd-run payload sees only its stdio plus its own
    /proc/self/fd handle.  A path survives that boundary; an fd number does not.
    """
    path = arm_dir / name
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        srv.bind(str(path))
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            srv.close()
            raise
        # A path is already bound.  Two very different situations look identical
        # over the socket API -- both accept a connect() -- so connect() alone
        # cannot tell them apart:
        #   (a) a LIVE harness process holds it.  Hijacking it would silently
        #       substitute a different peer under the same endpoint identity.
        #   (b) an ORPHANED listener whose owner died (a systemd scope outliving
        #       its payload leaves exactly this).  Nothing will ever serve it, so
        #       the leg would connect into a void.
        # Decide from the kernel's socket-inode table: find the listener's inode
        # via /proc/net/unix, then ask whether ANY process still holds that
        # inode.  No holder means orphan, and an orphan is reclaimable.
        holder = _unix_socket_holder(str(path))
        if holder is not None:
            srv.close()
            raise RuntimeError(
                "provider endpoint %s is held by live pid %s; refusing to "
                "substitute a different peer under the same identity"
                % (path, holder))
        path.unlink()
        srv.bind(str(path))
        try:
            (arm_dir / "endpoint-reclaimed.json").write_text(
                json.dumps({"path": str(path),
                            "reason": "orphaned_listener_unlinked",
                            "prior_listener_live": False}))
        except OSError:
            pass
    srv.listen(1)
    return srv, str(path)


def _unix_socket_holder(path: str):
    """Return the pid holding a bound AF_UNIX path, or None if orphaned.

    /proc/net/unix gives the listener's inode; /proc/<pid>/fd then tells us
    whether any process still holds it.  This is the only way to distinguish a
    live listener from a socket the kernel kept bound after its owner died --
    and the difference matters, because one must never be hijacked and the other
    would otherwise wedge every subsequent run.
    """
    try:
        inode = None
        with open("/proc/net/unix", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.split() and line.split()[-1] == path:
                    inode = line.split()[6]
                    break
        if inode is None:
            return None
        target = "socket:[%s]" % inode
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            fd_dir = "/proc/%s/fd" % entry
            try:
                for fd in os.listdir(fd_dir):
                    try:
                        if os.readlink(os.path.join(fd_dir, fd)) == target:
                            return int(entry)
                    except OSError:
                        continue
            except OSError:
                continue
    except OSError:
        # If the probe itself fails we cannot prove the listener is orphaned, so
        # treat it as held (fail closed) rather than reclaiming it.
        return -1
    return None


# ---------------------------------------------------------------------------
# Precommit: every declaration is fixed BEFORE any leg exists
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    """Hash a real byte image.  Used to bind artifacts into receipts."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_precommit(arm_dir: Path, arm: str, role: str, leg_bin: Path,
                    declared: dict, policy_identity: dict,
                    prediction_sha256: str = None) -> dict:
    """Freeze the allowlist and the expectations before launching anything.

    The allowlist is committed here and HASHED, so the arm cannot widen its own
    allowances after seeing the measurement.  Deriving the allowlist from the
    measurement it is meant to check would be circular, and the specific way it
    fails is not hypothetical: D3-E's broker pipe and the entry barrier were both
    FIFOs, so a measurement-derived allowlist permitted the exact channel the arm
    exists to condemn.
    """
    allowlist = inspector.descriptor_allowlist_identity(
        entries=declared.get("entries", []),
        permitted_channel_fds=declared.get("permitted_channel_fds", []))
    precommit = {
        "harness_version": HARNESS_VERSION,
        "arm": arm,
        "role": role,
        "leg_binary": str(leg_bin),
        "leg_binary_sha256": sha256_file(leg_bin),
        "leg_binary_bytes": leg_bin.stat().st_size,
        "policy": {
            "policy_sha256": policy_identity["policy_sha256"],
            "filter_sha256": policy_identity["filter_sha256"],
            "instruction_count": policy_identity["filter_instructions"],
            "denied_syscalls": list(
                policy_identity["policy_spec"]["denied_syscall_names"]),
            "denied_syscall_numbers": list(
                policy_identity["policy_spec"]["denied_syscall_numbers"]),
            "denied_errno": policy_identity["denied_errno"],
            "kill_actions_used": policy_identity["policy_spec"][
                "kill_actions_used"],
            "policy_bytes_sha256_on_disk":
                policy_identity["policy_bytes_sha256_on_disk"],
            "filter_bytes_sha256_on_disk":
                policy_identity["filter_bytes_sha256_on_disk"],
            "spec_bytes_match": policy_identity["spec_bytes_match"],
            "filter_bytes_match": policy_identity["filter_bytes_match"],
        },
        "descriptor_allowlist": allowlist,
        "declared_expected_identities":
            declared.get("expected_identity_names", []),
        "expectation": {
            "predicate_should_hold":
            predicate.ARM_EXPECTATION.get(arm, (True, predicate.NO_FAILURE))[0],
            "expected_failure_code": predicate.ARM_EXPECTATION.get(
                arm, (True, predicate.NO_FAILURE))[1],
        },
        # The frozen prediction is a SEPARATE artifact sealed before launch; this
        # binds its exact bytes.  Rehashing prediction.json must reproduce this.
        "prediction_sha256": prediction_sha256,
        "sequence_required": list(predicate.SEQUENCE_STEPS),
        "sequence_forbidden": list(predicate.FORBIDDEN_SEQUENCE),
        "precommit_wall": time.time(),
    }
    atomic_write_json(arm_dir / "precommit.json", precommit)
    return precommit


# ---------------------------------------------------------------------------
# The arm runner
# ---------------------------------------------------------------------------

def run_arm(arm: str) -> dict:
    """Run one arm end-to-end and return everything a checker needs.

    External observation is REAL strace under a UNIQUE TRANSIENT systemd-run
    cgroup, one per arm, with KillMode=process and the observer held until the
    cgroup is quiescent.  The raw trace is drained and hashed BEFORE parsing, so
    the parse cannot be accused of having edited its own input.
    """
    role = LEG_ROLES[arm]
    leg_bin = BUILD_DIR / LEG_BINARIES[arm]
    leg_plan = arm_leg_plan(arm)
    arm_dir = WORK_ROOT / ("arm-%s" % arm)
    if arm_dir.exists():
        # The clean run is REPLICATION of the same apparatus, not a second chance
        # to overwrite a failed retained result.  Refuse rather than wipe: an
        # unconditional rmtree silently destroys the very evidence a rerun might
        # be tempted to replace.  Setting D3_ALLOW_WIPE=1 is an explicit,
        # auditable act, and retained/clean runs must use distinct D3_WORK_ROOTs.
        if os.environ.get("D3_ALLOW_WIPE") != "1":
            raise SystemExit(
                "REFUSED: arm dir already holds evidence and would be destroyed: %s\n"
                "Retained and clean runs must use distinct D3_WORK_ROOTs. "
                "Set D3_ALLOW_WIPE=1 only if you intend to discard that evidence." % arm_dir)
        shutil.rmtree(arm_dir)
    arm_dir.mkdir(parents=True, exist_ok=True)

    ledgers = empty_ledgers(arm_dir)
    marker = arm_dir / "markers.txt"
    marker.touch(mode=0o600)

    # ---- The REAL provider boundary, reused from D2 -----------------------
    # The cell makes its ONE authorized provider opportunity BEFORE the legs
    # start, through the D2 gate+mock fixtures.  This is what makes the delta
    # conjunct a measurement instead of a vacuous read of empty files: the
    # ledgers are populated by a real attempt/dispatch/receive, so "after ==
    # before" can only be true if the legs induced NO additional opportunity.
    falsifier_arm = arm in FALSIFIER_INJECTION_ARMS
    boundary = boundary_module.ProviderBoundary(
        arm_dir, cell_id="d3-cell-%s" % arm,
        inject_extra_attempt=falsifier_arm)
    boundary.start()
    tries = 0
    while tries < 60 and not all(
            boundary_module.count_ledger_records(
                arm_dir / boundary_module.LEDGER_FILES[n])["records"] > 0
            for n in ("attempts", "dispatches")):
        tries += 1
        time.sleep(0.05)
    opportunity = boundary.cell_opportunity()
    time.sleep(0.3)   # let the gate's writers flush before snapshotting
    before_snapshot = boundary_module.snapshot_counts(arm_dir)

    # ---- SEALED PRE-LEG LEDGER PREFIX --------------------------------------
    # `provider-before.json` is a CLAIM ABOUT the ledgers; it is not the ledgers.
    # Under snapshot-only authority a snapshot can be repointed at a different
    # ledger, or both snapshots synthesised to agree, and D1_PROVIDER_OPPORTUNITY_
    # DELTA_ZERO then reports a clean zero while the real ledgers moved.  So the
    # pre-leg ledger BYTES are sealed to their own artifact here, before the
    # release: the checker then proves those exact bytes are an exact PREFIX of the
    # final ledger, which closes both substitution and retrospective-baseline
    # reconstruction.  Copied as raw bytes, never re-serialised.
    ledger_prefix_seal = {}
    for _name in boundary_module.LEDGER_NAMES:
        _src = arm_dir / boundary_module.LEDGER_FILES[_name]
        _raw = _src.read_bytes() if _src.exists() else b""
        _seal = arm_dir / ("d1-prefix-%s.jsonl" % _name)
        _seal.write_bytes(_raw)
        ledger_prefix_seal[_name] = {
            "sealed_path": _seal.name,
            "sealed_bytes": len(_raw),
            "sealed_sha256": hashlib.sha256(_raw).hexdigest(),
            "shorter_than_a_full_record": len(_raw) < 2,
        }

    boundary_module.atomic_write_json(arm_dir / "provider-before.json", {
        "opportunity": opportunity,
        "counts": {n: before_snapshot[n] for n in boundary_module.LEDGER_NAMES},
        "snapshot_sha256": before_snapshot["_sha256"],
        "wall": before_snapshot["_wall"],
        "falsifier_arm": falsifier_arm,
        "sealed_ledger_prefix": ledger_prefix_seal,
    })

    # ---- PRE-LEG cell identity (sealed before any leg is released) ---------
    # TOTAL_MODEL_CELL_COUNT_UNCHANGED is a claim about UNCHANGED, not about
    # existence, so it needs a pre-leg measurement to be unchanged FROM.  Taken
    # here, before the release below, so the "before" is a genuine boundary state
    # rather than a reconstruction performed after seeing the outcome.
    cell_manifest_before = boundary_module.cell_manifest(
        arm_dir,
        cell_binaries={"model": BUILD_DIR / "d3-model-cell",
                       "order": BUILD_DIR / "d3-order-cell"},
        declared={"model": MODEL_CELL_COUNT, "order": ORDER_CELL_COUNT})
    boundary_module.atomic_write_json(arm_dir / "cell-manifest-before.json", {
        "phase": "PRE_LEG_RELEASE",
        "wall": time.time(),
        "manifest": cell_manifest_before,
        "taken_before_leg_release": True,
    })

    # ---- Bind the D2 sealed-response identity -----------------------------
    # D3 captures NOTHING new: the bytes are the ones the D2 gate+mock boundary
    # actually returned for the cell's authorized opportunity.  D2's capture and
    # seal semantics are reused, and the leg consumes the read-only copy by path,
    # hash-verifying at point of use.
    response_bytes = b""
    decision_path = arm_dir / "response-decision.json"
    if decision_path.exists():
        try:
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            b64 = decision.get("response_b64") or decision.get("response") or ""
            response_bytes = base64.b64decode(b64) if b64 else b""
        except (ValueError, OSError):
            response_bytes = b""
    if not response_bytes:
        # Deterministic fallback derived from the real gate dispatch record, so
        # the identity is still bound to what the boundary produced rather than
        # to a constant invented here.
        dispatch_rows = []
        dpath = arm_dir / boundary_module.LEDGER_FILES["dispatches"]
        if dpath.exists():
            for line in dpath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        dispatch_rows.append(json.loads(line))
                    except ValueError:
                        pass
        response_bytes = json.dumps({
            "kind": "d3_reused_captured_response",
            "dispatch_records": dispatch_rows,
        }, sort_keys=True).encode("utf-8")

    sealed_doc = sealed_identity.bind_sealed_identity(
        arm_dir, response_bytes, "d3-cell-%s" % arm,
        leg_identities=D2_LEG_IDENTITIES)
    sealed_identity.atomic_write_json(
        arm_dir / "sealed-response-identity.json", sealed_doc)
    receipt_dir = arm_dir / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)

    # The policy is emitted and hashed before anything runs.
    policy_identity = policy.write_policy_artifacts(arm_dir)

    # ---- Declarations (precommit) ----
    # The clean arms inherit NOTHING beyond stdio, and that emptiness is
    # DECLARED, not assumed.
    declared = {"entries": [], "permitted_channel_fds": [],
                "expected_identity_names": []}
    provider_fd = None
    broker_fd = None
    conn = None
    srv = None

    provider_path = None
    broker_path = None
    broker_proc = None
    if arm == predicate.ARM_B:
        # An already-connected provider-capable socket, inherited by design.
        # The D2 gate fixture ALREADY owns this endpoint -- ProviderBoundary
        # binds provider-gate.sock when it starts, because that is the endpoint
        # the cell's one authorized opportunity goes through.  So the leg connects
        # to THAT listener; binding a second one on the same path would fail
        # EADDRINUSE (it did) and, worse, would mean this arm's inherited
        # capability pointed at a different peer than the one the ledger counts.
        # Reuse by identity: the path IS the D2 endpoint identity.
        provider_path = boundary.paths["gate_socket"]
        if not Path(provider_path).exists():
            raise RuntimeError(
                "D3-B requires the D2 gate endpoint %s to exist before the leg "
                "starts; it is the identity this arm inherits" % provider_path)
        declared["expected_identity_names"].append("inherited_provider_socket")
    elif arm == predicate.ARM_E:
        # A channel whose PEER is a broker that would translate leg bytes into a
        # provider request.  The channel carries NO provider identity of its own,
        # so only its EXISTENCE can condemn it -- and the peer is what makes the
        # existence meaningful.
        srv, broker_path = make_provider_endpoint(arm_dir, "broker-peer.sock")
        boundary.adopt_socket(srv)   # closed by boundary.stop(), even on raise
        declared["expected_identity_names"].append("broker_channel")
    elif arm in (predicate.ARM_A, predicate.ARM_C, predicate.ARM_D):
        pass

    # ---- FROZEN PREDICTION (gate requirement) ----
    # The prediction is sealed as its own byte artifact BEFORE the arm launches,
    # and its hash is bound into the precommit.  An expectation that lives only
    # as a Python expression evaluated at report time is not a prediction, it is
    # a description of whatever happened: it cannot be falsified, and repairing a
    # mismatch by rerunning the arm until it matches would be invisible.
    # The delta falsifier is NOT a measurement arm: it is exempt from the
    # five-arm expectation table on purpose, because it exists to prove the DELTA
    # CONJUNCT can fail, not to predict an arm outcome.  Requiring an entry here
    # would force a prediction that would then be reported as an arm result.
    expected_hold, expected_code = predicate.ARM_EXPECTATION.get(
        arm, (True, predicate.NO_FAILURE))
    prediction = {
        "arm": arm,
        "role": role,
        "leg_binary": LEG_BINARIES[arm],
        "leg_binary_sha256": sha256_of(leg_bin),
        "predicted_predicate_holds": expected_hold,
        "predicted_failure_code": expected_code,
        "predicted_verdict": ("PASS" if expected_hold else "FAIL"),
        "frozen_before": "launch",
        "prediction_wall": time.time(),
    }
    atomic_write_json(arm_dir / "prediction.json", prediction)
    prediction_bytes = (arm_dir / "prediction.json").read_bytes()
    prediction_sha = hashlib.sha256(prediction_bytes).hexdigest()

    precommit = write_precommit(arm_dir, arm, role, leg_bin, declared,
                                policy_identity, prediction_sha256=prediction_sha)
    allowlist = precommit["descriptor_allowlist"]

    # ---- Launch under strace in a transient cgroup ----
    env = dict(os.environ)
    env.update({
        "D3_MARKER_FILE": str(marker),
        "D3_ARM_DIR": str(arm_dir),
        "D3_LEG_ROLE": role,
        "D3_ATTEMPTS": str(ledgers["attempts"]),
        "D3_DISPATCHES": str(ledgers["dispatches"]),
        "D3_MOCK_RECEIVES": str(ledgers["receives"]),
        # The sealed response reaches the leg BY PATH: systemd-run drops
        # inherited descriptors, so the read-only audit copy is the handoff and
        # the leg re-derives point_of_use_sha256 from the bytes it consumed.
        "D3_SEALED_RESPONSE_PATH": sealed_doc["handoff_path"],
        "D3_RECEIPT_DIR": str(receipt_dir),
    })
    pass_fds = ()
    if provider_path is not None:
        env["D3_PROVIDER_ENDPOINT_PATH"] = str(provider_path)
    if broker_path is not None:
        env["D3_BROKER_ENDPOINT_PATH"] = str(broker_path)

    trace_prefix = str(arm_dir / "trace-prefix.")
    unit = "a12d3-%s-%d-%d.service" % (arm.lower(), os.getpid(), time.time_ns())
    command = [SYSTEMD_RUN, "--user", "--pipe", "--wait", "--quiet",
               "--property=KillMode=process", "--unit=" + unit,
               "--working-directory=" + str(arm_dir)]
    for key in sorted(env):
        if key.startswith("D3_"):
            command.append("--setenv=%s=%s" % (key, env[key]))
    # ---- THREE LEGS, ONE POLICY WINDOW, ONE BARRIER -----------------------
    # The three D2 legs are launched together under a single strace so they share
    # ONE policy installation and ONE measurement window.  Running them in
    # separate windows would let each leg be judged under a different policy
    # activation, and the whole claim is that the honest legs survive the SAME
    # policy the offender is denied by.
    #
    # NOTE on `-f`: strace follows forks, and the three legs are three separate
    # execs from the supervisor shell.  Traces land in per-pid files with the
    # prefix, which is also how the legs are located below.
    supervisor = arm_dir / "run-legs.sh"
    leg_lines = ["#!/bin/sh", "set -u"]
    for identity, injection, binary in leg_plan:
        # D3_LEG_ROLE must be set PER LEG.  The leg asserts that the env role
        # equals the role compiled into it (a mismatch exits 90), so a single
        # process-wide D3_LEG_ROLE would make two of the three legs refuse to
        # start -- which is exactly what happened: the legs exited instantly with
        # "missing required env D3_LEG_ROLE" and not one tracee was ever measured.
        #
        # Everything else is shared deliberately: one policy, one barrier, one
        # sealed response, one set of D1 ledgers.  Only the identity and the
        # binary differ, and the identity is enforced against the binary's own
        # compiled-in role rather than trusted from argv.
        leg_lines.append(
            'D3_LEG_ROLE="%s" "%s" &' % (identity, BUILD_DIR / binary))
    leg_lines.append("wait")
    supervisor.write_text("\n".join(leg_lines) + "\n", encoding="utf-8")
    supervisor.chmod(0o700)

    command += ["--", STRACE, "-ff", "-qq", "-ttt",
                "-e", "trace=process,network", "-o", trace_prefix,
                str(supervisor)]

    service = subprocess.Popen(command, cwd=str(arm_dir), env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)

    # Every leg must be released on ALL exit paths. A leg blocked at the entry
    # barrier with no live harness is a LEAK even though nothing crashed: the
    # tracer waits on it forever and the transient unit never settles. Arm this
    # guard the moment the unit exists, BEFORE any probe that can raise.
    # With three legs this guard must release ALL of them -- releasing one and
    # leaving two blocked would wedge the unit exactly as before, only less
    # obviously.
    _escrow = {"leg_pids": [], "released": False, "unit": unit}

    def _guaranteed_release():
        """Release + reap every leg whatever happens. Idempotent, never raises."""
        if _escrow["released"]:
            return
        for pid in _escrow["leg_pids"]:
            try:
                os.kill(pid, signal.SIGUSR1)
            except OSError:
                pass
        # Reap the launcher even if the payload is wedged; then stop the unit so
        # the transient scope cannot outlive the harness.
        try:
            service.kill()
        except OSError:
            pass
        try:
            service.wait(timeout=10)
        except Exception:
            pass
        try:
            subprocess.run([SYSTEMD_RUN, "--user", "--quiet",
                            "systemctl", "--user", "stop", unit],
                           timeout=15, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        _escrow["released"] = True

    # Identify the legs as the tracer's children, then BIND the measurement to
    # them.  The launcher is systemd-run; the TRACER is a sibling of it inside
    # the transient unit, so it is located by comm rather than by parentage.
    launcher_pid = service.pid
    try:
        tracer_pid = locate_tracer(launcher_pid, trace_prefix)
        # locate_legs returns {identity: pid}.  The escrow needs PIDS, not the
        # identity KEYS: `list(a_dict)` yields the keys, and os.kill() on a str
        # would raise inside the release guard -- i.e. the guard meant to prevent
        # a leak would itself be the thing that failed to release.
        leg_pids = locate_legs(tracer_pid, leg_plan, arm_dir) if tracer_pid else {}
        _escrow["leg_pids"] = sorted(leg_pids.values())
    except BaseException:
        _guaranteed_release()
        raise
    if len(leg_pids) != len(leg_plan):
        # Fail closed and LOUD.  A partial leg set would let the arm report a
        # three-leg contract while only two legs were ever measured.
        _guaranteed_release()
        raise RuntimeError(
            "expected %d legs in %s, located %d" % (
                len(leg_plan), arm, len(leg_pids)))

    # ---- MEASUREMENT WINDOW: every leg is filtered and blocked, holding nothing.
    # Everything from here to the release is inside a guard: a probe that raises
    # must still release the legs, or they block at the barrier forever.
    #
    # Each leg is measured SEPARATELY and its measurement is kept PER LEG.  The
    # two possession conjuncts are per-leg over the three measured descriptor
    # sets, so a per-arm aggregate would destroy exactly the information they
    # need -- and, worse, would let one leg's capability be attributed to another.
    try:
        leg_measurements = []
        for identity, injection, binary in leg_plan:
            pid = leg_pids[identity]
            binary_path = BUILD_DIR / binary
            leg_hold = inspector.await_blocked(pid, timeout=30.0)
            leg_seccomp = inspector.seccomp_state(
                pid, expected_exe=str(binary_path))
            leg_descriptors = inspector.enumerate_descriptors(
                pid, expected_exe=str(binary_path))
            leg_measurements.append({
                "identity": identity,
                "injection": injection,
                "binary": binary,
                "binary_sha256": sha256_file(binary_path),
                "pid": pid,
                "hold": leg_hold,
                "seccomp": leg_seccomp,
                "descriptors": leg_descriptors,
            })
        # The head-to-head is taken against the OFFENDING leg when there is one,
        # and the first leg otherwise: it is a liveness check that the target
        # process is really the binary we think it is, which is strongest on the
        # leg whose identity the arm's verdict turns on.
        offender_identity = OFFENDER_LEG[arm]
        hh_pid = leg_pids.get(offender_identity) or leg_pids[leg_plan[0][0]]
        hh_bin = BUILD_DIR / _LEG_BIN[(offender_identity or leg_plan[0][0],
                                       ARM_INJECTION[arm] if offender_identity
                                       else "none")]
        head_to_head = inspector.negative_head_to_head(tracer_pid, hh_pid,
                                                       str(hh_bin))
    except BaseException:
        _guaranteed_release()
        raise
    measurement_wall = time.time()

    # Per-leg measurement is written as its own artifact: the checker recomputes
    # the possession conjuncts from THESE records, not from any aggregate.
    atomic_write_json(arm_dir / "leg-measurements.json", {
        "arm": arm,
        "offender_identity": OFFENDER_LEG[arm],
        "offender_injection": ARM_INJECTION[arm],
        "legs": leg_measurements,
        "measured_wall": measurement_wall,
    })
    # Backwards-compatible single-object view: the arm-level `descriptors` key has
    # always meant "the descriptors of the leg under test".  It now means the
    # OFFENDING leg's set, which is the one the arm's verdict turns on.  Kept so
    # existing readers do not silently see a different thing.
    descriptors = next(
        (m["descriptors"] for m in leg_measurements
         if m["identity"] == (OFFENDER_LEG[arm] or leg_plan[0][0])),
        leg_measurements[0]["descriptors"])
    # Same rule for the hold and seccomp aliases: they must describe the leg the
    # verdict turns on, not whichever leg happened to be measured first.  All
    # three are under ONE policy and ONE barrier, so they agree -- but if they
    # ever stopped agreeing, reporting leg 0 would hide exactly the disagreement
    # that matters.
    _verdict_leg = next(
        (m for m in leg_measurements
         if m["identity"] == (OFFENDER_LEG[arm] or leg_plan[0][0])),
        leg_measurements[0])
    hold = _verdict_leg["hold"]
    seccomp = _verdict_leg["seccomp"]

    # ---- AFTER snapshot + the measured delta ------------------------------
    # Taken HERE: the legs have completed and the boundary stayed UP for the whole
    # leg window, so a leg that reached it would have left a real record -- and,
    # decisively, it is taken BEFORE the falsifier injects, so `after` describes the
    # ARM's own run rather than the arm's run plus an injected perturbation.
    #
    # The ordering is what makes the falsifier a measurement: the injection must land
    # AFTER the after-snapshot, otherwise the extra opportunity would be absorbed into
    # `after`, the delta would stay zero by construction, and the conjunct would prove
    # nothing about the delta being live.  The settle is for the gate's writers.
    # (The boundary is stopped AFTER the falsifier block below: F1b's full traverse
    #  needs a LIVE gate to dispatch through, and stopping here would make every
    #  F1b injection fail with a missing socket.)
    time.sleep(0.3)
    after_snapshot = boundary_module.snapshot_counts(arm_dir)
    provider_delta = boundary_module.measured_delta(before_snapshot,
                                                    after_snapshot)

    # ---- FALSIFIER (D3-X): inject a REAL extra provider opportunity HERE ----
    # The leg is alive and blocked at the entry barrier, the before-snapshot is
    # already written and its hash sealed, and the arm's own after-snapshot is taken.
    # Injecting now guarantees the extra opportunity cannot be absorbed into either
    # `before` or `after`: the DELTA itself must move.
    # Without a real injection point the conjunct could only ever fail for a
    # structural reason, which would not be a measurement of the delta at all.
    falsifier_injection = {"attempted": False}
    # Named on every arm so the publish below never depends on a name that only
    # exists on the falsifier path.
    f1_byte_authority = {}
    f1_authority_record = {}
    f1_conjunct_value = False
    f1_delta = {"attempts": 0, "dispatches": 0, "receives": 0}
    f1_matches_frozen_shape = False
    if falsifier_arm:
        try:
            # ── F1: the FROZEN, contract-bearing falsifier ────────────────────
            # A real second gate attempt, with the second dispatch prevented, so
            # the arm ends 2/1/1 and the delta is {attempts:+1, dispatches:0,
            # receives:0} -- exactly the shape the frozen text names.
            extra = boundary.inject_extra_attempt_f1()
            time.sleep(0.3)   # let the gate's writers flush
            mid = boundary_module.snapshot_counts(arm_dir)
            f1_after = {n: mid[n] for n in boundary_module.LEDGER_NAMES}
            f1_delta = {
                "attempts": (f1_after["attempts"]["records"]
                             - before_snapshot["attempts"]["records"]),
                "dispatches": (f1_after["dispatches"]["records"]
                               - before_snapshot["dispatches"]["records"]),
                "receives": (f1_after["receives"]["records"]
                             - before_snapshot["receives"]["records"]),
            }
            # The frozen shape, asserted rather than assumed: had the mechanism
            # dispatched, the contract-bearing falsifier would silently be F1b.
            f1_matches_frozen_shape = (f1_delta == {"attempts": 1, "dispatches": 0,
                                                    "receives": 0})

            # ── F1's OWN BYTE-LEVEL STATE ─────────────────────────────────────
            # F1's facts are sealed as BYTES so the checker can recompute F1's delta
            # WITHOUT believing this record: it reads d1-prefix-<name>.jsonl (the
            # pre-leg bytes) and d1-f1-final-<name>.jsonl (the bytes immediately after
            # F1, before F1b ran) and derives both counts from those bytes itself.
            # Without this the checker's only option would be to trust `f1_delta`,
            # which is exactly the class of harness-trusted number the gate rejected.
            #
            # The byte seals are taken by the shared helper at the END of this block
            # so that BOTH F1's and F1b's states are covered by one mechanism.
            def _seal_ledger_stage(prefix_label):
                """Copy every live ledger to its stage file and return the stage's
                declared identities.  Used for BOTH F1's post state and F1b's post
                state, so the two stages are sealed by one mechanism rather than by
                two code paths that could drift apart."""
                stage = {}
                for _name in boundary_module.LEDGER_NAMES:
                    _live = arm_dir / boundary_module.LEDGER_FILES[_name]
                    _dest = arm_dir / ("d1-%s-%s.jsonl" % (prefix_label, _name))
                    _dest.write_bytes(_live.read_bytes())
                    _raw = _dest.read_bytes()
                    stage[_name] = {
                        "sealed_path": _dest.name,
                        "sealed_bytes": len(_raw),
                        "sealed_sha256": hashlib.sha256(_raw).hexdigest(),
                    }
                return stage

            f1_baseline_seal = {}
            for _name in boundary_module.LEDGER_NAMES:
                _base = arm_dir / ("d1-prefix-%s.jsonl" % _name)
                _base_bytes = _base.read_bytes() if _base.exists() else b""
                f1_baseline_seal[_name] = {
                    "sealed_path": _base.name,
                    "sealed_bytes": len(_base_bytes),
                    "sealed_sha256": hashlib.sha256(_base_bytes).hexdigest(),
                }
            f1_final_seal = _seal_ledger_stage("f1-final")

            # ── F1b: SUPPLEMENTAL full-traverse falsifier ─────────────────────
            # Run separately, and recorded under its own name with its own
            # baseline.  It is explicitly NOT contract-bearing: the gate ruled that
            # the frozen text names 2/1/1 and that F1b may not be relabelled as F1.
            # Its baseline is the post-F1 state, so its OWN delta is the honest
            # measure of what the full traverse added.
            f1b_result = {}
            try:
                f1b_extra = boundary.inject_extra_attempt_f1b()
                time.sleep(0.3)
                f1b_mid = boundary_module.snapshot_counts(arm_dir)
                f1b_after = {n: f1b_mid[n] for n in boundary_module.LEDGER_NAMES}
                f1b_delta = {
                    n: (f1b_after[n]["records"] - f1_after[n]["records"])
                    for n in boundary_module.LEDGER_NAMES}
                _f1b_reached_mock = f1b_delta.get("receives", 0) > 0
                f1b_result = {
                    "attempted": True,
                    "ok": True,
                    "injection": f1b_extra,
                    "baseline": "state_after_F1",
                    "baseline_counts": f1_after,
                    "counts_after": f1b_after,
                    "delta_from_F1_baseline": f1b_delta,
                    "expected_full_traverse_delta": {
                        "attempts": 1, "dispatches": 1, "receives": 1},
                    "is_full_traverse": (f1b_delta == {"attempts": 1,
                                                       "dispatches": 1,
                                                       "receives": 1}),
                    "reached_mock": _f1b_reached_mock,
                    "gate_response_head": f1b_extra.get("response_head", ""),
                    # STATED PLAINLY, because the difference matters: with the gate's
                    # `authorized_attempt_limit` left at its frozen value the gate
                    # answers BLOCKED_ATTEMPT_LIMIT, so the extra opportunity is
                    # recorded as an attempt and as a blocked dispatch but never
                    # reaches the mock and produces no receive.  The gate reads its
                    # policy ONCE at startup, so rewriting the policy file is not
                    # enough to raise it; doing so would require an injected
                    # authorization limit, which would change the boundary under
                    # test.  This is why F1b is labelled SUPPLEMENTAL and why its
                    # shortfall is reported rather than smoothed over.
                    "shortfall_reason": (
                        None if _f1b_reached_mock else
                        "gate answered BLOCKED_ATTEMPT_LIMIT at the frozen "
                        "authorized_attempt_limit, so the extra attempt was recorded "
                        "and a blocked dispatch row written, but no mock receive "
                        "occurred; the full traverse is therefore partial"),
                    "contract_bearing": False,
                }
            except BaseException as exc:
                f1b_result = {"attempted": True, "ok": False,
                              "error": "%s: %s" % (type(exc).__name__, exc),
                              "contract_bearing": False}

            # F1b's own post state, sealed by the same mechanism.  Its baseline is
            # F1's post state, so the pair (f1-final, f1b-final) is what the
            # supplemental full-traverse delta is derived from.
            f1b_final_seal = _seal_ledger_stage("f1b-final")
            if f1b_result.get("ok"):
                f1b_result["byte_authority"] = {
                    "baseline_seal": "d1-f1-final-<name>.jsonl",
                    "post_seal": f1b_final_seal,
                }

            # Written to a CARRIER, not to `provider_delta`: that dict does not exist
            # yet at this point and is rebound by measured_delta() further down, so
            # writing through it here silently lost every seal (measured: the field
            # arrived in provider-after.json as an empty object and the checker
            # correctly reported "F1 byte seals absent").
            f1_authority_record = {
                "pre_leg_seal": f1_baseline_seal,
                "post_f1_seal": f1_final_seal,
                "post_f1b_seal": f1b_final_seal,
                "note": ("F1's and F1b's states are sealed as BYTES so the checker "
                         "derives both deltas from bytes rather than from any number "
                         "this summary states."),
            }

            f1_conjunct_value = bool(
                f1_matches_frozen_shape
                and before_snapshot["attempts"]["records"] == 1
                and before_snapshot["dispatches"]["records"] == 1)

            f1_offenders = 0
            if not f1_conjunct_value:
                boundary_module.publish_offenders(
                    arm_dir, before_snapshot, provider_delta,
                    falsifier_injection.get("injected_attempt"))
                f1_offenders = 1

            falsifier_injection = {
                "attempted": True,
                "ok": True,
                "contract_bearing_falsifier": "F1",
                "frozen_shape_required": {"attempts": 1, "dispatches": 0,
                                          "receives": 0},
                "frozen_shape_observed": f1_delta,
                "frozen_shape_matches": f1_matches_frozen_shape,
                "injection_point": "leg_alive_at_entry_barrier_after_before_snapshot",
                "injected_attempt": extra,
                "counts_after_injection": f1_after,
                "delta_after_injection": f1_delta,
                "supplemental_falsifier": {
                    "name": "F1b_EXTRA_DISPATCH_FULL_TRAVERSE",
                    "contract_bearing": False,
                    **f1b_result},
            }
        except BaseException as exc:
            falsifier_injection = {"attempted": True, "ok": False,
                                   "error": "%s: %s" % (type(exc).__name__, exc)}
    atomic_write_json(arm_dir / "falsifier-injection.json", falsifier_injection)
    # The boundary has now served both the arm and the supplemental falsifier.
    boundary.stop()

    atomic_write_json(arm_dir / "measurement.json", {
        "hold": hold, "seccomp": seccomp, "descriptors": descriptors,
        "negative_head_to_head": head_to_head,
        "measured_wall": measurement_wall,
    })

    # Reconcile by EQUALITY against the precommitted declaration -- PER LEG.
    # The allowlist is precommitted once and is the same allowlist every leg is
    # judged against: a per-leg allowlist would be a measurement-derived
    # allowance, which is precisely the circularity the precommit exists to stop.
    try:
        equality_per_leg = {}
        for measurement in leg_measurements:
            equality_per_leg[measurement["identity"]] = (
                inspector.reconcile_descriptor_equality(
                    measurement["descriptors"],
                    {"role": measurement["identity"],
                     "expected": declared["entries"]},
                    phase="ENTRY_BARRIER_REACHED"))
        equality = equality_per_leg[
            OFFENDER_LEG[arm] or leg_plan[0][0]]
    except BaseException:
        _guaranteed_release()
        raise

    # ---- Release: a SIGNAL to each externally verified pid, no fd involved.
    # A leg whose seccomp state was NOT independently verified is never signalled
    # -- signalling an unverified pid would release something else entirely.  The
    # release is therefore per-leg: one leg failing verification must not block
    # (or force) the release of the others.
    released = {"signal": "SIGUSR1", "wall": time.time(),
                "released_only_after_measurement": True, "per_leg": {}}
    for measurement in leg_measurements:
        identity = measurement["identity"]
        if measurement["seccomp"].get("target_verified"):
            try:
                os.kill(measurement["pid"], signal.SIGUSR1)
                released["per_leg"][identity] = {
                    "released": True, "pid": measurement["pid"]}
            except OSError as exc:
                released["per_leg"][identity] = {
                    "released": False, "pid": measurement["pid"],
                    "error": str(exc)}
        else:
            released["per_leg"][identity] = {
                "released": False, "pid": measurement["pid"],
                "reason": "target_not_verified_withholding_release"}
    released["released"] = bool(released["per_leg"]) and all(
        entry["released"] for entry in released["per_leg"].values())
    released["released_count"] = sum(
        1 for entry in released["per_leg"].values() if entry["released"])
    released["leg_count"] = len(released["per_leg"])
    _escrow["released"] = True

    stdout, stderr = service.communicate(timeout=180)

    # ---- Drain BEFORE parse, then hash both states ----
    drain_wall = time.time()
    drained, drained_sha = trace_manifest(arm_dir)
    atomic_write_json(arm_dir / "drain.json",
                      {"drain_wall": drain_wall, "manifest": drained,
                       "manifest_sha256": drained_sha})
    raw_lines = read_raw_trace_lines(arm_dir)
    parsed = parse_trace_lines(raw_lines)
    parse_wall = time.time()
    parsed_manifest, parsed_sha = trace_manifest(arm_dir)
    atomic_write_json(arm_dir / "parse.json",
                      {"parse_wall": parse_wall, "raw_lines": len(raw_lines),
                       "events": len(parsed["events"]),
                       "unparsable": parsed["unparsable"],
                       "manifest_sha256_after_parse": parsed_sha})

    markers = read_markers(marker)

    if conn is not None:
        conn.close()
    if srv is not None:
        srv.close()

    ledger_counts = {name: count_ledger(path) for name, path in ledgers.items()}

    # (The AFTER snapshot and the measured delta were taken BEFORE the falsifier
    #  block above, so F1's extra opportunity cannot be absorbed into the arm's own
    #  `after` state.  Re-taking them here would overwrite `provider_delta` and
    #  destroy exactly that property.)
    # F1's byte authority and F1b's own record must appear IN provider-after.json,
    # which is the file the checker reads.  They were computed inside the falsifier
    # block above; they are attached here because `measured_delta` returns a fresh
    # dict and `provider_delta` is rebound at this point.
    # F1's byte authority and F1b's own record must appear IN provider-after.json,
    # which is the file the checker reads.  `provider_delta` was built before the
    # injection, so these are attached now -- and `conjunct_value` is set from F1's
    # OWN delta (taken above), never from a re-measurement that would include F1b.
    if falsifier_injection.get("attempted"):
        provider_delta["falsifier_injection"] = falsifier_injection
        provider_delta["f1_byte_authority"] = f1_authority_record
        provider_delta["f1_delta_observed"] = f1_delta
        provider_delta["f1_frozen_shape_required"] = dict(F1_FROZEN_DELTA)
        provider_delta["f1_conjunct_value"] = f1_conjunct_value
        # D3-X's conjunct is F1's shape, NOT the arm's own zero delta: the arm's zero
        # delta is what a clean run looks like, and grading on it would make the
        # falsifier's conjunct true whether or not the injection happened.
        provider_delta["conjunct_value"] = f1_conjunct_value
    boundary_module.atomic_write_json(arm_dir / "provider-after.json", {
        "counts": {n: after_snapshot[n] for n in boundary_module.LEDGER_NAMES},
        "snapshot_sha256": after_snapshot["_sha256"],
        "wall": after_snapshot["_wall"],
        "delta": provider_delta["delta"],
        "conjunct_value": provider_delta["conjunct_value"],
        "falsifier_injection": provider_delta.get("falsifier_injection"),
        "f1_byte_authority": provider_delta.get("f1_byte_authority"),
        "f1_delta_observed": provider_delta.get("f1_delta_observed"),
        "f1_frozen_shape_required": provider_delta.get("f1_frozen_shape_required"),
        # The sealed pre-leg prefix this `after` state is comparable against, named
        # so the checker's join is to a specific sealed artifact rather than to
        # "whatever the before-snapshot happened to say".
        "sealed_ledger_prefix": {
            n: {
                "sealed_path": "d1-prefix-%s.jsonl" % n,
                "sealed_bytes": (ledger_prefix_seal.get(n) or {}).get("sealed_bytes"),
                "sealed_sha256": (ledger_prefix_seal.get(n) or {}).get("sealed_sha256"),
                "prefix_is_exact_prefix_of_final": (
                    (arm_dir / ("d1-prefix-%s.jsonl" % n)).exists()
                    and (arm_dir / ("d1-prefix-%s.jsonl" % n)).read_bytes()
                    == (arm_dir / boundary_module.LEDGER_FILES[n]).read_bytes()[
                        :(ledger_prefix_seal.get(n) or {}).get("sealed_bytes", 0)]),
            }
            for n in boundary_module.LEDGER_NAMES
        },
    })
    if not provider_delta["conjunct_value"]:
        boundary_module.publish_offenders(
            arm_dir, before_snapshot, provider_delta,
            falsifier_injection.get("injected_attempt"))

    # ---- The D2 identity join from RAW artifacts --------------------------
    # ALL THREE legs, by D2's own identity names.  With one leg the "all three
    # legs share one captured response" property was satisfied over a single
    # element and therefore had no content; the join now has to bind three
    # distinct leg receipts to one captured response.
    leg_receipts = {}
    for identity, _injection, _binary in leg_plan:
        leg_receipts[identity] = sealed_identity.read_leg_receipt(
            arm_dir, identity)
    sealed_join = sealed_identity.join_point_of_use(sealed_doc, leg_receipts)
    sealed_join["offender_identity"] = OFFENDER_LEG[arm]
    sealed_join["offender_injection"] = ARM_INJECTION[arm]
    sealed_identity.atomic_write_json(arm_dir / "sealed-identity-join.json",
                                      sealed_join)

    # ---- REAL cell artifacts (never inferred from ledger emptiness) -------
    # The model cell is RUN, not enumerated by name: its count comes from a
    # report it actually produced.  Counting files by filename would let an
    # absent apparatus and a successful run read the same, which is exactly the
    # fail-open this replaced.
    model_cell = boundary_module.run_model_cell(
        arm_dir, "d3-cell-%s" % arm, BUILD_DIR / "d3-model-cell")
    cells = boundary_module.cell_artifacts(arm_dir)
    cells["model_cell_run"] = model_cell
    cells["model_cell_count_measured"] = (
        1 if model_cell.get("report_present") else 0)
    cells["order_cell_count_measured"] = 0
    cells["counted_by"] = ("executed model-cell report + filesystem enumeration; "
                           "never ledger emptiness")

    # ---- POST-LEG cell identity, joined to the sealed pre-leg manifest ------
    # The conjunct is a claim about the boundary being UNCHANGED, so it is decided
    # by comparing two independently taken enumerations, not by one existence test.
    cell_manifest_after = boundary_module.cell_manifest(
        arm_dir,
        cell_binaries={"model": BUILD_DIR / "d3-model-cell",
                       "order": BUILD_DIR / "d3-order-cell"},
        declared={"model": MODEL_CELL_COUNT, "order": ORDER_CELL_COUNT})
    boundary_module.atomic_write_json(arm_dir / "cell-manifest-after.json", {
        "phase": "POST_LEG_COMPLETION",
        "wall": time.time(),
        "manifest": cell_manifest_after,
        "cell_manifest_before_sha256": sha256_of(
            arm_dir / "cell-manifest-before.json"),
    })
    cells["cell_manifest_before"] = cell_manifest_before
    cells["cell_manifest_after"] = cell_manifest_after
    cells["cell_count_before"] = {
        "model": cell_manifest_before["model_cell_count"],
        "order": cell_manifest_before["order_cell_count"],
    }
    cells["cell_count_after"] = {
        "model": cell_manifest_after["model_cell_count"],
        "order": cell_manifest_after["order_cell_count"],
    }
    # Identity continuity is decided on (st_dev, st_ino) plus content hash, so a
    # same-path-different-inode swap is NOT silently continuous.
    def _ident(manifest, kind):
        return sorted((r.get("st_dev"), r.get("st_ino"), r.get("sha256"))
                      for r in manifest.get("%s_cell_entries" % kind, []))
    cells["model_cell_identity_same"] = (
        _ident(cell_manifest_before, "model")
        == _ident(cell_manifest_after, "model"))
    cells["order_cell_identity_same"] = (
        _ident(cell_manifest_before, "order")
        == _ident(cell_manifest_after, "order"))
    cells["model_cell_count_unchanged"] = (
        cell_manifest_before["model_cell_count"]
        == cell_manifest_after["model_cell_count"] == MODEL_CELL_COUNT)
    cells["order_cell_count_unchanged"] = (
        cell_manifest_before["order_cell_count"]
        == cell_manifest_after["order_cell_count"] == ORDER_CELL_COUNT)
    cells["cell_measurement_valid"] = bool(
        cell_manifest_before["model_cell_count"] == MODEL_CELL_COUNT
        and cell_manifest_after["model_cell_count"] == MODEL_CELL_COUNT
        and cell_manifest_before["order_cell_count"] == ORDER_CELL_COUNT
        and cell_manifest_after["order_cell_count"] == ORDER_CELL_COUNT
        and model_cell.get("report_present"))

    return {
        "arm": arm, "role": role, "arm_dir": str(arm_dir),
        "service_rc": service.returncode, "unit": unit,
        "service_stdout": stdout[-4000:], "service_stderr": stderr[-4000:],
        "leg_plan": [{"identity": i, "injection": j, "binary": b}
                      for i, j, b in leg_plan],
        "precommit": precommit, "allowlist": allowlist,
        "leg_pid": leg_pids.get(OFFENDER_LEG[arm] or leg_plan[0][0], 0),
        "leg_pids": dict(leg_pids), "tracer_pid": tracer_pid,
        "launcher_pid": launcher_pid,
        "leg_measurements": leg_measurements,
        "equality_per_leg": equality_per_leg,
        "hold": hold, "seccomp": seccomp, "descriptors": descriptors,
        "measurement_wall": measurement_wall,
        "head_to_head": head_to_head, "equality": equality,
        "released": released, "markers": markers,
        "trace_events": parsed["events"], "trace_unparsable": parsed["unparsable"],
        "trace_raw_lines": len(raw_lines),
        "drain": {"wall": drain_wall, "sha256": drained_sha,
                  "manifest": drained,
                  "drain_completed_before_parse": True,
                  "drain_before_parse_before_seal": True},
        "ledgers": ledger_counts, "policy_identity": policy_identity,
        "provider_fd": provider_fd, "broker_fd": broker_fd,
        # ---- The de-vacuumed measurements ----
        "provider_delta": provider_delta,
        "falsifier_injection": falsifier_injection,
        "provider_before": {n: before_snapshot[n]
                            for n in boundary_module.LEDGER_NAMES},
        "provider_after": {n: after_snapshot[n]
                           for n in boundary_module.LEDGER_NAMES},
        "opportunity": opportunity,
        "falsifier_arm": falsifier_arm,
        "sealed_identity": sealed_doc,
        "sealed_join": sealed_join,
        "leg_receipts": leg_receipts,
        "cell_artifacts": cells,
        "model_cell_count_expected": MODEL_CELL_COUNT,
        "order_cell_count_expected": ORDER_CELL_COUNT,
    }


def _children_of(pid: int) -> list:
    try:
        return [int(t) for t in Path("/proc/%d/task/%d/children"
                                     % (pid, pid)).read_text().split()]
    except (OSError, ValueError):
        return []


def leak_check(arm_names=None, build_dir=None) -> dict:
    """ACTIVELY hunt for the three leak classes. Never report 'no processes
    matched the arm name' as if it were a clean bill of health.

    A leg that hangs forever is a leak even though nothing crashed, so this
    looks for the SYMPTOMS instead of trusting names:
      (a) a leg blocked at a barrier with no live harness,
      (b) an orphaned tracer (parent dead or reparented to init),
      (c) a leftover transient unit.
    """
    import glob as _glob

    def _status(pid_dir):
        try:
            out = {}
            for line in Path(pid_dir, "status").read_text().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    out[k.strip()] = v.strip()
            return out
        except OSError:
            return {}

    blocked, orphaned_tracers, stale_units, stray = [], [], [], []
    my_pid = os.getpid()

    for entry in _glob.glob("/proc/[0-9]*"):
        try:
            pid = int(entry.rsplit("/", 1)[1])
        except ValueError:
            continue
        if pid == my_pid:
            continue
        try:
            comm = Path(entry, "comm").read_text().strip()
        except OSError:
            continue
        st = _status(entry)
        ppid = int(st.get("PPid", "0") or 0)
        try:
            wchan = Path(entry, "wchan").read_text().strip()
        except OSError:
            wchan = ""

        # (a) a leg parked at the signal rendezvous with no live harness parent
        if comm.startswith("d3-"):
            parent_alive = ppid not in (0, 1) and Path("/proc/%d" % ppid).exists()
            if (not parent_alive) or "sigsuspend" in wchan:
                blocked.append({"pid": pid, "comm": comm, "ppid": ppid,
                                "wchan": wchan, "parent_alive": parent_alive})
        # (b) an orphaned tracer. NOTE: under systemd-run the tracer is
        # reparented to the USER SYSTEMD MANAGER, not to init, so a ppid test of
        # (0,1) alone misses it. Treat "parent is a systemd user manager" and
        # "parent is not a live harness process" as orphaned too.
        if "strace" in comm:
            try:
                parent_comm = Path("/proc/%d/comm" % ppid).read_text().strip()
            except OSError:
                parent_comm = ""
            orphan_parent = (
                ppid in (0, 1)
                or not Path("/proc/%d" % ppid).exists()
                or parent_comm.startswith("systemd")
            )
            if orphan_parent:
                try:
                    cmd = Path(entry, "cmdline").read_bytes().replace(
                        b"\0", b" ").decode()[:200]
                except OSError:
                    cmd = ""
                orphaned_tracers.append({"pid": pid, "ppid": ppid,
                                         "parent_comm": parent_comm, "cmd": cmd})

    # (c) leftover transient units (failed ones count: they outlive the harness)
    try:
        proc = subprocess.run(["systemctl", "--user", "list-units",
                               "a12d3-*", "--all", "--no-legend",
                               "--plain", "--no-pager"],
                              capture_output=True, text=True, timeout=20)
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line:
                stale_units.append(line)
    except Exception as exc:
        stale_units.append("unit query failed: %s" % exc)

    # (d) scratch residue outside the sealed run dirs
    if build_dir:
        for pat in ("*.fifo", "*.sock"):
            stray.extend(p for p in _glob.glob(str(Path(build_dir) / pat)))

    clean = not (blocked or orphaned_tracers or stale_units or stray)
    return {"clean": clean, "blocked_legs": blocked,
            "orphaned_tracers": orphaned_tracers,
            "leftover_units": stale_units, "stray_fixture_paths": stray,
            "arm_names_checked": list(arm_names or []),
            "method": "symptom-based; name matching alone is insufficient"}


def reap_transient_units() -> dict:
    """Stop + reset any a12d3-* transient units this harness left behind."""
    done = {}
    for verb in ("stop", "reset-failed"):
        try:
            proc = subprocess.run(["systemctl", "--user", verb, "a12d3-*"],
                                  capture_output=True, text=True, timeout=30)
            done[verb] = proc.returncode
        except Exception as exc:
            done[verb] = "error: %s" % exc
    return done


def _comm_of(pid: int) -> str:
    try:
        return Path("/proc/%d/comm" % pid).read_text().strip()
    except OSError:
        return ""


def locate_tracer(launcher_pid: int, trace_prefix: str,
                  timeout: float = 20.0) -> int:
    """Find the strace process that is tracing OUR leg.

    WHY THE LAUNCHER'S CHILDREN ARE NOT IT.  `systemd-run --pipe --wait` does not
    fork the payload as its child: it asks the user manager to start a transient
    unit, and the payload is reparented.  Measured on this host: the launcher had
    NO descendants at all while strace (its sibling) and the leg were reparented
    to the systemd --user manager (pid 1576444).  So walking down from the
    launcher finds nothing -- which is exactly what happened, and why the first
    battery sat forever measuring pid 0 while a correctly filtered leg slept in
    sigsuspend.

    IDENTITY IS BOUND BY THE TRACE PREFIX, not by comm alone.  Several strace
    processes can exist at once (a stale run, another arm, an unrelated trace), so
    matching on `comm == strace` could binder us to a foreign tracer and measure
    the wrong tree -- the precise failure this harness exists to refuse.  Each
    arm passes a unique `-o <prefix>` in its argv, so `/proc/<pid>/cmdline` is a
    positive identifier: the tracer whose command line contains our exact prefix
    is ours, and no other process can satisfy that.
    """
    deadline = time.time() + timeout
    needle = trace_prefix.encode()
    while time.time() < deadline:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                if Path(entry / "comm").read_text().strip() != "strace":
                    continue
                cmdline = (entry / "cmdline").read_bytes()
            except (OSError, ValueError):
                continue
            if needle in cmdline:
                return pid
        time.sleep(0.01)
    return 0


def _descendant_pids(root: int, max_depth: int = 6) -> list:
    """All pids below `root` (breadth-first), excluding root itself."""
    found, frontier = [], [root]
    for _ in range(max_depth):
        nxt = []
        for pid in frontier:
            for child in _children_of(pid):
                if child not in found:
                    found.append(child)
                    nxt.append(child)
        if not nxt:
            break
        frontier = nxt
    return found


def locate_leg(tracer_pid: int, timeout: float = 20.0) -> int:
    """Find the leg as the tracer's child.  Here the child relationship IS real:
    strace forks the tracee directly, so /proc/<strace>/children is authoritative.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        children = _children_of(tracer_pid)
        if children:
            return children[0]
        time.sleep(0.01)
    return 0


def locate_legs(tracer_pid: int, leg_plan, arm_dir: Path,
                timeout: float = 30.0) -> dict:
    """Locate ALL THREE legs and bind each pid to its compiled IDENTITY.

    This cannot use `children[0]`: with three legs under one tracer the child
    list has three entries and its order is not the launch order, so indexing
    would silently attribute one leg's descriptors to another -- and the two
    possession conjuncts are exactly a per-leg statement about descriptors.  A
    mis-binding there would publish a capability under the wrong leg's name.

    The binding is made on EVIDENCE the leg itself produces, not on launch order
    or process age:
      1. every descendant of the tracer is enumerated;
      2. each candidate's /proc/<pid>/environ is read -- D3_LEG_ROLE is set
         per-leg by the supervisor, and it is the ONLY per-leg identifier that
         actually differs between the three processes;
      3. the identity must be one of the three D2 identities, and must not be
         claimed by two different pids.

    WHY NOT argv.  The leg takes its role from the ENVIRONMENT and asserts it
    equals the role compiled into the binary; a supervisor that passed the
    identity as argv would have the leg exit 90 on the mismatch.  Matching on
    argv would therefore bind to a process that never becomes a leg at all.
    (Measured: an argv-identity supervisor produced three immediate exits and
    zero tracees.)

    Returns {identity: pid}.  Raises if any identity is missing or duplicated:
    a partial set must never be reported as a complete three-leg run.
    """
    wanted = [identity for identity, _injection, _binary in leg_plan]
    wanted_binaries = {
        str(BUILD_DIR / binary) for _identity, _injection, binary in leg_plan}
    deadline = time.time() + timeout
    found = {}
    while time.time() < deadline:
        found = {}
        duplicates = set()
        for pid, cmdline, exe in iter_tracer_descendants(tracer_pid):
            if not exe or exe not in wanted_binaries:
                continue
            identity = _environ_value(pid, "D3_LEG_ROLE")
            if identity in wanted:
                if identity in found and found[identity] != pid:
                    duplicates.add(identity)
                found[identity] = pid
        if duplicates:
            raise RuntimeError(
                "identity claimed by multiple pids: %s" % sorted(duplicates))
        if all(identity in found for identity in wanted):
            return found
        time.sleep(0.02)
    missing = [identity for identity in wanted if identity not in found]
    raise RuntimeError(
        "legs not located in %.1fs; found=%s missing=%s"
        % (timeout, sorted(found), missing))


def _environ_value(pid: int, name: str):
    """Read one variable from /proc/<pid>/environ, or None.

    /proc/<pid>/environ is the INITIAL environment and is world-readable only for
    the owning user, so this stays inside the harness's own credentials.
    """
    try:
        raw = Path("/proc/%d/environ" % pid).read_bytes()
    except OSError:
        return None
    prefix = (name + "=").encode()
    for entry in raw.split(b"\0"):
        if entry.startswith(prefix):
            return entry[len(prefix):].decode("utf-8", "replace")
    return None


def iter_tracer_descendants(tracer_pid: int):
    """Yield (pid, cmdline_list, exe) for the tracer itself and its descendants.

    Walks /proc rather than trusting a single parent link, because systemd-run
    reparents: the tracer and its tracees are siblings under the user manager,
    and a chain-following walk from the tracer would find nothing at all.
    """
    by_parent = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open("/proc/%d/stat" % pid, "rb") as handle:
                stat = handle.read().decode("utf-8", "replace")
            rparen = stat.rfind(")")
            ppid = int(stat[rparen + 2:].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        by_parent.setdefault(ppid, []).append(pid)

    seen = set()
    queue = [tracer_pid]
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        cmdline, exe = [], ""
        try:
            raw = Path("/proc/%d/cmdline" % pid).read_bytes()
            cmdline = [part.decode("utf-8", "replace")
                       for part in raw.split(b"\0") if part]
        except OSError:
            pass
        try:
            exe = os.readlink("/proc/%d/exe" % pid)
        except OSError:
            pass
        yield pid, cmdline, exe
        queue.extend(by_parent.get(pid, []))


def trace_manifest(arm_dir: Path) -> tuple[dict, str]:
    files = {}
    for path in sorted(arm_dir.glob("trace-prefix.*"), key=lambda p: p.name):
        data = path.read_bytes()
        files[path.name] = {"bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()}
    value = {"files": files}
    return value, hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_raw_trace_lines(arm_dir: Path) -> list[str]:
    lines = []
    for path in sorted(arm_dir.glob("trace-prefix.*"), key=lambda p: p.name):
        lines.extend(path.read_text(encoding="utf-8",
                                    errors="replace").splitlines())
    return lines


def parse_trace_lines(raw_lines: list[str]) -> dict:
    """Parse the raw external trace into events.  Never invents an event."""
    events, unparsable = [], 0
    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith("+++") or line.startswith("---"):
            continue
        event = parse_trace_line(line)
        if event is None:
            unparsable += 1
            continue
        events.append(event)
    return {"events": events, "unparsable": unparsable}


# strace has TWO failure spellings and only one of them is numeric:
#   ... = -1 EACCES (Permission denied)     <- named errno, resolvable
#   ... = -1 ECHILD (No child processes)    <- named errno, resolvable
# The leading `-1` is a PLACEHOLDER in both, not the errno number.  A parser that
# computes `-ret` turns EVERY named failure into errno 1 (EPERM), which is an
# accepted denial errno here -- so the supervisor shell's ordinary `wait()`
# returning ECHILD was silently counted as a DENIED `wait4`, inflating the denial
# evidence with a syscall that was never denied.  The name is therefore captured
# and resolved through the policy's errno table.
_ERRNO_BY_NAME = dict(policy.ERRNO_BY_NAME)

_SYSCALL_RE = __import__("re").compile(
    r"^(?:(?P<ts>\d+\.\d+)\s+)?"
    r"(?:\[pid\s+(?P<pid>\d+)\]\s+)?"
    r"(?P<nr>[a-z_0-9]+)\((?P<args>.*)\)\s*=\s*(?P<ret>-?\d+)"
    r"(?P<named_errno>\s+[A-Z][A-Z0-9_]+)?"
    r"(?:\s|$)")


def parse_trace_line(line: str) -> dict | None:
    match = _SYSCALL_RE.match(line)
    if not match:
        return None
    ret = int(match.group("ret"))
    named = (match.group("named_errno") or "").strip()
    # Resolve the errno from the NAME when strace printed one, and only fall back
    # to `-ret` for the bare numeric form.  `-ret` is the errno number ONLY when
    # the return is a plain negative integer; with a named errno the printed -1
    # is a placeholder and `-ret` would be 1 (EPERM) regardless of the real errno.
    if named and ret < 0:
        errno_value = _ERRNO_BY_NAME.get(named)
        if errno_value is None:
            # An errno name this harness cannot resolve is UNKNOWN, not zero and
            # not an accepted denial.  Guessing would reintroduce the very
            # coercion being fixed, so it is recorded as unresolved.
            return {
                "syscall": match.group("nr"),
                "return": ret,
                "errno": None,
                "errno_name": named,
                "errno_resolved": False,
                "denied": False,
                "timestamp": float(match.group("ts")) if match.group("ts") else None,
                "observed_pid": int(match.group("pid")) if match.group("pid") else None,
            }
        errno_value = int(errno_value)
    else:
        errno_value = -ret if ret < 0 else 0
    return {
        "syscall": match.group("nr"),
        "return": ret,
        "errno": errno_value,
        "errno_name": named or None,
        "errno_resolved": True,
        "denied": ret < 0 and errno_value in policy.ACCEPTED_DENIAL_ERRNOS,
        "timestamp": float(match.group("ts")) if match.group("ts") else None,
        "observed_pid": int(match.group("pid")) if match.group("pid") else None,
    }


def read_markers(path: Path) -> list[dict]:
    """Parse the leg's marker file: `<EVENT> wall=<sec>.<nsec> [k=v ...]`.

    The EVENT NAME COMES FIRST -- it is the whole point of the line.  An earlier
    revision assumed `wall=` led the line and therefore skipped every real line,
    which silently produced an empty timeline; the lesson is that a parser for a
    self-reported format must be written against the writer, not against an
    imagined one (see d3_note() in a12d3_d3_legs.c for the authoritative format).

    Rows are parsed defensively: an unparsable line is COUNTED and skipped, never
    guessed at, because a marker the harness cannot read is missing evidence and
    must not silently become evidence of the wrong kind.
    """
    events, unparsable = [], 0
    for line in Path(path).read_text(encoding="utf-8",
                                     errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        event = {"marker": parts[0], "wall": None, "detail": line}
        for token in parts[1:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key == "wall":
                try:
                    event["wall"] = float(value)
                except ValueError:
                    pass
            elif key not in event:
                event[key] = value
        if event["wall"] is None:
            unparsable += 1
            continue
        events.append(event)
    if unparsable:
        events.append({"marker": "UNPARSABLE_MARKER_LINES",
                       "count": unparsable, "wall": None})
    return events


# ---------------------------------------------------------------------------
# Ordered-timeline verification against the frozen sequence
# ---------------------------------------------------------------------------

def build_timeline(arm: dict) -> dict:
    """Extract the seven ordered sequence steps from RAW artifacts only.

    Sources are deliberately mixed, and NONE of them is this harness's own
    summary.  Process start comes from the external strace trace; the
    installation, barrier, and release come from the leg's own timestamped
    markers; the measurement, activation, and reconciliation are timed by this
    process but their CONTENT comes from the external inspector.

    `DESCRIPTOR_SET_MEASURED_EXTERNALLY`, `POLICY_ACTIVATION_EVIDENCED` and
    `DESCRIPTOR_ALLOWLIST_RECONCILED` are recorded at the instant the external
    reads returned, because those are observations rather than leg actions --
    there is no leg-side marker for them, and inventing one would let the leg
    self-report evidence about itself.
    """
    points = {}
    for event in arm["trace_events"]:
        if event["syscall"] in ("execve", "execveat") and \
                event.get("timestamp") is not None:
            if "LEG_PROCESS_START" not in points:
                points["LEG_PROCESS_START"] = event["timestamp"]
        if event.get("denied"):
            key = "FIRST_DENIAL_AFTER_RELEASE"
            if key not in points or event["timestamp"] < points[key]:
                points[key] = event["timestamp"]

    for marker in arm["markers"]:
        name = marker.get("marker")
        if name == "DENIAL_POLICY_INSTALLED":
            points["DENIAL_POLICY_INSTALLED"] = marker["wall"]
        elif name == "ENTRY_BARRIER_REACHING":
            points["ENTRY_BARRIER_REACHED"] = marker["wall"]
        elif name == "BUSINESS_LOGIC_RELEASED":
            points["BUSINESS_LOGIC_RELEASED"] = marker["wall"]
        elif name == "LEG_COMPLETED":
            points["LEG_COMPLETED"] = marker["wall"]

    measurement = arm.get("measurement_wall")
    if measurement is not None:
        points["DESCRIPTOR_SET_MEASURED_EXTERNALLY"] = measurement
        points["POLICY_ACTIVATION_EVIDENCED"] = measurement
        points["DESCRIPTOR_ALLOWLIST_RECONCILED"] = measurement

    timeline = inspector.ordered_timeline(points, tuple(predicate.SEQUENCE_STEPS),
                                          tuple(predicate.FORBIDDEN_SEQUENCE))
    return timeline


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_arm(arm: dict) -> dict:
    """Turn one arm's raw results into a conjunct set and a verdict."""
    timeline = build_timeline(arm)
    denied = [e for e in arm["trace_events"] if e.get("denied")]
    denied_syscalls = sorted({e["syscall"] for e in denied})
    killed = [e for e in arm["trace_events"]
              if e["syscall"] in ("tgkill", "kill") and
              e.get("errno") == 0]
    seccomp = arm["seccomp"]
    equality = arm["equality"]

    groups_ok = all(
        any(s in denied_syscalls for s in group)
        for group in (policy.NETWORK_CREATION_SYSCALLS,
                      policy.PROCESS_CREATION_SYSCALLS,
                      policy.EXEC_SYSCALLS))

    # Did THIS ARM actually attempt a denied operation?  Read from its own
    # marker file, which distinguishes an arm that attempted and was refused
    # from an arm that never attempted at all (it emits ATTEMPT_SKIPPED).
    #
    # This is deliberately separate from the *_DENIED_AFTER_LEG_ENTRY conjuncts.
    # Those conjuncts assert a property of the POLICY -- "creation is denied
    # after leg entry" -- and are satisfied by the arms that exercise it.  The
    # ATTEMPT failure code asserts a property of the ARM -- "it tried to reach
    # provider cognition".  Conflating them inverts the verdict at both ends:
    # a clean arm that never attempts would be labelled ATTEMPT (because no
    # denial exists to observe), and a genuine attempt arm would be labelled
    # clean (because its denial satisfied the conjunct).
    intent = [m for m in arm["markers"] if m.get("marker") == "ATTEMPT_INTENT"]
    attempted = bool(intent) and any(
        m.get("intent") == "reach_provider_cognition" for m in intent)
    attempt_intent = intent[0].get("intent") if intent else None
    attempt_skipped = attempt_intent == "none"

    # The errnos the kernel returned to THIS leg's denied calls, read from the
    # leg's own ATTEMPT_* markers.  These are the authoritative denial errnos:
    # the call and its return status are recorded by the process that made the
    # call.  The strace errno column is NOT a substitute -- it also carries the
    # tracer's own syscalls (a clone3 returning EPERM, for instance), so reading
    # denial errnos from the trace attributes a tracer artefact to the leg's
    # seccomp policy and can make a RET_ERRNO|EACCES policy look like EPERM.
    # read_markers() yields every key=value token as TEXT, because the marker
    # line is parsed generically and a value's type is not knowable from the
    # line alone.  Coerce explicitly: an int-only filter here silently produced
    # an EMPTY errno set while the markers plainly carried errno=13, which would
    # have let the receipt claim "no denial errnos" next to refuted denials.
    def _int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    leg_denial_errnos = sorted({
        errno_value for errno_value in
        (_int(m.get("errno")) for m in arm["markers"]
         if str(m.get("marker", "")).startswith("ATTEMPT_") and
         m.get("marker") != "ATTEMPT_INTENT")
        if errno_value})

    # ---- PER-LEG POSSESSION, ACROSS ALL THREE MEASURED DESCRIPTOR SETS ------
    # The two possession conjuncts are evaluated per leg over all three measured
    # descriptor sets.  An arm-level aggregate would be wrong twice over: it would
    # lose the ability to say WHICH leg carried the capability, and it would let
    # one leg's descriptors stand in for another's.
    possession = per_leg_possession(arm)

    conjuncts = {
        "LEG_ENTRY_IDENTITIES_PRECOMMITTED":
            bool(arm["precommit"]["leg_binary_sha256"]),
        "LEG_DESCRIPTOR_ALLOWLIST_PRECOMMITTED":
            bool(arm["precommit"]["descriptor_allowlist"]["allowlist_sha256"]),
        # Measured means: every leg was measured at its own barrier, every leg's
        # kernel seccomp state was independently verified, and the measured set is
        # exactly the precommitted three identities.
        "LEG_DESCRIPTOR_SET_MEASURED":
            possession["measured_leg_count"] == len(D2_LEG_IDENTITIES) and
            possession["all_legs_target_verified"] and
            possession["identities_match_precommit"],
        "NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED":
            not possession["legs_with_provider_descriptor"],
        "NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED":
            not possession["legs_with_broker_endpoint"],
        "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY":
            any(s in denied_syscalls for s in
                policy.NETWORK_CREATION_SYSCALLS),
        "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY":
            any(s in denied_syscalls for s in
                policy.PROCESS_CREATION_SYSCALLS),
        "EXEC_DENIED_AFTER_LEG_ENTRY":
            any(s in denied_syscalls for s in policy.EXEC_SYSCALLS),
        "KERNEL_DENIAL_POLICY_PRECOMMITTED":
            bool(arm["precommit"]["policy"]["filter_sha256"]),
        "KERNEL_DENIAL_POLICY_ACTIVE_AT_POINT_OF_USE": bool(
            seccomp.get("activation_evidenced_by_kernel")) and not killed,
        # ALL THREE legs.  This conjunct had no content while an arm ran a single
        # leg: "all three legs consumed the sealed response" was satisfied by one.
        # It now requires three distinct leg receipts, every point-of-use hash
        # equal to the captured response hash, and the honest legs complete --
        # which is what makes a negative arm evidence about the boundary rather
        # than about stopping executables.
        "HONEST_COUNTERFACTUAL_LEGS_COMPLETE":
            bool(arm.get("sealed_join", {}).get("leg_count") ==
                 len(D2_LEG_IDENTITIES)) and
            bool(arm.get("sealed_join", {}).get("legs_consumed_sealed_response"))
            and bool(arm.get("sealed_join", {}).get("point_of_use_hash_valid"))
            and bool(arm.get("sealed_join", {}).get(
                "same_captured_response_bound_to_all_legs"))
            and bool(arm.get("sealed_join", {}).get("no_response_substitution"))
            and possession["honest_legs_completed"],
        # The three former vacuous derivations.  They used to read
        # `count["records"] == 0` on files nothing wrote, so "the apparatus is
        # absent" and "no opportunity occurred" produced the SAME true value and
        # could never go false.  They are now measured against a REAL D2
        # gate+mock boundary that writes real records: each requires a populated
        # before-snapshot AND after == before.
        "D1_PROVIDER_OPPORTUNITY_DELTA_ZERO":
            bool(arm.get("provider_delta", {}).get("conjunct_value")),
        "TOTAL_MODEL_CELL_COUNT_UNCHANGED":
            bool(arm.get("cell_artifacts", {}).get("model_cell_count_unchanged"))
            and bool(arm.get("cell_artifacts", {}).get("model_cell_identity_same")),
        "ORDER_CELL_COUNT_UNCHANGED":
            bool(arm.get("cell_artifacts", {}).get("order_cell_count_unchanged"))
            and bool(arm.get("cell_artifacts", {}).get("order_cell_identity_same")),
        "ALL_CAPABILITY_BINDINGS_RECONCILED":
            bool(equality.get("measurement_valid")) and
            possession["all_legs_reconciled"],
    }
    result = predicate.evaluate_predicate(conjuncts)
    holds = bool(result["value"])

    # The reason is bound to the RAW signals that produced it, so a failure code
    # always travels with the descriptor/syscall/endpoint that justifies it.  A
    # bare code would be an assertion; the binding makes it auditable.
    reason = predicate.map_reason(conjuncts, extra_signals={
        "provider_capable_descriptors": {
            "undeclared_but_measured": equality.get("undeclared_but_measured"),
            "declared_but_unmeasured": equality.get("declared_but_unmeasured"),
            "measured_non_stdio_identities":
                equality.get("measured_non_stdio_identities"),
            # WHICH LEG.  The frozen vocabulary is only actionable if the failure
            # travels with the leg and endpoint that earned it; a code without a
            # leg is an assertion rather than a finding.
            "legs_with_provider_descriptor":
                possession["legs_with_provider_descriptor"],
        },
        "broker_endpoints": {
            "broker_channel_identities": broker_identities(arm),
            "legs_with_broker_endpoint": possession["legs_with_broker_endpoint"],
        },
        "network_denials": {
            "denied": sorted({e["syscall"] for e in denied
                              if e["syscall"] in policy.NETWORK_CREATION_SYSCALLS}),
        },
        "process_denials": {
            "denied": sorted({e["syscall"] for e in denied
                              if e["syscall"] in policy.PROCESS_CREATION_SYSCALLS}),
        },
        "exec_denials": {
            "denied": sorted({e["syscall"] for e in denied
                              if e["syscall"] in policy.EXEC_SYSCALLS}),
        },
    })
    # An ARM that attempted a denied operation reports ATTEMPT, and this
    # escalates OVER the conjunct-derived reason.
    #
    # The escalation direction matters.  map_reason() reads the conjuncts, and
    # the conjuncts are predominantly properties of the POLICY and the
    # ENVIRONMENT (is the filter active, was the descriptor set measured, did
    # D1 count zero).  An arm that possessed a provider socket AND attempted to
    # use it satisfies both readings; the more specific and more serious finding
    # is the possession, which map_reason already ranks first.  So ATTEMPT is
    # applied only when possession and broker reachability are both clean --
    # exactly the case where the arm's own attempt is the whole story.  The
    # reason still travels with the syscalls the kernel refused.
    if attempted and reason["reason"] == predicate.NO_FAILURE:
        reason = {
            "reason": predicate.PROVIDER_CAPABILITY_ATTEMPT,
            "reason_kind": "ATTEMPTED_USE_DENIED",
            "bound_signals": {
                "attempt_intent": attempt_intent,
                "denied_syscalls": denied_syscalls,
                "leg_denial_errnos": leg_denial_errnos,
            },
        }

    # ── Reconciling two readings that are both correct, and are not the same
    #    question ──────────────────────────────────────────────────────────────
    #
    # `holds` answers: DID THE DENIAL BOUNDARY HOLD?  For D3-C and D3-D it is
    # True, and that is the right answer -- the kernel refused the socket, the
    # fork, and the exec, so every *_DENIED_AFTER_LEG_ENTRY conjunct is
    # satisfied.  The boundary did its job.
    #
    # `semantic_ok` answers the question the arm was built to ask: IS THIS A
    # LEG THAT COULD HAVE REACHED PROVIDER COGNITION?  For D3-C and D3-D it is
    # False, and that is also the right answer -- an arm that TRIED, and had to
    # be refused, has already failed the counterfactual.  A refusal is evidence
    # that the governance worked; it is not evidence that the leg was clean.
    #
    # The frozen ARM_EXPECTATION encodes the second question, so the frozen
    # vocabulary governs: an arm that possessed a capability, or reached a
    # broker, or attempted a use, fails -- regardless of whether the attempt was
    # denied.  Reporting `holds` here would mark D3-C and D3-D as PASSING legs,
    # which inverts the entire point of having falsifier arms: the harness would
    # be certifying that an arm which reached for provider cognition was
    # governed, when the finding is that it reached at all.
    #
    # So `holds` is preserved verbatim as the boundary reading, and
    # `semantic_ok` -- the value the contract checks -- additionally requires
    # that no failure code was bound.
    semantic_ok = holds and reason["reason"] == predicate.NO_FAILURE

    check = predicate.check_arm_expectation(arm["arm"], semantic_ok,
                                            reason["reason"])
    expected_hold, expected_code = predicate.ARM_EXPECTATION.get(
        arm["arm"], (True, predicate.NO_FAILURE))

    return {
        "arm": arm["arm"], "role": arm["role"],
        "conjuncts": conjuncts, "predicate": result,
        "holds": holds,
        "holds_denial_boundary": holds,
        "semantic_ok": semantic_ok,
        "structural_defect": result["structural_defect"],
        "missing_conjuncts": result["missing_conjuncts"],
        "falsified_conjuncts": result["falsified_conjuncts"],
        "failure_code": reason["reason"],
        "arm_attempted_denied_ops": attempted,
        "attempt_intent": attempt_intent,
        "attempt_skipped": attempt_skipped,
        "failure_kind": reason["reason_kind"],
        "failure_bound_signals": reason["bound_signals"],
        "leg_denial_errnos": leg_denial_errnos,
        # The leg's denial errnos must equal the errno the PRECOMMITTED policy
        # declares.  This is the check that ties what the kernel returned to the
        # policy whose hash is in the receipt: without it, a leg could report
        # errno=1 (EPERM, a different enforcement mechanism entirely) and still
        # satisfy "a denial was observed".
        "leg_errno_matches_policy": bool(leg_denial_errnos) and
            set(leg_denial_errnos) == {policy.DENIED_ERRNO},
        "policy_denied_errno": policy.DENIED_ERRNO,
        # ── The de-vacuumed measurements, carried through to the receipt ──────
        # These four blocks are the EVIDENCE for four of the fifteen conjuncts:
        # the D1 delta, the real cell counts, the D2 identity join, and the
        # sealed identity itself.  The conjuncts evaluate correctly without
        # them, because evaluate_arm receives the whole run dict -- but a
        # conjunct whose evidence never reaches the receipt is a claim with no
        # artifact behind it, and a reader (or an independent checker) cannot
        # recompute what was not published.  They were being silently dropped.
        "provider_delta": arm.get("provider_delta"),
        "provider_before": arm.get("provider_before"),
        "provider_after": arm.get("provider_after"),
        "cell_artifacts": arm.get("cell_artifacts"),
        "sealed_identity": arm.get("sealed_identity"),
        "sealed_join": arm.get("sealed_join"),
        # Per-leg possession across ALL THREE measured descriptor sets, naming
        # which leg carried which capability.  Published because the two
        # possession conjuncts are now per-leg statements: a reader must be able
        # to see WHICH leg earned the failure, not just that one occurred.
        "possession": possession,
        "leg_measurements": arm.get("leg_measurements"),
        "leg_plan": arm.get("leg_plan"),
        "offender_identity": possession["offender_identity"],
        "offender_injection": possession["offender_injection"],
        "honest_legs": possession["honest_legs"],
        "honest_legs_completed": possession["honest_legs_completed"],
        "measured_non_stdio_identities":
            equality.get("measured_non_stdio_identities"),
        "expected_predicate_holds": expected_hold,
        "expected_failure_code": expected_code,
        "expectation_met": check["control_ok"],
        "expectation_detail": check,
        "timeline": timeline,
        "forbidden_sequence_observed": timeline.get(
            "forbidden_sequence_observed"),
        "denied_syscalls": denied_syscalls,
        "denied_event_count": len(denied),
        "denial_errnos": sorted({e["errno"] for e in denied}),
        "kill_action_observed": bool(killed),
        "all_denial_groups_denied": groups_ok,
        "seccomp_raw": seccomp.get("seccomp_raw"),
        "seccomp_filter_count": seccomp.get("seccomp_filter_count"),
        "activation_evidenced_by_kernel":
            seccomp.get("activation_evidenced_by_kernel"),
        "target_verified": seccomp.get("target_verified"),
        # REPLACED.  This used to be
        #   all(count["records"] == 0 for count in arm["ledgers"].values())
        # i.e. "every ledger is empty" -- the vacuous reading the whole round was
        # about, still sitting in the receipt after the conjunct itself was
        # fixed.  It is now the MEASURED delta, which requires the ledgers to be
        # populated and unchanged.
        "provider_delta_zero":
            bool((arm.get("provider_delta") or {}).get("conjunct_value")),
        "provider_delta_detail":
            (arm.get("provider_delta") or {}).get("delta"),
    }


def broker_identities(arm: dict) -> list:
    """Identities of non-stdio descriptors held at measurement time."""
    return sorted(entry.get("identity") or "UNRESOLVED"
                  for entry in arm["descriptors"].get("descriptors", [])
                  if entry["fd"] not in (0, 1, 2))


def conjunct_leg_completed(arm: dict) -> bool:
    return any(m.get("marker") == "LEG_COMPLETED" for m in arm["markers"])


def per_leg_possession(arm: dict) -> dict:
    """Evaluate the two possession conjuncts PER LEG over all three measured sets.

    Returns a record that always NAMES the leg and the endpoint identity that
    carried the capability.  A bare boolean would leave the report unable to say
    where the capability was, and the failure vocabulary is only useful if it
    travels with the leg that earned it.

    The classification is by BOUND PEER, not descriptor appearance: D3-B and D3-E
    both hold an AF_UNIX stream socket, and asking "is there a non-stdio socket?"
    would answer TRUE for both.  The declared endpoint identity is what separates
    an inherited provider socket from a broker channel, and it is read from the
    PRECOMMIT (declared before launch), with possession confirmed against the
    per-leg MEASUREMENT.
    """
    measurements = arm.get("leg_measurements") or []
    declared = set(arm["precommit"].get("declared_expected_identities") or [])
    offender_identity = arm.get("offender_identity") or OFFENDER_LEG.get(
        arm.get("arm"))
    offender_injection = arm.get("offender_injection") or ARM_INJECTION.get(
        arm.get("arm"))
    allowlist_identities = set(
        (arm["precommit"].get("descriptor_allowlist") or {}).get(
            "declared_expected_identities") or []) | set(
        (arm["precommit"].get("descriptor_allowlist") or {}).get(
            "allowed_identities") or [])

    legs_with_provider, legs_with_broker = [], []
    per_leg = {}
    for measurement in measurements:
        identity = measurement.get("identity")
        non_stdio = [
            entry for entry in
            (measurement.get("descriptors") or {}).get("descriptors", [])
            if entry.get("fd") not in (0, 1, 2)]
        # An endpoint is a provider capability if the identity it is registered
        # against is declared as one.  `inherited_provider_socket` is declared by
        # D3-B; `broker_channel` by D3-E.  Both are capabilities; only the second
        # is a broker.
        endpoint_identities = sorted({
            str(entry.get("identity")) for entry in non_stdio
            if entry.get("identity")})
        carries_provider = bool(
            non_stdio and "inherited_provider_socket" in declared)
        carries_broker = bool(non_stdio and "broker_channel" in declared)
        per_leg[identity] = {
            "identity": identity,
            "injection": measurement.get("injection"),
            "is_offender": identity == offender_identity,
            "non_stdio_fd_count": len(non_stdio),
            "endpoint_identities": endpoint_identities,
            "carries_provider_capability": carries_provider,
            "carries_broker_endpoint": carries_broker,
        }
        if carries_provider:
            legs_with_provider.append({
                "leg_identity": identity,
                "endpoint_identities": endpoint_identities,
                "declared_identity": "inherited_provider_socket"})
        if carries_broker:
            legs_with_broker.append({
                "leg_identity": identity,
                "endpoint_identities": endpoint_identities,
                "declared_identity": "broker_channel"})

    # Honest legs are those WITHOUT the arm's injection.  In a negative arm the
    # two honest legs must complete normally -- that is what distinguishes
    # "the boundary denied a possessed capability" from "the harness stopped the
    # executables".
    honest = [m["identity"] for m in measurements
              if m.get("injection") == "none"]
    offender = [m["identity"] for m in measurements
                if m.get("injection") not in (None, "none")]
    join = arm.get("sealed_join") or {}
    per_leg_join = join.get("per_leg") or {}
    honest_joined = [identity for identity in honest if identity in per_leg_join]
    # The field is `matches_captured_response`.  Reading a name that does not
    # exist yields None, and `all()` over Nones is False -- which looks like a
    # correct refusal but is really a typo, and it hid a fully green three-leg
    # join behind a failed conjunct.  A missing key is therefore made EXPLICIT:
    # it is a defect in the derivation, not evidence about the leg.
    _MATCH_KEY = "matches_captured_response"
    _honest_rows = [per_leg_join.get(identity) or {} for identity in honest]
    _honest_fields_present = bool(_honest_rows) and all(
        _MATCH_KEY in row for row in _honest_rows)
    honest_completed = (bool(honest) and _honest_fields_present and
                        all(row[_MATCH_KEY] for row in _honest_rows) and
                        len(honest_joined) == len(honest))

    equality_per_leg = arm.get("equality_per_leg") or {}
    all_legs_reconciled = bool(measurements) and all(
        (equality_per_leg.get(m["identity"]) or {}).get("measurement_valid")
        for m in measurements)

    return {
        "measured_leg_count": len(measurements),
        "measured_identities": [m["identity"] for m in measurements],
        "all_legs_target_verified": bool(measurements) and all(
            (m.get("seccomp") or {}).get("target_verified")
            for m in measurements),
        "identities_match_precommit": sorted(
            m["identity"] for m in measurements) == sorted(D2_LEG_IDENTITIES),
        "offender_identity": offender_identity,
        "offender_injection": offender_injection,
        "offender_legs": offender,
        "honest_legs": honest,
        "honest_legs_joined": sorted(honest_joined),
        "honest_legs_completed": honest_completed,
        "all_legs_reconciled": all_legs_reconciled,
        "declared_identities": sorted(declared),
        "allowlist_identities": sorted(allowlist_identities),
        "legs_with_provider_descriptor": legs_with_provider,
        "legs_with_broker_endpoint": legs_with_broker,
        "per_leg": per_leg,
    }


def broker_capability_present(arm: dict) -> bool:
    """Does this arm hold a channel to a broker endpoint?

    D3-E requires this to be TRUE so the arm fails on the channel's existence.
    The check is on the MEASURED set, so it is possession, not use.

    THE DISTINCTION IS BY BOUND PEER, NOT BY DESCRIPTOR APPEARANCE.  Both D3-B
    and D3-E hold an AF_UNIX stream socket, and the measured identities are
    nearly indistinguishable -- one is registered against the provider gate, the
    other against the broker peer.  A test that asked "is there a non-stdio
    socket?" would return TRUE for both and, because INHERITED is checked first,
    D3-E could only ever be reported as INHERITED.  PROVIDER_BROKER_REACHABLE
    would then be a code the harness could never emit -- an unreachable branch
    masquerading as a control.

    Read against the actual outcome, D3-B and D3-E differ in the one way that
    matters: D3-B's peer would ANSWER as a provider, D3-E's peer would TRANSLATE
    the leg's bytes into a provider request.  Both are capabilities, but only
    the second is a broker, so both the precommit and the measurement must carry
    which is which.
    """
    declared = set(arm["precommit"].get("declared_expected_identities") or [])
    if "broker_channel" not in declared:
        return False
    # Declared as a broker channel AND actually measured holding it.  The
    # declaration alone is not possession: the arm must be observed to hold the
    # descriptor, otherwise a precommit typo would condemn a clean arm.
    return any(entry.get("identity") and entry["fd"] not in (0, 1, 2)
               for entry in arm["descriptors"].get("descriptors", []))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    print("harness: %s" % HARNESS_VERSION)

    policy_self_check = policy.policy_self_check()
    print("policy self-check: %s" % json.dumps(policy_self_check,
                                               sort_keys=True))
    if not all(v for k, v in policy_self_check.items() if isinstance(v, bool)):
        print("REFUSING: policy self-check failed")
        return 2

    if os.environ.get("D3_EXECUTE") != "1":
        # Refuse loudly rather than emitting a receipt full of null arms with a
        # success exit code: an all-null receipt that exits 0 is a fail-open,
        # because "no arm ran" is indistinguishable from "every arm passed" to
        # any reader that only looks at the exit status.
        print("REFUSING: D3_EXECUTE=1 is required to run the arms "
              "(silent empty receipts are not evidence)")
        return 2

    arms = {}
    for arm in predicate.ARM_ORDER:
        result = evaluate_arm(run_arm(arm))
        arms[arm] = result
        if result:
            # Print BOTH readings.  `boundary` is whether the denial policy held
            # (True for every arm that probes); `semantic` is the contract
            # verdict (an arm that possessed, reached, or attempted fails).
            # Printing only one would let a reader mistake a working boundary
            # for a clean leg, or vice versa.
            print("arm %s: boundary_holds=%s semantic_ok=%s code=%s "
                  "expectation_met=%s"
                  % (arm, result["holds"], result["semantic_ok"],
                     result["failure_code"], result["expectation_met"]))

    # ---- The DELTA falsifier (D3-X) ---------------------------------------
    # Run alongside the five measurement arms but reported SEPARATELY: it is not
    # an arm outcome, it is the proof that D1_PROVIDER_OPPORTUNITY_DELTA_ZERO is
    # a live measurement rather than a constant.  A conjunct that can never be
    # made false is not measuring anything, so this result is a precondition of
    # the whole predicate, not a sixth arm.
    falsifier_run = run_arm(FALSIFIER_INJECTION_ARMS[0])
    falsifier_delta = falsifier_run.get("provider_delta", {})
    falsifier = {
        "arm": FALSIFIER_INJECTION_ARMS[0],
        "before": {n: (falsifier_run.get("provider_before", {}).get(n) or {})
                   .get("records") for n in boundary_module.LEDGER_NAMES},
        "after": {n: (falsifier_run.get("provider_after", {}).get(n) or {})
                  .get("records") for n in boundary_module.LEDGER_NAMES},
        "delta": falsifier_delta.get("delta"),
        "conjunct_value_with_injection": falsifier_delta.get("conjunct_value"),
        "boundary_populated_before": falsifier_delta.get(
            "boundary_populated_before"),
        "injection": falsifier_run.get("falsifier_injection"),
        "offending_records_published": len(
            falsifier_delta.get("offending_records") or []),
        "offenders_path": str(Path(falsifier_run.get("arm_dir", ""))
                              / "delta-offenders.json"),
    }
    # ── WHAT "PROVED LIVE" MEANS, WITH F1 AND F1b SEPARATED ────────────────────
    #
    # `falsifier_delta` is the ARM's own delta: before-snapshot -> the state when the
    # legs completed, taken BEFORE the falsifier injected.  On D3-X that is
    # correctly ZERO, because the arm's own run must produce no extra provider
    # opportunity.  F1's delta is a DIFFERENT number and lives in the injection
    # record, measured against that same baseline immediately after F1 was injected.
    #
    # The old test was `conjunct_value is False` -- require the conjunct to FLIP
    # FALSE.  That was right while every arm shared one expected shape, because 2/1/1
    # is not 1/1/1 and the conjunct necessarily went false.  It is the wrong test
    # once the falsifier arm is graded against the frozen F1 shape per the gate's
    # ruling: after a CORRECT injection the conjunct is correctly TRUE.
    #
    # Liveness is therefore proved by all of:
    #   * the ARM's own delta is zero            (the run itself opened no opportunity)
    #   * F1's delta is EXACTLY the frozen shape  (the injected cause, not drift)
    #   * the boundary was POPULATED beforehand   (there was something to move FROM)
    #   * the conjunct is TRUE on that shape      (it grades the injected delta)
    f1_injection = falsifier_run.get("falsifier_injection") or {}
    f1_observed_delta = f1_injection.get("delta_after_injection")
    falsifier["frozen_f1_delta_expected"] = dict(F1_FROZEN_DELTA)
    falsifier["arm_own_delta"] = falsifier_delta.get("delta")
    falsifier["arm_own_delta_is_zero"] = all(
        v == 0 for v in (falsifier_delta.get("delta") or {}).values()) \
        and bool(falsifier_delta.get("delta"))
    falsifier["f1_observed_delta"] = f1_observed_delta
    falsifier["f1_delta_is_frozen_shape"] = bool(
        f1_observed_delta == dict(F1_FROZEN_DELTA))
    falsifier["frozen_shape_matches"] = bool(
        f1_injection.get("frozen_shape_matches"))
    falsifier["delta_moved"] = bool(
        f1_observed_delta and any(v > 0 for v in f1_observed_delta.values()))
    falsifier["conjunct_true_on_injected_delta"] = (
        falsifier_delta.get("conjunct_value") is True)
    falsifier["supplemental_f1b"] = (
        f1_injection.get("supplemental_falsifier") or {})
    falsifier["proves_delta_is_live_measurement"] = bool(
        falsifier["arm_own_delta_is_zero"]
        and falsifier["delta_moved"]
        and falsifier["f1_delta_is_frozen_shape"]
        and falsifier["frozen_shape_matches"]
        and falsifier_delta.get("boundary_populated_before")
        and falsifier["conjunct_true_on_injected_delta"])
    print("falsifier %s: arm_delta=%s f1_delta=%s frozen=%s proved_live=%s "
          "f1b_full_traverse=%s"
          % (falsifier["arm"], falsifier["arm_own_delta"], f1_observed_delta,
             falsifier["f1_delta_is_frozen_shape"],
             falsifier["proves_delta_is_live_measurement"],
             falsifier["supplemental_f1b"].get("is_full_traverse")))

    receipt = {
        "harness_version": HARNESS_VERSION,
        "predicate": predicate.PREDICATE_NAME,
        "predicate_text": predicate.COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED_TEXT,
        "failure_vocabulary": list(predicate.FAILURE_VOCABULARY),
        "conjunct_count": len(predicate.CONJUNCTS),
        "policy_self_check": policy_self_check,
        "arms": arms,
        "delta_falsifier": falsifier,
        "all_arms_meet_contract": all(
            a is not None and a["expectation_met"] for a in arms.values())
        and falsifier["proves_delta_is_live_measurement"],
        "generated_wall": time.time(),
    }
    atomic_write_json(WORK_ROOT / "receipt.json", receipt)
    print("receipt: %s" % (WORK_ROOT / "receipt.json"))
    if receipt["all_arms_meet_contract"]:
        print("ALL_ARMS_MEET_CONTRACT: True")
        return 0
    print("ALL_ARMS_MEET_CONTRACT: False")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
