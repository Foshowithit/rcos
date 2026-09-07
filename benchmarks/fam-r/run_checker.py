#!/usr/bin/env python3
"""Fam-R checker runner: executes each task's check.sh, writes EVAL results to runs/.

Usage:
  python3 benchmarks/fam-r/run_checker.py --tasks r01,r02
  python3 benchmarks/fam-r/run_checker.py --all

Results land under $RCOS_RUN_DIR (default ./runs) — never inside benchmarks/.
Verdicts: ship (pass) / fix (checker failed) / blocked (infra error).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "benchmarks" / "fam-r" / "tasks"
RUN_DIR = Path(os.environ.get("RCOS_RUN_DIR", ROOT / "runs"))


def all_tasks():
    with open(TASKS_DIR.parent / "tasks.json") as f:
        return [t["id"] for t in json.load(f)["tasks"]]


def run_task(task_id):
    gate = json.loads((TASKS_DIR / task_id / "EVAL.json").read_text())
    check = TASKS_DIR / task_id / "check.sh"
    start = time.time()
    if not check.exists():
        return gate, "blocked", f"missing check.sh for {task_id}"
    try:
        proc = subprocess.run(
            ["bash", str(check)],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "TASK_DIR": str(TASKS_DIR / task_id)},
        )
        elapsed = time.time() - start
        log = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            verdict = gate["verdict_map"]["pass"]
        elif proc.returncode == 1:
            verdict = gate["verdict_map"]["fail"]
        else:
            verdict = gate["verdict_map"]["error"]
        return gate, verdict, f"{log} [{elapsed:.1f}s]"
    except Exception as e:  # noqa: BLE001 — infra failure => blocked
        return gate, gate["verdict_map"]["error"], f"runner error: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", help="comma-separated ids, e.g. r01,r02")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    ids = all_tasks() if args.all else (args.tasks or "").split(",")
    ids = [i.strip() for i in ids if i.strip()]
    if not ids:
        print("usage: run_checker.py --tasks r01,r02 | --all")
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RUN_DIR / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    code = 0
    for tid in ids:
        gate, verdict, log = run_task(tid)
        result = {
            "task_id": tid,
            "family": gate.get("family", "R"),
            "verdict": verdict,
            "log": log,
            "timestamp": stamp,
        }
        (out_dir / f"{tid}.EVAL.json").write_text(json.dumps(result, indent=2) + "\n")
        print(f"{tid}: verdict: {verdict} — {log}")
        if verdict != "ship":
            code = 1
    print(f"results -> {out_dir}")
    return code


if __name__ == "__main__":
    sys.exit(main())
