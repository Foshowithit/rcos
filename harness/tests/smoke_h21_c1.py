#!/usr/bin/env python3
"""H21 — A12c slice C1: T4 registry set-equality in V2, readiness reframe,
K.md-oracle regression proof.

C1-0 (no code change; regression proof that the slice-B-closed P0 #5
K.md acceptance oracle is gone):
  (a) an independently worded producer `semantic_core` sharing no long
      substring with hidden K.md still promotes through the production
      controller (receipt carries the producer text verbatim);
  (b) a receipt whose `semantic_core` differs by one character from the
      T0 arrival declaration denies, naming the arrival mismatch;
  (c) `grep -c "K.md" harness/order.py` == 0 and order.py opens no K.md.
C1-2 (auditor P0 #7): exact registry<->PREREG set equality lives in V2
preflight (`validate_t4_registry`, wired into `validate_protocol`) —
hermetic matrix: unmutated green; {drop fam03, add fam07, rename
fam01's id, key/value family mismatch} each refuse naming the id.
C1-3 (auditor A12c.8): the T4-CONFORMANCE-READINESS surface never
silently skips a lock — corrupt/unreadable/symlinked locks are
inadmissible naming path+reason and force ready False, even beside a
good lock; a family whose only lock is corrupt is inadmissible, not
absent; the previously-green discriminating case still passes.

Stdlib only. Hermetic fixtures in throwaway dirs (no live-tree
mutation); live-tree reads are read-only. Prints
`H21 C1 smoke: N/N closed`; exits non-zero on any failure.
"""
import hashlib
import json
import os
import re as _re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
FAMC = os.path.join(os.path.dirname(HARNESS), "benchmarks", "fam-c")
sys.path.insert(0, HARNESS)
sys.path.insert(0, HERE)
sys.path.insert(0, FAMC)

import lock as LOCK_MOD  # noqa: E402
import order  # noqa: E402
import promotion  # noqa: E402
import specificity as SPEC  # noqa: E402
import preflight as PF  # noqa: E402
from fixture_modelrun import (build_model_run,  # noqa: E402
                              t0_candidate_sha256)

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
SOLVER = ("def solve(input_dir, output_path):\n"
          "    import json, os\n"
          "    json.dump({'ok': sorted(os.listdir(input_dir))},\n"
          "              open(output_path, 'w'))\n")
SPEC_CLI = os.path.join(HARNESS, "specificity.py")

# C1-0(a): independently worded fam05 producer contract, authored for
# this proof from the visible task surface (never copied from K.md).
C1A_CORE = ("Walk a directory inventory: for every pathname written in "
            "the inventory, stat the file where it lives, weigh it in "
            "bytes, fingerprint its contents, then sort each line into "
            "verified or broken.")
C1A_PRE = [{"requires": "The inventory arrives in the house v1 "
                         "arrangement of pathnames plus weights plus "
                         "fingerprints."},
           {"requires": "Each pathname names a nearby document that can "
                         "be opened and weighed."}]
C1A_CONTRACT = {"semantic_core": C1A_CORE, "preconditions": list(C1A_PRE),
                "limitations": []}
# "Long substring" bar: nothing shared with K.md at or above this
# length (measured max on this text is 8 chars).
C1A_SUBSTRING_BAR = 24

# C1-3 green control: a predicate-matching fam05 requires claim (the
# frozen affirmative bridge: only a requires claim naming the T4's
# applicability condition supports the id) -> discriminating, through
# the reframed surface. The control still carries one real limitation
# (free prose, never evidence).
_B_CORE = ("Audit a file listing: measure every named file on disk and "
           "match its byte count and digest against the listing, then file "
           "each entry as good or bad.")
_B_PRE = ["The listing follows the v1 layout of on-disk paths plus byte "
          "counts plus digests.",
          "Each named file sits on local disk and can be opened for "
          "reading."]
LIMITATION_CONTRACT = {
    "semantic_core": _B_CORE,
    "preconditions": [{"requires": p} for p in _B_PRE] + [
        {"requires": "Synthetic H21 requires: only valid for local v1 "
                     "sha256 manifests."}],
    "limitations": ["Synthetic H21 limitation: rejected payloads are "
                    "reported without detail."]}


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def lcs_len(a, b):
    """Length of the longest common substring (quadratic DP; inputs tiny)."""
    m, n = len(a), len(b)
    dp = [0] * (n + 1)
    best = 0
    for i in range(1, m + 1):
        ndp = [0] * (n + 1)
        ai = a[i - 1]
        for j in range(1, n + 1):
            if ai == b[j - 1]:
                ndp[j] = dp[j - 1] + 1
                if ndp[j] > best:
                    best = ndp[j]
        dp = ndp
    return best


