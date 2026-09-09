#!/usr/bin/env python3
"""H30 — A12i slice D9 acceptance: experiment-branch protocol chronology
(P0) + named lock-container failures (P2 folded in).

D9.1 closes the lineage-authority gap: for every governed file V2
derives the ORDERED distinct committed content states from the
EXPERIMENT BRANCH (`git log --first-parent --format=%H --
benchmarks/fam-c/<fn>` from HEAD, oldest -> newest, consecutive
duplicates collapsed; first-parent since A12l slice D11) and
requires the recorded root -> tip node sequence to be a SUBSEQUENCE
of it (Rule A lineage membership replaces the all-refs
retrievability test; Rule B chronology). A recorded chain with two
real committed states swapped, or with a side-branch-only state
inserted, FAILs with a named V2 finding even though every sha is
real, the graph is linear, and disk == tip. Collapsing several real
commits into one recorded edge stays legal.

D9.2 closes the malformed-container crashes: `"governed": []`,
`"governed": null`, `"amendments": [null]`, and a non-dict
amendment entry each yield a NAMED V2 finding (naming the offending
container/index), never a traceback.

Proven end-to-end through the real `validate_protocol` path on
throwaway repos (green baseline asserted first, same fixture) plus
hermetic pure-function probes. Stdlib only. No live-tree mutation
(live-tree reads are read-only). Prints `H30 D9 smoke: N/N closed`;
exits non-zero on any failure.
"""
import ast
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
sys.path.insert(0, FAMC)

import preflight as PF  # noqa: E402

RESULTS = []
FREEZE = json.load(open(os.path.join(FAMC, "FREEZE.json")))["freeze_commit"]
TOP = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=FAMC,
                     capture_output=True, text=True).stdout.strip()


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git_bytes(rev_path):
    p = subprocess.run(["git", "show", rev_path], cwd=TOP,
                       capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout


# --- D9.1 STATIC: the all-refs walk is gone, purity kept -----------------
_SRC = open(os.path.join(FAMC, "preflight.py")).read()
check("D9.1-STATIC no `--all` anywhere in benchmarks/fam-c/preflight.py",
      "--all" not in _SRC)
check("D9.1-STATIC the branch-sequence helper exists and the all-refs "
      "map is gone",
      "def _branch_seq_shas" in _SRC
      and "_file_version_shas" not in _SRC)
_VFC = next(n for n in ast.walk(ast.parse(_SRC))
            if isinstance(n, ast.FunctionDef)
            and n.name == "validate_file_chain")
_VFC_DUMP = ast.dump(_VFC)
check("D9.1-STATIC validate_file_chain takes the branch sequence in "
      "(git walk stays out of the pure function)",
      any(a.arg == "branch_seq" for a in _VFC.args.args)
      and "_branch_seq_shas" not in _VFC_DUMP)
check("D9.1-STATIC validate_file_chain stays pure and I/O-free (no "
      "open(), no subprocess, no os./git. I/O)",
      not any(isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name) and n.func.id == "open"
              for n in ast.walk(_VFC))
      and "subprocess" not in _VFC_DUMP
      and "git." not in _VFC_DUMP
      and "os." not in _VFC_DUMP)

# --- D9.1 LIVE: branch sequences, subsequence, green lock -----------------
LIVE_LOCK = json.load(open(os.path.join(FAMC, "PROTOCOL-LOCK.json")))


def _live_branch_seq(fn):
    commits = subprocess.run(
        ["git", "log", "--first-parent", "--format=%H", "--",
         f"benchmarks/fam-c/{fn}"],
        cwd=TOP, capture_output=True, text=True).stdout.split()
    seq = []
    for c in reversed(commits):
        raw = _git_bytes(f"{c}:benchmarks/fam-c/{fn}")
        assert raw is not None, (fn, c[:12])
        h = hashlib.sha256(raw).hexdigest()
        if not seq or seq[-1] != h:
            seq.append(h)
    return seq


