#!/usr/bin/env python3
"""Fam02 fallible page fetcher (task-provided harness, NOT solver code).
Usage: fetch.py <taskdir> <counterdir> <pagefile>
Fails the first N reads of pages listed in <taskdir>/faults.json
(counter files in <counterdir> track attempts). Prints page bytes on
success (exit 0), "TRANSIENT <page> attempt <n>" on failure (exit 3).
Stdlib only. Solvers MUST call this (no direct page reads) and MUST
append every attempt to retry.log as '<page> <attempt> ok|fail'.
"""
import json
import os
import sys

taskdir, counterdir, page = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(counterdir, exist_ok=True)
faults = json.load(open(os.path.join(taskdir, "faults.json")))["failures"]
rel = os.path.relpath(page, taskdir)
cf = os.path.join(counterdir, rel.replace(os.sep, "_") + ".count")
n = int(open(cf).read()) + 1 if os.path.exists(cf) else 1
open(cf, "w").write(str(n))
if n <= faults.get(rel, 0):
    print(f"TRANSIENT {rel} attempt {n}")
    sys.exit(3)
sys.stdout.write(open(page).read())
