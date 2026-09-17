#!/usr/bin/env python3
"""EPOCH-2 LINEAGE (third-party ruling recorded in benchmarks/fam-c/
EPOCH-1-CLOSURE.md: "EPOCH-2 PROTOCOL (a)" + "TERMINAL-OUTCOME PROGRESS
SEMANTICS").

Epoch 1 is CLOSED — terminated-not-repaired, immutable at its recorded
FINAL protocol and execution locks. Its state tree (benchmarks/fam-c/
state/**) is historical evidence and MUST NOT be amended, reclassified,
replayed into, or used to satisfy cells in a later epoch. Epoch 2
therefore exists as an EXPLICIT, on-disk lineage:

  * transition record `EPOCH-2-TRANSITION.json` at the Fam-C root. It
    cites the epoch-1 closure facts — the closure record's own sha256 and
    the recorded FINAL lock bytes (EXECUTION-LOCK.json sha256
    f6616ea2..., PROTOCOL-LOCK.json sha256 96eac57b...) — so the epoch
    boundary is anchored to the closed epoch, not to a later mutable
    state. A structurally valid record ACTIVATES epoch 2; without one the
    tree behaves exactly as epoch 1 (the historical layout, which keeps
    every hermetic fixture working unchanged);
  * fresh epoch-2 lock files (`EXECUTION-LOCK-EPOCH2.json`,
    `PROTOCOL-LOCK-EPOCH2.json`) that carry `epoch: 2` plus a `transition`
    block citing the record and the same epoch-1 closure hashes, and that
    start their OWN append-only amendment lineage (amendments: [] at the
    transition — never an amendment to the epoch-1 lineage). They mint
    OPEN and finalize later under the standard flow;
  * an epoch-2 state root `state/epoch2/`: every derive_paths() namespace
    (runs and capability dirs) is prefixed with it, so epoch-2
    completed_cells()/cell_state()/specificity walks can never advance on
    epoch-1 evidence and epoch-1 state is never written to.

Epoch-1 locks keep their recorded FINAL bytes forever; in epoch 2 they are
checked as HISTORICAL records (byte sha256 against the closure-cited
values + the recorded status), never as the live harness/protocol
authority — the epoch-2 locks are the authority the moment the record
exists. Stdlib only; every reader fails closed.
"""
import hashlib
import json
import os
import re

EPOCH_ID = "epoch2"
EPOCH_NUMBER = 2
FROM_EPOCH = 1
STATE_SUBDIR = "epoch2"
STATE_PREFIX = "state/epoch2"
TRANSITION_FILE = "EPOCH-2-TRANSITION.json"
EXECUTION_LOCK_FILE = "EXECUTION-LOCK-EPOCH2.json"
PROTOCOL_LOCK_FILE = "PROTOCOL-LOCK-EPOCH2.json"
EPOCH1_CLOSURE_FILE = "EPOCH-1-CLOSURE.md"
EPOCH1_EXECUTION_LOCK_FILE = "EXECUTION-LOCK.json"
EPOCH1_PROTOCOL_LOCK_FILE = "PROTOCOL-LOCK.json"

# The epoch-1 closure facts (EPOCH-1-CLOSURE.md, ruling 2026-09-17). The
# transition record must cite these verbatim; a record naming other bytes
# is not a transition FROM the closed epoch and never activates epoch 2.
EPOCH1_EXECUTION_LOCK_SHA256 = (
    "f6616ea2a495ae3f5a5d2f5d5b35b503eddc9aaca21a43358d756c1bd49b0f24")
EPOCH1_PROTOCOL_LOCK_SHA256 = (
    "96eac57be905b2f030f02615e4774d2a9ac2adab8c7e1aa26fe3e39efe695a54")
EPOCH1_FINALIZATION_COMMIT = "1e146279077b8b442e8c0542887349156aa4571f"
EPOCH1_CERTIFICATION_REF = "2a1309d302440ef060a436b31152fb646758840a"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")


