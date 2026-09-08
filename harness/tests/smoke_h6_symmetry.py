#!/usr/bin/env python3
"""H6 adversarial smoke — item 6 (single VISIBLE snapshot, canonical
envelope, arm symmetry). Every probe must FAIL CLOSED; exit 0 only if all
green. Stdlib only, no network, no model, no docker daemon (the sandbox is
constructed for its file staging only)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, "/home/chow/chow-work/rcos/benchmarks/fam-c/harness-run")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import run_arm_h1 as RA
from dockersandbox import DockerSandbox, _hash_tree
from seal import build_visible_root, seal_probe

BASE = "/tmp/h6-smoke"
FAM = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam05"
TASK = os.path.join(FAM, "T0")
results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


# Legacy (pre-item-6) DISABLED template: control-arm bytes must be unchanged.
LEGACY_DISABLED = """You are solving the task below from scratch. No registry/capability/prior solution exists. Output ONLY one JSON object, no other text.

TASK DEFINITION:
__TASKDEF__

TASK DIRECTORY LISTING: __LISTING__
TASK FILE CONTENTS (exact bytes):
__BLOBS__

Output object: {"solver_py": <complete Python script taking (src_dir, dst_path) and writing the ordinary task output>, "notes": "one line"}. No explanations/fences."""

os.system("rm -rf " + BASE)
os.makedirs(BASE)

# --- canonical pair ---
env = RA.build_envelope("TASKDEF-BYTES", "a.txt, b.txt", "--- a.txt ---\nAA")
cor = RA.build_arm_prompt("correct", env, "MANIFEST", "NOTES", "ENGINE")
dis = RA.build_arm_prompt("disabled", env)
check("canonical pair has zero findings",
      RA.check_arm_symmetry(cor, dis, env) == [],
      str(RA.check_arm_symmetry(cor, dis, env)))
check("disabled arm bytes == legacy pre-item-6 template",
      RA.DISABLED == LEGACY_DISABLED)
check("both arms embed the identical envelope object",
      cor.count(env) == 1 and dis.count(env) == 1)

# --- one-byte hint asymmetry in the SHARED region ---
tamper = dis.replace("a.txt, b.txt", "a.txt, b.txt ", 1)  # ONE byte
check("one-byte shared-region asymmetry fails closed",
      RA.check_arm_symmetry(cor, tamper, env) != [])
tamper2 = cor.replace("TASKDEF-BYTES", "TASKDEF-BYTEZ", 1)
check("one-byte taskdef asymmetry fails closed",
      RA.check_arm_symmetry(tamper2, dis, env) != [])
# asymmetry hidden in a fixture blob
tamper3 = dis.replace("--- a.txt ---\nAA", "--- a.txt ---\nAB", 1)
check("one-byte fixture-blob asymmetry fails closed",
      RA.check_arm_symmetry(cor, tamper3, env) != [])

# --- delimiters / stray block ---
check("stray capability block in disabled fails closed",
      RA.check_arm_symmetry(cor, dis + "\n" + RA._CAP_BEGIN + "\nX\n"
                            + RA._CAP_END, env) != [])
check("duplicated delimiter in correct fails closed",
      RA.check_arm_symmetry(cor.replace(RA._CAP_END, RA._CAP_END
                                        + RA._CAP_END, 1), dis, env) != [])
check("missing begin delimiter fails closed",
      RA.check_arm_symmetry(cor.replace(RA._CAP_BEGIN, "", 1), dis, env) != [])
check("end-before-begin fails closed",
      RA.check_arm_symmetry(cor.replace(
          RA._CAP_BEGIN + "\nCAPABILITY MANIFEST:\nMANIFEST\n", "").replace(
          RA._CAP_END, RA._CAP_BEGIN, 1), dis, env) != [])
check("capability block missing frozen section header fails closed",
      RA.check_arm_symmetry(
          RA.build_arm_prompt("correct", env, "M", "N", "E").replace(
              "ENGINE SOURCE (frozen, do not modify):", "ENGINE:"),
          dis, env) != [])
check("correct preamble drift fails closed",
      RA.check_arm_symmetry(cor.replace("PROVIDED capability", "PROVIDED CAPABILITY", 1),
                            dis, env) != [])
check("disabled tail content past envelope fails closed",
      RA.check_arm_symmetry(cor, dis + "\nPS: prefer b.txt", env) != [])
check("correct output schema drift fails closed",
      RA.check_arm_symmetry(cor.replace('"records"', '"rows"', 1), dis, env) != [])
check("capability block placed before the envelope fails closed",
      RA.check_arm_symmetry(
          RA._PRE_CORRECT
          + "\n" + RA._CAP_BEGIN + "\nCAPABILITY MANIFEST:\nM\nADAPTER "
          "NOTES:\nN\nENGINE SOURCE (frozen, do not modify):\nE\n"
          + RA._CAP_END + "\n" + env + RA._OUT_CORRECT, dis, env) != [])
# mechanical statement of the diff: shared envelope is all that is common
cor_norm = cor.replace(RA._PRE_CORRECT, "P").replace(RA._OUT_CORRECT, "O")
dis_norm = dis.replace(RA._PRE_DISABLED, "P").replace(RA._OUT_DISABLED, "O")
check("disabled == preamble + envelope + frozen output schema",
      dis_norm == "P" + env + "O", repr(dis_norm[:60]))
check("correct == preamble + envelope + delimited block + output schema",
      cor_norm.startswith("P" + env + "\n" + RA._CAP_BEGIN + "\n")
      and cor_norm.endswith(RA._CAP_END + "\nO")
      and cor_norm.count(env) == 1, repr(cor_norm[:60]))
check("counterfactual sentinel never enters the real disabled prompt",
      RA.COUNTERFACTUAL_CAP not in dis and RA.COUNTERFACTUAL_CAP in
      RA.build_arm_prompt("correct", env, RA.COUNTERFACTUAL_CAP,
                          RA.COUNTERFACTUAL_CAP, RA.COUNTERFACTUAL_CAP))

# --- single staged snapshot: context bytes == sandbox bytes ---
vis = os.path.join("/tmp/rcos-visible", "h6-smoke")
work = os.path.join("/tmp/rcos-runs", "h6-smoke")
os.makedirs(work, exist_ok=True)
copied, refused = build_visible_root(TASK, vis)
staged_tree = _hash_tree(vis)
sb = DockerSandbox(work, vis)
check("sandbox staged snapshot == staged visible source hash",
      sb.task_snapshot == staged_tree, str(sorted(staged_tree)[:3]))
check("staged tree carries no sealed basename",
      not [f for f in os.listdir(vis)
           if f in ("truth.json", "check.py", "K.md", "registry.json")])
check("visible root copies only prompt.md + declared fixtures",
      sorted(copied) == sorted(
          ["prompt.md"] + [w for line in open(os.path.join(TASK, "VISIBLE.md"))
                           if "task fixtures:" in line
                           for w in line.split("task fixtures:", 1)[1].split()]),
      str(copied))
# the prompt's embedded bytes are exactly the staged bytes
read_files = {}
for root, _d, files in os.walk(vis):
    for fn in sorted(files):
        p = os.path.join(root, fn)
        read_files["file|" + os.path.relpath(p, vis)] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
check("prompt-read file hashes == staged tree file hashes",
      read_files == {k: v for k, v in staged_tree.items()
                     if k.startswith("file|")})
ctx_hash = hashlib.sha256(json.dumps(staged_tree, sort_keys=True).encode()).hexdigest()
sb_hash = hashlib.sha256(json.dumps(sb.task_snapshot, sort_keys=True).encode()).hexdigest()
check("context_task_snapshot_hash == sandbox_task_snapshot_hash",
      ctx_hash == sb_hash)

# --- seal oracle (new jail-visibility attempt_read) ---
check("seal probe clean on a properly staged task",
      seal_probe(sb, vis, FAM, "T0") == [], str(seal_probe(sb, vis, FAM, "T0")))
ok, why = sb.attempt_read(os.path.join(vis, "alpha.txt"))
check("declared fixture readable in jail", ok, why)
ok, _ = sb.attempt_read(os.path.join(FAM, "truth.json"))
check("family-root truth.json denied in jail", not ok)
ok, _ = sb.attempt_read(os.path.join(vis, "..", "truth.json"))
check("traversal ../truth.json denied in jail", not ok)
planted = os.path.join(vis, "truth.json")
open(planted, "w").write("{}")
findings = seal_probe(sb, vis, FAM, "T0")
check("planted sealed file under staged root is a finding",
      any("truth.json" in f for f in findings), str(findings))
os.remove(planted)

# --- drift between the two reads must fail closed ---
os.remove(os.path.join(vis, "alpha.txt"))
check("post-staging mutation breaks the byte binding",
      _hash_tree(vis) != sb.task_snapshot)

# --- the runner's own offline prompt selfcheck (real fam05/T0) ---
r = subprocess.run(
    [sys.executable, "/home/chow/chow-work/rcos/benchmarks/fam-c/harness-run/"
     "run_arm_h1.py", "--selfcheck-prompt"], capture_output=True, text=True)
check("runner --selfcheck-prompt green on real fam05/T0",
      r.returncode == 0 and "PROMPT-SELFCHECK ok" in r.stdout,
      (r.stdout + r.stderr)[-200:])

bad = [n for n, ok_ in results if not ok_]
print(f"\nH6 smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)
