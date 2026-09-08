#!/usr/bin/env python3
"""Slice-3 full execution: 10 held-outs x 3 arms via role-C lane.
Mechanical scheduler: frozen prompts, raw outputs saved, arrivals executed
verbatim, no semantic repairs. Infra-error retries only (max 3); eval fail
is recorded, never retried on judgment. Stdlib only.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from c_call import main as c_call, LANE  # noqa: E402 (reuses frozen prompts)

TASKS = [f"h{i:02d}" for i in range(1, 11)]
ARMS = ["correct", "forced", "disabled"]
SHIP_ENG = os.path.join(HERE, "capabilities/ship-normalize-v1/engine.py")
INV_ENG = os.path.join(HERE, "..", "v0-validated-reuse",
                       "capabilities/normalize-invoice-v1/engine.py")
CHECK = os.path.join(HERE, "tasks/check.py")


def extract_json(raw, arm):
    m = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.S)
    if m:
        return json.loads(m.group(1)), "json-fence"
    try:
        return json.loads(raw[raw.find("{"):raw.rfind("}") + 1]), "bare-json"
    except Exception:
        pass
    if arm == "disabled":
        m2 = re.search(r"```python\s*(.*?)\s*```", raw, re.S)
        if m2:
            return {"solver_py": m2.group(1),
                    "notes": "fallback: bare code fence, no envelope"}, \
                "py-fence-fallback"
    raise ValueError("arrival unparseable (no JSON envelope)")


def run_eval(task, out_path):
    p = subprocess.run([sys.executable, CHECK, task, out_path],
                       capture_output=True, text=True)
    return ("ship" if p.returncode == 0 else
            "blocked" if p.returncode == 2 else "fix",
            (p.stdout + p.stderr).strip()[:200])


def call_with_retry(task, arm, outdir, tries=3):
    last = None
    for _ in range(tries):
        try:
            c_call(task, arm, outdir)
            return True, None
        except Exception as e:  # infra only; eval fails never reach here
            last = str(e)[:120]
            time.sleep(10)
    return False, last


def execute_arm(task, arm, outdir, used_calls):
    """Run arrival verbatim. Returns (verdict, detail, wall_s)."""
    t0 = time.time()
    inp = glob.glob(os.path.join(HERE, "tasks", task, "input.*"))[0]
    try:
        o, how = extract_json(open(os.path.join(outdir, "raw.txt")).read(), arm)
        open(os.path.join(outdir, "extract_note.txt"), "w").write(how + "\n")
        if arm == "disabled":
            sol = os.path.join(outdir, "solver.py")
            open(sol, "w").write(o["solver_py"])
            out = os.path.join(outdir, "OUTPUT.json")
            r = subprocess.run([sys.executable, sol, inp, out],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not os.path.exists(out):
                return ("fix", f"solver crashed: {r.stderr.strip()[:150]}",
                        round(time.time() - t0, 1))
        else:
            eng = SHIP_ENG if arm == "correct" else INV_ENG
            rec = os.path.join(outdir, "records.json")
            fmp = os.path.join(outdir, "field_map.json")
            open(rec, "w").write(json.dumps(o["records"]))
            open(fmp, "w").write(json.dumps(o["field_map"]))
            out = os.path.join(outdir, "OUTPUT.json")
            r = subprocess.run([sys.executable, eng, fmp, rec, out],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not os.path.exists(out):
                return ("fix",
                        f"engine failed (rc={r.returncode}): "
                        f"{r.stderr.strip()[:120] or r.stdout.strip()[:120]}",
                        round(time.time() - t0, 1))
        verdict, detail = run_eval(task, out)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        verdict, detail = ("fix", f"arrival unusable: {str(e)[:150]}")
    except Exception as e:
        verdict, detail = ("blocked", f"harness-error: {str(e)[:150]}")
    return verdict, detail, round(time.time() - t0, 1)


def main():
    trace_path = os.path.join(HERE, "trace.jsonl")
    table_path = os.path.join(HERE, "RESULTS_TABLE.json")
    table = []
    if os.path.exists(table_path):
        try:
            table = json.load(open(table_path))
        except Exception:
            table = []
    table = [r for r in table
             if not (r.get("task") == "h01" and r.get("arm") != "correct")]
    only = sys.argv[1:] or None
    for i, task in enumerate(TASKS):
        if only and task not in only:
            continue
        order = ARMS[i % 3:] + ARMS[:i % 3]  # rotate starting arm
        for arm in order:
            if task == "h01" and arm == "correct":
                continue  # already shipped, row kept in trace
            outdir = os.path.join(HERE, f"runs/c-{task}-{arm}")
            ok, err = call_with_retry(task, arm, outdir)
            if not ok:
                row = {"task": task, "arm": arm, "verdict": "blocked",
                       "detail": f"c-call infra fail x3: {err}"}
            else:
                usage = json.load(open(os.path.join(outdir, "usage.json")))
                verdict, detail, wall = execute_arm(task, arm, outdir, 1)
                row = {"task": task, "arm": arm, "verdict": verdict,
                       "detail": detail, "tokens": usage.get("usage"),
                       "wall_s": wall}
            table.append(row)
            print(f"{task}/{arm}: {row['verdict']} | {row.get('detail','')[:90]}",
                  flush=True)
            open(trace_path, "a").write(json.dumps(row) + "\n")
    open(os.path.join(HERE, "RESULTS_TABLE.json"), "w").write(
        json.dumps(table, indent=1))
    print(f"DONE: {len(table)} arm-runs")


if __name__ == "__main__":
    main()
