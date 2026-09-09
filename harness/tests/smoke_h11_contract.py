#!/usr/bin/env python3
"""H11 contract smoke — A11b.2: ONE output schema, ONE parser, ONE runtime
path. Exercises run_arm_h1.execute_arrival() directly with a REAL
DockerSandbox jail and the REAL frozen fam05 checker; model responses are
synthetic (no network, no model). Every negative must FAIL CLOSED; every
happy path must SHIP through the frozen checker. Exit 0 only if all green.
Stdlib only."""
import inspect
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, "/home/chow/chow-work/rcos/benchmarks/fam-c/harness-run")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import run_arm_h1 as RA
from dockersandbox import DockerSandbox
from seal import build_visible_root

FAM = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam05"
TASK = os.path.join(FAM, "T0")
TAG = "h11-smoke"
WORKROOT = os.path.join("/tmp/rcos-runs", TAG)
VISDIR = os.path.join("/tmp/rcos-visible", TAG, "T0")
CAP = os.path.join(WORKROOT, "cap")
results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


# Synthetic capability engine (real locked engines are capability-registry
# files; here a frozen fixture file stands in, exactly as the harness would
# copy one). argv: engine.py <field_map.json> <records.json> <OUTPUT.json>.
# A12d D1-A3: the engine jail's /task carries ONLY the adapted payload, so
# the engine renders its inputs from argv ALONE — it never reads the raw
# task tree (no MANIFEST rides /task anymore).
ENGINE_SRC = '''\
import hashlib, json, os, sys
fm_path, rec_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
fmap = json.load(open(fm_path))
records = json.load(open(rec_path))
indir = os.path.join(os.path.dirname(os.path.abspath(out_path)), "_h11_in")
os.makedirs(indir, exist_ok=True)
for rel, spec in sorted((fmap.get("files") or {}).items()):
    p = os.path.join(indir, rel)
    os.makedirs(os.path.dirname(p) or indir, exist_ok=True)
    text = spec.get("literal", "") if isinstance(spec, dict) else spec
    with open(p, "w") as f:
        f.write(text if isinstance(text, str) else "")
d = indir
want = {}
for line in open(os.path.join(d, "MANIFEST")).read().splitlines():
    p, size, sha = line.split(":")
    want[p] = (int(size), sha)
ok, bad = [], []
for p, (size, sha) in sorted(want.items()):
    data = open(os.path.join(d, p), "rb").read()
    if len(data) == size and hashlib.sha256(data).hexdigest() == sha:
        ok.append(p)
    else:
        bad.append({"path": p, "reason": "size or sha256 mismatch"})
report = {"ok": sorted(ok), "bad": bad, "unverified": []}
with open(out_path, "w") as f:
    json.dump(report, f)
'''

# Synthetic fresh solver. argv: solver.py <taskdir> <OUTPUT.json>.
SOLVER_SRC = '''\
import hashlib, json, os, sys
d, out_path = sys.argv[1], sys.argv[2]
want = {}
for line in open(os.path.join(d, "MANIFEST")).read().splitlines():
    p, size, sha = line.split(":")
    want[p] = (int(size), sha)
ok, bad = [], []
for p, (size, sha) in sorted(want.items()):
    data = open(os.path.join(d, p), "rb").read()
    if len(data) == size and hashlib.sha256(data).hexdigest() == sha:
        ok.append(p)
    else:
        bad.append({"path": p, "reason": "size or sha256 mismatch"})
report = {"ok": sorted(ok), "bad": bad, "unverified": []}
with open(out_path, "w") as f:
    json.dump(report, f)
'''

os.system("rm -rf " + WORKROOT + " " + os.path.dirname(VISDIR))
os.makedirs(WORKROOT)
os.makedirs(CAP)
os.makedirs(os.path.dirname(VISDIR), exist_ok=True)
eng_path = os.path.join(CAP, "engine.py")
with open(eng_path, "w") as f:
    f.write(ENGINE_SRC)