def _sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def transition_path(fam_c_dir):
    return os.path.join(fam_c_dir, TRANSITION_FILE)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def transition_record(fam_c_dir):
    """The ACTIVE epoch-2 transition record, or None.

    STRUCTURAL activation (read on every path derivation): the record must
    be a JSON object that names epoch 2, the epoch-2 state prefix, the two
    epoch-2 lock files, it must cite the recorded epoch-1 closure lock
    hashes verbatim, and it must cite the closure record's ACTUAL bytes
    (closure_record_sha256 == sha256 of EPOCH-1-CLOSURE.md on disk). A
    record whose citation does not match the frozen closure record does
    not activate epoch 2 (fail closed: the epoch boundary is anchored to
    the closed epoch, never to a later edit). Malformed/absent => None
    (epoch 1). The authoritative field-by-field audit (epoch-1 lock bytes
    on disk, epoch-2 lock binding) lives in validate_record() /
    validate_transition(), which preflight runs."""
    try:
        obj = _read_json(transition_path(fam_c_dir))
    except (ValueError, OSError):
        return None
    if not isinstance(obj, dict):
        return None
    for key, want in (("to_epoch", EPOCH_NUMBER),
                      ("from_epoch", FROM_EPOCH),
                      ("epoch_id", EPOCH_ID),
                      ("state_prefix", STATE_PREFIX),
                      ("execution_lock", EXECUTION_LOCK_FILE),
                      ("protocol_lock", PROTOCOL_LOCK_FILE),
                      ("epoch1_closure_record", EPOCH1_CLOSURE_FILE),
                      ("epoch1_execution_lock_sha256",
                       EPOCH1_EXECUTION_LOCK_SHA256),
                      ("epoch1_protocol_lock_sha256",
                       EPOCH1_PROTOCOL_LOCK_SHA256)):
        if obj.get(key) != want:
            return None
    try:
        with open(os.path.join(fam_c_dir, EPOCH1_CLOSURE_FILE), "rb") as f:
            closure_sha = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None
    if obj.get("closure_record_sha256") != closure_sha:
        return None
    return obj


def is_epoch2(fam_c_dir):
    """True iff the tree carries a structurally valid epoch-2 transition
    record (see transition_record()). Epoch 1 otherwise."""
    return transition_record(fam_c_dir) is not None


def active_epoch(fam_c_dir):
    return EPOCH_NUMBER if is_epoch2(fam_c_dir) else FROM_EPOCH


def state_root(fam_c_dir):
    """The ACTIVE epoch's persistent state root: state/epoch2 under epoch 2
    (epoch-1 state/ is untouched and never scanned by epoch-2 walks),
    state/ under epoch 1."""
    if is_epoch2(fam_c_dir):
        return os.path.join(fam_c_dir, "state", STATE_SUBDIR)
    return os.path.join(fam_c_dir, "state")


def lock_path(fam_c_dir, name):
    """Path of one lock file: the epoch-2 lock under epoch 2, else the
    historical path."""
    if name in (EXECUTION_LOCK_FILE, PROTOCOL_LOCK_FILE):
        return os.path.join(fam_c_dir, name)
    if is_epoch2(fam_c_dir):
        return os.path.join(fam_c_dir, {
            EPOCH1_EXECUTION_LOCK_FILE: EXECUTION_LOCK_FILE,
            EPOCH1_PROTOCOL_LOCK_FILE: PROTOCOL_LOCK_FILE}.get(name, name))
    return os.path.join(fam_c_dir, name)


def active_lock_names(fam_c_dir):
    """(execution, protocol) lock file names of the ACTIVE epoch."""
    if is_epoch2(fam_c_dir):
        return (EXECUTION_LOCK_FILE, PROTOCOL_LOCK_FILE)
    return (EPOCH1_EXECUTION_LOCK_FILE, EPOCH1_PROTOCOL_LOCK_FILE)


def genesis_base_map(record):
    """The epoch-2 per-file genesis base recorded in the transition record
    ({governed file: sha256} of the bytes at the transition). Returns {}
    when absent/malformed — callers fail closed."""
    base = record.get("genesis") if isinstance(record, dict) else None
    out = {}
    if isinstance(base, dict):
        for fn, sha in base.items():
            if isinstance(fn, str) and isinstance(sha, str) \
                    and _HEX64.match(sha):
                out[fn] = sha
    return out


