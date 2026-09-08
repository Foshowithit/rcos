#!/usr/bin/env python3
"""Slice-3 forced-wrong CORRECTION runner (preregistered null test).

Executes the EXACT extract-incident-v1 engine on each h02-h10 shipment
fixture and grades the result with the frozen shipment checker.

Adapter rule (best-effort hostile adaptation, declared): the incident
engine consumes parsed event records, which shipment fixtures are not.
Each non-empty source line becomes one INFO event; service is derived
from the task id; timestamps are synthetic deterministic sequence stamps
(they carry no information — the point is to execute the engine, not to
pretend shipment lines are telemetry). No truth.json reads anywhere in
this script. Stdlib only.

Usage (from slices/v3-crossmodel/):
  PYTHONDONTWRITEBYTECODE=1 python3 runs/forced-incident/run_forced_incident.py

Writes per task: records-<id>.json, arm-<id>-forced-incident.json,
and appends one evidence record per task to evidence.jsonl.
Never touches arm-<id>-forced.json (superseded invoice runs), correct,
or disabled outputs.
"""
import glob
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ENGINE = os.path.join(
    ROOT, "..", "v2-replication", "capabilities",
    "extract-incident-v1", "engine.py")
ENGINE = os.path.normpath(ENGINE)
CHECKER = os.path.join(ROOT, "tasks/check.py")
FIELDMAP = os.path.join(HERE, "field_map.json")
TASKS = ["h02", "h03", "h04", "h05", "h06", "h07", "h08", "h09", "h10"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def adapt(task_id, src):
    """Source lines -> event records. Declared hostile adaptation."""
    with open(src, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f]
    events = [{"ts": f"2026-09-08T00:00:{i:02d}Z", "level": "INFO",
               "msg": ln}
              for i, ln in enumerate(l for l in lines if l.strip())]
    return {"service": f"shipment-{task_id}", "events": events}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()[:500]


def main():
    engine_sha = sha(ENGINE)
    checker_sha = sha(CHECKER)
    fieldmap_sha = sha(FIELDMAP)
    evidence_path = os.path.join(HERE, "evidence.jsonl")
    summary = []
    for task in TASKS:
        src = glob.glob(os.path.join(ROOT, "tasks", task, "input.*"))[0]
        rec_path = os.path.join(HERE, f"records-{task}.json")
        out_path = os.path.join(HERE, f"arm-{task}-forced-incident.json")
        with open(rec_path, "w") as f:
            json.dump(adapt(task, src), f, indent=1)
        eng_argv = [sys.executable, ENGINE, FIELDMAP, rec_path, out_path]
        eng_rc, eng_out = run(eng_argv)
        chk_argv = [sys.executable, CHECKER, task, out_path]
        chk_rc, chk_out = run(chk_argv)
        rec = {
            "task_id": task,
            "arm": "forced-wrong-corrected",
            "capability_id": "extract-incident-v1",
            "version": 1,
            "engine_argv": eng_argv,
            "engine_returncode": eng_rc,
            "engine_output": eng_out,
            "checker_argv": chk_argv,
            "checker_returncode": chk_rc,
            "checker_output": chk_out,
            "engine_sha256": engine_sha,
            "fieldmap_sha256": fieldmap_sha,
            "checker_sha256": checker_sha,
            "input_sha256": sha(os.path.join(HERE, f"records-{task}.json")),
            "output_sha256": (sha(out_path)
                              if os.path.exists(out_path) else None),
            "verdict": ("fix" if chk_rc == 1
                        else "ship" if chk_rc == 0 else "blocked"),
        }
        with open(evidence_path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        summary.append((task, rec["verdict"], eng_rc, chk_rc))
    for task, verdict, eng_rc, chk_rc in summary:
        print(f"{task}: {verdict} (engine rc={eng_rc}, checker rc={chk_rc})")
    bad = [s for s in summary if s[1] not in ("fix",)]
    if bad:
        print("UNEXPECTED (wanted all fix):", bad)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
