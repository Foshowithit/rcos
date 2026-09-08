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

    def record_run(self, pair_id, arm, verdict, failure_kind=None):
        runs = self.state["pairs"].setdefault(
            pair_id, {"runs": [], "replacements": 0, "status": "open"})
        runs["runs"].append({"arm": arm, "verdict": verdict,
                             "failure_kind": failure_kind})
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
        runs["replacements"] += 1
        runs["settings_id"] = frozen_settings_id
        runs["expected_arms"] = sorted(
            {r["arm"] for r in runs["runs"]})
        runs["status"] = "replaced-once"
        self._save()
        return True, "one whole-pair replacement allowed"

    def pair_status(self, pair_id):
        return self.state["pairs"].get(pair_id, {}).get("status", "unknown")

    def complete_replacement(self, pair_id, arm, run_id, settings_id):
        """Record one replacement arm execution. The pair becomes
        `replacement-complete` ONLY when BOTH arms have recorded runs
        under the SAME frozen settings as the authorization. Grading
        may consume replacement results only in that state."""
        runs = self.state["pairs"].get(pair_id)
        if runs is None:
            raise ValueError(f"unknown pair {pair_id}")
        if runs.get("status") != "replaced-once":
            raise ValueError(f"pair {pair_id} has no open replacement "
                             f"(status={runs.get('status')})")
        if settings_id != runs.get("settings_id"):
            raise ValueError("replacement settings differ from authorized")
        if arm not in runs.get("expected_arms", []):
            raise ValueError(f"arm {arm} not in authorized pair arms "
                             f"{runs.get('expected_arms')}")
        done = runs.setdefault("replacement_runs", {})
        if arm in done:
            raise ValueError(f"arm {arm} already recorded for replacement")
        done[arm] = run_id
        if set(done) >= set(runs["expected_arms"]):
            runs["status"] = "replacement-complete"
        self._save()
        return runs["status"]

    def replacement_complete(self, pair_id):
        """Gate for grading: True only with both replacement arms linked."""
        runs = self.state["pairs"].get(pair_id, {})
        return runs.get("status") == "replacement-complete"