_SEQ = {fn: _live_branch_seq(fn) for fn in PF.PROTOCOL_GOVERNED}
check("D9.1-LIVE branch-sequence lengths match the certified facts "
      "(untouched files 5/5/1/7; preflight.py by its one D11 commit "
      "to 18, PREREG.md by its one D11 commit to 20, "
      "HARNESS-READINESS.md still at its D10 12)",
      {fn: len(_SEQ[fn]) for fn in PF.PROTOCOL_GOVERNED} == {
          "PREREG.md": 20, "ORDER.md": 5, "LANES.md": 5,
          "HARNESS-READINESS.md": 12, "preflight.py": 18,
          "T4-SEMANTIC-IDS.json": 1, "T4-CONFORMANCE.json": 7},
      str({fn: len(s) for fn, s in _SEQ.items()}))


def _live_recorded(fn):
    raw = _git_bytes(f"{FREEZE}:benchmarks/fam-c/{fn}")
    if raw is None:
        gen = [a for a in LIVE_LOCK["amendments"]
               if a.get("file") == fn and a.get("from_sha") is None]
        assert len(gen) == 1, fn
        root = gen[0]["to_sha"]
    else:
        root = hashlib.sha256(raw).hexdigest()
    by_from = {}
    for a in LIVE_LOCK["amendments"]:
        if a.get("file") == fn and a.get("from_sha") is not None:
            by_from.setdefault(a["from_sha"], []).append(a["to_sha"])
    rec, cur = [root], root
    while cur in by_from:
        cur = by_from[cur][0]
        rec.append(cur)
    return rec


_SUBSEQ_BAD = []
for _fn in PF.PROTOCOL_GOVERNED:
    _rec = _live_recorded(_fn)
    _pos, _ok = -1, True
    for _n in _rec:
        try:
            _pos = _SEQ[_fn].index(_n, _pos + 1)
        except ValueError:
            _ok = False
            break
    if not _ok:
        _SUBSEQ_BAD.append(_fn)
check("D9.1-LIVE every live recorded chain is a subsequence of its "
      "branch sequence (no chain repair needed)",
      _SUBSEQ_BAD == [], str(_SUBSEQ_BAD))
check("D9.1-LIVE the live chains collapse multi-commit edges "
      "(recorded shorter than branch history, still legal)",
      all(len(_live_recorded(fn)) < len(_SEQ[fn])
          for fn in ("PREREG.md", "preflight.py",
                     "HARNESS-READINESS.md")),
      str({fn: (len(_live_recorded(fn)), len(_SEQ[fn]))
           for fn in PF.PROTOCOL_GOVERNED}))
_ALL = PF.validate_all(FAMC)
check("D9.1-LIVE the live lock stays green (V1/V2/V3 = 0/0/0)",
      _ALL == [], str(_ALL[:2])[:240])
_V1 = [f for f in _ALL if f.startswith("V1")]
_V2 = [f for f in _ALL if f.startswith("V2")]
_V3 = [f for f in _ALL if f.startswith("V3")]
check("D9.1-LIVE preflight counts are 0/0/0",
      (len(_V1), len(_V2), len(_V3)) == (0, 0, 0),
      f"{len(_V1)}/{len(_V2)}/{len(_V3)}")
_TIPS, _TIP_FIND = PF.protocol_tips(FAMC, FREEZE)
check("D9.1-LIVE validator tips computed for every governed file",
      _TIP_FIND == []
      and sorted(_TIPS) == sorted(PF.PROTOCOL_GOVERNED),
      f"tips={sorted(_TIPS)} finds={str(_TIP_FIND[:1])[:160]}")
_DISK = {fn: _sha_file(os.path.join(FAMC, fn))
         for fn in PF.PROTOCOL_GOVERNED}
_TIP_BAD = [fn for fn in PF.PROTOCOL_GOVERNED if _TIPS.get(fn) != _DISK[fn]]
check("D9.1-LIVE every governed file: disk sha256 == the validator's "
      "unique tip",
      _TIP_BAD == [], str(_TIP_BAD))

