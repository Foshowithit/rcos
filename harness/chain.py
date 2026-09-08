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
        """expected_grading_rule: frozen {"hash":..., "version":...}.
        When provided, the terminal grade's rule hash/version must EQUAL
        it (mere presence is insufficient)."""
        """Re-verify the whole chain. Returns list of findings
        (empty = intact). Checks: genesis binding, hash linkage order,
        no gaps, no duplicate link hashes (reorder/substitution),
        payload presence per kind."""
        findings = []
        # Link 0 must be the genesis record itself, bound to the frozen
        # commit and run manifest the audit was invoked with.
        if not self.links or self.links[0].get("kind") != "genesis":
            findings.append("missing genesis link 0")
            return findings
        g0 = self.links[0]["payload"]
        if g0.get("frozen_commit") != frozen_commit:
            findings.append("genesis frozen-commit mismatch")
        if g0.get("run_manifest") != run_manifest:
            findings.append("genesis run-manifest mismatch")
        expect_prev = self.links[0].get("link_hash")
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
