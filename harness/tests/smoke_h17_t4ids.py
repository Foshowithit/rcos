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
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

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
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE, solver_py=SOLVER)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))


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

# --- 6. A12b.2 T1 candidate-validation surface -----------------------------
import run_arm_h1 as RA  # noqa: E402

_CAND_SHA = "ab" * 32
_CAND_SRC = "import sys\nprint('candidate')\n"
block = RA.build_candidate_validation_block(_CAND_SHA, _CAND_SRC)
check("candidate block carries the delimited sha + source + argv ABI",
      block.count(RA._CAND_BEGIN) == 1 and block.count(RA._CAND_END) == 1
      and f"candidate_sha256: {_CAND_SHA}" in block
      and "abi: python3 candidate.py <input_dir> <output_path>" in block
      and _CAND_SRC in block)
for bad_sha, bad_src, why in ((None, _CAND_SRC, "non-sha"),
                              ("zz" * 32, _CAND_SRC, "non-hex"),
                              (_CAND_SHA, "  ", "empty source"),
                              (_CAND_SHA, "x\n" + RA._CAND_END + "\n",
                               "delimiter smuggling")):
    try:
        RA.build_candidate_validation_block(bad_sha, bad_src)
        refused = False
    except ValueError:
        refused = True
    check(f"candidate block builder refuses {why}", refused)

_env = RA.build_envelope("TASKDEF", "a.txt", "--- a.txt ---\nAA")
_t1prompt = RA._PRE + _env + block + RA._OUT
check("full stripper removes the candidate block (leak-stripping)",
      RA.strip_capability_block(_t1prompt) == RA._PRE + _env + RA._OUT)
_cap = RA._CAP_FMT.replace("__MANIFEST__", "M").replace("__NOTES__", "N") \
    .replace("__ENGINE__", "E")
_both = RA._PRE + _env + _cap + block + RA._OUT
check("full stripper removes BOTH blocks together",
      RA.strip_capability_block(_both) == RA._PRE + _env + RA._OUT)
_cor = RA.build_arm_prompt("correct", _env, "M", "N", "E")
_dis = RA.build_arm_prompt("disabled", _env)
check("arm symmetry refuses a candidate block leaked into treatment",
      RA.check_arm_symmetry(_cor + "\n" + RA._CAND_BEGIN + "\nX\n"
                            + RA._CAND_END, _dis, _env) != [])
check("arm symmetry refuses a candidate block leaked into control",
      RA.check_arm_symmetry(_cor, _dis + block, _env) != [])
check("canonical pair still symmetric (no candidate markers)",
      RA.check_arm_symmetry(_cor, _dis, _env) == [])


def _chain_kinds(run_dir):
    return [json.loads(x)["kind"]
            for x in open(os.path.join(run_dir, "EVIDENCE-CHAIN.jsonl"))
            if x.strip()]


_bare = hermetic()
exp_b = order.load_expansion(_bare)
_b0 = order.expected_event(exp_b, "PQ", "fam05", "T0", "A")
_b1 = order.expected_event(exp_b, "PQ", "fam05", "T1", "A")
_d0 = build_model_run(_bare, cell=_b0, freeze_commit=FREEZE, solver_py=SOLVER)
_d1 = build_model_run(_bare, cell=_b1, freeze_commit=FREEZE, solver_py=SOLVER)
check("bare T1 chain carries no candidate-validation event",
      "candidate-validation" not in _chain_kinds(_d1))
