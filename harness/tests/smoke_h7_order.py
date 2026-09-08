#!/usr/bin/env python3
"""H7 adversarial smoke — item 7 (frozen order expansion + pre-call cell
authorization). Every unauthorized invocation must FAIL CLOSED; exit 0
only if all green. Stdlib only, no network, no model, no docker."""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAMC = "/home/chow/chow-work/rcos/benchmarks/fam-c"
RUNNER = os.path.join(FAMC, "harness-run", "run_arm_h1.py")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import order as ORD
import run_arm_h1 as RA

BASE = "/tmp/h7-smoke"
results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


os.system("rm -rf " + BASE)
os.makedirs(BASE)

ORDER_TEXT = open(os.path.join(FAMC, "ORDER.md")).read()
EXP = ORD.expand(ORDER_TEXT)

# --- mechanical expansion of the frozen ORDER.md ---
check("expansion parses the frozen order", EXP["total_cells"] == 144,
      str(EXP["total_cells"]))
check("family order == frozen seed order",
      EXP["families"] == ["fam05", "fam03", "fam01", "fam04", "fam06", "fam02"],
      str(EXP["families"]))
check("block order PQ then QP", EXP["blocks"] == ["PQ", "QP"])
check("downstream universe is T2,T3,T4",
      EXP["downstream_tasks"] == ["T2", "T3", "T4"])
check("cell 0 is fam05/T2/A on lane P (correct)",
      [EXP["cells"][0][k] for k in ("family", "task", "letter", "lane",
                                    "arm")]
      == ["fam05", "T2", "A", "P", "correct"])
check("fam05 letter order A,B,C,D",
      [c["letter"] for c in EXP["cells"]
       if c["block"] == "PQ" and c["family"] == "fam05"
       and c["task"] == "T2"] == ["A", "B", "C", "D"])
check("fam03 letter order flipped B,A,D,C",
      [c["letter"] for c in EXP["cells"]
       if c["block"] == "PQ" and c["family"] == "fam03"
       and c["task"] == "T2"] == ["B", "A", "D", "C"])
check("QP block primed (lane roles swapped)",
      all(c["primed"] for c in EXP["cells"] if c["block"] == "QP")
      and all(not c["primed"] for c in EXP["cells"] if c["block"] == "PQ"))
check("QP first cell is lane Q (primed consumer)",
      [c for c in EXP["cells"] if c["block"] == "QP"][0]["lane"] == "Q")
check("cell ids unique", len({c["cell_id"] for c in EXP["cells"]}) == 144)
check("committed ORDER-EXPANSION.json matches ORDER.md",
      ORD.verify_expansion(FAMC) == [], str(ORD.verify_expansion(FAMC)))

# --- derivation drift fails closed ---
tmp = os.path.join(BASE, "famc-drift")
os.makedirs(tmp)
shutil.copy2(os.path.join(FAMC, "ORDER.md"), os.path.join(tmp, "ORDER.md"))
bad = json.load(open(os.path.join(FAMC, "ORDER-EXPANSION.json")))
bad["cells"][5]["family"] = "fam99"          # hand-edited cell
json.dump(bad, open(os.path.join(tmp, "ORDER-EXPANSION.json"), "w"))
check("hand-edited expansion fails derivation",
      ORD.verify_expansion(tmp) != [])
bad2 = json.load(open(os.path.join(FAMC, "ORDER-EXPANSION.json")))
bad2["order_sha256"] = "0" * 64
json.dump(bad2, open(os.path.join(tmp, "ORDER-EXPANSION.json"), "w"))
check("stale order_sha256 fails derivation",
      any("order_sha256" in f for f in ORD.verify_expansion(tmp)))
open(os.path.join(tmp, "ORDER.md"), "w").write(
    ORDER_TEXT.replace("fam05, fam03", "fam03, fam05"))
check("reordered ORDER.md makes the committed expansion stale",
      ORD.verify_expansion(tmp) != [])

# --- authorization: the sequence is the authority ---
def auth(block, family, task, lane, arm, done=None):
    return ORD.authorize(EXP, block, family, task, lane, arm, done or {})


cell, f = auth("PQ", "fam05", "T2", "P", "correct")
check("first cell authorized with nothing done", not f and cell["index"] == 0,
      str(f))
check("fam01 before fam05 refused as out of order",
      any("out of order" in x and "fam05" in x
          for x in auth("PQ", "fam01", "T2", "P", "correct")[1]))
check("QP before PQ completes refused as out of order",
      any("out of order" in x
          for x in auth("QP", "fam05", "T2", "Q", "correct")[1]))