def hermetic(tag, families=("fam05",)):
    root = tempfile.mkdtemp(prefix="h21-" + tag + "-")
    for name in ("ORDER-EXPANSION.json", "PROTOCOL-LOCK.json",
                 "EXECUTION-LOCK.json", "FREEZE.json", "FREEZE-HASHES.sha256",
                 "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json", "PREREG.md"):
        shutil.copy2(os.path.join(FAMC, name), os.path.join(root, name))
    fam = os.path.join(root, "families")
    os.makedirs(fam)
    for f in families:
        shutil.copytree(os.path.join(FAMC, "families", f),
                        os.path.join(fam, f))
    for dirpath, dirnames, _f in os.walk(root):
        os.chmod(dirpath, 0o755)
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
    return root


def mint(root, family, universe="A", producer_contract=None):
    """Acquire/promote/lock one family through the production path.
    Returns (receipt, lock, capdir)."""
    exp = order.load_expansion(root)
    t0 = order.expected_event(exp, "PQ", family, "T0", universe)
    t1 = order.expected_event(exp, "PQ", family, "T1", universe)
    d0 = build_model_run(root, cell=t0, freeze_commit=FREEZE,
                         solver_py=SOLVER, producer_contract=producer_contract)
    build_model_run(root, cell=t1, freeze_commit=FREEZE, solver_py=SOLVER,
                    validates_candidate=t0_candidate_sha256(d0))
    res = promotion.advance(root, "PQ", family, universe, FREEZE,
                            evidence_grade="harness-validation")
    assert res["event"] == "PROMOTION", res
    res2 = promotion.advance(root, "PQ", family, universe, FREEZE,
                             evidence_grade="harness-validation")
    assert res2["event"] == "CAPABILITY_LOCK", res2
    capdir = order.capability_dir(root, "PQ", universe, family)
    lock = json.load(open(os.path.join(capdir, "CAPABILITY_LOCK.json")))
    return res, lock, capdir


def lock_path(root, family, universe="A"):
    return os.path.join(order.capability_dir(root, "PQ", universe, family),
                        "CAPABILITY_LOCK.json")


def run_cli(root):
    return subprocess.run([sys.executable, SPEC_CLI, root],
                          capture_output=True, text=True, timeout=120)


# --- C1-0(a): independently worded producer text still promotes -------
kmd_text = open(os.path.join(FAMC, "families", "fam05", "K.md")).read()
shared = max([lcs_len(C1A_CORE, kmd_text)]
             + [lcs_len(p["requires"], kmd_text) for p in C1A_PRE])
check("C1-0(a) independently worded core shares no long substring "
      "with K.md",
      shared < C1A_SUBSTRING_BAR, f"max shared run = {shared}")
root_a = hermetic("c10a")
res_a, lock_a, _cap_a = mint(root_a, "fam05", producer_contract=C1A_CONTRACT)
check("C1-0(a) independently worded producer promotes (PROMOTION "
      "then CAPABILITY_LOCK)",
      res_a["event"] == "PROMOTION" and lock_a is not None)
rec_a = json.load(open(res_a["receipt"]))
check("C1-0(a) receipt carries the producer text verbatim (no oracle "
      "rewrite)",
      rec_a.get("semantic_core") == C1A_CORE
      and rec_a.get("preconditions") == C1A_PRE
      and rec_a.get("limitations") == [])

# --- C1-0(b): one-character receipt rewrite denies --------------------
root_b = hermetic("c10b")
res_b, _lock_b, _cap_b = mint(root_b, "fam05")
exp_b = order.load_expansion(root_b)
prom_b = order.expected_event(exp_b, "PQ", "fam05", "PROMOTION", "A")
rp_b = os.path.join(order.run_dir(root_b, prom_b), "PROMOTION-RECEIPT.json")
receipt_b = json.load(open(rp_b))
core_b = receipt_b["semantic_core"]
flip = ("X" if core_b[10] != "X" else "Y")
receipt_b["semantic_core"] = core_b[:10] + flip + core_b[11:]
receipt_b["semantic_core_sha256"] = hashlib.sha256(
    receipt_b["semantic_core"].encode()).hexdigest()