# --- D9 GOVERNANCE: stanza, forward entries, counts ----------------------
check("D9-GOV the D9 stanza lives in PREREG.md (chronology rule + "
      "all-refs removal + no-repair fact)",
      "AMEND-2026-09-09-d9-protocol-chronology"
      in open(os.path.join(FAMC, "PREREG.md")).read()
      and "no chain repair" in
      open(os.path.join(FAMC, "PREREG.md")).read().lower())
check("D9-GOV no amendment entry deleted (35 at D10 + 2 D11 forward "
      "= 37)",
      len(LIVE_LOCK["amendments"]) == 37,
      str(len(LIVE_LOCK["amendments"])))
check("D9-GOV the D9 slice recorded as its own forward amendment "
      "(PREREG + preflight edges)",
      sum(1 for a in LIVE_LOCK["amendments"]
          if a.get("slice") == "a12i-slice-d9") == 2)
check("D9-GOV earlier slices intact (D8 shared-lineage 2, D7 "
      "lineage-repair 2)",
      sum(1 for a in LIVE_LOCK["amendments"]
          if "AMEND-2026-09-09-d8-shared-lineage"
          in (a.get("reason") or "")) == 2
      and sum(1 for a in LIVE_LOCK["amendments"]
              if "AMEND-2026-09-09-d7-lineage-repair"
              in (a.get("reason") or "")) == 2)
check("D9-GOV lock-global hygiene still clean on the live lock",
      PF.validate_lock_global(LIVE_LOCK) == [],
      str(PF.validate_lock_global(LIVE_LOCK)[:1])[:200])

# --- D9.1 FORGES, end-to-end through validate_protocol -------------------
_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")


def _git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       env=_ENV, text=True)
    assert r.returncode == 0, (args, r.stderr[:200])
    return r.stdout.strip()


def _live_bytes():
    return {fn: open(os.path.join(FAMC, fn), "rb").read()
            for fn in PF.PROTOCOL_GOVERNED}