def validate_record(fam_c_dir):
    """The epoch BOUNDARY audit (protocol authority, V2): the transition
    record exists, satisfies the structural activation contract, cites the
    closure record's OWN bytes, cites the closure-recorded epoch-1
    finalization facts, and carries a non-empty genesis base map whose
    entries are 64-hex. Returns findings (empty = green)."""
    out = []
    rec = transition_record(fam_c_dir)
    if rec is None:
        return ["EPOCH-2-TRANSITION: no structurally valid "
                f"{TRANSITION_FILE} under {fam_c_dir} (epoch 2 is not "
                "active)"]
    p = transition_path(fam_c_dir)
    try:
        with open(p, "rb") as f:
            rec_sha = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        return [f"EPOCH-2-TRANSITION: record unreadable: {e}"]
    if not _HEX64.match(str(rec.get("closure_record_sha256") or "")):
        out.append("EPOCH-2-TRANSITION: closure_record_sha256 is not "
                   "64-lowercase-hex")
    cp = os.path.join(fam_c_dir, EPOCH1_CLOSURE_FILE)
    try:
        with open(cp, "rb") as f:
            closure_sha = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        out.append(f"EPOCH-2-TRANSITION: {EPOCH1_CLOSURE_FILE} unreadable: "
                   f"{e}")
    else:
        if rec.get("closure_record_sha256") != closure_sha:
            out.append("EPOCH-2-TRANSITION: the record cites closure "
                       f"record bytes "
                       f"{str(rec.get('closure_record_sha256'))[:12]} but "
                       f"the on-disk {EPOCH1_CLOSURE_FILE} hashes to "
                       f"{closure_sha[:12]} (the epoch boundary must cite "
                       f"the frozen closure record, never a later edit)")
    if rec.get("epoch1_finalization_commit") != EPOCH1_FINALIZATION_COMMIT:
        out.append("EPOCH-2-TRANSITION: epoch1_finalization_commit "
                   f"{rec.get('epoch1_finalization_commit')!r} != the "
                   f"closure-recorded {EPOCH1_FINALIZATION_COMMIT}")
    if rec.get("epoch1_certification_ref") != EPOCH1_CERTIFICATION_REF:
        out.append("EPOCH-2-TRANSITION: epoch1_certification_ref "
                   f"{rec.get('epoch1_certification_ref')!r} != the "
                   f"closure-recorded {EPOCH1_CERTIFICATION_REF}")
    if not genesis_base_map(rec):
        out.append("EPOCH-2-TRANSITION: the record carries no genesis base "
                   "map (the transition-time governed bytes); the epoch-2 "
                   "protocol lock has no verifiable base")
    return out


def validate_epoch1_historical_lock(fam_c_dir, name, want_sha, prefix):
    """An epoch-1 FINAL lock in the epoch-2 world is a HISTORICAL record:
    its bytes must still hash to the closure-cited sha256 and it must still
    record status FINAL. It is never the live harness/protocol authority
    (the epoch-2 locks are). Returns findings (empty = green)."""
    out = []
    p = os.path.join(fam_c_dir, name)
    if not os.path.isfile(p):
        return [f"{prefix}: epoch-1 historical lock {name} missing at "
                f"the recorded path (the epoch-1 closure record pins its "
                f"bytes; epoch 2 must not delete or move it)"]
    try:
        with open(p, "rb") as f:
            live = hashlib.sha256(f.read()).hexdigest()
        with open(p) as f:
            obj = json.load(f)
    except (OSError, ValueError) as e:
        return [f"{prefix}: epoch-1 historical lock {name} unreadable: {e}"]
    if live != want_sha:
        out.append(f"{prefix}: epoch-1 historical lock {name} bytes "
                   f"{live[:12]} != the closure-recorded sha256 "
                   f"{want_sha[:12]} (epoch-1 is immutable at its recorded "
                   f"FINAL bytes)")
    if not isinstance(obj, dict) or obj.get("status") != "FINAL":
        st = obj.get("status") if isinstance(obj, dict) else None
        out.append(f"{prefix}: epoch-1 historical lock {name} status "
                   f"{st!r} != 'FINAL' (the closure record's terminal "
                   f"state is part of the historical bytes)")
    return out


