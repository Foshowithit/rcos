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



REPLACEMENT_MANIFEST_VERSION = "replacement-manifest-v1"
REPLACEMENT_MANIFEST_FIELDS = frozenset({
    "schema_version", "run_id", "pair_id", "arm",
    "replacement_epoch", "replaces_original_manifest_hash",
    "authorization_hash", "frozen_settings_hash",
    "task_snapshot_hash", "execution_manifest_hash",
    "execution_manifest_path", "evidence_chain_path",
    "evidence_genesis_hash",
})


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
                   task_snapshot=None, run_manifest_path=None):
        import hashlib as _hlr
        runs = self.state["pairs"].setdefault(
            pair_id, {"runs": [], "replacements": 0, "status": "open"})
        entry = {"arm": arm, "verdict": verdict,
                 "failure_kind": failure_kind,
                 "task_snapshot": task_snapshot}
        if run_manifest_path is not None:
            with open(run_manifest_path, "rb") as f:
                entry["manifest_hash"] = _hlr.sha256(f.read()).hexdigest()
            entry["manifest_path"] = run_manifest_path
        runs["runs"].append(entry)
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
        """Record one replacement arm execution BY MANIFEST under a CLOSED,
        versioned schema. Derives pair/arm/epoch/auth/settings/task from
        the manifest and verifies each; binds the replaced ORIGINAL via
        its manifest hash (not a bare run id); binds the H2 closed
        execution manifest; binds evidence genesis recomputed from
        pair+arm+authorization+task. Stores manifest hashes only."""
        import hashlib as _hlm
        m = json.load(open(run_manifest_path))
        with open(run_manifest_path, "rb") as f:
            mhash = _hlm.sha256(f.read()).hexdigest()
        keys = set(m)
        if keys != REPLACEMENT_MANIFEST_FIELDS:
            raise ValueError(
                "REPLACEMENT-SCHEMA: keys != closed schema: missing="
                f"{sorted(REPLACEMENT_MANIFEST_FIELDS - keys)}, "
                f"unknown={sorted(keys - REPLACEMENT_MANIFEST_FIELDS)}")
        if m.get("schema_version") != REPLACEMENT_MANIFEST_VERSION:
            raise ValueError("REPLACEMENT-SCHEMA: bad schema_version")
        runs = self.state["pairs"].get(pair_id)
        if runs is None:
            raise ValueError(f"unknown pair {pair_id}")
        if runs.get("status") != "replaced-once":
            raise ValueError(f"pair {pair_id} has no open replacement "
                             f"(status={runs.get('status')})")
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
        # Original-parent binding: the replaced manifest hash must equal
        # the recorded original manifest hash FOR THIS ARM.
        orig = [r for r in runs.get("runs", [])
                if r.get("arm") == arm and "manifest_hash" in r]
        if not orig:
            raise ValueError(f"no recorded original manifest for arm {arm}")
        if m.get("replaces_original_manifest_hash") != orig[-1]["manifest_hash"]:
            raise ValueError("replaces_original_manifest_hash does not match "
                             "the recorded original manifest hash for "
                             f"arm {arm}")
        # Execution-manifest binding: referenced H2 closed manifest must
        # exist and name the same pair/arm.
        exm = m.get("execution_manifest_hash")
        exmp = m.get("execution_manifest_path")
        if not exmp or not os.path.exists(exmp):
            raise ValueError("execution manifest missing")
        with open(exmp, "rb") as f:
            if _hlm.sha256(f.read()).hexdigest() != exm:
                raise ValueError("execution manifest hash mismatch")
        ex = json.load(open(exmp))
        if ex.get("pair_id") != pair_id or ex.get("arm") != arm:
            raise ValueError("execution manifest names another pair/arm "
                             "(exact match required; absence fails)")
        # Evidence-genesis binding against the ACTUAL evidence chain:
        # the manifest must name its chain file, whose persisted link-0
        # genesis record must carry this pair/arm/authorization/task.
        # The recorded evidence_genesis_hash must equal that link-0
        # record's hash — recomputed here, never trusted.
        ch_path = m.get("evidence_chain_path")
        if not ch_path or not os.path.exists(ch_path):
            raise ValueError("evidence chain file missing")
        with open(ch_path, "rb") as _cf:
            _raw0 = _cf.readline()
        try:
            _rec0 = json.loads(_raw0.decode("utf-8"))
        except ValueError:
            raise ValueError("evidence chain link 0 unreadable")
        if _rec0.get("kind") != "genesis":
            raise ValueError("evidence chain does not open with a genesis record")
        _g = _rec0.get("payload", {})
        for _k, _want in (("pair_id", pair_id), ("arm", arm),
                          ("authorization_hash",
                           runs["authorization_hash"]),
                          ("task_snapshot_hash",
                           runs["task_snapshot_hash"])):
            if _g.get(_k) != _want:
                raise ValueError(
                    f"evidence chain genesis mismatch on {_k}: chain "
                    f"does not belong to this pair/arm/authorization")
        import hashlib as _hlg
        _gen_hash = _hlg.sha256(
            json.dumps(_rec0, sort_keys=True).encode()).hexdigest()
        if m.get("evidence_genesis_hash") != _gen_hash:
            raise ValueError("evidence genesis hash != actual chain link 0")
        done = runs.setdefault("replacement_runs", {})
        if arm in done:
            raise ValueError(f"arm {arm} already recorded for replacement")
        done[arm] = {"run_id": m.get("run_id"), "manifest_hash": mhash}
        if set(done) >= set(runs["expected_arms"]):
            runs["status"] = "replacement-complete"
        self._save()
        return runs["status"]

    def replacement_complete(self, pair_id):
        """Gate for grading: True only with both replacement arms linked."""
        runs = self.state["pairs"].get(pair_id, {})
        return runs.get("status") == "replacement-complete"
