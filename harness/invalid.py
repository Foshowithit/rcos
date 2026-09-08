#!/usr/bin/env python3
"""H3 invalid/infrastructure state machine — the frozen taxonomy as code.
Agent/model failure is ALWAYS an experimental outcome (recorded, never
invalidated). Only a qualifying infrastructure failure permits EXACTLY
ONE whole-pair replacement under identical frozen settings, with
originals immutable and linked. Anything else is rejected. Stdlib only.
"""
import json
import os

# Agent-side failures: experimental outcomes. NEVER infrastructure.
AGENT_FAILURES = frozenset({
    "reasoning-failure", "tool-misuse", "agent-timeout",
    "bad-generated-code", "capability-invocation-failure",
    "malformed-output",
})
# Infrastructure failures: the ONLY invalidating class.
INFRA_FAILURES = frozenset({
    "machine-down", "provider-outage", "harness-crash",
    "storage-unavailable", "network-partition",
})


def classify(failure_kind):
    """Returns 'outcome' | 'infrastructure' | raises on unknown kinds
    (unknown failure modes are experimental outcomes by default — the
    conservative direction for validity, since outcomes count and
    invalidations erase)."""
    if failure_kind in AGENT_FAILURES:
        return "outcome"
    if failure_kind in INFRA_FAILURES:
        return "infrastructure"
    return "outcome"


class PairLedger:
    """Tracks replacement state per paired comparison. Persisted as JSON."""

    def __init__(self, path):
        self.path = path
        if os.path.exists(path):
            self.state = json.load(open(path))
        else:
            self.state = {"pairs": {}}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.state, f, indent=1)

    def record_run(self, pair_id, arm, verdict, failure_kind=None,
                   task_snapshot=None):
        runs = self.state["pairs"].setdefault(
            pair_id, {"runs": [], "replacements": 0, "status": "open"})
        runs["runs"].append({"arm": arm, "verdict": verdict,
                             "failure_kind": failure_kind,
                             "task_snapshot": task_snapshot})
        if task_snapshot is not None and runs.get("task_snapshot_hash") is None:
            import hashlib as _hl3
            runs["task_snapshot_hash"] = _hl3.sha256(
                json.dumps(task_snapshot, sort_keys=True).encode()).hexdigest()
        self._save()
        return runs

    def request_replacement(self, pair_id, failure_kind, frozen_settings_id):
        """Returns (allowed: bool, reason). Enforces: single replacement,
        whole-pair only (caller passes BOTH arms), identical settings,
        infrastructure-only cause. Originals stay; replacements link."""
        runs = self.state["pairs"].get(pair_id)
        if runs is None:
            return False, "unknown pair"
        if classify(failure_kind) != "infrastructure":
            return False, (f"agent/model failure {failure_kind!r} is an "
                           f"experimental outcome, not invalid")
        if runs["replacements"] >= 1:
            runs["status"] = "missing-evidence"
            self._save()
            return False, "second replacement refused: pair marked " \
                          "missing-evidence per frozen precedence"
        if runs.get("settings_id") and \
                runs["settings_id"] != frozen_settings_id:
            return False, "settings differ from frozen original"
        import hashlib as _hl2
        runs["replacements"] += 1
        runs["settings_id"] = frozen_settings_id
        runs["settings_hash"] = _hl2.sha256(
            json.dumps(frozen_settings_id, sort_keys=True).encode()
            if not isinstance(frozen_settings_id, str)
            else frozen_settings_id.encode()).hexdigest()
        runs["authorization_hash"] = _hl2.sha256(json.dumps(
            {"pair": pair_id, "generation": runs["replacements"],
             "settings": frozen_settings_id}, sort_keys=True).encode()
        ).hexdigest()
        runs["replacement_epoch"] = runs["replacements"]
        runs["task_snapshot_hash"] = _hl2.sha256(json.dumps(
            runs.get("task_snapshot", {}), sort_keys=True).encode()
        ).hexdigest()
        runs["expected_arms"] = sorted(
            {r["arm"] for r in runs["runs"]})
        runs["status"] = "replaced-once"
        self._save()
        return True, "one whole-pair replacement allowed"

    def pair_status(self, pair_id):
        return self.state["pairs"].get(pair_id, {}).get("status", "unknown")

    def complete_replacement(self, pair_id, run_manifest_path):
        """Record one replacement arm execution BY MANIFEST, not by
        caller assertion. The manifest must carry: run_id, pair_id, arm,
        replacement_epoch, replaces_original_run_id, authorization_hash,
        frozen_settings_hash, task/input_snapshot_hash, evidence genesis
        hash. The ledger derives every property from the manifest and
        verifies: same pair, same authorization as granted, same frozen
        settings, arm in the authorized pair set, epoch matches the open
        replacement generation, and the task snapshot equals the
        original pair's. Stores the manifest HASH, never bare run ids.
        Grading may consume replacement results only when both arms are
        so bound (status replacement-complete)."""
        runs = self.state["pairs"].get(pair_id)
        if runs is None:
            raise ValueError(f"unknown pair {pair_id}")
        if runs.get("status") != "replaced-once":
            raise ValueError(f"pair {pair_id} has no open replacement "
                             f"(status={runs.get('status')})")
        m = json.load(open(run_manifest_path))
        with open(run_manifest_path, "rb") as f:
            import hashlib as _hl
            mhash = _hl.sha256(f.read()).hexdigest()
        if m.get("pair_id") != pair_id:
            raise ValueError("manifest pair mismatch "
                             f"({m.get('pair_id')!r} != {pair_id!r})")
        arm = m.get("arm")
        if arm not in runs.get("expected_arms", []):
            raise ValueError(f"arm {arm!r} not in authorized pair arms "
                             f"{runs.get('expected_arms')}")
        if m.get("frozen_settings_hash") != runs.get("settings_hash"):
            raise ValueError("manifest frozen-settings mismatch")
        if m.get("authorization_hash") != runs.get("authorization_hash"):
            raise ValueError("manifest authorization mismatch")
        if m.get("replacement_epoch") != runs.get("replacement_epoch"):
            raise ValueError("manifest epoch mismatch")
        if m.get("task_snapshot_hash") != runs.get("task_snapshot_hash"):
            raise ValueError("manifest task snapshot mismatch")
        done = runs.setdefault("replacement_runs", {})
        if arm in done:
            raise ValueError(f"arm {arm} already recorded for replacement")
        done[arm] = {"run_id": m.get("run_id"),
                     "manifest_hash": mhash}
        if set(done) >= set(runs["expected_arms"]):
            runs["status"] = "replacement-complete"
        self._save()
        return runs["status"]

    def replacement_complete(self, pair_id):
        """Gate for grading: True only with both replacement arms linked."""
        runs = self.state["pairs"].get(pair_id, {})
        return runs.get("status") == "replacement-complete"