def _forge_repo(tag):
    """Throwaway repo: freeze the live bytes, then commit three
    post-freeze PREREG.md states A/B/C on master plus a side-branch
    state X (X committed ONLY off master). Returns
    (famc, FC, R, A, B, C, X)."""
    base = tempfile.mkdtemp(prefix="h30-" + tag + "-")
    repo = os.path.join(base, "repo")
    famc = os.path.join(repo, "benchmarks", "fam-c")
    os.makedirs(famc)
    for fn, data in _live_bytes().items():
        with open(os.path.join(famc, fn), "wb") as f:
            f.write(data)
    shutil.copy2(os.path.join(FAMC, "ORDER-EXPANSION.json"),
                 os.path.join(famc, "ORDER-EXPANSION.json"))
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "freeze")
    fc = _git(repo, "rev-parse", "HEAD")
    r = _sha_file(os.path.join(famc, "PREREG.md"))
    states = []
    for mark in ("A", "B", "C"):
        with open(os.path.join(famc, "PREREG.md"), "ab") as f:
            f.write(f"\n# h30 fixture {mark}\n".encode())
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "post " + mark)
        states.append(_sha_file(os.path.join(famc, "PREREG.md")))
    a, b, c = states
    _git(repo, "checkout", "-qb", "side", fc)
    with open(os.path.join(famc, "PREREG.md"), "wb") as f:
        f.write(_live_bytes()["PREREG.md"] + b"\n# h30 side X\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "side X")
    x = _sha_file(os.path.join(famc, "PREREG.md"))
    _git(repo, "checkout", "-q", "master")
    assert _sha_file(os.path.join(famc, "PREREG.md")) == c
    return famc, fc, r, a, b, c, x


_FAMC, _FC, _R, _A, _B, _C, _X = _forge_repo("forge")
_FROZEN = {fn: hashlib.sha256(d).hexdigest()
           for fn, d in _live_bytes().items()}


def _v2(chain):
    lock = {"freeze_commit": _FC, "governed": dict(_FROZEN),
            "amendments": [{"file": "PREREG.md", "from_sha": f,
                            "to_sha": t} for (f, t) in chain]}
    with open(os.path.join(_FAMC, "PROTOCOL-LOCK.json"), "w") as f:
        json.dump(lock, f)
    # A12l slice D11.1: the lock under test must be COMMITTED (the
    # byte authority compares worktree bytes against HEAD) — a
    # fixture strengthening, never a weakening: the assertions below
    # still prove the same chain verdicts. --allow-empty covers the
    # double-call pattern (baseline evaluated twice for the extra).
    _repo = os.path.dirname(os.path.dirname(_FAMC))
    _git(_repo, "add", "benchmarks/fam-c/PROTOCOL-LOCK.json")
    subprocess.run(["git", "commit", "--allow-empty", "-qm",
                    "h30 test lock"], cwd=_repo, capture_output=True,
                   env=_ENV, text=True)
    return [g for g in PF.validate_protocol(_FAMC, _FC)
            if g.startswith("V2")]


check("D9.1-E2E baseline (true R->A->B->C) is V2 green through the "
      "real path",
      _v2([(_R, _A), (_A, _B), (_B, _C)]) == [],
      str(_v2([(_R, _A), (_A, _B), (_B, _C)])[:1])[:200])
check("D9.1-E2E collapsed edge (R->C over three real commits) stays "
      "legal — no over-tightening",
      _v2([(_R, _C)]) == [],
      str(_v2([(_R, _C)])[:1])[:200])
_F_TT = _v2([(_R, _B), (_B, _A), (_A, _C)])
check("D9.1-E2E TIME-TRAVEL (R->B->A->C, disk == tip) FAILs naming "
      "PREREG.md as a non-monotonic lineage",
      any("PREREG.md" in g and "non-monotonic" in g for g in _F_TT),
      str(_F_TT[:1])[:240])
_F_OB = _v2([(_R, _X), (_X, _C)])
check("D9.1-E2E OFF-BRANCH (R->X->C, X side-only, tip == disk) "
      "FAILs naming the node as not on the experiment-HEAD lineage",
      any("PREREG.md" in g and "experiment-HEAD lineage" in g
          for g in _F_OB),
      str(_F_OB[:1])[:240])
_F_GHOST = _v2([(_R, "ff" * 32), ("ff" * 32, _C)])
check("D9.1-E2E never-committed node FAILs naming retrievable bytes "
      "(D8 phrase kept)",
      any("PREREG.md" in g and "no retrievable bytes" in g
          for g in _F_GHOST),
      str(_F_GHOST[:1])[:240])

# --- D9.1 hermetic pure-function probes (no git) --------------------------
_HA, _HB, _HC, _HR = "aa" * 32, "bb" * 32, "cc" * 32, "dd" * 32
_SEQ4 = [_HR, _HA, _HB, _HC]


def _pure(chain, seq, disk=None, root=None):
    ams = [{"file": "PREREG.md", "from_sha": f, "to_sha": t}
           for (f, t) in chain]
    f, tip = PF.validate_file_chain(
        "PREREG.md", root if root is not None else _HR, ams,
        disk if disk is not None else chain[-1][1],
        root if root is not None else _HR, seq)
    return f, tip


_F, _T = _pure([(_HR, _HA), (_HA, _HB), (_HB, _HC)], _SEQ4)
check("D9.1-PURE in-order chain over an explicit branch_seq is green",
      _F == [] and _T == _HC, str(_F[:1])[:160])
_F, _ = _pure([(_HR, _HC)], _SEQ4)
check("D9.1-PURE collapsed edge over an explicit branch_seq is green",
      _F == [], str(_F[:1])[:160])
_F, _ = _pure([(_HR, _HB), (_HB, _HA), (_HA, _HC)], _SEQ4)
check("D9.1-PURE swapped pair over an explicit branch_seq FAILs as "
      "non-monotonic naming PREREG.md",
      any("PREREG.md" in g and "non-monotonic" in g for g in _F),
      str(_F[:1])[:200])
_F, _ = _pure([(_HR, "ee" * 32), ("ee" * 32, _HC)], _SEQ4)
check("D9.1-PURE off-sequence node FAILs naming the node + "
      "experiment-HEAD lineage",
      any("PREREG.md" in g and "experiment-HEAD lineage" in g
          for g in _F),
      str(_F[:1])[:200])
_F, _ = _pure([(_HR, _HA), (_HA, _HC)], "notalist")
check("D9.1-PURE a non-list branch_seq fails closed naming PREREG.md",
      any("PREREG.md" in g for g in _F), str(_F[:1])[:160])
_F5, _T5 = PF.validate_file_chain(
    "ORDER.md", None, [], _DISK["ORDER.md"], _DISK["ORDER.md"])
check("D9.1-PURE branch_seq=None keeps the hermetic topology-only "
      "mode (5-arg calls unchanged)",
      isinstance(_F5, list), str(_F5)[:120])

# --- D9.2 malformed containers: named findings, no traceback -------------


def _v2_lock(lock):
    with open(os.path.join(_FAMC, "PROTOCOL-LOCK.json"), "w") as f:
        json.dump(lock, f)
    return [g for g in PF.validate_protocol(_FAMC, _FC)
            if g.startswith("V2")]


def _base_lock():
    return {"freeze_commit": _FC, "governed": dict(_FROZEN),
            "amendments": []}


try:
    _F_BASE = _v2_lock(_base_lock())
    check("D9.2-E2E unmutated lock is the green baseline",
          all("governed map" not in g and "amendments list" not in g
              and "not an object" not in g for g in _F_BASE),
          str(_F_BASE[:2])[:200])
except Exception as e:  # noqa: BLE001
    check("D9.2-E2E unmutated lock is the green baseline", False,
          f"{type(e).__name__}: {e}")

_CASES = [
    ("governed-is-list", {"governed": []}, "governed map"),
    ("governed-is-null", {"governed": None}, "governed map"),
    ("amendments-holds-null", {"amendments": [None]},
     "amendment entry #0"),
    ("amendment-entry-is-str", {"amendments": ["oops"]},
     "amendment entry #0"),
]
for _tag, _mut, _needle in _CASES:
    _lock = _base_lock()
    _lock.update(_mut)
    try:
        _found = _v2_lock(_lock)
        check(f"D9.2-E2E {_tag} yields a NAMED V2 finding "
              f"({_needle}), no traceback",
              any("V2 PROTOCOL-LOCK" in g and _needle in g
                  for g in _found),
              str(_found[:2])[:240])
    except Exception as e:  # noqa: BLE001
        check(f"D9.2-E2E {_tag} yields a NAMED V2 finding "
              f"({_needle}), no traceback",
              False, f"{type(e).__name__}: {e}")

for _tag, _mut, _needle in _CASES:
    _lock = _base_lock()
    _lock.update(_mut)
    try:
        _found = PF.validate_lock_global(_lock)
        check(f"D9.2-PURE validate_lock_global({_tag}) names "
              f"{_needle}, no traceback",
              any(_needle in g for g in _found),
              str(_found[:1])[:200])
    except Exception as e:  # noqa: BLE001
        check(f"D9.2-PURE validate_lock_global({_tag}) names "
              f"{_needle}, no traceback",
              False, f"{type(e).__name__}: {e}")
try:
    _found = PF.validate_lock_global(["not", "a", "dict"])
    check("D9.2-PURE validate_lock_global(non-dict lock) names the "
          "lock, no traceback",
          any("not an object" in g for g in _found),
          str(_found[:1])[:160])
except Exception as e:  # noqa: BLE001
    check("D9.2-PURE validate_lock_global(non-dict lock) names the "
          "lock, no traceback",
          False, f"{type(e).__name__}: {e}")

# --- D9 fail-closed derivation -------------------------------------------
_NOGIT = tempfile.mkdtemp(prefix="h30-nogit-")
shutil.copy2(os.path.join(FAMC, "PROTOCOL-LOCK.json"),
             os.path.join(_NOGIT, "PROTOCOL-LOCK.json"))
_T, _F = PF.protocol_tips(_NOGIT, FREEZE)
check("D9-CLOSED history outside git fails closed naming git "
      "unavailability",
      any("git unavailable" in g for g in _F), str(_F[:1])[:160])

bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH30 D9 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)
