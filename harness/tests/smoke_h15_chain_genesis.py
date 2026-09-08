#!/usr/bin/env python3
"""H15 A12.0-c smoke — genesis link verification. The chain auditor must
verify link 0 on its own terms (kind, prev == GENESIS-ROOT, recomputed
link_hash, bound frozen commit + manifest, run_manifest_hash against the
real manifest) and continue linkage from the VERIFIED genesis hash. Each
of the five genesis mutations must fail verify_chain() on a copy of a
real genesis-bearing chain; a clean copy must still verify and a
downstream link-1 mutation must still fail (no regression). Exit 0 only
if all green. Stdlib only. Private temp root: /tmp/h15-genesis-*."""
import copy
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from chain import Chain, verify_chain

results = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


# --- build a REAL genesis-bearing chain (genesis + links + grade) ---
root = tempfile.mkdtemp(prefix="h15-genesis-", dir="/tmp")
FROZEN = "f" * 40
MANIFEST = {"run_id": "h15-genesis", "wired": True, "dev_mode": False,
            "instance_freeze_commit": FROZEN, "arm": "A", "lane": "L"}
chain_path = os.path.join(root, "EVIDENCE-CHAIN.jsonl")
c = Chain(chain_path, FROZEN, MANIFEST)
c.append("model-call", {"usage": {"in": 10, "out": 5}})
c.append("capability-event", {"invoked": "k1"})
ev = c.append("evaluator", {"verdict": "ship"})
c.append("grade", {"evaluator_link_hash": ev,
                   "grading_rule_hash": "0" * 64,
                   "grading_rule_version": "h15-1"})
records = [json.loads(ln) for ln in open(chain_path) if ln.strip()]
assert records[0]["kind"] == "genesis", "fixture genesis record broken"
assert records[0]["prev"] == Chain.GENESIS_PREV
assert len(records) == 5


def variant(name, mutate):
    """Write a fresh COPY of the chain with exactly one field mutated in
    records[0] (or another link for the regression probe). Returns the
    copy path, or None if the mutation did not actually change anything
    (vacuous-guard failure)."""
    recs = [copy.deepcopy(r) for r in records]
    mutated = mutate(recs)
    if mutated is False:
        return None
    p = os.path.join(root, name + ".jsonl")
    with open(p, "w") as f:
        f.write("\n".join(json.dumps(r, sort_keys=True) for r in recs) + "\n")
    return p


def verify_fails(path, reason_token):
    """verify_chain() on the copy must raise CHAIN-INVALID whose message
    carries the exact explicit GENESIS/link reason token."""
    if path is None:
        return False, "mutation did not change the record"
    try:
        verify_chain(path, FROZEN, MANIFEST)
        return False, "verify_chain accepted the mutated chain"
    except ValueError as e:
        msg = str(e)
        if reason_token not in msg:
            return False, f"reason {reason_token!r} not in: {msg}"
        return True, ""
    except Exception as e:                                    # noqa: BLE001
        return False, f"unexpected error: {e!r}"


# clean copy must still verify
clean_path = os.path.join(root, "clean.jsonl")
shutil.copy(chain_path, clean_path)
try:
    ok = verify_chain(clean_path, FROZEN, MANIFEST) == []
    check("clean genesis-bearing chain verifies", ok)
except Exception as e:                                        # noqa: BLE001
    check("clean genesis-bearing chain verifies", False, str(e))

# mutation 1: genesis `at`
p = variant("at-mut", lambda r: (r[0].update(
    at="2000-01-01T00:00:00Z"), True)[1] if r[0]["at"] != "2000-01-01T00:00:00Z"
    else False)
ok, why = verify_fails(p, "GENESIS link 0 link_hash: recomputed != stored")
check("genesis `at` mutation fails verify_chain", ok, why)

# mutation 2: genesis `prev`
p = variant("prev-mut", lambda r: (r[0].update(
    prev="GENESIS-ROOT-FORGED"), True)[1]
    if r[0]["prev"] == Chain.GENESIS_PREV else False)
ok, why = verify_fails(p, "GENESIS link 0 prev:")
check("genesis `prev` mutation fails verify_chain", ok, why)

# mutation 3: genesis payload.run_manifest_hash
p = variant("rmanhash-mut", lambda r: (r[0]["payload"].update(
    run_manifest_hash="0" * 64), True)[1]
    if r[0]["payload"]["run_manifest_hash"] != "0" * 64 else False)
ok, why = verify_fails(p, "GENESIS payload run_manifest_hash:")
check("genesis payload.run_manifest_hash mutation fails verify_chain",
      ok, why)

# mutation 4a: genesis payload.frozen_commit
p = variant("freeze-mut", lambda r: (r[0]["payload"].update(
    frozen_commit="f" * 64), True)[1]
    if r[0]["payload"]["frozen_commit"] != "f" * 64 else False)
ok, why = verify_fails(p, "GENESIS payload frozen_commit: mismatch")
check("genesis payload.frozen_commit mutation fails verify_chain", ok, why)

# mutation 4b: genesis payload.run_manifest (deep equality, hash kept)
p = variant("manifest-mut", lambda r: (r[0]["payload"].update(
    run_manifest={"run_id": "FORGED"}), True)[1]
    if r[0]["payload"]["run_manifest"] != {"run_id": "FORGED"} else False)
ok, why = verify_fails(p, "GENESIS payload run_manifest: mismatch")
check("genesis payload.run_manifest mutation fails verify_chain", ok, why)

# mutation 5: genesis stored link_hash
p = variant("lh-mut", lambda r: (r[0].update(
    link_hash="0" * 64), True)[1] if r[0]["link_hash"] != "0" * 64 else False)
ok, why = verify_fails(p, "GENESIS link 0 link_hash: recomputed != stored")
check("genesis stored link_hash mutation fails verify_chain", ok, why)

# regression: mutation of link 1 (a normal downstream link) still fails
p = variant("link1-mut", lambda r: (r[1]["payload"].update(
    usage={"in": 999}), True)[1]
    if r[1]["payload"].get("usage", {}).get("in") != 999 else False)
ok, why = verify_fails(p, "link 1: content altered post-write")
check("downstream link-1 mutation still fails (no regression)", ok, why)

bad = [n for n, ok_ in results if not ok_]
print(f"\nH15 chain-genesis smoke: {len(results) - len(bad)}/{len(results)} "
      "closed")
sys.exit(1 if bad else 0)