try:
    promotion.advance(_bare, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _bare_denied = False
    _bare_msg = "promotion SUCCEEDED without candidate-validation evidence"
except PermissionError as e:
    _bare_denied = "PROMOTION-DENY" in str(e)
    _bare_msg = str(e)[:160]
check("bare T1 pair never promotes (fail closed)", _bare_denied, _bare_msg)
# the SHIP verdict stands: both bare cells are still COMPLETE, so the
# refusal names promotion (not acquisition).
check("bare T0/T1 cells still SHIP (COMPLETE) while promotion denies",
      order.cell_state(_bare, _b0, FREEZE)["status"] == "COMPLETE"
      and order.cell_state(_bare, _b1, FREEZE)["status"] == "COMPLETE")
# a T1 that validated the WRONG candidate (chain fully valid, but bound
# to another root) denies with the candidate binding — end-to-end proof
# the gate compares against THIS universe's frozen candidate.
_v1 = build_model_run(_bare, cell=_b1, freeze_commit=FREEZE, solver_py=SOLVER,
                      validates_candidate="ff" * 32)
try:
    promotion.advance(_bare, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _wrong_denied = False
except PermissionError as e:
    _wrong_denied = ("PROMOTION-DENY" in str(e)
                     and "validated candidate" in str(e))
check("T1 validating another candidate denies (candidate binding)",
      _wrong_denied)
_v1 = build_model_run(_bare, cell=_b1, freeze_commit=FREEZE, solver_py=SOLVER,
                      validates_candidate=t0_candidate_sha256(_d0))

_cve = [json.loads(x) for x in
        open(os.path.join(_v1, "EVIDENCE-CHAIN.jsonl")) if x.strip()
        and json.loads(x)["kind"] == "candidate-validation"]
check("validating T1 chain carries exactly one candidate-validation event",
      len(_cve) == 1
      and _cve[0]["payload"]["candidate_sha256"]
      == _cve[0]["payload"]["executed_sha256"]
      == t0_candidate_sha256(_d0)
      and _cve[0]["payload"]["validated"] is True)

# tamper: a T1 arrival declaring a different candidate still denies, and
# a chain event whose executed bytes differ from the frozen candidate
# denies (the binding is byte-exact, not asserted).
_tam = hermetic()
exp_t = order.load_expansion(_tam)
_q0 = order.expected_event(exp_t, "PQ", "fam05", "T0", "A")
_q1 = order.expected_event(exp_t, "PQ", "fam05", "T1", "A")
_qd0 = build_model_run(_tam, cell=_q0, freeze_commit=FREEZE, solver_py=SOLVER)
_qd1 = build_model_run(_tam, cell=_q1, freeze_commit=FREEZE, solver_py=SOLVER,
                       validates_candidate=t0_candidate_sha256(_qd0))
_arr = json.load(open(os.path.join(_qd1, "arrival.json")))
_arr["execution_payload"]["candidate_sha256"] = "ff" * 32
json.dump(_arr, open(os.path.join(_qd1, "arrival.json"), "w"))
try:
    promotion.advance(_tam, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _tam_denied = False
except PermissionError as e:
    _tam_denied = "PROMOTION-DENY" in str(e)
check("T1 declaring a different candidate denies", _tam_denied)
_arr["execution_payload"]["candidate_sha256"] = t0_candidate_sha256(_qd0)
json.dump(_arr, open(os.path.join(_qd1, "arrival.json"), "w"))
# rewriting the committed validation event voids the T1 cell itself
# (chain tamper -> not COMPLETE), so the promotion path refuses. The
# precise executed-binding is proven by the valid-chain unit cases below.
_chain_p = os.path.join(_qd1, "EVIDENCE-CHAIN.jsonl")
_lines = [json.loads(x) for x in open(_chain_p) if x.strip()]
for _l in _lines:
    if _l.get("kind") == "candidate-validation":
        _l["payload"]["executed_sha256"] = "ee" * 32
with open(_chain_p, "w") as f:
    for _l in _lines:
        f.write(json.dumps(_l) + "\n")
check("rewriting the validation event voids the T1 cell",
      order.cell_state(_tam, _q1, FREEZE)["status"] != "COMPLETE")
try:
    promotion.advance(_tam, "PQ", "fam05", "A", FREEZE,
                      evidence_grade="harness-validation")
    _exe_denied = False
except PermissionError:
    _exe_denied = True
check("voided validation evidence denies the promotion path", _exe_denied)

# precise gate proof: hand-built VALID chains through the real reader —
# zero events, two events, and executed != candidate each refuse with
# the fail-closed PROMOTION-DENY (not with a chain-tamper message).
import chain as CHAIN_MOD  # noqa: E402


def _cv_chain(payloads):
    td = tempfile.mkdtemp(prefix="h17-cv-")
    cp = os.path.join(td, "EVIDENCE-CHAIN.jsonl")
    ch = CHAIN_MOD.Chain(cp, FREEZE, {"fixture": "h17-cv"})
    for p in payloads:
        ch.append("candidate-validation", p)
    return td


_CV_OK = {"candidate_sha256": "aa" * 32, "executed_sha256": "aa" * 32,
          "adapter_sha256": "cc" * 32, "validated": True}
_td0 = _cv_chain([])
try:
    promotion._t1_candidate_validation(_td0, "aa" * 32)
    _z = False
except PermissionError as e:
    _z = "PROMOTION-DENY" in str(e) and "exactly one" in str(e)
check("zero candidate-validation events denies", _z)
_td2 = _cv_chain([dict(_CV_OK), dict(_CV_OK)])
try:
    promotion._t1_candidate_validation(_td2, "aa" * 32)
    _t = False
except PermissionError as e:
    _t = "PROMOTION-DENY" in str(e) and "exactly one" in str(e)
check("two candidate-validation events deny", _t)
_td3 = _cv_chain([dict(_CV_OK, executed_sha256="bb" * 32)])
try:
    promotion._t1_candidate_validation(_td3, "aa" * 32)
    _x = False
except PermissionError as e:
    _x = "PROMOTION-DENY" in str(e) and "executed" in str(e)
check("executed != candidate denies with the execution binding", _x)
_td4 = _cv_chain([dict(_CV_OK)])
try:
    _got = promotion._t1_candidate_validation(_td4, "aa" * 32)
    _v = _got == dict(_CV_OK)
except PermissionError:
    _v = False
check("matching validation evidence derives cleanly", _v)

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH17 t4-registry smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)
