#!/usr/bin/env python3
"""H17 — frozen governed T4 semantic-ID registry smoke (A12b.5; A12b.6
conformance checks join this suite in slice 2 commit 3).

  * the registry exists, is versioned, and carries exactly one frozen id
    per family (fam01..fam06), each prefixed by its family;
  * the registry id set EQUALS the PREREG frozen-block id set in BOTH
    directions (a registry id outside PREREG refuses at resolve time; a
    PREREG id missing from the registry fails this suite);
  * resolve(): registered family -> (frozen id, True) on any grade;
    unregistered family -> (T4-UNRATIFIED-sha12, False) on
    harness-validation, PROMOTION-DENY on estimand;
  * a registry id not frozen in PREREG refuses (PROMOTION-DENY) — unit
    level and end-to-end through the production promotion controller;
  * the registry bytes are PROTOCOL-LOCK governed: a one-byte mutation
    with no listed forward amendment is a V2 finding (hermetic fake-repo
    proof in the H5 pattern; the live triple-green is H5's).

Stdlib only. Hermetic fixtures live in throwaway dirs under /tmp (no
live-tree mutation); live-tree reads are read-only.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(FAMC, "harness-run"))

import t4_ids  # noqa: E402

RESULTS = []
FAMS = [f"fam0{i}" for i in range(1, 7)]
EXPECT = {
    "fam01": "fam01.rows_are_records",
    "fam02": "fam02.pages_disjoint",
    "fam03": "fam03.repeats_are_duplicates",
    "fam04": "fam04.promised_acyclic",
    "fam05": "fam05.local_v1_sha256",
    "fam06": "fam06.common_unit_basis",
}


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# --- 1. registry shape -------------------------------------------------
reg_p = os.path.join(FAMC, "T4-SEMANTIC-IDS.json")
check("registry file exists", os.path.isfile(reg_p))
reg = json.load(open(reg_p))
check("registry version is t4-semantic-ids-v1",
      reg.get("version") == "t4-semantic-ids-v1", reg.get("version"))
check("registry names the PREREG frozen block + fam01 amendment",
      isinstance(reg.get("prereg_source"), str)
      and "Conformance semantic IDs (frozen)" in reg["prereg_source"]
      and "AMEND-2026-09-08-fam01" in reg["prereg_source"],
      reg.get("prereg_source"))
fams = reg.get("families") if isinstance(reg, dict) else None
check("registry carries exactly fam01..fam06",
      isinstance(fams, dict) and sorted(fams) == FAMS, sorted(fams or {}))
check("registry ids are exactly the six frozen ids",
      isinstance(fams, dict) and fams == EXPECT,
      {k: (fams or {}).get(k) for k in FAMS})

# --- 2. set equality both directions -----------------------------------
live_reg = t4_ids.frozen_set(FAMC)
live_frozen = t4_ids.prereg_frozen_set(FAMC)
check("registry set == PREREG frozen set (live tree)",
      set(live_reg.values()) == live_frozen,
      f"extra={sorted(set(live_reg.values()) - live_frozen)} "
      f"missing={sorted(live_frozen - set(live_reg.values()))}")
check("PREREG frozen block carries the fam01 amendment id",
      "fam01.rows_are_records" in live_frozen)

# the check is not vacuous: on a mutated copy the inequality is detected
mut = tempfile.mkdtemp(prefix="h17-mut-")
shutil.copy2(reg_p, os.path.join(mut, "T4-SEMANTIC-IDS.json"))
shutil.copy2(os.path.join(FAMC, "PREREG.md"), os.path.join(mut, "PREREG.md"))
rogue = json.load(open(os.path.join(mut, "T4-SEMANTIC-IDS.json")))
rogue["families"]["fam06"] = "fam06.smuggled_id"
json.dump(rogue, open(os.path.join(mut, "T4-SEMANTIC-IDS.json"), "w"))
check("a registry id outside PREREG is detected (not-equal sets)",
      set(t4_ids.frozen_set(mut).values()) != t4_ids.prereg_frozen_set(mut))
drop = json.load(open(os.path.join(FAMC, "T4-SEMANTIC-IDS.json")))
del drop["families"]["fam01"]
json.dump(drop, open(os.path.join(mut, "T4-SEMANTIC-IDS.json"), "w"))
check("a PREREG id missing from the registry is detected",
      t4_ids.prereg_frozen_set(mut) - set(
          t4_ids.frozen_set(mut).values()) == {"fam01.rows_are_records"})

# --- 3. resolve() behavior ----------------------------------------------
tid, rat = t4_ids.resolve(FAMC, "fam05", "0" * 64, "harness-validation")
check("registered fam05 resolves ratified on harness-validation",
      (tid, rat) == ("fam05.local_v1_sha256", True), f"{tid} {rat}")
tid_e, rat_e = t4_ids.resolve(FAMC, "fam05", "0" * 64, "estimand")
check("registered fam05 resolves ratified on estimand too",
      (tid_e, rat_e) == ("fam05.local_v1_sha256", True))
u_id, u_rat = t4_ids.resolve(FAMC, "fam99", "ab" * 32, "harness-validation")
check("unregistered family is explicitly UNRATIFIED (harness-validation)",
      u_rat is False and u_id == "T4-UNRATIFIED-" + "ab" * 6, u_id)
try:
    t4_ids.resolve(FAMC, "fam99", "ab" * 32, "estimand")
    denied = False
except PermissionError as e:
    denied = "PROMOTION-DENY" in str(e)
check("unregistered family on estimand is PROMOTION-DENY", denied)
shutil.copy2(reg_p, os.path.join(mut, "T4-SEMANTIC-IDS.json"))
rogue2 = json.load(open(os.path.join(mut, "T4-SEMANTIC-IDS.json")))
rogue2["families"]["fam06"] = "fam06.smuggled_id"
json.dump(rogue2, open(os.path.join(mut, "T4-SEMANTIC-IDS.json"), "w"))
try:
    t4_ids.resolve(mut, "fam06", "ab" * 32, "harness-validation")
    refused = False
except PermissionError as e:
    refused = "PROMOTION-DENY" in str(e)
check("a registry id outside PREREG refuses (PROMOTION-DENY)", refused)

# --- 4. end-to-end: rogue registry denies through the controller --------
import order  # noqa: E402
import promotion  # noqa: E402
from fixture_modelrun import build_model_run  # noqa: E402

FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("def solve(input_dir, output_path):\n"
          "    import json, os\n"
          "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
          "              open(output_path, 'w'))\n")


def hermetic(governed_mut=None):
    root = tempfile.mkdtemp(prefix="h17-pair-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    if governed_mut:
        governed_mut(root)
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    shutil.copytree(os.path.join(FAMC, "families", "fam05"),
                    os.path.join(fam, "fam05"))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def build_pair(root):
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", "fam05", "T0", "A")
    t1 = order.expected_event(exp, "PQ", "fam05", "T1", "A")
    build_model_run(root, cell=t0, freeze_commit=FREEZE, solver_py=SOLVER)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER)


root_ok = hermetic()
build_pair(root_ok)
res = promotion.advance(root_ok, "PQ", "fam05", "A", FREEZE,
                        evidence_grade="harness-validation")
rec = json.load(open(res["receipt"]))
check("fam05 promotion receipt carries the frozen id, ratified",
      rec.get("t4_semantic_id") == "fam05.local_v1_sha256"
      and rec.get("t4_ratified") is True,
      f"{rec.get('t4_semantic_id')} {rec.get('t4_ratified')}")


def _rogue(root):
    d = json.load(open(os.path.join(root, "T4-SEMANTIC-IDS.json")))
    d["families"]["fam05"] = "fam05.smuggled_id"
    json.dump(d, open(os.path.join(root, "T4-SEMANTIC-IDS.json"), "w"))


root_bad = hermetic(_rogue)
build_pair(root_bad)
try:
    promotion.advance(root_bad, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    e2e_denied = False
except PermissionError as e:
    e2e_denied = "PROMOTION-DENY" in str(e)
check("rogue registry id denies end-to-end (PROMOTION-DENY)", e2e_denied)

# --- 5. V2 governance: mutation without amendment is a finding ----------
_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")


def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       env=_ENV, text=True)
    assert r.returncode == 0, (args, r.stderr[:200])
    return r.stdout.strip()


sys.path.insert(0, FAMC)
import preflight as PF  # noqa: E402

v2 = os.path.join(tempfile.mkdtemp(prefix="h17-v2-"), "repo",
                  "benchmarks", "fam-c")
os.makedirs(v2)
open(os.path.join(v2, "PREREG.md"), "w").write(
    "## Conformance semantic IDs (frozen)\n\n```text\n"
    "fam01.rows_are_records\n```\n")
open(os.path.join(v2, "ORDER.md"), "w").write("frozen order\n")
repo = os.path.dirname(os.path.dirname(v2))
git(repo, "init", "-q")
git(repo, "add", "-A")
git(repo, "commit", "-qm", "freeze")
FC = git(repo, "rev-parse", "HEAD")
disk_reg = {"version": "t4-semantic-ids-v1",
            "prereg_source": "h17 fixture",
            "families": {"fam01": "fam01.rows_are_records"}}
open(os.path.join(v2, "T4-SEMANTIC-IDS.json"), "w").write(
    json.dumps(disk_reg, indent=1))
reg_sha = sha_file(os.path.join(v2, "T4-SEMANTIC-IDS.json"))
lock = {"freeze_commit": FC,
        "governed": {"T4-SEMANTIC-IDS.json": reg_sha},
        "amendments": [{"file": "T4-SEMANTIC-IDS.json", "from_sha": None,
                        "to_sha": reg_sha, "added_after_freeze": True,
                        "reason": "h17 fixture genesis", "base": FC[:7],
                        "slice": "h17"}]}
open(os.path.join(v2, "PROTOCOL-LOCK.json"), "w").write(json.dumps(lock))
f_reg = [f for f in PF.validate_protocol(v2, FC)
         if "T4-SEMANTIC-IDS.json" in f]
check("post-freeze genesis amendment governs the new file (V2 green)",
      f_reg == [], str(f_reg))
open(os.path.join(v2, "T4-SEMANTIC-IDS.json"), "w").write(
    json.dumps(disk_reg, indent=1) + "\n# unlisted drift\n")
f_mut = [f for f in PF.validate_protocol(v2, FC)
         if "T4-SEMANTIC-IDS.json" in f]
check("registry drift with no listed amendment is a V2 finding",
      any("no listed forward amendment" in f for f in f_mut), str(f_mut))

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH17 t4-registry smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)