def validate_epoch2_lock_binding(fam_c_dir, lock_name, prefix):
    """One epoch-2 lock's transition binding: `epoch: 2`, a `transition`
    block citing the record (name + sha256 of its bytes) and the epoch-1
    closure lock hashes, a non-terminal amendment lineage (a list; no FINAL
    amendment at the transition — the fresh lineage starts OPEN), and the
    shared instance freeze. Returns findings (empty = green)."""
    out = []
    rec = transition_record(fam_c_dir)
    if rec is None:
        return [f"{prefix}: {lock_name} cites a transition record that is "
                f"not validly present (epoch 2 is not active)"]
    try:
        with open(transition_path(fam_c_dir), "rb") as f:
            rec_sha = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        return [f"{prefix}: transition record unreadable: {e}"]
    p = os.path.join(fam_c_dir, lock_name)
    if not os.path.isfile(p):
        return [f"{prefix}: epoch-2 lock {lock_name} missing (the "
                f"transition record names it; mint it via "
                f"harness/epoch_transition.py)"]
    try:
        with open(p) as f:
            lock = json.load(f)
    except (OSError, ValueError) as e:
        return [f"{prefix}: epoch-2 lock {lock_name} unparsable: {e}"]
    if not isinstance(lock, dict):
        return [f"{prefix}: epoch-2 lock {lock_name} is not a JSON object"]
    if lock.get("epoch") != EPOCH_NUMBER:
        out.append(f"{prefix}: epoch-2 lock {lock_name} does not carry "
                   f"epoch: {EPOCH_NUMBER} (got {lock.get('epoch')!r})")
    tr = lock.get("transition")
    if not isinstance(tr, dict):
        out.append(f"{prefix}: epoch-2 lock {lock_name} carries no "
                   f"transition citation block")
    else:
        for key, want in (("record", TRANSITION_FILE),
                          ("record_sha256", rec_sha),
                          ("from_epoch", FROM_EPOCH),
                          ("epoch1_closure_record", EPOCH1_CLOSURE_FILE),
                          ("epoch1_execution_lock_sha256",
                           EPOCH1_EXECUTION_LOCK_SHA256),
                          ("epoch1_protocol_lock_sha256",
                           EPOCH1_PROTOCOL_LOCK_SHA256)):
            if tr.get(key) != want:
                out.append(f"{prefix}: epoch-2 lock {lock_name} "
                           f"transition.{key} {tr.get(key)!r} != {want!r}")
    am = lock.get("amendments")
    if not isinstance(am, list):
        out.append(f"{prefix}: epoch-2 lock {lock_name} amendments is not "
                   f"a list (the new lineage is an append-only list)")
    # The terminal-state rules of the FRESH lineage (status vocabulary,
    # exactly one FINAL amendment as the LAST entry, FINAL fields, no
    # amendment past FINAL) are validate_execution_final /
    # validate_protocol_final's: the transition mints the locks OPEN with
    # amendments [], and the owner's later finalization IS the legitimate
    # terminal amendment — this binding audit only requires the append-only
    # container to exist.
    if lock.get("freeze_commit") is None:
        out.append(f"{prefix}: epoch-2 lock {lock_name} records no "
                   f"freeze_commit (the instance freeze is shared across "
                   f"epochs)")
    return out


def validate_transition(fam_c_dir):
    """Full epoch-2 transition audit (the transition script's --check and
    the epoch-2 suite use this; preflight's V2/V3 split the same helpers
    across authorities so a defect is named exactly once there):
    record + both epoch-1 historical lock bytes + both epoch-2 lock
    bindings. Returns findings (empty = green)."""
    out = validate_record(fam_c_dir)
    out += validate_epoch1_historical_lock(
        fam_c_dir, EPOCH1_EXECUTION_LOCK_FILE,
        EPOCH1_EXECUTION_LOCK_SHA256, "EPOCH-2-TRANSITION")
    out += validate_epoch1_historical_lock(
        fam_c_dir, EPOCH1_PROTOCOL_LOCK_FILE,
        EPOCH1_PROTOCOL_LOCK_SHA256, "EPOCH-2-TRANSITION")
    out += validate_epoch2_lock_binding(fam_c_dir, EXECUTION_LOCK_FILE,
                                        "EPOCH-2-TRANSITION")
    out += validate_epoch2_lock_binding(fam_c_dir, PROTOCOL_LOCK_FILE,
                                        "EPOCH-2-TRANSITION")
    return out

