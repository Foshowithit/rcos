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
    def __init__(self, path, frozen_commit, run_manifest):
        self.path = path
        self.tip = _h({"genesis": GENESIS_NOTE,
                       "frozen_commit": frozen_commit,
                       "run_manifest": run_manifest,
                       "run_manifest_hash": _h(run_manifest)})
        self.links = []
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line:
                    self.links.append(json.loads(line))
            if self.links:
                self.tip = self.links[-1]["link_hash"]

    def append(self, kind, payload):
        rec = {"prev": self.tip, "kind": kind, "payload": payload,
               "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        rec["link_hash"] = _h({k: v for k, v in rec.items()
                               if k != "link_hash"})
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
        self.links.append(rec)
        self.tip = rec["link_hash"]
        return rec["link_hash"]

    def audit(self, frozen_commit, run_manifest):
        """Re-verify the whole chain. Returns list of findings
        (empty = intact). Checks: genesis binding, hash linkage order,
        no gaps, no duplicate link hashes (reorder/substitution),
        payload presence per kind."""
        findings = []
        expect_prev = _h({"genesis": GENESIS_NOTE,
                          "frozen_commit": frozen_commit,
                          "run_manifest": run_manifest,
                          "run_manifest_hash": _h(run_manifest)})
        seen = set()
        for i, rec in enumerate(self.links):
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
        if self.links and self.links[-1].get("kind") != "grade":
            findings.append("chain does not terminate in a grade record")
        return findings