json.dump(receipt_b, open(rp_b, "w"), indent=1)
st_b = order.cell_state(root_b, prom_b, FREEZE)
check("C1-0(b) one-character receipt rewrite is not COMPLETE",
      st_b["status"] != "COMPLETE", st_b["status"])
check("C1-0(b) denial names the frozen T0 arrival declaration",
      any("frozen T0 arrival declaration" in r
          for r in st_b["reasons"]), "; ".join(st_b["reasons"])[:200])

# --- C1-0(c): no K.md coupling in order.py -----------------------------
order_src = open(os.path.join(HARNESS, "order.py"),
                 encoding="utf-8").read()
order_kcount = order_src.count("K.md")
check("C1-0(c) grep -c K.md harness/order.py == 0", order_kcount == 0,
      f"count={order_kcount}")
check("C1-0(c) order.py opens no hidden-contract file",
      _re.search(r"open\([^)]*K\.md", order_src) is None)

# --- C1-2: registry<->PREREG equality is a V2 gate ---------------------
check("C1-2 live registry check is green", PF.validate_t4_registry(FAMC) == [])
check("C1-2 validate_protocol enforces the registry rule (wired)",
      "validate_t4_registry" in
      open(os.path.join(FAMC, "preflight.py")).read())


def registry_case(tag, mut=None):
    d = tempfile.mkdtemp(prefix="h21-reg-")
    shutil.copy2(os.path.join(FAMC, "T4-SEMANTIC-IDS.json"),
                 os.path.join(d, "T4-SEMANTIC-IDS.json"))
    shutil.copy2(os.path.join(FAMC, "PREREG.md"),
                 os.path.join(d, "PREREG.md"))
    if mut is not None:
        p = os.path.join(d, "T4-SEMANTIC-IDS.json")
        r = json.load(open(p))
        mut(r)
        json.dump(r, open(p, "w"))
    return PF.validate_t4_registry(d)


def drop_fam03(r):
    r["families"].pop("fam03")


def add_fam07(r):
    r["families"]["fam07"] = "fam07.novel_id"


def rename_fam01(r):
    r["families"]["fam01"] = "fam01.renamed_id"


def mismatch_fam01(r):
    r["families"]["fam01"] = "fam02.pages_disjoint"


check("C1-2 unmutated registry is V2-green",
      registry_case("ok") == [])
f_drop = registry_case("drop", drop_fam03)
check("C1-2 dropped fam03 refuses naming the id",
      f_drop != [] and any("fam03.repeats_are_duplicates" in f
                           for f in f_drop), str(f_drop)[:200])
f_add = registry_case("add", add_fam07)
check("C1-2 added fam07 refuses naming the id",
      f_add != [] and any("fam07.novel_id" in f for f in f_add),
      str(f_add)[:200])
f_ren = registry_case("rename", rename_fam01)
check("C1-2 renamed fam01 id refuses naming the id",
      f_ren != [] and any("fam01.renamed_id" in f for f in f_ren),
      str(f_ren)[:200])
f_mm = registry_case("mismatch", mismatch_fam01)
check("C1-2 key/value family mismatch refuses naming the id",
      f_mm != [] and any("fam02.pages_disjoint" in f for f in f_mm)
      and any("mismatch" in f for f in f_mm), str(f_mm)[:200])

# --- C1-3: corrupt/symlinked locks are inadmissible, never skipped -----
# Two-lock sets use universes A+C of fam05 (the H20 pattern): the frozen
# expansion orders fam05 before every other family, so a second family
# cannot mint without fam05's full downstream; A+C exercises the same
# discovery surface (two committed locks, worst-verdict-wins per family).
root_g = hermetic("c13g")
mint(root_g, "fam05", universe="A", producer_contract=LIMITATION_CONTRACT)
mint(root_g, "fam05", universe="C", producer_contract=LIMITATION_CONTRACT)
rep_g = SPEC.report(root_g)
check("C1-3 discriminating control is contract-conformance-ready",
      rep_g["verdict"] == "contract-conformance-ready"
      and rep_g["contract_conformance_ready"] is True
      and rep_g["discriminating"] == ["fam05"]
      and rep_g["inadmissible"] == {}, str(rep_g))
