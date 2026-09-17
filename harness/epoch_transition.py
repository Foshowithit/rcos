#!/usr/bin/env python3
"""EPOCH-1 -> EPOCH-2 TRANSITION (third-party ruling recorded in
benchmarks/fam-c/EPOCH-1-CLOSURE.md).

Epoch 1 is CLOSED (terminated-not-repaired, immutable at its recorded FINAL
protocol and execution locks). This tool performs the ONE explicit
transition the ruling orders, mechanically and fail closed:

  1. verify the epoch-1 closure facts are still on disk EXACTLY as
     recorded — the closure record exists, and the two FINAL lock files
     still hash to the closure-cited sha256 (EXECUTION-LOCK.json
     f6616ea2..., PROTOCOL-LOCK.json 96eac57b...) with status "FINAL";
     a tree whose epoch-1 bytes drifted is refused (no transition FROM an
     unverified epoch);
  2. write `EPOCH-2-TRANSITION.json` (the on-disk epoch boundary record:
     epoch-2 state prefix, the two fresh lock file names, and the cited
     epoch-1 closure hashes), which ACTIVATES the epoch-2 lineage
     (harness/epoch.py);
  3. mint the FRESH epoch-2 locks — `EXECUTION-LOCK-EPOCH2.json`
     (status "open-round2", harness bytes observed NOW, its own
     amendments: []) and `PROTOCOL-LOCK-EPOCH2.json` (status
     "living-lock", governed = the live protocol-doc bytes, its own
     amendments: [], ORDER-EXPANSION.json pin) — each carrying
     `epoch: 2` and a `transition` block citing the record and the
     epoch-1 closure hashes. They start a NEW append-only amendment
     lineage: never an amendment to the epoch-1 lineage.

The epoch-2 locks then go through the STANDARD mint/finalize lifecycle:
re-mint via `python3 harness/mint_execution_lock.py --slice ... --reason
...` (it targets the active epoch's lock) and finalize via `--finalize`
when the owner authorizes it. This tool never finalizes: the epoch-2 locks
are minted OPEN, and the runner's FINAL gate refuses a wired estimand cell
until both epoch-2 authorities are FINAL.

Usage:
  python3 harness/epoch_transition.py --check
      # report the active epoch; exit 0 when the state is consistent
  python3 harness/epoch_transition.py --transition \
      --reason "third-party ruling EPOCH-2 PROTOCOL; fresh locks/lineage"
      # perform the transition (refuses when one is already recorded)
Stdlib only; every step fails closed.
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAMC = os.path.join(ROOT, "benchmarks", "fam-c")
sys.path.insert(0, HERE)
sys.path.insert(0, FAMC)

import epoch as EPOCH  # noqa: E402
from preflight import (PROTOCOL_GOVERNED, EPOCH3_GOVERNED,  # noqa: E402
                       _harness_closure)


def _sha_rel(rel):
    with open(os.path.join(ROOT, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sha_abs(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _manifest_sha(files):
    lines = sorted(f"{k}:{v}" for k, v in files.items())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def _stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _freeze_commit():
    try:
        return json.load(open(os.path.join(FAMC, "FREEZE.json")))[
            "freeze_commit"]
    except (OSError, ValueError, KeyError) as e:
        raise SystemExit(f"EPOCH-2-TRANSITION-REFUSED: FREEZE.json "
                         f"unreadable ({e}); the epoch-2 locks must record "
                         f"the shared instance freeze")


def _verify_epoch1_closure():
    """Fail closed unless the epoch-1 closure facts on disk are EXACTLY as
    EPOCH-1-CLOSURE.md records them. Returns the closure record sha256."""
    findings = []
    cp = os.path.join(FAMC, EPOCH.EPOCH1_CLOSURE_FILE)
    if not os.path.isfile(cp):
        raise SystemExit("EPOCH-2-TRANSITION-REFUSED: "
                         f"{EPOCH.EPOCH1_CLOSURE_FILE} missing under "
                         f"{FAMC}; the transition must cite the closure "
                         f"record")
    closure_sha = _sha_abs(cp)
    for name, want in ((EPOCH.EPOCH1_EXECUTION_LOCK_FILE,
                        EPOCH.EPOCH1_EXECUTION_LOCK_SHA256),
                       (EPOCH.EPOCH1_PROTOCOL_LOCK_FILE,
                        EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256)):
        p = os.path.join(FAMC, name)
        if not os.path.isfile(p):
            findings.append(f"{name} missing (the closure record pins its "
                            f"bytes)")
            continue
        got = _sha_abs(p)
        if got != want:
            findings.append(f"{name} bytes {got[:12]} != the "
                            f"closure-recorded sha256 {want[:12]}")
            continue
        try:
            st = json.load(open(p)).get("status")
        except (OSError, ValueError) as e:
            findings.append(f"{name} unparsable: {e}")
            continue
        if st != "FINAL":
            findings.append(f"{name} status {st!r} != 'FINAL' (the recorded "
                            f"epoch-1 terminal state)")
    if findings:
        raise SystemExit("EPOCH-2-TRANSITION-REFUSED: the epoch-1 closure "
                         "facts do not verify on disk — refusing to "
                         "transition FROM an unverified epoch:\n  - "
                         + "\n  - ".join(findings))
    return closure_sha


def _mint_execution_lock(record_rel_sha, freeze_commit, reason):
    files = {}
    entry = os.path.join("benchmarks", "fam-c", "harness-run",
                         "run_arm_h1.py")
    for rel in sorted(_harness_closure(ROOT, entry)):
        files[rel] = _sha_rel(rel)
    hdir = os.path.join(ROOT, "harness")
    for name in sorted(os.listdir(hdir)):
        if name.endswith(".py"):
            rel = f"harness/{name}"
            files[rel] = _sha_rel(rel)
    try:
        sys.path.insert(0, HERE)
        import adaptation as AD
        consts = json.loads(json.dumps(AD.FROZEN_CONSTANTS,
                                       sort_keys=True))
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        raise SystemExit(f"EPOCH-2-TRANSITION-REFUSED: frozen constants "
                         f"mirror unreadable: {e}")
    lock = {
        "lock": "EXECUTION-LOCK",
        "epoch": EPOCH.EPOCH_NUMBER,
        "status": "open-round2",
        "freeze_commit": freeze_commit,
        "note": ("EPOCH-2 lineage (fresh locks + new finalization). Minted "
                 "by harness/epoch_transition.py from the epoch-1 closure "
                 "record; its own append-only amendment lineage (NOT an "
                 "amendment to the epoch-1 lineage). The epoch-1 "
                 "EXECUTION-LOCK.json stays frozen as the historical "
                 "record of the closed epoch. Re-mint on every harness "
                 "change via harness/mint_execution_lock.py --slice ... "
                 "--reason ...; finalize only by owner authorization."),
        "harness_manifest_sha256": _manifest_sha(files),
        "harness_files": files,
        "frozen_constants": consts,
        "amendments": [],
        "transition": {
            "record": EPOCH.TRANSITION_FILE,
            "record_sha256": record_rel_sha,
            "from_epoch": EPOCH.FROM_EPOCH,
            "epoch1_closure_record": EPOCH.EPOCH1_CLOSURE_FILE,
            "epoch1_execution_lock_sha256":
                EPOCH.EPOCH1_EXECUTION_LOCK_SHA256,
            "epoch1_protocol_lock_sha256":
                EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256,
            "epoch1_finalization_commit": EPOCH.EPOCH1_FINALIZATION_COMMIT,
            "reason": reason},
        "created_at": _stamp(),
    }
    p = os.path.join(FAMC, EPOCH.EXECUTION_LOCK_FILE)
    with open(p, "w") as f:
        json.dump(lock, f, indent=1)
        f.write("\n")
    return p, lock["harness_manifest_sha256"], len(files)


def _mint_protocol_lock(record_rel_sha, freeze_commit, genesis, reason):
    governed = {fn: _sha_abs(os.path.join(FAMC, fn))
                for fn in PROTOCOL_GOVERNED}
    lock = {
        "lock": "PROTOCOL-LOCK",
        "epoch": EPOCH.EPOCH_NUMBER,
        "status": "living-lock",
        "freeze_commit": freeze_commit,
        "note": ("EPOCH-2 lineage (fresh locks + new finalization). Minted "
                 "by harness/epoch_transition.py from the epoch-1 closure "
                 "record; its own append-only amendment lineage (NOT an "
                 "amendment to the epoch-1 lineage). The epoch-1 "
                 "PROTOCOL-LOCK.json stays frozen as the historical record "
                 "of the closed epoch. Forward amendments to a governed "
                 "file are appended here (human-written reason), exactly "
                 "as before — on this new base."),
        "governed": governed,
        "amendments": [],
        "protocol_artifacts": {
            "ORDER-EXPANSION.json":
                _sha_abs(os.path.join(FAMC, "ORDER-EXPANSION.json"))},
        "transition": {
            "record": EPOCH.TRANSITION_FILE,
            "record_sha256": record_rel_sha,
            "from_epoch": EPOCH.FROM_EPOCH,
            "epoch1_closure_record": EPOCH.EPOCH1_CLOSURE_FILE,
            "epoch1_execution_lock_sha256":
                EPOCH.EPOCH1_EXECUTION_LOCK_SHA256,
            "epoch1_protocol_lock_sha256":
                EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256,
            "epoch1_finalization_commit": EPOCH.EPOCH1_FINALIZATION_COMMIT,
            "reason": reason},
        "created_at": _stamp(),
    }
    if governed != genesis:
        raise SystemExit("EPOCH-2-TRANSITION-REFUSED: protocol genesis map "
                         "drifted between record and lock mint (concurrent "
                         "edit?); re-run the transition from a clean tree")
    p = os.path.join(FAMC, EPOCH.PROTOCOL_LOCK_FILE)
    with open(p, "w") as f:
        json.dump(lock, f, indent=1)
        f.write("\n")
    return p, len(governed)


def _check():
    print(f"epoch state: epoch {EPOCH.active_epoch(FAMC)} "
          f"(state root {os.path.relpath(EPOCH.state_root(FAMC), ROOT)})")
    if EPOCH.is_epoch3(FAMC):
        findings = EPOCH.validate_transition3(FAMC)
        for f in findings:
            print("FAIL:", f)
        if findings:
            return 1
        print("epoch-3 transition record + fresh locks + the epoch-2 "
              "boundary it cites verify: green")
        return 0
    if not EPOCH.is_epoch2(FAMC):
        print("no epoch-2 transition recorded: epoch 1 (historical layout) "
              "— consistent")
        return 0
    findings = EPOCH.validate_transition(FAMC)
    for f in findings:
        print("FAIL:", f)
    if findings:
        return 1
    print("epoch-2 transition record + fresh locks verify: green")
    return 0


# ---------------------------------------------------------------------------
# EPOCH-2 -> EPOCH-3 TRANSITION (EPOCH-3-PROTOCOL-SPEC.md §6, frozen)
# ---------------------------------------------------------------------------

def _verify_epoch2_boundary():
    """Fail closed unless the FROZEN epoch-2 boundary facts are exactly as
    the epoch-3 spec pins them: the epoch-2 transition record bytes, both
    epoch-2 FINAL lock bytes, the epoch-2 finalization commit, the corrected
    stop record, the frozen epoch-3 spec, and the exact frozen
    ORDER-EXPANSION.json pin. Returns the epoch-2 transition sha256."""
    findings = []
    want = {
        EPOCH.TRANSITION_FILE: (EPOCH.EPOCH2_TRANSITION_SHA256,
                                "the epoch-2 transition record bytes"),
        EPOCH.EXECUTION_LOCK_FILE: (EPOCH.EPOCH2_EXECUTION_LOCK_SHA256,
                                    "the epoch-2 FINAL execution lock"),
        EPOCH.PROTOCOL_LOCK_FILE: (EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256,
                                   "the epoch-2 FINAL protocol lock"),
        EPOCH.EPOCH2_STOP_RECORD_FILE: (EPOCH.EPOCH2_STOP_RECORD_SHA256,
                                        "the corrected stop record"),
        EPOCH.EPOCH3_SPEC_FILE: (EPOCH.EPOCH3_SPEC_SHA256,
                                 "the frozen epoch-3 protocol spec"),
        "ORDER-EXPANSION.json": (EPOCH.ORDER_EXPANSION_SHA256,
                                 "the frozen order expansion"),
    }
    for name, (want_sha, label) in sorted(want.items()):
        p = os.path.join(FAMC, name)
        if not os.path.isfile(p):
            findings.append(f"{name} missing (the epoch-3 transition must "
                            f"cite {label})")
            continue
        got = _sha_abs(p)
        if got != want_sha:
            findings.append(f"{name} bytes {got[:12]} != the frozen "
                            f"{label} {want_sha[:12]}")
    for name in (EPOCH.EXECUTION_LOCK_FILE, EPOCH.PROTOCOL_LOCK_FILE):
        p = os.path.join(FAMC, name)
        if not os.path.isfile(p):
            continue
        try:
            lock = json.load(open(p))
        except (OSError, ValueError) as e:
            findings.append(f"{name} unparsable: {e}")
            continue
        if lock.get("status") != "FINAL":
            findings.append(f"{name} status {lock.get('status')!r} != "
                            f"'FINAL' (epoch 2 must be finalized before "
                            f"epoch 3 restarts the order)")
        if lock.get("finalization_commit") != EPOCH.EPOCH2_FINALIZATION_COMMIT:
            findings.append(f"{name} finalization_commit "
                            f"{lock.get('finalization_commit')!r} != the "
                            f"recorded "
                            f"{EPOCH.EPOCH2_FINALIZATION_COMMIT}")
    _find = EPOCH.validate_transition(FAMC)
    findings += [f"epoch-2 boundary: {f}" for f in _find]
    if findings:
        raise SystemExit("EPOCH-3-TRANSITION-REFUSED: the epoch-2 boundary "
                         "does not verify on disk — refusing to transition "
                         "FROM an unverified epoch:\n  - "
                         + "\n  - ".join(findings))
    return EPOCH.EPOCH2_TRANSITION_SHA256


def _mint_execution_lock3(record_rel_sha, freeze_commit, reason):
    files = {}
    entry = os.path.join("benchmarks", "fam-c", "harness-run",
                         "run_arm_h1.py")
    for rel in sorted(_harness_closure(ROOT, entry)):
        files[rel] = _sha_rel(rel)
    hdir = os.path.join(ROOT, "harness")
    for name in sorted(os.listdir(hdir)):
        if name.endswith(".py"):
            rel = f"harness/{name}"
            files[rel] = _sha_rel(rel)
    try:
        sys.path.insert(0, HERE)
        import adaptation as AD
        consts = json.loads(json.dumps(AD.FROZEN_CONSTANTS,
                                       sort_keys=True))
    except (ImportError, AttributeError, TypeError, ValueError) as e:
        raise SystemExit(f"EPOCH-3-TRANSITION-REFUSED: frozen constants "
                         f"mirror unreadable: {e}")
    lock = {
        "lock": "EXECUTION-LOCK",
        "epoch": EPOCH.EPOCH3_NUMBER,
        "status": "open-round2",
        "freeze_commit": freeze_commit,
        "note": ("EPOCH-3 lineage (fresh locks + new finalization). Minted "
                 "by harness/epoch_transition.py from the frozen epoch-2 "
                 "boundary; its own append-only amendment lineage (NOT an "
                 "amendment to the epoch-2 or epoch-1 lineages, which stay "
                 "frozen as the historical records of the stopped epoch and "
                 "the closed epoch). The status vocabulary is unchanged "
                 "from epoch 2 (open-round2 | FINAL). Re-mint on every "
                 "harness change via harness/mint_execution_lock.py --slice "
                 "... --reason ...; finalize only by owner authorization "
                 "AFTER independent certification and the "
                 "execution-authorization ruling."),
        "harness_manifest_sha256": _manifest_sha(files),
        "harness_files": files,
        "frozen_constants": consts,
        "amendments": [],
        "transition": {
            "record": EPOCH.EPOCH3_TRANSITION_FILE,
            "record_sha256": record_rel_sha,
            "from_epoch": EPOCH.EPOCH3_FROM_EPOCH,
            "epoch2_transition_record": EPOCH.TRANSITION_FILE,
            "epoch2_transition_sha256": EPOCH.EPOCH2_TRANSITION_SHA256,
            "epoch2_execution_lock_sha256":
                EPOCH.EPOCH2_EXECUTION_LOCK_SHA256,
            "epoch2_protocol_lock_sha256":
                EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256,
            "epoch2_finalization_commit": EPOCH.EPOCH2_FINALIZATION_COMMIT,
            "reason": reason},
        "created_at": _stamp(),
    }
    p = os.path.join(FAMC, EPOCH.EPOCH3_EXECUTION_LOCK_FILE)
    with open(p, "w") as f:
        json.dump(lock, f, indent=1)
        f.write("\n")
    return p, lock["harness_manifest_sha256"], len(files)


def _mint_protocol_lock3(record_rel_sha, freeze_commit, genesis, reason):
    lock = {
        "lock": "PROTOCOL-LOCK",
        "epoch": EPOCH.EPOCH3_NUMBER,
        "status": "living-lock",
        "freeze_commit": freeze_commit,
        "note": ("EPOCH-3 lineage (fresh locks + new finalization). Minted "
                 "by harness/epoch_transition.py from the frozen epoch-2 "
                 "boundary; its own append-only amendment lineage (NOT an "
                 "amendment to the epoch-2 or epoch-1 lineages). The "
                 "governed set is the frozen FR-13 rule: the existing seven "
                 "governed files PLUS EPOCH-3-PROTOCOL-SPEC.md (being V1 "
                 "META never exempts the spec from V2). Forward amendments "
                 "to a governed file are appended here (human-written "
                 "reason), exactly as before — on this new base."),
        "governed": dict(genesis),
        "amendments": [],
        "protocol_artifacts": {
            "ORDER-EXPANSION.json":
                _sha_abs(os.path.join(FAMC, "ORDER-EXPANSION.json"))},
        "transition": {
            "record": EPOCH.EPOCH3_TRANSITION_FILE,
            "record_sha256": record_rel_sha,
            "from_epoch": EPOCH.EPOCH3_FROM_EPOCH,
            "epoch2_transition_record": EPOCH.TRANSITION_FILE,
            "epoch2_transition_sha256": EPOCH.EPOCH2_TRANSITION_SHA256,
            "epoch2_execution_lock_sha256":
                EPOCH.EPOCH2_EXECUTION_LOCK_SHA256,
            "epoch2_protocol_lock_sha256":
                EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256,
            "epoch2_finalization_commit": EPOCH.EPOCH2_FINALIZATION_COMMIT,
            "reason": reason},
        "created_at": _stamp(),
    }
    p = os.path.join(FAMC, EPOCH.EPOCH3_PROTOCOL_LOCK_FILE)
    with open(p, "w") as f:
        json.dump(lock, f, indent=1)
        f.write("\n")
    return p, len(lock["governed"])


def transition_epoch3(reason):
    """Perform the ONE epoch-2 -> epoch-3 transition the frozen spec
    orders: refuse if a record or either fresh lock already exists, verify
    the frozen epoch-2 boundary byte for byte, write the record, mint both
    epoch-3 locks OPEN on their own lineage, and re-validate. It NEVER
    finalizes: finalization follows independent certification + the
    execution-authorization ruling."""
    if os.path.exists(EPOCH.transition_path3(FAMC)):
        print("EPOCH-3-TRANSITION-REFUSED: a transition record already "
              f"exists ({EPOCH.EPOCH3_TRANSITION_FILE}); the transition is "
              "write-once")
        return 1
    for name in (EPOCH.EPOCH3_EXECUTION_LOCK_FILE,
                 EPOCH.EPOCH3_PROTOCOL_LOCK_FILE):
        if os.path.exists(os.path.join(FAMC, name)):
            print(f"EPOCH-3-TRANSITION-REFUSED: {name} already exists; "
                  "refusing to overwrite a fresh-lineage lock (the "
                  "transition is write-once)")
            return 1
    epoch2_sha = _verify_epoch2_boundary()
    freeze_commit = _freeze_commit()
    genesis = {fn: _sha_abs(os.path.join(FAMC, fn))
               for fn in EPOCH3_GOVERNED}
    rec = {
        "transition": "epoch-2-to-epoch-3",
        "epoch_id": EPOCH.EPOCH3_ID,
        "from_epoch": EPOCH.EPOCH3_FROM_EPOCH,
        "to_epoch": EPOCH.EPOCH3_NUMBER,
        "ruling": ("EPOCH-3-PROTOCOL-SPEC.md (frozen): "
                   "MODEL-OUTPUT-INVALID terminal + attempt accounting + "
                   "event-0 restart; epoch 2 stays STOPPED / INCOMPLETE, "
                   "preserved, never carried forward"),
        "epoch2_transition_record": EPOCH.TRANSITION_FILE,
        "epoch2_transition_sha256": epoch2_sha,
        "epoch2_execution_lock_sha256": EPOCH.EPOCH2_EXECUTION_LOCK_SHA256,
        "epoch2_protocol_lock_sha256": EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256,
        "epoch2_finalization_commit": EPOCH.EPOCH2_FINALIZATION_COMMIT,
        "epoch2_stop_record": EPOCH.EPOCH2_STOP_RECORD_FILE,
        "epoch2_stop_record_sha256": EPOCH.EPOCH2_STOP_RECORD_SHA256,
        "epoch3_protocol_spec": EPOCH.EPOCH3_SPEC_FILE,
        "epoch3_protocol_spec_sha256": EPOCH.EPOCH3_SPEC_SHA256,
        "epoch3_freeze_commit": EPOCH.EPOCH3_FREEZE_COMMIT,
        "order_expansion_sha256": EPOCH.ORDER_EXPANSION_SHA256,
        "state_prefix": EPOCH.EPOCH3_STATE_PREFIX,
        "execution_lock": EPOCH.EPOCH3_EXECUTION_LOCK_FILE,
        "protocol_lock": EPOCH.EPOCH3_PROTOCOL_LOCK_FILE,
        "genesis": genesis,
        "reason": reason,
        "created_at": _stamp(),
        "created_from": ("frozen-evidence (epoch-2 stop record + FINAL "
                         "epoch-2 locks + frozen epoch-3 spec)"),
    }
    rp = EPOCH.transition_path3(FAMC)
    with open(rp, "w") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    rec_sha = _sha_abs(rp)
    print(f"EPOCH-3-TRANSITION: record written "
          f"({EPOCH.EPOCH3_TRANSITION_FILE} sha256 {rec_sha[:12]}) citing "
          f"epoch-2 transition {epoch2_sha[:12]}, FINAL locks "
          f"{EPOCH.EPOCH2_EXECUTION_LOCK_SHA256[:12]}/"
          f"{EPOCH.EPOCH2_PROTOCOL_LOCK_SHA256[:12]}, stop record "
          f"{EPOCH.EPOCH2_STOP_RECORD_SHA256[:12]}, spec "
          f"{EPOCH.EPOCH3_SPEC_SHA256[:12]} @ "
          f"{EPOCH.EPOCH3_FREEZE_COMMIT[:12]}, order expansion "
          f"{EPOCH.ORDER_EXPANSION_SHA256[:12]}")
    ep, msha, nfiles = _mint_execution_lock3(rec_sha, freeze_commit, reason)
    print(f"EPOCH-3-TRANSITION: minted {os.path.basename(ep)} ({nfiles} "
          f"harness file(s), manifest {msha[:12]}, status open-round2, "
          f"amendments: [])")
    pp, ngov = _mint_protocol_lock3(rec_sha, freeze_commit, genesis, reason)
    print(f"EPOCH-3-TRANSITION: minted {os.path.basename(pp)} ({ngov} "
          f"governed file(s), status living-lock, amendments: [])")
    findings = EPOCH.validate_transition3(FAMC)
    if findings:
        for f in findings:
            print("FAIL:", f)
        print("EPOCH-3-TRANSITION-REFUSED: post-mint validation failed "
              "(the fresh locks do not verify; inspect before committing)")
        return 1
    print("EPOCH-3-TRANSITION COMPLETE: epoch 3 is active; state prefixes "
          f"under {EPOCH.EPOCH3_STATE_PREFIX}/. Both epoch-3 locks are OPEN "
          "— the runner refuses wired estimand cells until BOTH are "
          "finalized by the owner AFTER independent certification and the "
          "execution-authorization ruling. Epoch-2 and epoch-1 state and "
          "locks are untouched historical records.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--transition", action="store_true")
    ap.add_argument("--transition-epoch3", action="store_true",
                    dest="transition_epoch3")
    ap.add_argument("--reason", default="third-party ruling: EPOCH-2 "
                    "PROTOCOL (EPOCH-1-CLOSURE.md); fresh locks + new "
                    "lineage")
    a = ap.parse_args(argv)
    _n = sum(1 for x in (a.check, a.transition, a.transition_epoch3) if x)
    if _n != 1:
        ap.error("choose exactly one of --check / --transition / "
                 "--transition-epoch3")
    if a.check:
        return _check()
    if a.transition_epoch3:
        return transition_epoch3(a.reason)
    if os.path.exists(EPOCH.transition_path(FAMC)):
        print("EPOCH-2-TRANSITION-REFUSED: a transition record already "
              f"exists ({EPOCH.TRANSITION_FILE}); the transition is "
              "write-once (epoch-2 state and locks are live now — use "
              "harness/mint_execution_lock.py for further amendments)")
        return 1
    for name in (EPOCH.EXECUTION_LOCK_FILE, EPOCH.PROTOCOL_LOCK_FILE):
        if os.path.exists(os.path.join(FAMC, name)):
            print(f"EPOCH-2-TRANSITION-REFUSED: {name} already exists; "
                  "refusing to overwrite a fresh-lineage lock (the "
                  "transition is write-once)")
            return 1
    closure_sha = _verify_epoch1_closure()
    freeze_commit = _freeze_commit()
    # The epoch-2 genesis base IS the transition-time governed bytes (they
    # must be committed on the experiment branch: preflight's Rule A/B
    # subsequence test proves it). Recorded in the transition record, which
    # both epoch-2 locks cite by hash.
    genesis = {fn: _sha_abs(os.path.join(FAMC, fn))
               for fn in PROTOCOL_GOVERNED}
    rec = {
        "transition": "epoch-1-to-epoch-2",
        "epoch_id": EPOCH.EPOCH_ID,
        "from_epoch": EPOCH.FROM_EPOCH,
        "to_epoch": EPOCH.EPOCH_NUMBER,
        "ruling": ("EPOCH-1-CLOSURE.md (third-party ruling, 2026-09-17): "
                   "EPOCH-2 PROTOCOL + TERMINAL-OUTCOME PROGRESS "
                   "SEMANTICS; epoch 1 terminated-not-repaired, immutable"),
        "epoch1_closure_record": EPOCH.EPOCH1_CLOSURE_FILE,
        "closure_record_sha256": closure_sha,
        "epoch1_execution_lock_sha256":
            EPOCH.EPOCH1_EXECUTION_LOCK_SHA256,
        "epoch1_protocol_lock_sha256": EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256,
        "epoch1_finalization_commit": EPOCH.EPOCH1_FINALIZATION_COMMIT,
        "epoch1_certification_ref": EPOCH.EPOCH1_CERTIFICATION_REF,
        "state_prefix": EPOCH.STATE_PREFIX,
        "execution_lock": EPOCH.EXECUTION_LOCK_FILE,
        "protocol_lock": EPOCH.PROTOCOL_LOCK_FILE,
        "genesis": genesis,
        "reason": a.reason,
        "created_at": _stamp(),
        "created_from": "frozen-evidence (epoch-1 closure record)",
    }
    rp = EPOCH.transition_path(FAMC)
    with open(rp, "w") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    rec_sha = _sha_abs(rp)
    print(f"EPOCH-2-TRANSITION: record written ({EPOCH.TRANSITION_FILE} "
          f"sha256 {rec_sha[:12]}) citing closure {closure_sha[:12]}, "
          f"exec-lock {EPOCH.EPOCH1_EXECUTION_LOCK_SHA256[:12]}, "
          f"proto-lock {EPOCH.EPOCH1_PROTOCOL_LOCK_SHA256[:12]}")
    ep, msha, nfiles = _mint_execution_lock(rec_sha, freeze_commit, a.reason)
    print(f"EPOCH-2-TRANSITION: minted {os.path.basename(ep)} "
          f"({nfiles} harness file(s), manifest {msha[:12]}, status "
          f"open-round2, amendments: [])")
    pp, ngov = _mint_protocol_lock(rec_sha, freeze_commit, genesis, a.reason)
    print(f"EPOCH-2-TRANSITION: minted {os.path.basename(pp)} "
          f"({ngov} governed file(s), status living-lock, amendments: [])")
    findings = EPOCH.validate_transition(FAMC)
    if findings:
        for f in findings:
            print("FAIL:", f)
        print("EPOCH-2-TRANSITION-REFUSED: post-mint validation failed "
              "(the fresh locks do not verify; inspect before committing)")
        return 1
    print("EPOCH-2-TRANSITION COMPLETE: epoch 2 is active; state prefixes "
          f"under {EPOCH.STATE_PREFIX}/. The epoch-2 locks are OPEN — the "
          "runner refuses wired estimand cells until BOTH are finalized "
          "by the owner. Epoch-1 state/ and locks are untouched historical "
          "records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
