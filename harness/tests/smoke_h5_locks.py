#!/usr/bin/env python3
"""H5 adversarial smoke — item 4 three-authority preflight. Modifying any
governed file must fail EXACTLY its lock (no double-jeopardy, no silence).
Exit 0 only if all green. Stdlib only. Hermetic fixtures live in throwaway
git repos under /tmp (no live-tree mutation); plus a live end-to-end run
proving the real tree is triple-green."""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "..", "benchmarks", "fam-c"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import preflight as PF

BASE = "/tmp/h5-smoke"
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")


def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       env=_ENV, text=True)
    assert r.returncode == 0, (args, r.stderr[:200])
    return r.stdout.strip()


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


os.system("rm -rf " + BASE)
os.makedirs(BASE)

# --- hermetic V1: instance authority over a fake frozen root ---
v1 = os.path.join(BASE, "v1repo")
os.makedirs(os.path.join(v1, "D", "families", "fam99", "T0"))
prompt = os.path.join(v1, "D", "families", "fam99", "T0", "prompt.md")
open(prompt, "w").write("frozen\n")
man = f"{sha('frozen\n')}  families/fam99/T0/prompt.md\n"
open(os.path.join(v1, "D", "FREEZE-HASHES.sha256"), "w").write(man)
git(v1, "init", "-q")
git(v1, "add", "-A")
git(v1, "commit", "-qm", "freeze")
FC1 = git(v1, "rev-parse", "HEAD")
D = os.path.join(v1, "D")
check("V1 clean green", PF.validate_instance(D, FC1) == [])
open(prompt, "w").write("TAMPERED\n")
check("V1 instance drift fails V1",
      any("V1" in f and "mismatch" in f
          for f in PF.validate_instance(D, FC1)))
open(prompt, "w").write("frozen\n")
open(os.path.join(v1, "D", "families", "fam99", "T0", "extra.txt"), "w").write("x")
f_extra = PF.validate_instance(D, FC1)
check("V1 extra file fails V1",
      any("V1" in f and "extra file" in f for f in f_extra))
os.remove(os.path.join(v1, "D", "families", "fam99", "T0", "extra.txt"))
# separation: protocol-governed drift is NOT V1's business (V2 owns it).
open(os.path.join(v1, "D", "LANES.md"), "w").write("drifted protocol\n")
check("V1 ignores protocol-governed paths (V2 owns them)",
      PF.validate_instance(D, FC1) == [])
os.remove(os.path.join(v1, "D", "LANES.md"))
check("V1 rewritten history refused",
      len(PF.validate_instance(D, "0" * 40)) > 0)

# --- hermetic V2: protocol authority over fake fam-c ---
v2 = os.path.join(BASE, "v2repo", "benchmarks", "fam-c")
os.makedirs(v2)
open(os.path.join(v2, "ORDER.md"), "w").write("frozen order\n")
git(os.path.join(BASE, "v2repo"), "init", "-q")
git(os.path.join(BASE, "v2repo"), "add", "-A")
git(os.path.join(BASE, "v2repo"), "commit", "-qm", "freeze")
FC2 = git(os.path.join(BASE, "v2repo"), "rev-parse", "HEAD")
FROZEN_ORDER = sha("frozen order\n")
lock = {"freeze_commit": FC2,
        "governed": {"PREREG.md": "00" * 32, "ORDER.md": FROZEN_ORDER,
                     "LANES.md": "00" * 32, "HARNESS-READINESS.md": "00" * 32,
                     "preflight.py": "00" * 32},
        "amendments": []}
open(os.path.join(v2, "PROTOCOL-LOCK.json"), "w").write(json.dumps(lock))
# only ORDER.md exists on disk among governed; others correctly flagged
# missing — so scope this probe to the missing-file behavior + ORDER drift.
open(os.path.join(v2, "ORDER.md"), "w").write("drifted order\n")
f_v2 = PF.validate_protocol(v2, FC2)
check("V2 unlisted drift fails V2",
      any("V2" in f and "ORDER.md" in f and "no listed" in f for f in f_v2),
      str(f_v2))
open(os.path.join(v2, "ORDER.md"), "w").write("amended order\n")
lock["amendments"] = [{"file": "ORDER.md", "from_sha": FROZEN_ORDER,
                       "to_sha": sha("amended order\n"),
                       "reason": "test amendment", "base": FC2[:7],
                       "slice": "test"}]
open(os.path.join(v2, "PROTOCOL-LOCK.json"), "w").write(json.dumps(lock))
# precise predicate: ORDER-EXPANSION findings also mention ORDER.md by name
f_v2b = [f for f in PF.validate_protocol(v2, FC2)
         if f.startswith("V2 PROTOCOL-LOCK: ORDER.md ")]
check("V2 listed amendment passes", f_v2b == [], str(f_v2b))
# item-7 positive control: a fam-c dir with no derived expansion is a V2 finding
f_exp = PF.validate_protocol(v2, FC2)
check("V2 flags a missing ORDER-EXPANSION.json",
      any("ORDER-EXPANSION.json missing" in f for f in f_exp), str(f_exp))
lock["amendments"][0]["from_sha"] = "ff" * 32
open(os.path.join(v2, "PROTOCOL-LOCK.json"), "w").write(json.dumps(lock))
check("V2 amendment not chained to frozen bytes fails",
      any("ORDER.md" in f for f in PF.validate_protocol(v2, FC2)))
lock["amendments"][0]["from_sha"] = FROZEN_ORDER
lock["freeze_commit"] = "00" * 40
open(os.path.join(v2, "PROTOCOL-LOCK.json"), "w").write(json.dumps(lock))
check("V2 lock on wrong freeze fails",
      any("locks disagree" in f for f in PF.validate_protocol(v2, FC2)))

# --- hermetic V3: execution authority over fake harness ---
v3 = os.path.join(BASE, "v3repo")
os.makedirs(os.path.join(v3, "harness"))
open(os.path.join(v3, "harness", "x.py"), "w").write("v1\n")
git(v3, "init", "-q")
git(v3, "add", "-A")
git(v3, "commit", "-qm", "harness")
elock = {"status": "open-test",
         "harness_manifest_sha256": "00" * 32,
         "harness_files": {"harness/x.py": sha("v1\n")},
         "amendments": []}
open(os.path.join(v3, "EXECUTION-LOCK.json"), "w").write(json.dumps(elock))
check("V3 clean green", PF.validate_execution(v3) == [])
open(os.path.join(v3, "harness", "x.py"), "w").write("v2-tampered\n")
check("V3 harness drift fails V3",
      any("V3" in f and "changed" in f for f in PF.validate_execution(v3)))
open(os.path.join(v3, "harness", "x.py"), "w").write("v1\n")
os.remove(os.path.join(v3, "harness", "x.py"))
check("V3 missing module fails V3 (never skips)",
      any("V3" in f and "missing" in f for f in PF.validate_execution(v3)))

# --- live end-to-end: the real tree is triple-green ---
FAMC = os.path.normpath(os.path.join(ROOT, "..", "benchmarks", "fam-c"))
r = subprocess.run([sys.executable, os.path.join(FAMC, "preflight.py")],
                   capture_output=True, text=True)
check("live preflight triple-green exit 0",
      r.returncode == 0 and "0 finding(s), V2-protocol 0 finding(s)" in r.stdout,
      (r.stdout + r.stderr)[-300:])
live = PF.validate_all(FAMC)
check("live validate_all findings empty", live == [], str(live)[:300])

bad = [n for n, ok_ in results if not ok_]
print(f"\nH5 smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)