cli_g = run_cli(root_g)
check("C1-3 CLI exits 0 on the discriminating control",
      cli_g.returncode == 0, f"rc={cli_g.returncode}")

# Two-family-shaped set, one lock corrupted: failure listing that path.
root_c = hermetic("c13c")
mint(root_c, "fam05", universe="A", producer_contract=LIMITATION_CONTRACT)
mint(root_c, "fam05", universe="C", producer_contract=LIMITATION_CONTRACT)
bad_p = lock_path(root_c, "fam05", universe="C")
good_bytes = open(bad_p, "rb").read()
open(bad_p, "wb").write(b"NOT-JSON{{{corrupt lock bytes")
rep_c = SPEC.report(root_c)
check("C1-3 corrupt lock beside a good lock forces failure",
      rep_c["verdict"] == "contract-conformance-failure"
      and rep_c["contract_conformance_ready"] is False, rep_c["verdict"])
bad_reasons = rep_c["inadmissible"].get("fam05") or []
check("C1-3 corrupt lock is inadmissible naming path+reason",
      any(bad_p in r and "unparsable" in r for r in bad_reasons),
      "; ".join(bad_reasons)[:220])
check("C1-3 good lock beside corruption still discriminates (not "
      "hidden)",
      rep_c["discriminating"] == ["fam05"])
check("C1-3 corrupt lock is not counted as a lock (problems surface "
      "it, discovery keeps the one good lock)",
      set(SPEC.discover_locks(root_c)) == {"fam05"}
      and len(SPEC.discover_problems(root_c).get("fam05") or []) == 1)
cli_c = run_cli(root_c)
check("C1-3 CLI exits 1 on the corrupted set", cli_c.returncode == 1,
      f"rc={cli_c.returncode}")
check("C1-3 CLI names the corrupt path on stdout",
      bad_p in cli_c.stdout, cli_c.stdout[-200:])

# Symlinked lock: same refusal.
root_s = hermetic("c13s")
mint(root_s, "fam05", universe="A", producer_contract=LIMITATION_CONTRACT)
mint(root_s, "fam05", universe="C", producer_contract=LIMITATION_CONTRACT)
link_p = lock_path(root_s, "fam05", universe="C")
os.unlink(link_p)
os.symlink(os.path.join(root_s, "PROTOCOL-LOCK.json"), link_p)
rep_s = SPEC.report(root_s)
check("C1-3 symlinked lock forces failure",
      rep_s["verdict"] == "contract-conformance-failure"
      and rep_s["contract_conformance_ready"] is False, rep_s["verdict"])
link_reasons = rep_s["inadmissible"].get("fam05") or []
check("C1-3 symlinked lock is inadmissible naming path+reason",
      any(link_p in r and "symlink" in r for r in link_reasons),
      "; ".join(link_reasons)[:220])
cli_s = run_cli(root_s)
check("C1-3 CLI exits 1 on the symlinked set", cli_s.returncode == 1,
      f"rc={cli_s.returncode}")

# A family whose only lock is corrupt is inadmissible, not absent.
root_o = hermetic("c13o")
mint(root_o, "fam05")
only_p = lock_path(root_o, "fam05")
open(only_p, "wb").write(b"\x00\x01not a lock")
rep_o = SPEC.report(root_o)
check("C1-3 sole corrupt lock: family inadmissible, not absent",
      "fam05" in rep_o["inadmissible"]
      and "fam05" in rep_o["families"]
      and rep_o["contract_conformance_ready"] is False, str(rep_o))
only_reasons = rep_o["inadmissible"].get("fam05") or []
check("C1-3 sole corrupt lock names path+reason",
      any(only_p in r for r in only_reasons),
      "; ".join(only_reasons)[:220])

# Production-caller discipline guards on the reframed module.
spec_src = open(SPEC_CLI, encoding="utf-8").read()
check("specificity.py delegates to lock.specificity_gate",
      "specificity_gate" in spec_src)
check("specificity.py derives capability dirs via the order API",
      "capability_dir" in spec_src)
check("specificity.py has no hidden-contract reader (no K.md open)",
      _re.search(r"open\([^)]*K\.md", spec_src) is None)

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH21 C1 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)
