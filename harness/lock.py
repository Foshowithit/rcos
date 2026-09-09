#!/usr/bin/env python3
"""H3 CAPABILITY_LOCK enforcement: promotion writes once, downstream is
read-only. The loader resolves by exact hash, verifies bytes
pre-execution, and refuses on any mismatch.

A12.2 (audit round-2 #12/#14) — the lock is now ESTIMAND-AWARE. A lock that
does not carry the full estimand field set is not merely incomplete, it is
INADMISSIBLE: `verify_lock()` returns a named reason for every missing or
malformed field and every caller refuses. Legacy locks (the pre-A12 shape,
which recorded only artifacts + a promotion receipt sha) are therefore
LOCK-INADMISSIBLE by construction: they can never be silently treated as a
frozen capability again. Stdlib only.
"""
import hashlib
import json
import os
import re
import time

LOCK_SCHEMA_VERSION = "capability-lock-v3"

# The complete estimand-aware field set (audit round-2 item #9). Every field
# must be present AND carry the right shape; a lock missing any of them is
# inadmissible. Additions require a schema-version bump + re-freeze.
LOCK_REQUIRED_FIELDS = (
    "schema_version",            # == LOCK_SCHEMA_VERSION
    "block", "universe", "family",
    "capability_id", "version",
    "acquisition_chain_tips",    # {"T0": 64hex, "T1": 64hex} distinct
    "source_cells",              # {"T0": cell_id, "T1": cell_id}
    "producer_identity",         # dict (builder/lane/model evidence)
    "protocol_lock_sha256",      # 64hex, matches the frozen protocol lock
    "execution_lock_sha256",     # 64hex, matches the frozen execution lock
    "artifacts",                 # {name: 64hex} exactly the promoted set
    "semantic_core",             # nonempty str
    # A12d slice D2 (auditor A12d.3/A12d.4): producer applicability
    # requirements in the structurally positive v2 form.
    # A12d slice D4 (auditor D3-post P1): the lock schema is v3. The v2
    # identifier predates `preconditions` becoming
    # `list[{"requires": ...}]` and no longer uniquely describes the
    # shape, so the bump is the explicit freeze: v2 meant the
    # pre-`list[{"requires": ...}]` shape (the D2
    # interpret-with-v2-shape note is superseded by this bump). The
    # producer-contract shape itself stays v2; only the lock schema
    # version moves.
    "preconditions",             # list[{"requires": nonempty str}]
                                 # (may be empty: no declared
                                 # applicability requirement)
    "limitations",               # list[str] (may be empty; free prose)
    # A12b.6 actual-contract conformance (auditor rule: the lock records
    # the contract the producer ACTUALLY shipped, and conformance is
    # checked against that contract):
    "limitation_present",        # bool: the locked contract carries a
                                 # limitation (== bool(limitations))
    "non_discriminating",        # bool: the family's T4 cannot
                                 # discriminate on this contract
    "conformance_cause",         # nonempty str: the committed reason
    # A12c slice C2 (auditor P0 #6: the frozen limitation->T4-id bridge):
    "supported_t4_ids",          # sorted list[str]: T4 ids the locked
                                 # contract supports (presence, not
                                 # truthiness: [] is a real verdict)
    "conformance_map_sha256",    # 64hex: sha256 of the governed
                                 # T4-CONFORMANCE.json bytes the verdict
                                 # was derived from
    "t4_semantic_id",            # auditor-side conformance id (nonempty str)
    "evidence_grade",            # "estimand" | "harness-validation"
    "candidate_sha256",          # 64hex: causal root of the capability
    "candidate_provenance_sha256",  # 64hex: sha256 of the promotion receipt
    "promotion_receipt_sha256",
    "manifest", "manifest_sha256",
    "locked_at",
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_GRADES = ("estimand", "harness-validation")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verify_lock(lock, expect=None, fam_c_dir=None):
    """Return a list of refusal reasons; empty means the lock is admissible.

    `expect` may pin {"capability_id", "block", "universe", "family",
    "protocol_lock_sha256", "execution_lock_sha256", "candidate_sha256",
    "promotion_receipt_sha256", "evidence_grade"}; every pinned value must
    match exactly. `fam_c_dir`, when given, additionally binds the lock's
    `conformance_map_sha256` to the LIVE governed T4-CONFORMANCE.json
    bytes (a map edited without re-minting the lock refuses here).
    Legacy / malformed locks produce a `LOCK-INADMISSIBLE`
    reason naming the exact field, never a silent pass.
    """
    out = []
    if not isinstance(lock, dict):
        return ["LOCK-INADMISSIBLE: lock is not a JSON object"]
    sv = lock.get("schema_version")
    if sv is None:
        out.append("LOCK-INADMISSIBLE: legacy lock (no schema_version; "
                   "pre-A12 locks carry no estimand fields and may not be "
                   "reused)")
    elif sv != LOCK_SCHEMA_VERSION:
        out.append(f"LOCK-INADMISSIBLE: schema_version {sv!r} != "
                   f"{LOCK_SCHEMA_VERSION!r}")
    missing = [f for f in LOCK_REQUIRED_FIELDS
               if f not in lock or lock.get(f) is None]
    if missing:
        out.append("LOCK-INADMISSIBLE: missing required field(s): "
                   + ", ".join(sorted(missing)))
    for f in ("protocol_lock_sha256", "execution_lock_sha256",
              "candidate_sha256", "candidate_provenance_sha256",
              "promotion_receipt_sha256", "manifest_sha256",
              "conformance_map_sha256"):
        v = lock.get(f)
        if v is not None and not (isinstance(v, str) and _HEX64.match(v)):
            out.append(f"LOCK-INADMISSIBLE: {f} must be 64-hex, got {v!r}")
    tips = lock.get("acquisition_chain_tips")
    if tips is not None:
        if not isinstance(tips, dict) or set(tips) != {"T0", "T1"}:
            out.append("LOCK-INADMISSIBLE: acquisition_chain_tips must name "
                       f"exactly T0 and T1, got {tips!r}")
        else:
            for ev in ("T0", "T1"):
                if not _HEX64.match(str(tips[ev])):
                    out.append(f"LOCK-INADMISSIBLE: acquisition_chain_tips"
                               f"[{ev}] must be 64-hex, got {tips[ev]!r}")
            if tips.get("T0") == tips.get("T1"):
                out.append("LOCK-INADMISSIBLE: T0 and T1 tips are identical "
                           "(promotion requires two distinct runs)")
    cells = lock.get("source_cells")
    if cells is not None:
        if not isinstance(cells, dict) or set(cells) != {"T0", "T1"} \
                or not all(isinstance(v, str) and v for v in cells.values()):
            out.append("LOCK-INADMISSIBLE: source_cells must name exactly "
                       f"the T0 and T1 cell ids, got {cells!r}")
        elif cells.get("T0") == cells.get("T1"):
            out.append("LOCK-INADMISSIBLE: T0 and T1 source cells identical")
    arts = lock.get("artifacts")
    if arts is not None:
        if not isinstance(arts, dict) or not arts:
            out.append("LOCK-INADMISSIBLE: artifacts must be a nonempty "
                       f"object, got {arts!r}")
        else:
            for name, sha in sorted(arts.items()):
                if not (isinstance(name, str) and name
                        and os.path.basename(name) == name):
                    out.append(f"LOCK-INADMISSIBLE: artifact name {name!r} "
                               "must be a bare filename")
                if not (isinstance(sha, str) and _HEX64.match(sha)):
                    out.append(f"LOCK-INADMISSIBLE: artifact {name} hash "
                               f"{sha!r} is not 64-hex")
    sc = lock.get("semantic_core")
    if sc is not None and not (isinstance(sc, str) and sc.strip()):
        out.append("LOCK-INADMISSIBLE: semantic_core must be a nonempty "
                   f"string, got {sc!r}")
    for f in ("preconditions", "limitations"):
        v = lock.get(f)
        if f == "preconditions":
            if v is not None and (not isinstance(v, list)
                                  or not all(
                                      isinstance(x, dict)
                                      and set(x) == {"requires"}
                                      and isinstance(x.get("requires"), str)
                                      and x["requires"].strip()
                                      for x in v)):
                out.append("LOCK-INADMISSIBLE: preconditions must be a "
                           "list of {\"requires\": nonempty str} objects "
                           "(v3 lock schema; v2 contract shape), "
                           f"got {v!r}")
        elif v is not None and (not isinstance(v, list)
                                or not all(isinstance(x, str) for x in v)):
            out.append(f"LOCK-INADMISSIBLE: {f} must be a list of strings, "
                       f"got {v!r}")
    # A12b.6 actual-contract conformance. The lock records the producer's
    # ACTUAL contract plus the derived conformance verdict — never a
    # claim smuggled from hidden auditor text (the controller derives
    # these mechanically from the producer-declared contract; the
    # conformance check reads the lock only):
    #   * limitation_present must be a bool and must equal
    #     bool(limitations) — lying about presence voids the lock;
    #   * non_discriminating must be a bool;
    #   * conformance_cause must be a nonempty committed reason.
    # A12d slice D2: discrimination rides the affirmative requires
    # claims, never limitations — so no rule here may void a lock for
    # carrying empty limitations alongside a discriminating verdict
    # (that is the legitimate C2 shape: limitations are free prose).
    # Discrimination is set membership, checked below.
    lim = lock.get("limitations")
    lim_present = lock.get("limitation_present")
    non_disc = lock.get("non_discriminating")
    cause = lock.get("conformance_cause")
    if lim_present is not None and not isinstance(lim_present, bool):
        out.append("LOCK-INADMISSIBLE: limitation_present must be a "
                   f"boolean, got {lim_present!r}")
    elif isinstance(lim, list) and isinstance(lim_present, bool) \
            and lim_present != bool(lim):
        out.append("LOCK-INADMISSIBLE: limitation_present "
                   f"{lim_present!r} != the locked limitations "
                   f"({'present' if lim else 'absent'})")
    if non_disc is not None and not isinstance(non_disc, bool):
        out.append("LOCK-INADMISSIBLE: non_discriminating must be a "
                   f"boolean, got {non_disc!r}")
    if cause is not None and not (isinstance(cause, str) and cause.strip()):
        out.append("LOCK-INADMISSIBLE: conformance_cause must be a "
                   f"nonempty committed reason, got {cause!r}")
    # A12c slice C2 (auditor P0 #6), A12d slice D2 (auditor A12d.3): the
    # frozen bridge. The verdict is set membership over the supported id
    # set, never bare presence:
    #   * supported_t4_ids must be a list of strings (an empty list is
    #     a real verdict — presence, not truthiness);
    #   * non_discriminating must equal (t4_semantic_id not in
    #     supported_t4_ids);
    #   * a lock claiming a discriminating T4 whose id is NOT in
    #     supported_t4_ids is LOCK-INADMISSIBLE naming the id (an
    #     unsupported requires claim discriminates nothing; limitations
    #     never support an id).
    sup = lock.get("supported_t4_ids")
    if sup is not None and (not isinstance(sup, list)
                            or not all(isinstance(x, str) and x.strip()
                                       for x in sup)):
        out.append("LOCK-INADMISSIBLE: supported_t4_ids must be a list "
                   f"of strings, got {sup!r}")
    _tid = lock.get("t4_semantic_id")
    if isinstance(sup, list) and isinstance(_tid, str) and _tid.strip() \
            and isinstance(non_disc, bool):
        if non_disc != (_tid not in sup):
            out.append("LOCK-INADMISSIBLE: non_discriminating "
                       f"{non_disc!r} != (t4_semantic_id {_tid!r} not in "
                       f"supported_t4_ids {sorted(sup)!r}) (the frozen "
                       f"bridge: discrimination is set membership)")
        if non_disc is False and _tid not in sup:
            _nolim = (" (the locked contract carries no limitations)"
                      if isinstance(lim, list) and not lim else "")
            out.append(f"LOCK-INADMISSIBLE: lock claims a discriminating "
                       f"T4 {_tid!r} whose id is not in supported_t4_ids "
                       f"{sorted(sup)!r} — an unsupported requires claim "
                       f"cannot discriminate{_nolim}")
    # The lock's verdict is bound to the governed map bytes live on
    # disk: a map edited without re-minting the lock refuses here
    # (preflight V2 owns the before-any-model-call refusal; this is
    # the at-consumption binding).
    if fam_c_dir is not None:
        mapp = os.path.join(fam_c_dir, "T4-CONFORMANCE.json")
        try:
            if os.path.islink(mapp):
                raise OSError("is a symlink, not a committed map file")
            with open(mapp, "rb") as f:
                live = hashlib.sha256(f.read()).hexdigest()
        except OSError as e:
            out.append("LOCK-INADMISSIBLE: governed T4-CONFORMANCE.json "
                       f"unreadable at {mapp}: {e}")
        else:
            want = lock.get("conformance_map_sha256")
            if isinstance(want, str) and want != live:
                out.append("LOCK-INADMISSIBLE: conformance_map_sha256 "
                           f"{want[:12]} != the live governed "
                           f"T4-CONFORMANCE.json {live[:12]} (the map "
                           f"was edited without re-minting the lock)")
    tid = lock.get("t4_semantic_id")
    if tid is not None and not (isinstance(tid, str) and tid.strip()):
        out.append("LOCK-INADMISSIBLE: t4_semantic_id must be a nonempty "
                   f"string, got {tid!r}")
    grade = lock.get("evidence_grade")
    if grade is not None and grade not in _GRADES:
        out.append(f"LOCK-INADMISSIBLE: evidence_grade {grade!r} not in "
                   f"{list(_GRADES)}")
    pid = lock.get("producer_identity")
    if pid is not None and not isinstance(pid, dict):
        out.append(f"LOCK-INADMISSIBLE: producer_identity must be an object, "
                   f"got {type(pid).__name__}")
    if expect:
        for k, want in sorted(expect.items()):
            got = lock.get(k)
            if got != want:
                out.append(f"LOCK-INADMISSIBLE: {k} {got!r} != expected "
                           f"{want!r}")
    return out


def promote(out_dir, capability_id, version, artifact_paths,
            manifest_obj, training_receipts, builder_identity,
            promotion_receipt_sha256=None, *, block=None, universe=None,
            family=None, acquisition_chain_tips=None, source_cells=None,
            producer_identity=None, protocol_lock_sha256=None,
            execution_lock_sha256=None, semantic_core=None, preconditions=None,
            limitations=None, limitation_present=None,
            non_discriminating=None, conformance_cause=None,
            supported_t4_ids=None, conformance_map_sha256=None,
            t4_semantic_id=None, evidence_grade=None,
            candidate_sha256=None, candidate_provenance_sha256=None):
    """Write an immutable, estimand-aware CAPABILITY_LOCK. Returns path.

    Fails if the lock file already exists (promotion writes once; no
    repromotion) and fails closed if ANY estimand field is absent: a lock
    may only be minted from a validated promotion, never from whatever
    artifacts happen to sit in a directory (audit round-2 #11). The
    caller-supplied `artifact_paths` are hashed as the lock's artifact map,
    so the production writer passes EXACTLY the paths named by the
    validated promotion receipt.
    """
    missing = [n for n, v in (
        ("block", block), ("universe", universe), ("family", family),
        ("acquisition_chain_tips", acquisition_chain_tips),
        ("source_cells", source_cells), ("producer_identity", producer_identity),
        ("protocol_lock_sha256", protocol_lock_sha256),
        ("execution_lock_sha256", execution_lock_sha256),
        ("semantic_core", semantic_core), ("preconditions", preconditions),
        ("limitations", limitations),
        ("limitation_present", limitation_present),
        ("non_discriminating", non_discriminating),
        ("conformance_cause", conformance_cause),
        ("supported_t4_ids", supported_t4_ids),
        ("conformance_map_sha256", conformance_map_sha256),
        ("t4_semantic_id", t4_semantic_id),
        ("evidence_grade", evidence_grade), ("candidate_sha256", candidate_sha256),
        ("candidate_provenance_sha256", candidate_provenance_sha256),
        ("promotion_receipt_sha256", promotion_receipt_sha256)) if v is None]
    if missing:
        raise ValueError("LOCK-INADMISSIBLE: refuse to mint a lock missing "
                         "estimand field(s): " + ", ".join(missing))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "CAPABILITY_LOCK.json")
    if os.path.exists(path):
        raise PermissionError("LOCK-DENY lock already exists (no repromotion)")
    art = {}
    for p in sorted(artifact_paths):
        art[os.path.basename(p)] = _sha(p)
    lock = {"schema_version": LOCK_SCHEMA_VERSION,
            "block": block, "universe": universe, "family": family,
            "capability_id": capability_id, "version": version,
            "acquisition_chain_tips": dict(acquisition_chain_tips),
            "source_cells": dict(source_cells),
            "producer_identity": dict(producer_identity),
            "protocol_lock_sha256": protocol_lock_sha256,
            "execution_lock_sha256": execution_lock_sha256,
            "artifacts": art,
            "semantic_core": semantic_core,
            "preconditions": list(preconditions),
            "limitations": list(limitations),
            "limitation_present": limitation_present,
            "non_discriminating": non_discriminating,
            "conformance_cause": conformance_cause,
            "supported_t4_ids": list(supported_t4_ids),
            "conformance_map_sha256": conformance_map_sha256,
            "t4_semantic_id": t4_semantic_id,
            "evidence_grade": evidence_grade,
            "candidate_sha256": candidate_sha256,
            "candidate_provenance_sha256": candidate_provenance_sha256,
            "promotion_receipt_sha256": promotion_receipt_sha256,
            "manifest_sha256": hashlib.sha256(
                json.dumps(manifest_obj, sort_keys=True).encode()).hexdigest(),
            "manifest": manifest_obj,
            "training_receipts": list(training_receipts),
            "builder_identity": dict(builder_identity),
            "locked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    reasons = verify_lock(lock)
    if reasons:
        raise ValueError("LOCK-INADMISSIBLE: refusing to write a lock that "
                         "fails its own contract: " + "; ".join(reasons))
    with open(path, "w") as f:
        json.dump(lock, f, indent=1)
    return path


def specificity_gate(locks_by_family):
    """A12b.6 specificity gate over committed CAPABILITY_LOCKs.

    `locks_by_family` maps family -> lock dict (each lock read from its
    capability dir, never hand-built). Returns a report dict:

        {"discriminating": [families whose locked T4 discriminates],
         "non_discriminating": {family: committed conformance_cause},
         "inadmissible": {family: [lock refusal reasons]},
         "verdict": "specificity-pass" | "specificity-failure"}

    The gate counts ONLY discriminating families: a T4 that the locked
    capability cannot discriminate (no limitation in the actual locked
    contract) is excluded WITH its committed cause, and fewer families
    do not lower the bar — any exclusion or inadmissible lock is a
    specificity failure with cause, never a silent pass. Stdlib only.
    """
    discriminating, excluded, inadmissible = [], {}, {}
    for family in sorted(locks_by_family):
        lock = locks_by_family[family]
        reasons = verify_lock(lock)
        if reasons:
            inadmissible[family] = list(reasons)
            continue
        if lock.get("non_discriminating") is True:
            excluded[family] = lock.get("conformance_cause")
        else:
            discriminating.append(family)
    verdict = ("specificity-pass"
               if not excluded and not inadmissible
               else "specificity-failure")
    return {"discriminating": discriminating,
            "non_discriminating": excluded,
            "inadmissible": inadmissible, "verdict": verdict}


def load_artifact(lock_path, artifact_name, dest_dir):
    """Resolve ONE artifact by exact locked hash from a source tree.
    `dest_dir` must contain a same-named file whose bytes hash to the
    locked value; returns the verified path. Refuses otherwise — including
    when the lock itself is legacy/inadmissible (A12.2).
    (The source tree is the harness-controlled capability store —
    callers never supply artifact bytes directly.)"""
    lock = json.load(open(lock_path))
    reasons = verify_lock(lock)
    if reasons:
        raise PermissionError("LOCK-INADMISSIBLE: " + "; ".join(reasons))
    want = lock["artifacts"].get(artifact_name)
    if want is None:
        raise PermissionError(
            f"LOCK-DENY {artifact_name!r} not in lock "
            f"{lock.get('capability_id')}")
    cand = os.path.join(dest_dir, artifact_name)
    if not os.path.exists(cand):
        raise PermissionError(f"LOCK-DENY artifact absent: {cand}")
    if _sha(cand) != want:
        raise PermissionError(
            f"LOCK-DENY hash mismatch for {artifact_name}: locked "
            f"{want[:12]} vs present {_sha(cand)[:12]}")
    return cand