done = {c["cell_id"]: "run-" + c["cell_id"] for c in EXP["cells"]
        if c["block"] == "PQ"}
cell2, f2 = auth("QP", "fam05", "T2", "Q", "correct", done)
check("QP first cell authorized once PQ is complete", not f2, str(f2))
check("duplicate completed cell refused",
      any("duplicate cell" in x for x in auth(
          "PQ", "fam05", "T2", "P", "correct",
          {EXP["cells"][0]["cell_id"]: "r0"})[1]))
check("wrong family universe refused",
      any("outside the frozen universe" in x
          for x in auth("PQ", "fam99", "T2", "P", "correct")[1]))
check("wrong task universe refused",
      any("outside the frozen downstream universe" in x
          for x in auth("PQ", "fam05", "T9", "P", "correct")[1]))
check("unknown block refused",
      any("unknown block" in x
          for x in auth("QQ", "fam05", "T2", "P", "correct")[1]))
check("unknown lane refused",
      any("no authorized cell" in x
          for x in auth("PQ", "fam05", "T2", "X", "correct")[1]))
check("unknown arm refused",
      any("unknown arm" in x
          for x in auth("PQ", "fam05", "T2", "P", "sideways")[1]))
# a partial PQ block: only the earliest missing cell is named, and the
# second cell of a family cannot jump the queue
done2 = {EXP["cells"][0]["cell_id"]: "r0"}
c3, f3 = auth("PQ", "fam05", "T2", "P", "disabled", done2)
check("second cell of the pair runs once the first is complete",
      not f3, str(f3))
c4, f4 = auth("PQ", "fam05", "T3", "P", "correct", done2)
check("later task refused while an earlier cell is missing",
      any("out of order" in x and "fam05/T2/B" in x for x in f4), str(f4))

# --- completed-cell ledger: only wired, non-dev manifests count ---
runs = os.path.join(BASE, "runs")
for name, wired, dev, cid in (
        ("wired-ok", True, False, "aaaa111122223333"),
        ("dev-escape", False, None, "bbbb111122223333"),
        ("dev-flag", True, True, "cccc111122223333"),
        ("no-cell", True, False, None)):
    d = os.path.join(runs, name)
    os.makedirs(d)
    json.dump({"wired": wired, "dev_mode": dev, "cell_id": cid},
              open(os.path.join(d, "H1-RUN-MANIFEST.json"), "w"))
done_ids = ORD.completed_cells(runs)
check("ledger counts only wired non-dev cells with a cell_id",
      done_ids == {"aaaa111122223333": "wired-ok"}, str(done_ids))

# --- foreign registry refused ---
foreign = os.path.join(BASE, "foreign-cap")
os.makedirs(foreign)
try:
    RA._verify_capability(foreign)
    check("foreign registry refused", False, "no refusal")
except PermissionError as e:
    check("foreign registry refused", "FOREIGN-REGISTRY-DENY" in str(e),
          str(e))

# --- the runner itself refuses before any model call ---
def run_runner(args):
    return subprocess.run([sys.executable, RUNNER] + args,
                          capture_output=True, text=True, timeout=180)


r = run_runner(["P", "fam05", "T2", "correct", "/tmp/h7-out"])
check("runner without --block refuses (ORDER-DENY)",
      r.returncode != 0 and "ORDER-DENY" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["Q", "fam05", "T2", "correct", "/tmp/h7-out", "--block", "QP"])
check("runner QP-before-PQ refuses before any call",
      r.returncode != 0 and "out of order" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["P", "fam01", "T2", "correct", "/tmp/h7-out",
                "--block", "PQ"])
check("runner fam01-before-fam05 refuses before any call",
      r.returncode != 0 and "out of order" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])
r = run_runner(["P", "fam99", "T2", "correct", "/tmp/h7-out",
                "--block", "PQ"])
check("runner foreign family refuses before any call",
      r.returncode != 0 and "frozen universe" in (r.stderr + r.stdout),
      (r.stderr + r.stdout)[-200:])

# --- the execution lock must be current for the executed bytes ---
r = subprocess.run([sys.executable, "/home/chow/chow-work/rcos/harness/"
                    "mint_execution_lock.py", "--check"],
                   capture_output=True, text=True)
check("EXECUTION-LOCK is current (mint --check exit 0)",
      r.returncode == 0 and "current" in r.stdout,
      (r.stdout + r.stderr)[-200:])

bad = [n for n, ok_ in results if not ok_]
print(f"\nH7 smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)
