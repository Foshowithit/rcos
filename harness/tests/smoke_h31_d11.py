#!/usr/bin/env python3
"""H31 — A12l slice D11 acceptance: lock self-authentication (P0) +
first-parent chronology (P1).

D11.1 closes the authority gap: V2 requires the on-disk
PROTOCOL-LOCK.json bytes to equal the committed experiment-HEAD
bytes (BYTE comparison, before any consumer parses the lock) and
otherwise emits the named finding
`V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json differs from committed
experiment-HEAD authority`, withholding lock-derived tips. A forged
single-edge lock and even a cosmetic reformat are refused; an
untouched clone stays green.

D11.2 stops linearizing the DAG: `_branch_seq_shas` walks
`git log --first-parent`, so a merged side-branch state never
enters the chronology (a forged side-branch chain names the node;
a genuine first-parent chain stays clean). The seven live
sequences are measured unchanged (first-parent == old walk).

Proven on throwaway clones/repos (live tree never mutated) plus
hermetic pure-function probes. Stdlib only. Prints
`H31 D11 smoke: N/N closed`; exits non-zero on any failure.
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
REPO = TOP
AUTH_FINDING = ("V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json differs from "
                "committed experiment-HEAD authority")
_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", HOME="/tmp",
            GIT_AUTHOR_NAME="s", GIT_AUTHOR_EMAIL="s@s",
            GIT_COMMITTER_NAME="s", GIT_COMMITTER_EMAIL="s@s")


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not cond else ""))


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True,
                       env=_ENV, text=True)
    assert r.returncode == 0, (args, r.stderr[:200])
    return r.stdout.strip()


def _content_sha(repo, rev, rel):
    b = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=repo,
                       capture_output=True).stdout
    return hashlib.sha256(b).hexdigest()


# --- D11.1 STATIC: authority derived in the git layer, pure fn pure ---
_SRC = open(os.path.join(FAMC, "preflight.py")).read()
check("D11.1-STATIC the lock-authority helper exists and is verified "
      "before any lock parse",
      "def _lock_authority_findings" in _SRC
      and "auth = _lock_authority_findings(fam_c_dir)" in _SRC
      and _SRC.find("auth = _lock_authority_findings(fam_c_dir)")
      < _SRC.find("lock = json.load(open(os.path.join(fam_c_dir,")
      and "HEAD:" in _SRC)


def _vfc_calls():
    vfc = next(n for n in ast.walk(ast.parse(_SRC))
               if isinstance(n, ast.FunctionDef)
               and n.name == "validate_file_chain")
    out = []
    for node in ast.walk(vfc):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.append(f.id)
            elif isinstance(f, ast.Attribute):
                base = f.value.id if isinstance(f.value, ast.Name) else "?"
                out.append(f"{base}.{f.attr}")
    args = [a.arg for a in vfc.args.args]
    return vfc, ast.dump(vfc), out, args


_VFC, _VFC_DUMP, _VFC_CALLS, _VFC_ARGS = _vfc_calls()
check("D11.1-STATIC validate_file_chain takes the lock verdict in "
      "exactly like branch_seq and stays pure and I/O-free",
      "lock_authority_ok" in _VFC_ARGS
      and "branch_seq" in _VFC_ARGS
      and not [c for c in _VFC_CALLS
               if c in ("open", "subprocess.run",
                        "subprocess.check_output")
               or c.startswith(("os.", "io.", "pathlib."))]
      and "subprocess" not in _VFC_DUMP
      and "os." not in _VFC_DUMP
      and "_lock_authority_findings" not in
      [c for c in _VFC_CALLS])
check("D11.1-STATIC no `--all` anywhere in benchmarks/fam-c/preflight.py",
      "--all" not in _SRC)

# --- D11.1 LIVE: byte authority holds on the committed tree ------------
_LIVE_LOCK_SHA = _sha_file(os.path.join(FAMC, "PROTOCOL-LOCK.json"))
_HEAD_LOCK = subprocess.run(
    ["git", "show", "HEAD:benchmarks/fam-c/PROTOCOL-LOCK.json"],
    cwd=TOP, capture_output=True).stdout
check("D11.1-LIVE on-disk lock bytes == committed experiment-HEAD "
      "bytes",
      hashlib.sha256(_HEAD_LOCK).hexdigest() == _LIVE_LOCK_SHA)
_V2_LIVE = [f for f in PF.validate_protocol(FAMC, FREEZE)
            if f.startswith("V2")]
check("D11.1-LIVE the live lock stays V2 green", _V2_LIVE == [],
      str(_V2_LIVE[:1])[:200])

# --- D11.1 CLONE FORGES: refused with the exact named finding ---------
_BASE = tempfile.mkdtemp(prefix="h31-")


def _clone(tag):
    dst = os.path.join(_BASE, tag)
    r = subprocess.run(["git", "clone", "-q", REPO, dst],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:200]
    return dst


def _forge_single_edge(repo):
    lp = os.path.join(repo, "benchmarks", "fam-c", "PROTOCOL-LOCK.json")
    lock = json.load(open(lp))
    root = lock["governed"]["PREREG.md"]
    tip = _content_sha(repo, "HEAD", "benchmarks/fam-c/PREREG.md")
    entries = [a for a in lock["amendments"] if a.get("file") == "PREREG.md"]
    keep = [a for a in lock["amendments"] if a.get("file") != "PREREG.md"]
    forged = dict(entries[-1])
    forged.update({"from_sha": root, "to_sha": tip,
                   "reason": "h31: single forged edge",
                   "slice": "h31-d11"})
    lock["amendments"] = keep + [forged]
    json.dump(lock, open(lp, "w"), indent=2, sort_keys=True)


_C1 = _clone("forge")
_forge_single_edge(_C1)
_F1 = [f for f in PF.validate_protocol(
    os.path.join(_C1, "benchmarks", "fam-c"), FREEZE)
    if f.startswith("V2")]
check("D11.1-E2E forged single-edge lock refused with the exact "
      "lock-authority finding",
      AUTH_FINDING in _F1, str(_F1[:2])[:240])

_C2 = _clone("reformat")
_lp2 = os.path.join(_C2, "benchmarks", "fam-c", "PROTOCOL-LOCK.json")
json.dump(json.load(open(_lp2)), open(_lp2, "w"), indent=4)
_F2 = [f for f in PF.validate_protocol(
    os.path.join(_C2, "benchmarks", "fam-c"), FREEZE)
    if f.startswith("V2")]
check("D11.1-E2E cosmetic lock reformat refused (BYTE authority, "
      "not semantic equality)",
      AUTH_FINDING in _F2, str(_F2[:2])[:240])

_C3 = _clone("clean")
_F3 = [f for f in PF.validate_protocol(
    os.path.join(_C3, "benchmarks", "fam-c"), FREEZE)
    if f.startswith("V2")]
check("D11.1-E2E untouched clone stays V2 green (control)", _F3 == [],
      str(_F3[:1])[:200])

# --- D11.1 PURE: the verdict threads through the pure function --------
_HA, _HB = "aa" * 32, "bb" * 32
_AMS = [{"file": "PREREG.md", "from_sha": _HA, "to_sha": _HB}]
_FF, _TT = PF.validate_file_chain("PREREG.md", _HA, _AMS, _HB, _HA,
                                  [_HA, _HB], False)
check("D11.1-PURE lock_authority_ok=False refuses with the exact "
      "finding and no tip",
      _FF == [AUTH_FINDING] and _TT is None, str(_FF[:1])[:160])
_FT, _TT2 = PF.validate_file_chain("PREREG.md", _HA, _AMS, _HB, _HA,
                                   [_HA, _HB], True)
_FN, _TT3 = PF.validate_file_chain("PREREG.md", _HA, _AMS, _HB, _HA,
                                   [_HA, _HB])
check("D11.1-PURE lock_authority_ok=True/None leave the chain "
      "verdict to the chain (control)",
      _FT == [] and _TT2 == _HB and _FN == [] and _TT3 == _HB,
      str((_FT, _FN))[:160])

# No committed counterpart (synthetic hermetic path) means no
# authority to violate: the helper yields [] and the chain rules
# still judge the bytes on their merits.
_MINI = tempfile.mkdtemp(prefix="h31-mini-")
subprocess.run(["git", "init", "-q", _MINI], capture_output=True,
               env=_ENV)
open(os.path.join(_MINI, "note.txt"), "w").write("x\n")
_GMINI = lambda *a: _git(_MINI, *a)  # noqa: E731
_GMINI("add", "-A")
_GMINI("commit", "-qm", "seed")
os.makedirs(os.path.join(_MINI, "sub"))
shutil.copy2(os.path.join(FAMC, "PROTOCOL-LOCK.json"),
             os.path.join(_MINI, "sub", "PROTOCOL-LOCK.json"))
check("D11.1-PURE untracked lock path has no committed authority "
      "to violate (helper yields [], chain rules still apply)",
      PF._lock_authority_findings(os.path.join(_MINI, "sub")) == [])

# --- D11.1 GOVERNANCE: append-only-forward policy + lineage -----------
_LIVE_LOCK = json.load(open(os.path.join(FAMC, "PROTOCOL-LOCK.json")))
check("D11.1-GOV the append-only-forward lock policy is documented "
      "in PREREG.md",
      "append-only" in open(os.path.join(FAMC, "PREREG.md")).read()
      and "committed with the" in
      open(os.path.join(FAMC, "PREREG.md")).read())
check("D11.1-GOV no amendment entry deleted (35 at D10 + 10 D11 "
      "+ 1 D12 forward = 46) and D11+D12 recorded as forward amendments",
      len(_LIVE_LOCK["amendments"]) == 46
      and sum(1 for a in _LIVE_LOCK["amendments"]
              if a.get("slice") == "a12l-slice-d11") == 10
      and sum(1 for a in _LIVE_LOCK["amendments"]
              if a.get("slice") == "a12n-slice-d12") == 1,
      str(len(_LIVE_LOCK["amendments"])))

# --- D11.1-HISTORY: append-only genesis (delete/edit old entries) ----
import re as _re


def _anchor_ok():
    for fp in (os.path.join(FAMC, "preflight.py"),
               os.path.join(FAMC, "PREREG.md")):
        blob = open(fp, encoding="utf-8").read()
        m = _re.search(r"PROTOCOL_LOCK_APPEND_ONLY_GENESIS(.{0,400})",
                       blob, _re.S)
        seg = m.group(1) if m else ""
        if ("PROTOCOL_LOCK_APPEND_ONLY_GENESIS" in blob
                and _re.search(r"\b[0-9a-f]{40}\b", seg)
                and _re.search(r"\b[0-9a-f]{64}\b", seg)):
            return True
    return False


check("D11.1-HISTORY append-only genesis anchor frozen outside the "
      "lock (commit + lock sha256)", _anchor_ok())


def _history_attack(tag, mutate):
    c = _clone("hist-" + tag)
    lp = os.path.join(c, "benchmarks", "fam-c", "PROTOCOL-LOCK.json")
    lock = json.load(open(lp))
    am = lock["amendments"]
    idx = next(i for i, a in enumerate(am)
               if a.get("file") == "PREREG.md")
    if mutate == "delete":
        del am[idx]
    else:
        am[idx]["reason"] = am[idx].get("reason", "") + " (edited)"
    json.dump(lock, open(lp, "w"), indent=2, sort_keys=True)
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "lock history attack")
    fnd = [f for f in PF.validate_protocol(
        os.path.join(c, "benchmarks", "fam-c"), FREEZE)
        if f.startswith("V2")]
    return (bool(fnd) and any(w in " ".join(fnd).lower()
                              for w in ("append", "prefix", "history",
                                        "genesis", "immutable")), fnd)


_ok_del, _f_del = _history_attack("delete", "delete")
check("D11.1-HISTORY deleting an old amendment entry after genesis "
      "is a named lock-history finding", _ok_del, str(_f_del[:1])[:200])
_ok_ed, _f_ed = _history_attack("edit", "edit")
check("D11.1-HISTORY editing an old amendment entry after genesis "
      "is a named lock-history finding", _ok_ed, str(_f_ed[:1])[:200])


def _history_reorder():
    # The auditor's exact-prefix attack: swap the positions of two old
    # entries from DIFFERENT files. Every canonical dict and every
    # from/to link survives (multiset identical), but the genesis
    # prefix no longer matches elementwise.
    c = _clone("hist-reorder")
    lp = os.path.join(c, "benchmarks", "fam-c", "PROTOCOL-LOCK.json")
    lock = json.load(open(lp))
    am = lock["amendments"]
    i = next(i for i, a in enumerate(am)
             if a.get("file") == "PREREG.md")
    j = next(j for j, a in enumerate(am)
             if a.get("file") == "preflight.py")
    assert i != j
    am[i], am[j] = am[j], am[i]
    json.dump(lock, open(lp, "w"), indent=2, sort_keys=True)
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "lock history reorder attack")
    fnd = [f for f in PF.validate_protocol(
        os.path.join(c, "benchmarks", "fam-c"), FREEZE)
        if f.startswith("V2")]
    return (bool(fnd) and any(w in " ".join(fnd).lower()
                              for w in ("prefix", "reordered")), fnd)


_ok_re, _f_re = _history_reorder()
check("D11.1-HISTORY reordering old entries after genesis is a "
      "named lock-history finding (exact prefix)", _ok_re,
      str(_f_re[:1])[:200])


def _history_untrack_attack():
    # The untrack variant: reorder two old entries, then remove the
    # governed lock from the index and commit the removal. The
    # worktree lock is forged but has no committed counterpart, so
    # the byte authority skips — the history rule must still refuse
    # (canonical governed path, genesis resolvable in the clone).
    c = _clone("hist-untrack")
    lp = os.path.join(c, "benchmarks", "fam-c", "PROTOCOL-LOCK.json")
    lock = json.load(open(lp))
    am = lock["amendments"]
    i = next(i for i, a in enumerate(am)
             if a.get("file") == "PREREG.md")
    j = next(j for j, a in enumerate(am)
             if a.get("file") == "preflight.py")
    am[i], am[j] = am[j], am[i]
    json.dump(lock, open(lp, "w"), indent=2, sort_keys=True)
    _git(c, "rm", "--cached", "-q", "benchmarks/fam-c/PROTOCOL-LOCK.json")
    _git(c, "commit", "-qm", "untrack the governed lock")
    fnd = [f for f in PF.validate_protocol(
        os.path.join(c, "benchmarks", "fam-c"), FREEZE)
        if f.startswith("V2")]
    return (bool(fnd) and any(w in " ".join(fnd).lower()
                              for w in ("untracked", "lineage", "append")),
            fnd)


_ok_un, _f_un = _history_untrack_attack()
check("D11.1-HISTORY reordered + untracked governed lock refused "
      "with a named untracked-lineage finding", _ok_un,
      str(_f_un[:1])[:200])


def _history_post_genesis(mutate):
    # Post-genesis holes: swap (HOLE A) or rewrite (HOLE B) two
    # entries appended AFTER the genesis checkpoint (positions 37
    # and 38 on the 44-entry lock: a PREREG.md / preflight.py pair).
    # The genesis prefix survives intact, so only the
    # consecutive-pair walk can catch it.
    c = _clone("hist-postgen-" + mutate)
    lp = os.path.join(c, "benchmarks", "fam-c", "PROTOCOL-LOCK.json")
    lock = json.load(open(lp))
    am = lock["amendments"]
    assert len(am) >= 40, len(am)
    if mutate == "reorder":
        assert am[37].get("file") != am[38].get("file"), \
            (am[37].get("file"), am[38].get("file"))
        am[37], am[38] = am[38], am[37]
    else:
        last_pre = max(i for i, a in enumerate(am)
                       if a.get("file") == "PREREG.md")
        am[last_pre]["reason"] = (am[last_pre].get("reason", "")
                                  + " (post-genesis rewrite)")
    json.dump(lock, open(lp, "w"), indent=2, sort_keys=True)
    _git(c, "add", "-A")
    _git(c, "commit", "-qm", "post-genesis lock attack " + mutate)
    fnd = [f for f in PF.validate_protocol(
        os.path.join(c, "benchmarks", "fam-c"), FREEZE)
        if f.startswith("V2")]
    return (bool(fnd) and any(w in " ".join(fnd).lower()
                              for w in ("append", "prefix", "history",
                                        "genesis", "immutable", "commit")),
            fnd)


_ok_pa, _f_pa = _history_post_genesis("reorder")
check("D11.1-HISTORY post-genesis reorder refused with a named "
      "lock-history finding", _ok_pa, str(_f_pa[:1])[:200])
_ok_pb, _f_pb = _history_post_genesis("rewrite")
check("D11.1-HISTORY post-genesis rewrite refused with a named "
      "lock-history finding", _ok_pb, str(_f_pb[:1])[:200])


def _history_genesisless():
    # Synthetic repo whose history does NOT contain the genesis
    # commit, canonical layout, lock UNTRACKED: both the byte
    # authority and the history rule stay silent (nothing to anchor
    # to); fixtures are unaffected.
    r = os.path.join(_BASE, "genesisless")
    os.makedirs(os.path.join(r, "benchmarks", "fam-c"), exist_ok=True)
    famc = os.path.join(r, "benchmarks", "fam-c")
    open(os.path.join(famc, "PREREG.md"), "w").write("genesisless\n")
    shutil.copy2(os.path.join(FAMC, "FREEZE.json"),
                 os.path.join(famc, "FREEZE.json"))
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "synthetic freeze")
    disk = _sha_file(os.path.join(famc, "PREREG.md"))
    json.dump({"freeze_commit": FREEZE,
               "governed": {"PREREG.md": disk},
               "amendments": []},
              open(os.path.join(famc, "PROTOCOL-LOCK.json"), "w"))
    return (PF._lock_authority_findings(famc) == []
            and PF.validate_lock_history(famc) == [])


check("D11.1-HISTORY genesis-less synthetic repo with untracked "
      "canonical lock stays silent (fixtures unaffected)",
      _history_genesisless())
_V2_APPEND = [f for f in PF.validate_protocol(FAMC, FREEZE)
              if f.startswith("V2")]
check("D11.1-HISTORY control: pure append (live shape) stays V2 "
      "green", _V2_APPEND == [], str(_V2_APPEND[:1])[:200])

# --- D11.2 STATIC: first-parent walk -----------------------------------
_BSS = next(n for n in ast.walk(ast.parse(_SRC))
            if isinstance(n, ast.FunctionDef)
            and n.name == "_branch_seq_shas")
check("D11.2-STATIC the chronology walk is first-parent",
      "--first-parent" in ast.dump(_BSS))

# --- D11.2 DAG: a side-branch state never enters the chronology -------
_DAG = os.path.join(_BASE, "dag")
os.makedirs(os.path.join(_DAG, "benchmarks", "fam-c"), exist_ok=True)
_REL = "benchmarks/fam-c/PREREG.md"


def _w(txt):
    with open(os.path.join(_DAG, _REL), "w") as f:
        f.write(txt + "\n")


_GDAG = lambda *a: _git(_DAG, *a)  # noqa: E731
_GDAG("init", "-q")
for _msg, _txt in (("R", "v0"), ("A", "v1"), ("B", "v2")):
    _w(_txt)
    _GDAG("add", "-A")
    _GDAG("commit", "-qm", _msg)
_GDAG("checkout", "-qb", "side")
_w("vX")
_GDAG("commit", "-qam", "X")
_GDAG("checkout", "-q", "master")
_w("v2b")
_GDAG("commit", "-qam", "E")
subprocess.run(["git", "merge", "-q", "side", "-m", "M"], cwd=_DAG,
               capture_output=True, env=_ENV)
_w("vM")
_GDAG("add", "-A")
_GDAG("commit", "-qm", "M (resolved to a third state)")
_w("vC")
_GDAG("commit", "-qam", "C")
_DSHAS = {}
for _rev in subprocess.run(["git", "rev-list", "--all"], cwd=_DAG,
                           capture_output=True, text=True).stdout.split():
    _t = subprocess.run(["git", "show", f"{_rev}:{_REL}"], cwd=_DAG,
                        capture_output=True).stdout
    _DSHAS[_t.decode().strip()] = hashlib.sha256(_t).hexdigest()
_DSEQ = PF._branch_seq_shas(_DAG, _REL)
_VX = _DSHAS["vX"]
check("D11.2-E2E derived chronology excludes the side-branch state",
      _VX not in _DSEQ, f"vX_in_seq={_VX in _DSEQ} n={len(_DSEQ)}")
_V0, _V2B, _VC = _DSHAS["v0"], _DSHAS["v2b"], _DSHAS["vC"]
_FF2, _ = PF.validate_file_chain(
    "PREREG.md", _V0,
    [{"file": "PREREG.md", "from_sha": _V0, "to_sha": _VX,
      "reason": "h31", "slice": "h31-d11"},
     {"file": "PREREG.md", "from_sha": _VX, "to_sha": _VC,
      "reason": "h31", "slice": "h31-d11"}],
    _VC, _V0, branch_seq=_DSEQ)
check("D11.2-E2E forged side-branch chain refused naming the node",
      bool(_FF2) and any(_VX[:12] in f for f in _FF2), str(_FF2[:1])[:200])
_FG2, _ = PF.validate_file_chain(
    "PREREG.md", _V0,
    [{"file": "PREREG.md", "from_sha": _V0, "to_sha": _V2B,
      "reason": "h31", "slice": "h31-d11"},
     {"file": "PREREG.md", "from_sha": _V2B, "to_sha": _VC,
      "reason": "h31", "slice": "h31-d11"}],
    _VC, _V0, branch_seq=_DSEQ)
check("D11.2-E2E genuine first-parent chain stays clean (control)",
      not _FG2, str(_FG2[:1])[:200])

# --- D11.2 LIVE: non-regression measurement -----------------------------


def _plain_seq(fn):
    commits = subprocess.run(
        ["git", "log", "--format=%H", "--", f"benchmarks/fam-c/{fn}"],
        cwd=TOP, capture_output=True, text=True).stdout.split()
    seq = []
    for c in reversed(commits):
        raw = subprocess.run(
            ["git", "show", f"{c}:benchmarks/fam-c/{fn}"], cwd=TOP,
            capture_output=True).stdout
        h = hashlib.sha256(raw).hexdigest()
        if not seq or seq[-1] != h:
            seq.append(h)
    return seq


_BAD, _LENS = [], {}
for _fn in PF.PROTOCOL_GOVERNED:
    _live = PF._branch_seq_shas(TOP, f"benchmarks/fam-c/{_fn}")
    _LENS[_fn] = len(_live)
    if _live != _plain_seq(_fn):
        _BAD.append(_fn)
check("D11.2-LIVE first-parent sequences equal the old walk for all "
      "seven governed files (non-regression)",
      not _BAD, f"diverged={_BAD}")
check("D11.2-LIVE live sequence lengths match the certified D11 "
      "facts (PREREG 23, preflight 24, rest 5/5/12/1/7)",
      _LENS == {"PREREG.md": 23, "ORDER.md": 5, "LANES.md": 5,
                "HARNESS-READINESS.md": 12, "preflight.py": 24,
                "T4-SEMANTIC-IDS.json": 1, "T4-CONFORMANCE.json": 7},
      str(_LENS))

# --- D11.4-PROD: the production runner binds the constructed
# snapshot to an independently derived expected snapshot ---------
import io as _io
import tokenize as _tk


def _code_only(_src):
    try:
        _toks = list(_tk.generate_tokens(_io.StringIO(_src).readline))
    except Exception:  # noqa: BLE001
        return _src
    return " ".join(t.string for t in _toks
                    if t.type not in (_tk.COMMENT, _tk.STRING,
                                     _tk.NL, _tk.NEWLINE))


_RUNNER = os.path.join(FAMC, "harness-run",
                       "run_arm_h1.py")
_RTXT = open(_RUNNER, encoding="utf-8").read()
_RHITS = []
for _node in ast.walk(ast.parse(_RTXT)):
    if not isinstance(_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    _seg = ast.get_source_segment(_RTXT, _node) or ""
    _code = _code_only(_seg)
    if ("DockerSandbox" in _code and "(" in _code
            and "task_snapshot" in _code
            and _re.search(r"(expected|frozen|authorized)\w*_snapshot",
                           _code, _re.I)
            and ("raise" in _code or "PermissionError" in _code)):
        _RHITS.append(_node.name)
check("D11.4-PROD the production runner binds the constructed "
      "snapshot to an independently derived expected snapshot "
      "and refuses before jail use",
      bool(_RHITS), str(_RHITS[:2]))

# --- D11.4-ABA: the auditor's acceptance — the READER is
# monkeypatched so source_before == source_after == staged ==
# quiescence == H (every internal read agrees), while the expected
# value is E != H: the constructor must still DENY with
# SNAPSHOT-DENY before any jail use (no docker needed: refusal
# happens in __init__ before any mount). Control: E == H
# constructs with exact identity. Legacy: expected None behaves
# as before (quiescence path only, constructs).
sys.path.insert(0, HARNESS)
import dockersandbox as _dsmod  # noqa: E402


def _aba_src(tag):
    import shutil as _sh
    src = os.path.join("/tmp/rcos-visible", "h31-" + tag)
    _sh.rmtree(src, ignore_errors=True)
    os.makedirs(src, exist_ok=True)
    open(os.path.join(src, "x.txt"), "w").write("0\n")
    open(os.path.join(src, "y.txt"), "w").write("1\n")
    w = os.path.join("/tmp/rcos-runs", "h31-" + tag, "work")
    os.makedirs(w, exist_ok=True)
    return src, w


_ABA_SRC, _ABA_W = _aba_src("aba")
_H_REAL = _dsmod._hash_tree(_ABA_SRC)
_E_FORCED = dict(_H_REAL)
_E_FORCED["file|x.txt"] = "0" * 64
_REAL_HASH_TREE = _dsmod._hash_tree
_dsmod._hash_tree = lambda _top: dict(_H_REAL)  # noqa: E731
try:
    try:
        _dsmod.DockerSandbox(_ABA_W, _ABA_SRC, _E_FORCED)
        _aba_denied = False
    except PermissionError as _e:
        _aba_denied = "SNAPSHOT-DENY" in str(_e)
    check("D11.4-ABA forced H != E refused with SNAPSHOT-DENY even "
          "though every patched internal read agrees on H",
          _aba_denied)
    try:
        _sb_aba = _dsmod.DockerSandbox(_ABA_W, _ABA_SRC, dict(_H_REAL))
        _aba_good = (_sb_aba.task_snapshot == _H_REAL)
    except PermissionError:
        _aba_good = False
    check("D11.4-ABA matching expected snapshot constructs with exact "
          "identity (control)", _aba_good)
    try:
        _sb_legacy = _dsmod.DockerSandbox(_ABA_W, _ABA_SRC)
        _aba_legacy = (_sb_legacy.task_snapshot == _H_REAL)
    except PermissionError:
        _aba_legacy = False
    check("D11.4-ABA expected None keeps legacy behavior "
          "(constructs, quiescence path only)", _aba_legacy)
finally:
    _dsmod._hash_tree = _REAL_HASH_TREE

# --- D11.4-FROZEN: the authority is frozen bytes, not a fresh walk.
# Derive a frozen manifest from a source dir, then MUTATE the source:
# the constructor's own reads now agree on the mutated state, but
# the frozen manifest still refuses with SNAPSHOT-DENY.
_FZ_SRC, _FZ_W = _aba_src("frozen")
_FZ_E = _dsmod._hash_tree(_FZ_SRC)
open(os.path.join(_FZ_SRC, "x.txt"), "w").write("MUTATED\n")
open(os.path.join(_FZ_SRC, "y.txt"), "w").write("MUTATED\n")
try:
    _dsmod.DockerSandbox(_FZ_W, _FZ_SRC, dict(_FZ_E))
    _fz_denied = False
except PermissionError as _e:
    _fz_denied = "SNAPSHOT-DENY" in str(_e)
check("D11.4-FROZEN frozen manifest refuses post-freeze mutation "
      "even though constructor reads agree on mutated state",
      _fz_denied)

shutil.rmtree(_BASE, ignore_errors=True)
shutil.rmtree(_MINI, ignore_errors=True)
bad = [n for n, ok_ in RESULTS if not ok_]
print(f"\nH31 D11 smoke: {len(RESULTS) - len(bad)}/{len(RESULTS)} closed")
sys.exit(1 if bad else 0)
