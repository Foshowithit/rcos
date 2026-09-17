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

# ---------------------------------------------------------------------------
# EPOCH-3 (EPOCH-3-PROTOCOL-SPEC.md §6, frozen at 28cdf2a2…): the third
# epoch exists only as an explicit on-disk lineage in the same mechanical
# form as epoch 2 — a transition record citing the frozen epoch-2 boundary
# facts, fresh locks on their own append-only lineage minted OPEN, and the
# state namespace state/epoch3/. Epoch 3 RESTARTS the frozen 240-event order
# from event 0 (PQ/fam05/T0/A); no epoch-2 (or epoch-1) artifact is ever
# written to, and epoch-2 cells populate no epoch-3 prefix position.
# ---------------------------------------------------------------------------
EPOCH3_ID = "epoch3"
EPOCH3_NUMBER = 3
EPOCH3_FROM_EPOCH = 2
EPOCH3_STATE_SUBDIR = "epoch3"
EPOCH3_STATE_PREFIX = "state/epoch3"
EPOCH3_TRANSITION_FILE = "EPOCH-3-TRANSITION.json"
EPOCH3_EXECUTION_LOCK_FILE = "EXECUTION-LOCK-EPOCH3.json"
EPOCH3_PROTOCOL_LOCK_FILE = "PROTOCOL-LOCK-EPOCH3.json"
EPOCH2_STOP_RECORD_FILE = "EPOCH-2-STOP-RECORD.md"
EPOCH3_SPEC_FILE = "EPOCH-3-PROTOCOL-SPEC.md"

# The frozen epoch-2 boundary facts the epoch-3 transition must cite
# (EPOCH-2-STOP-RECORD.md + EPOCH-3-PROTOCOL-SPEC.md §6: the corrected stop
# record, the epoch-2 FINAL lock hashes, the epoch-2 transition hash, the
# epoch-2 finalization commit, the exact frozen ORDER-EXPANSION pin, and the
# frozen epoch-3 spec sha with its freeze commit). A record citing other
# bytes activates nothing.
EPOCH2_STOP_RECORD_SHA256 = (
    "4e0e84ec6c4f13baebd319b40e11ce1beb6258110146fb1d6066afed74e70f4c")
EPOCH2_EXECUTION_LOCK_SHA256 = (
    "e662463e50fbb7d08115063595a4392437ccac54e6d2dd989a730ecafe619a80")
EPOCH2_PROTOCOL_LOCK_SHA256 = (
    "978d5e3e8d6f8797343830d565583804ae58a426b114331e74b2f4ebe1f74b00")
EPOCH2_TRANSITION_SHA256 = (
    "047aef2fcfef76803cb0999edcd17027aa2997b91a7face8ad9a83012136bb6b")
EPOCH2_FINALIZATION_COMMIT = "53e72ef4cec5ec7ecc9628c348a36635c02bd2d4"
EPOCH3_SPEC_SHA256 = (
    "28cdf2a232f74ad44d2ca5de278352c152a976be3c85084c18aea8acab99c226")
EPOCH3_FREEZE_COMMIT = "03af3cddc51bffa3c568ae0de36d4205805fd638"
ORDER_EXPANSION_SHA256 = (
    "449be793cf764204b8326a56914dd19c90f16371600db9d97faf60ccbe43f47a")

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


def transition_path3(fam_c_dir):
    return os.path.join(fam_c_dir, EPOCH3_TRANSITION_FILE)


def is_epoch3(fam_c_dir):
    """True iff the tree carries a STRUCTURALLY VALID epoch-3 transition
    record (see transition_record3()) AND the epoch-2 boundary it cites is
    itself validly present and FINAL. Epoch 2 (or epoch 1) otherwise."""
    return transition_record3(fam_c_dir) is not None