copied, refused = build_visible_root(TASK, VISDIR)
check("frozen fam05/T0 visible root staged (prompt+fixtures only)",
      set(copied) == {"prompt.md", "MANIFEST", "alpha.txt", "beta.txt"},
      str(copied))
check("non-visible file (VISIBLE.md) refused by seal",
      refused == ["VISIBLE.md"], str(refused))


def run_arrival(arm, arrival, tag):
    work = os.path.join(WORKROOT, tag, "work")
    outdir = os.path.join(WORKROOT, tag, "out")
    os.makedirs(work, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    sb = DockerSandbox(work, VISDIR)
    return RA.execute_arrival(arm, arrival, work, outdir, TASK, eng_path, sb)


def _t0_field_map():
    """The adapted capability input for the synthetic USE arrival: the
    frozen fam05/T0 file bytes carried as argv literals (A12d D1-A3 —
    the engine jail never sees the raw task tree, so the arrival must
    carry the bytes the engine needs). Read-only live-tree reads."""
    files = {}
    for name in ("MANIFEST", "alpha.txt", "beta.txt"):
        with open(os.path.join(TASK, name)) as f:
            files[name] = {"literal": f.read()}
    return {"files": files}


USE_ARRIVAL = {"decision": "use_capability",
               "execution_payload": {"field_map": _t0_field_map(),
                                     "records": {}},
               "notes": "use the locked capability"}
FRESH_ARRIVAL = {"decision": "fresh",
                 "execution_payload": {"solver_py": SOLVER_SRC},
                 "notes": "synthetic fresh solver"}

# --- happy paths: ONE runtime path driven by the arrival's own decision ---
arr, mode = RA.extract(json.dumps(USE_ARRIVAL))
check("use_capability arrival parses as json-envelope",
      arr == USE_ARRIVAL and mode == "json-envelope", mode)
r = run_arrival("correct", arr, "use")
check("treatment USE: engine executes, frozen checker ships",
      r["verdict"] == "ship" and r["checker_returncode"] == 0 and
      r["execution_mode"] == "engine" and r["decision"] == "use_capability" and
      isinstance(r["output_sha256"], str) and len(r["output_sha256"]) == 64,
      json.dumps(r)[:200])

arr, mode = RA.extract(json.dumps(FRESH_ARRIVAL))
check("fresh arrival parses as json-envelope",
      arr == FRESH_ARRIVAL and mode == "json-envelope", mode)
r = run_arrival("correct", arr, "reject-fresh")
check("treatment REJECT -> fresh: solver executes, checker ships",
      r["verdict"] == "ship" and r["checker_returncode"] == 0 and
      r["execution_mode"] == "solver" and r["decision"] == "fresh",
      json.dumps(r)[:200])

r = run_arrival("disabled", FRESH_ARRIVAL, "ctrl-fresh")
check("control fresh: solver executes, checker ships",
      r["verdict"] == "ship" and r["checker_returncode"] == 0 and
      r["execution_mode"] == "solver" and r["decision"] == "fresh",
      json.dumps(r)[:200])

# fence-fallback still parses to the SAME object shape for both decisions
fenced = "```json\n" + json.dumps(FRESH_ARRIVAL) + "\n```"
arr, mode = RA.extract(fenced)
check("fenced arrival: same shape, fence-fallback mode",
      arr == FRESH_ARRIVAL and mode == "fence-fallback", mode)

# --- fail-closed negatives ----------------------------------------------
def raises(desc, fn, tag, kind=(ValueError, RuntimeError)):
    try:
        fn()
        check(desc, False, "no exception raised")
    except kind as e:
        ok_ = tag in str(e)
        check(desc, ok_, str(e)[:120])
    except Exception as e:  # wrong exception family is a FAIL-OPEN
        check(desc, False, "wrong exception type: " + repr(e))


raises("missing decision key fails closed (PARSE-DENY)",
       lambda: RA.extract(
           '{"execution_payload": {"solver_py": "x"}, "notes": "n"}'),
       "CONTRACT-PARSE-DENY")
raises("unknown decision string fails closed (DECISION-DENY)",
       lambda: RA.extract(
           '{"decision": "escalate", "execution_payload": {}, "notes": "n"}'),
       "CONTRACT-DECISION-DENY")
raises("use_capability payload missing field_map fails closed",
       lambda: RA.extract(
           '{"decision": "use_capability", '
           '"execution_payload": {"records": {}}, "notes": "n"}'),
       "CONTRACT-PARSE-DENY")
raises("use_capability payload missing records fails closed",
       lambda: RA.extract(
           '{"decision": "use_capability", '
           '"execution_payload": {"field_map": {}}, "notes": "n"}'),
       "CONTRACT-PARSE-DENY")
raises("fresh payload missing solver_py fails closed",
       lambda: RA.extract(
           '{"decision": "fresh", "execution_payload": {}, "notes": "n"}'),
       "CONTRACT-PARSE-DENY")
raises("fresh solver_py not a python source string fails closed",
       lambda: RA.extract(
           '{"decision": "fresh", '
           '"execution_payload": {"solver_py": 7}, "notes": "n"}'),
       "CONTRACT-PARSE-DENY")
raises("execution_payload not an object fails closed",
       lambda: RA.extract(
           '{"decision": "fresh", "execution_payload": [], "notes": "n"}'),
       "CONTRACT-PARSE-DENY")

# control (disabled arm) returning use_capability must be refused AT
# EXECUTION (the parser is arm-independent and cannot know the arm).
raises("control use_capability refused at execution (DECISION-DENY)",
       lambda: RA.execute_arrival("disabled", USE_ARRIVAL,
                                  os.path.join(WORKROOT, "n1"), os.path.join(WORKROOT, "n1"),
                                  TASK, eng_path, None),
       "CONTRACT-DECISION-DENY", kind=(RuntimeError,))
# treatment use_capability without a capability engine must be refused.
raises("treatment use_capability, no cap engine refused (ENGINE-DENY)",
       lambda: RA.execute_arrival("correct", USE_ARRIVAL,
                                  os.path.join(WORKROOT, "n2"), os.path.join(WORKROOT, "n2"),
                                  TASK, None, None),
       "CONTRACT-ENGINE-DENY", kind=(RuntimeError,))
raises("treatment use_capability, missing cap engine path refused (ENGINE-DENY)",
       lambda: RA.execute_arrival("correct", USE_ARRIVAL,
                                  os.path.join(WORKROOT, "n3"), os.path.join(WORKROOT, "n3"),
                                  TASK, os.path.join(CAP, "nope.py"), None),
       "CONTRACT-ENGINE-DENY", kind=(RuntimeError,))

# --- static probe: extract() has no arm-specific parser branch ----------
src = inspect.getsource(RA.extract)
sig = str(inspect.signature(RA.extract))
check("extract() takes raw only (no arm param)", sig == "(raw)", sig)
check("extract() source has no arm branch", "if arm" not in src)
check("extract() source has no arm-key substrings",
      '{"records"' not in src and '{"solver_py"' not in src)
check("extract() source does no substring envelope search", "raw.find" not in src)
# both arms are built on the SAME byte-identical shared contract tail
check("both arms share one byte-identical _OUT contract",
      RA.CORRECT.endswith(RA._OUT) and RA.DISABLED.endswith(RA._OUT))
check("shared _OUT names decision + both payload shapes",
      '"decision"' in RA._OUT and '"use_capability"' in RA._OUT
      and '"fresh"' in RA._OUT and '"execution_payload"' in RA._OUT)

bad = [n for n, ok_ in results if not ok_]
print(f"\nH11 contract smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)
