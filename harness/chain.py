#!/usr/bin/env python3
"""H3 evidence-manifest chain: every run auditable as an unbroken hash
chain — frozen commit → run manifest → model calls → capability events
→ evaluator → grade. The auditor re-verifies every link; any broken
link excludes the run. Deletion, reordering, and substitution are all
detectable because each record commits to its predecessor. Stdlib only.
"""
import hashlib
import json
import os
import time

GENESIS_NOTE = "chain starts at the frozen commit recorded in run manifest"


def _h(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True).encode()).hexdigest()


class Chain:
    GENESIS_PREV = "GENESIS-ROOT"

    def __init__(self, path, frozen_commit, run_manifest, pair_id=None,
                 arm=None, authorization_hash=None,
                 task_snapshot_hash=None):
        self.path = path
        genesis = {"genesis": GENESIS_NOTE,
                   "frozen_commit": frozen_commit,
                   "run_manifest": run_manifest,
                   "run_manifest_hash": _h(run_manifest)}
        # Genesis binds the pair/arm/authorization/task when provided;
        # replacement manifests verify against these exact values.
        for k, v in (("pair_id", pair_id), ("arm", arm),
                     ("authorization_hash", authorization_hash),
                     ("task_snapshot_hash", task_snapshot_hash)):
            if v is not None:
                genesis[k] = v
        self._genesis = genesis
        self.links = []
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line:
                    self.links.append(json.loads(line))
        if not self.links:
            # Genesis is link 0, persisted: the chain file always opens
            # with its own verifiable root.
            rec = {"prev": self.GENESIS_PREV, "kind": "genesis",
                   "payload": dict(genesis),
                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            rec["link_hash"] = _h({k: v for k, v in rec.items()
                                   if k != "link_hash"})
            with open(path, "w") as f:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
            self.links.append(rec)
        self.tip = self.links[-1]["link_hash"]

    @staticmethod
    def genesis_record(path):
        """Return the persisted link-0 genesis payload of a chain file."""
        with open(path) as f:
            first = json.loads(f.readline())
        if first.get("kind") != "genesis" or first.get("prev") != \
                Chain.GENESIS_PREV:
            raise ValueError("not a rooted evidence chain")
        return first["payload"]

    def append(self, kind, payload):
        if self.links and self.links[-1].get("kind") == "grade":
            raise PermissionError(
                "CHAIN-TERMINAL: grade is final; nothing may append after it")
        if kind == "grade":
            for f in ("evaluator_link_hash", "grading_rule_hash",
                      "grading_rule_version"):
                if f not in payload:
                    raise ValueError(
                        f"CHAIN-GRADE-INCOMPLETE: grade payload missing {f!r}")
        rec = {"prev": self.tip, "kind": kind, "payload": payload,
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec["link_hash"] = _h({k: v for k, v in rec.items()
                               if k != "link_hash"})
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        self.links.append(rec)
        self.tip = rec["link_hash"]
        return rec["link_hash"]

    def audit(self, frozen_commit, run_manifest, expected_grading_rule=None):
        """Re-verify the whole chain; returns list of findings
        (empty = intact). Link-0 genesis is verified on its own terms:
        kind, prev == GENESIS-ROOT, recomputed link_hash, bound frozen
        commit + run manifest (deep equality), and run_manifest_hash
        against the canonical expected manifest. Downstream linkage
        continues from the recomputed genesis hash, never from a stored
        value. expected_grading_rule: frozen {"hash":..., "version":...};
        when provided the terminal grade's rule hash/version must EQUAL
        it (mere presence is insufficient)."""
        findings = []
        # Link 0 must be the genesis record itself, bound to the frozen
        # commit and run manifest the audit was invoked with. A12.0-c:
        # genesis link 0 is never trusted from the stored record — kind,
        # root prev, hash recompute, frozen commit, manifest deep
        # equality and the canonical manifest hash are all re-checked.
        if not self.links:
            findings.append("GENESIS link 0 missing: chain has no links")
            return findings
        g0 = self.links[0]
        if g0.get("kind") != "genesis":
            findings.append(
                f"GENESIS link 0 kind: expected 'genesis', got "
                f"{g0.get('kind')!r}")
            return findings
        if g0.get("prev") != self.GENESIS_PREV:
            findings.append(
                f"GENESIS link 0 prev: {g0.get('prev')!r} != "
                f"{self.GENESIS_PREV}")
        recomputed_g0 = _h({k: v for k, v in g0.items()
                            if k != "link_hash"})
        if recomputed_g0 != g0.get("link_hash"):
            findings.append(
                "GENESIS link 0 link_hash: recomputed != stored "
                "(content altered post-write)")
        payload = g0.get("payload")
        if not isinstance(payload, dict):
            findings.append("GENESIS link 0 payload: missing")
            payload = {}
        if payload.get("frozen_commit") != frozen_commit:
            findings.append("GENESIS payload frozen_commit: mismatch")
        if payload.get("run_manifest") != run_manifest:
            findings.append("GENESIS payload run_manifest: mismatch")
        if payload.get("run_manifest_hash") != _h(run_manifest):
            findings.append(
                "GENESIS payload run_manifest_hash: != sha256 of "
                "canonical expected manifest")
        # Normal linkage starts from the VERIFIED genesis hash.
        expect_prev = recomputed_g0
        seen = {expect_prev}
        for i, rec in enumerate(self.links[1:], start=1):
            if rec.get("prev") != expect_prev:
                findings.append(f"link {i}: broken predecessor linkage")
            if rec.get("link_hash") in seen:
                findings.append(f"link {i}: duplicate hash (reorder/replay)")
            seen.add(rec.get("link_hash"))
            recomputed = _h({k: v for k, v in rec.items()
                             if k != "link_hash"})
            if recomputed != rec.get("link_hash"):
                findings.append(f"link {i}: content altered post-write")
            if rec.get("kind") not in ("model-call", "capability-event",
                                       "evaluator", "grade", "note"):
                findings.append(f"link {i}: unknown kind {rec.get('kind')!r}")
            expect_prev = rec.get("link_hash")
        grades = [i for i, r in enumerate(self.links)
                  if r.get("kind") == "grade"]
        if len(grades) != 1:
            findings.append(
                f"chain must contain exactly one grade, found {len(grades)}")
        elif grades[0] != len(self.links) - 1:
            findings.append("grade is not the final link")
        else:
            g = self.links[-1]["payload"]
            if expected_grading_rule is not None:
                if (g.get("grading_rule_hash")
                        != expected_grading_rule.get("hash")
                        or g.get("grading_rule_version")
                        != expected_grading_rule.get("version")):
                    findings.append(
                        "grade rule hash/version != frozen expected rule")
            ev_links = [i for i, r in enumerate(self.links)
                        if r.get("kind") == "evaluator"]
            if not ev_links:
                findings.append("grade binds no evaluator record")
            else:
                ev = self.links[ev_links[-1]]
                if g.get("evaluator_link_hash") != ev.get("link_hash"):
                    findings.append(
                        "grade does not bind the immediately preceding "
                        "admissible evaluator state")
        return findings


def verify_chain(path, frozen_commit=None, run_manifest=None,
                 expected_grading_rule=None):
    """Module-level evidence-chain verifier (A11b.3). Re-verifies ONE
    persisted chain file with the SAME authority as Chain.audit() — it
    constructs Chain(path, frozen_commit, run_manifest) and runs .audit();
    never a second independent implementation.

    Defaults: run_manifest = the H1-RUN-MANIFEST.json beside the chain
    file; frozen_commit = run_manifest["instance_freeze_commit"]. A chain
    is verified WITHOUT ever writing to the file (genesis is written by
    the runner at capture time, never by a verifier): an absent, dangling
    or empty chain file is invalid, not genesis-seeded here.

    Returns [] when the chain is intact; raises
    ValueError("CHAIN-INVALID: ...") on any finding."""
    if os.path.islink(path) or not os.path.isfile(path):
        raise ValueError(f"CHAIN-INVALID: no chain file at {path}")
    if run_manifest is None:
        mfp = os.path.join(os.path.dirname(os.path.abspath(path)),
                           "H1-RUN-MANIFEST.json")
        if os.path.islink(mfp) or not os.path.isfile(mfp):
            raise ValueError(f"CHAIN-INVALID: no H1-RUN-MANIFEST.json "
                             f"beside {path} (pass run_manifest= to verify "
                             "a bare chain)")
        run_manifest = json.load(open(mfp))
    if frozen_commit is None:
        frozen_commit = run_manifest.get("instance_freeze_commit")
        if not isinstance(frozen_commit, str) or not frozen_commit:
            raise ValueError("CHAIN-INVALID: run manifest carries no "
                             "instance_freeze_commit")
    lines = [ln for ln in open(path) if ln.strip()]
    if not lines:
        raise ValueError("CHAIN-INVALID: chain file is empty")
    chain = Chain(path, frozen_commit, run_manifest)
    findings = chain.audit(frozen_commit, run_manifest,
                           expected_grading_rule=expected_grading_rule)
    if findings:
        raise ValueError("CHAIN-INVALID: " + "; ".join(findings))
    return []