def transition_record3(fam_c_dir):
    """The ACTIVE epoch-3 transition record, or None.

    STRUCTURAL activation (read on every path derivation): the record must
    name epoch 3 + the epoch-3 state prefix + the two fresh epoch-3 lock
    files, cite the FROZEN epoch-2 boundary facts verbatim (the epoch-2
    transition sha256, both epoch-2 FINAL lock hashes, the epoch-2
    finalization commit), cite the corrected stop record's ACTUAL bytes,
    cite the frozen epoch-3 spec bytes AND the freeze commit, and cite the
    exact frozen ORDER-EXPANSION.json pin — and the on-disk bytes of the
    stop record / spec / order expansion must still hash to those
    citations (fail closed: the boundary is anchored to frozen documents,
    never to a later edit). Malformed/absent => None (epoch 2 or 1)."""
    try:
        obj = _read_json(transition_path3(fam_c_dir))
    except (ValueError, OSError):
        return None
    if not isinstance(obj, dict):
        return None
    for key, want in (("to_epoch", EPOCH3_NUMBER),
                      ("from_epoch", EPOCH3_FROM_EPOCH),
                      ("epoch_id", EPOCH3_ID),
                      ("state_prefix", EPOCH3_STATE_PREFIX),
                      ("execution_lock", EPOCH3_EXECUTION_LOCK_FILE),
                      ("protocol_lock", EPOCH3_PROTOCOL_LOCK_FILE),
                      ("epoch2_transition_record", TRANSITION_FILE),
                      ("epoch2_transition_sha256", EPOCH2_TRANSITION_SHA256),
                      ("epoch2_execution_lock_sha256",
                       EPOCH2_EXECUTION_LOCK_SHA256),
                      ("epoch2_protocol_lock_sha256",
                       EPOCH2_PROTOCOL_LOCK_SHA256),
                      ("epoch2_finalization_commit",
                       EPOCH2_FINALIZATION_COMMIT),
                      ("epoch2_stop_record", EPOCH2_STOP_RECORD_FILE),
                      ("epoch2_stop_record_sha256",
                       EPOCH2_STOP_RECORD_SHA256),
                      ("epoch3_protocol_spec", EPOCH3_SPEC_FILE),
                      ("epoch3_protocol_spec_sha256", EPOCH3_SPEC_SHA256),
                      ("epoch3_freeze_commit", EPOCH3_FREEZE_COMMIT),
                      ("order_expansion_sha256", ORDER_EXPANSION_SHA256)):
        if obj.get(key) != want:
            return None
    for name, want in ((EPOCH2_STOP_RECORD_FILE, EPOCH2_STOP_RECORD_SHA256),
                       (EPOCH3_SPEC_FILE, EPOCH3_SPEC_SHA256),
                       ("ORDER-EXPANSION.json", ORDER_EXPANSION_SHA256)):
        try:
            with open(os.path.join(fam_c_dir, name), "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() != want:
                    return None
        except OSError:
            return None
    # the epoch-2 boundary the epoch-3 record builds on must itself hold
    if not is_epoch2(fam_c_dir):
        return None
    return obj


def active_epoch(fam_c_dir):
    if is_epoch3(fam_c_dir):
        return EPOCH3_NUMBER
    return EPOCH_NUMBER if is_epoch2(fam_c_dir) else FROM_EPOCH


def state_root(fam_c_dir):
    """The ACTIVE epoch's persistent state root: state/epoch3 under epoch 3,
    state/epoch2 under epoch 2 (epoch-1 state/ is untouched and never
    scanned by later-epoch walks), state/ under epoch 1."""
    if is_epoch3(fam_c_dir):
        return os.path.join(fam_c_dir, "state", EPOCH3_STATE_SUBDIR)
    if is_epoch2(fam_c_dir):
        return os.path.join(fam_c_dir, "state", STATE_SUBDIR)
    return os.path.join(fam_c_dir, "state")


def state_roots(fam_c_dir):
    """EVERY epoch state root (epoch 1, epoch 2, epoch 3). Runtime state is
    evidence, never a frozen instance input: preflight's V1 walk prunes all
    of them, so a third epoch can never turn the preserved epoch-1/epoch-2
    evidence trees into 'extra file not in freeze manifest' findings."""
    return [os.path.join(fam_c_dir, "state"),
            os.path.join(fam_c_dir, "state", STATE_SUBDIR),
            os.path.join(fam_c_dir, "state", EPOCH3_STATE_SUBDIR)]


def active_lock_names(fam_c_dir):
    """(execution, protocol) lock file names of the ACTIVE epoch."""
    if is_epoch3(fam_c_dir):
        return (EPOCH3_EXECUTION_LOCK_FILE, EPOCH3_PROTOCOL_LOCK_FILE)
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


def validate_epoch2_historical_lock(fam_c_dir, name, want_sha, prefix):
    """An epoch-2 FINAL lock in the EPOCH-3 world is a HISTORICAL record:
    its bytes must still hash to the epoch-2-recorded sha256 and it must
    still record status FINAL. It is never the live authority (the epoch-3
    locks are). Epoch 3 must not delete, move, or rewrite it. Returns
    findings (empty = green)."""
    out = []
    p = os.path.join(fam_c_dir, name)
    if not os.path.isfile(p):
        return [f"{prefix}: epoch-2 historical lock {name} missing at the "
                f"recorded path (the epoch-3 transition pins its bytes; "
                f"epoch 3 must not delete or move it)"]
    try:
        with open(p, "rb") as f:
            live = hashlib.sha256(f.read()).hexdigest()
        with open(p) as f:
            obj = json.load(f)
    except (OSError, ValueError) as e:
        return [f"{prefix}: epoch-2 historical lock {name} unreadable: {e}"]
    if live != want_sha:
        out.append(f"{prefix}: epoch-2 historical lock {name} bytes "
                   f"{live[:12]} != the epoch-2-recorded sha256 "
                   f"{want_sha[:12]} (epoch 2 is immutable at its recorded "
                   f"FINAL bytes)")
    if not isinstance(obj, dict) or obj.get("status") != "FINAL":
        st = obj.get("status") if isinstance(obj, dict) else None
        out.append(f"{prefix}: epoch-2 historical lock {name} status "
                   f"{st!r} != 'FINAL' (the epoch-2 terminal state is part "
                   f"of the historical bytes)")
    return out


def validate_record3(fam_c_dir):
    """The EPOCH-3 BOUNDARY audit (protocol authority, V2): the epoch-3
    transition record exists, satisfies the structural activation contract
    (citations of the frozen epoch-2 boundary facts, the corrected stop
    record, the frozen spec + freeze commit, the exact ORDER-EXPANSION
    pin), carries a non-empty genesis base map, and the epoch-2 boundary it
    builds on still verifies. Returns findings (empty = green)."""
    out = []
    rec = transition_record3(fam_c_dir)
    if rec is None:
        return ["EPOCH-3-TRANSITION: no structurally valid "
                f"{EPOCH3_TRANSITION_FILE} under {fam_c_dir} (epoch 3 is "
                "not active)"]
    p = transition_path3(fam_c_dir)
    try:
        with open(p, "rb") as f:
            hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        return [f"EPOCH-3-TRANSITION: record unreadable: {e}"]
    if not isinstance(rec.get("genesis"), dict) or not rec.get("genesis"):
        out.append("EPOCH-3-TRANSITION: the record carries no genesis base "
                   "map (the transition-time governed bytes); the epoch-3 "
                   "protocol lock has no verifiable base")
    if not _HEX64.match(str(rec.get("epoch2_stop_record_sha256") or "")):
        out.append("EPOCH-3-TRANSITION: epoch2_stop_record_sha256 is not "
                   "64-lowercase-hex")
    # The epoch-2 boundary it cites must still hold on disk, byte for byte.
    out += validate_transition(fam_c_dir)
    if not out:
        out += validate_epoch3_lock_binding(fam_c_dir,
                                           EPOCH3_EXECUTION_LOCK_FILE,
                                           "EPOCH-3-TRANSITION")
        out += validate_epoch3_lock_binding(fam_c_dir,
                                           EPOCH3_PROTOCOL_LOCK_FILE,
                                           "EPOCH-3-TRANSITION")
    return out


def validate_epoch3_lock_binding(fam_c_dir, lock_name, prefix):
    """One epoch-3 lock's transition binding: `epoch: 3`, a `transition`
    block citing the epoch-3 record (name + sha256 of its bytes) and the
    epoch-2 boundary facts, a non-terminal amendment lineage (an
    append-only list starting empty at the transition), and the shared
    instance freeze. Returns findings (empty = green)."""
    out = []
    rec = transition_record3(fam_c_dir)
    if rec is None:
        return [f"{prefix}: {lock_name} cites a transition record that is "
                f"not validly present (epoch 3 is not active)"]
    try:
        with open(transition_path3(fam_c_dir), "rb") as f:
            rec_sha = hashlib.sha256(f.read()).hexdigest()
    except OSError as e:
        return [f"{prefix}: epoch-3 transition record unreadable: {e}"]
    p = os.path.join(fam_c_dir, lock_name)
    if not os.path.isfile(p):
        return [f"{prefix}: epoch-3 lock {lock_name} missing (the "
                f"transition record names it; mint it via "
                f"harness/epoch_transition.py)"]
    try:
        with open(p) as f:
            lock = json.load(f)
    except (OSError, ValueError) as e:
        return [f"{prefix}: epoch-3 lock {lock_name} unparsable: {e}"]
    if not isinstance(lock, dict):
        return [f"{prefix}: epoch-3 lock {lock_name} is not a JSON object"]
    if lock.get("epoch") != EPOCH3_NUMBER:
        out.append(f"{prefix}: epoch-3 lock {lock_name} does not carry "
                   f"epoch: {EPOCH3_NUMBER} (got {lock.get('epoch')!r})")
    tr = lock.get("transition")
    if not isinstance(tr, dict):
        out.append(f"{prefix}: epoch-3 lock {lock_name} carries no "
                   f"transition citation block")
    else:
        for key, want in (("record", EPOCH3_TRANSITION_FILE),
                          ("record_sha256", rec_sha),
                          ("from_epoch", EPOCH3_FROM_EPOCH),
                          ("epoch2_transition_record", TRANSITION_FILE),
                          ("epoch2_transition_sha256",
                           EPOCH2_TRANSITION_SHA256),
                          ("epoch2_execution_lock_sha256",
                           EPOCH2_EXECUTION_LOCK_SHA256),
                          ("epoch2_protocol_lock_sha256",
                           EPOCH2_PROTOCOL_LOCK_SHA256),
                          ("epoch2_finalization_commit",
                           EPOCH2_FINALIZATION_COMMIT)):
            if tr.get(key) != want:
                out.append(f"{prefix}: epoch-3 lock {lock_name} "
                           f"transition.{key} {tr.get(key)!r} != {want!r}")
    am = lock.get("amendments")
    if not isinstance(am, list):
        out.append(f"{prefix}: epoch-3 lock {lock_name} amendments is not "
                   f"a list (the new lineage is an append-only list)")
    if lock.get("freeze_commit") is None:
        out.append(f"{prefix}: epoch-3 lock {lock_name} records no "
                   f"freeze_commit (the instance freeze is shared across "
                   f"epochs)")
    return out


def validate_transition3(fam_c_dir):
    """Full epoch-3 transition audit: the record + the epoch-2 boundary it
    cites (transition record, both epoch-2 lock bindings, both epoch-1
    historical locks) + both epoch-2 FINAL locks as historical records +
    both fresh epoch-3 lock bindings. Returns findings (empty = green)."""
    out = validate_record3(fam_c_dir)
    out += validate_epoch2_historical_lock(
        fam_c_dir, EXECUTION_LOCK_FILE, EPOCH2_EXECUTION_LOCK_SHA256,
        "EPOCH-3-TRANSITION")
    out += validate_epoch2_historical_lock(
        fam_c_dir, PROTOCOL_LOCK_FILE, EPOCH2_PROTOCOL_LOCK_SHA256,
        "EPOCH-3-TRANSITION")
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

