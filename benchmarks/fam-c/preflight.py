#!/usr/bin/env python3
"""Fam-C three-authority preflight (round-2 item 4, option b — no re-freeze).

Three INDEPENDENT validators, each green on its own authority. Exit 0 =
all green, 1 = findings (each finding names its authority). Importable:
`validate_all(fam_c_dir)` returns findings without exiting, so the runner
refuses to start on any lock failure before any model token is spent.
A12c C1-2 (auditor P0 #7): V2 additionally enforces exact
T4-SEMANTIC-IDS.json <-> PREREG set equality, so a wrong registry
refuses here — naming the offending id — before any model call.
A12c slice C2 (auditor P0 #6): V2 additionally enforces the frozen
limitation->T4-id bridge — T4-CONFORMANCE.json must exist and satisfy
every refusal condition, or nothing runs.

  V1 INSTANCE-FREEZE — the frozen instance bytes (families/** task inputs,
      checkers, truth + frozen meta STAGED.md/FAMILIES.md) are byte-identical
      to FREEZE-HASHES.sha256 RESOLVED FROM the freeze commit via git (the
      working-tree copy is never trusted). Freeze-commit ancestry of HEAD
      is also proved (history-rewrite detection).
  V2 PROTOCOL-LOCK — the living protocol docs (PREREG/ORDER/LANES/
      HARNESS-READINESS + this validator) match EITHER their frozen bytes
      OR an explicit forward amendment recorded in PROTOCOL-LOCK.json.
      Unlisted drift fails this lock (never a silent substitution).
      A12d slice D7: the amendments per governed file must form ONE
      linear path from the frozen (or post-freeze genesis) node to
      exactly one tip, and the on-disk bytes must equal that tip
      (validate_file_chain; the old reachable-set is deleted).
      A12i slice D9: that recorded path must additionally be a
      SUBSEQUENCE of the file's committed content states on the
      experiment branch (Rule A lineage membership + Rule B
      chronology; the old all-refs retrievability test is deleted).
      A12l slice D11.1: the lock authenticates ITSELF first — the
      on-disk PROTOCOL-LOCK.json bytes must equal the committed
      experiment-HEAD bytes (byte comparison, before any consumer
      parses the lock), else the named finding
      `V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json differs from committed
      experiment-HEAD authority`, with lock-derived tips withheld.
      A12l slice D11.2: the branch walk is first-parent (a merged
      side-branch state is never experiment chronology); measured
      identical to the old walk for all seven governed files.
  V3 EXECUTION-LOCK — the executing harness bytes (8 modules + runner)
      match EXECUTION-LOCK.json. Status rides along: `open-round2`
      (placeholder, re-minted on every harness change) until round-2 #14
      mints the FINAL lock after items 1-13 + synthetic attack.

Meta files (FREEZE.json, FREEZE-HASHES.sha256, *-LOCK.json, AUDIT-*,
FAMC-EXECUTION-STATUS.md, ORDER-EXPANSION.json) are pinned by git history
+ the lock records, not by the content manifest. Operational dirs (runs/,
capabilities/, harness-run/) hold evidence/artifacts/tooling, never
freeze inputs.
"""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), os.pardir, "harness"))
from admissibility import (frozen_manifest_bytes, verify_freeze_tree,
                           load_freeze)
from order import verify_expansion as order_verify_expansion
import t4_ids
import conformance

FREEZE_COMMIT = "d1292434a261f44ad910c556e18624cef1676f37"

# Protocol docs with a life after the freeze: frozen bytes OR a listed
# forward amendment, never unlisted drift.
PROTOCOL_GOVERNED = ["PREREG.md", "ORDER.md", "LANES.md",
                     "HARNESS-READINESS.md", "preflight.py",
                     "T4-SEMANTIC-IDS.json", "T4-CONFORMANCE.json"]
# Meta pointers: integrity rides on git history + lock records.
META = {"FREEZE.json", "FREEZE-HASHES.sha256", "PROTOCOL-LOCK.json",
        "EXECUTION-LOCK.json", "FAMC-EXECUTION-STATUS.md",
        "AUDIT-ROUND1.md", "AUDIT-ROUND1-REPLY.txt",
        "AUDIT-ROUND2.md", "AUDIT-ROUND2-REPLY.txt",
        "AUDIT-ROUND3-REPLY.txt", "AUDIT-ROUND3-A11-REPLY.txt",
        "ORDER-EXPANSION.json"}
OPERATIONAL_DIRS = {"runs", "capabilities", "harness-run"}


def _sha(fp):
    with open(fp, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _git(args, cwd):
    try:
        p = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                           text=True)
    except FileNotFoundError:
        raise RuntimeError("git binary not found")
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           + (p.stderr or p.stdout).strip()[:200])
    return p.stdout.strip()


def validate_instance(fam_c_dir, freeze_commit):
    """V1 INSTANCE-FREEZE. Returns findings list (empty = green)."""
    out = []
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
        _git(["merge-base", "--is-ancestor", freeze_commit, "HEAD"],
             cwd=root)
    except RuntimeError as e:
        return [f"V1 INSTANCE-FREEZE: ancestry unprovable: {e}"]
    try:
        raw = frozen_manifest_bytes(fam_c_dir, freeze_commit).decode()
    except RuntimeError as e:
        return [f"V1 INSTANCE-FREEZE: {e}"]
    manifest = {}
    for line in raw.splitlines():
        line = line.strip()
        if line:
            h, p = line.split("  ", 1)
            manifest[p] = h
    governed = set(PROTOCOL_GOVERNED)
    for p, h in sorted(manifest.items()):
        if p in governed:
            continue  # living protocol doc: V2 authority owns this path
        fp = os.path.join(fam_c_dir, p)
        if not os.path.exists(fp):
            out.append(f"V1 INSTANCE-FREEZE: frozen file missing: {p}")
        elif _sha(fp) != h:
            out.append(f"V1 INSTANCE-FREEZE: hash mismatch vs frozen "
                       f"manifest: {p}")
    on_disk = set()
    for root, dirs, files in os.walk(fam_c_dir):
        if os.path.basename(root) in OPERATIONAL_DIRS:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if fn.endswith(".pyc"):
                continue  # interpreter bytecode cache, never freeze input
            rel = os.path.relpath(os.path.join(root, fn), fam_c_dir)
            if rel in META or rel in governed:
                continue
            on_disk.add(rel)
    for p in sorted(on_disk - set(manifest)):
        out.append(f"V1 INSTANCE-FREEZE: extra file not in freeze "
                   f"manifest: {p}")
    for p in sorted(set(manifest) - on_disk - governed):
        out.append(f"V1 INSTANCE-FREEZE: freeze-manifest file missing on "
                   f"disk: {p}")
    return out


# A12d slice D8.2: a recorded node sha is well-formed only as
# 64-lowercase-hex (a genesis from_sha is the sole null allowed).
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# A12l slice D11.1, append-only history checkpoint. The D11
# authority commit is the genesis from which lock history is
# immutable: every older amendment entry must survive verbatim in
# every later lock (new entries may only be appended).
# PROTOCOL_LOCK_APPEND_ONLY_GENESIS
# beceff56cb10a4449e53cb35e2b21fd1b3d94cc6
# 21d9f79d9255d53771027b645ad5fb44076c72b4c999b06dec97131fac48183f
# (genesis commit, then sha256 of its PROTOCOL-LOCK.json bytes;
# the same anchor is recorded in the PREREG D11 stanza).
_GENESIS_COMMIT = "beceff56cb10a4449e53cb35e2b21fd1b3d94cc6"
_GENESIS_LOCK_SHA256 = \
    "21d9f79d9255d53771027b645ad5fb44076c72b4c999b06dec97131fac48183f"


def _lock_authority_findings(fam_c_dir):
    """A12l slice D11.1 (auditor D9-post P0): the lock authenticates
    itself. Git-aware helper (I/O belongs here, never in
    validate_file_chain): requires the on-disk PROTOCOL-LOCK.json
    bytes to equal the committed experiment-HEAD bytes
    (`git show HEAD:<rel>`), by BYTE comparison, not semantic
    equality (even a cosmetic reformat refuses). Returns the single
    named finding on mismatch, else [].

    No committed counterpart (the lock path is untracked at HEAD,
    e.g. a synthetic hermetic fixture dir) means there is no
    authority to violate: [] (the chain/global rules below still
    evaluate the bytes on their merits). A missing lock, an
    unreadable lock, or an unusable git binary likewise yields []
    here — the missing/unparsable/git-unavailable paths below own
    those findings. Callers run this BEFORE parsing the lock and
    withhold lock-derived tips on mismatch (see protocol_tips), so
    a forged worktree lock can never certify tips; every production
    entry (CLI, validate_all via validate_protocol) refuses start
    on any V2 finding, and the full component diagnostics are still
    collected so each refusal names its own defect.
    """
    lp = os.path.join(fam_c_dir, "PROTOCOL-LOCK.json")
    if not os.path.exists(lp):
        return []
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
    except RuntimeError:
        return []
    rel = os.path.relpath(os.path.abspath(lp), root)
    try:
        proc = subprocess.run(["git", "show", f"HEAD:{rel}"],
                              cwd=root, capture_output=True)
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    try:
        with open(lp, "rb") as f:
            disk = f.read()
    except OSError:
        return []
    if hashlib.sha256(disk).hexdigest() != \
            hashlib.sha256(proc.stdout).hexdigest():
        return ["V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json differs from "
                "committed experiment-HEAD authority"]
    return []


def validate_lock_history(fam_c_dir):
    """A12l slice D11.1, append-only history (git-aware; never raises:
    every parse is guarded, so malformed locks still yield the
    container findings, never a traceback). Returns findings.

    From the genesis checkpoint above, lock history is immutable:
    the genesis amendment multiset must survive verbatim in the
    current lock (later slices only APPEND entries), and every
    genesis governed root must survive unmoved. Deleting or
    rewriting an old entry — even with the lock re-committed, so
    the byte authority passes — fails here with a named
    lock-history finding (append-only genesis violated).

    Scope: the check applies only where the genesis resolves in
    the enclosing history AND the lock is bound to the live
    instance freeze. Synthetic hermetic universes (their own
    freeze, or no genesis in history) have no anchor to violate:
    [] there, while the chain/global rules still judge their
    bytes on the merits.
    """
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
    except RuntimeError:
        return []
    try:
        proc = subprocess.run(
            ["git", "show",
             f"{_GENESIS_COMMIT}:benchmarks/fam-c/PROTOCOL-LOCK.json"],
            cwd=root, capture_output=True)
    except FileNotFoundError:
        return []
    if proc.returncode != 0:
        return []
    if hashlib.sha256(proc.stdout).hexdigest() != _GENESIS_LOCK_SHA256:
        return ["V2 PROTOCOL-LOCK: lock history violates append-only "
                "genesis " + _GENESIS_COMMIT[:12] + " (the genesis lock "
                "bytes do not match the checkpoint; history rewritten?)"]
    try:
        live_freeze = load_freeze(fam_c_dir)["freeze_commit"]
    except Exception:  # noqa: BLE001 - hermetic dir without FREEZE.json
        return []
    try:
        cur = json.load(open(os.path.join(fam_c_dir,
                                          "PROTOCOL-LOCK.json")))
    except (ValueError, OSError):
        return []
    if not isinstance(cur, dict):
        return []
    if cur.get("freeze_commit") != live_freeze:
        return []
    try:
        gen = json.loads(proc.stdout.decode())
    except ValueError:
        return []
    if not isinstance(gen, dict):
        return []

    def _canon(a):
        return json.dumps(a, sort_keys=True)

    want, have = {}, {}
    gen_am = gen.get("amendments")
    cur_am = cur.get("amendments")
    for a in gen_am if isinstance(gen_am, list) else []:
        if isinstance(a, dict):
            k = _canon(a)
            want[k] = want.get(k, 0) + 1
    for a in cur_am if isinstance(cur_am, list) else []:
        if isinstance(a, dict):
            k = _canon(a)
            have[k] = have.get(k, 0) + 1
    missing = sum(n - have.get(k, 0) for k, n in want.items()
                  if have.get(k, 0) < n)
    gen_gov = gen.get("governed")
    cur_gov = cur.get("governed")
    moved = 0
    if isinstance(gen_gov, dict) and isinstance(cur_gov, dict):
        moved = sum(1 for k, v in gen_gov.items() if cur_gov.get(k) != v)
    elif isinstance(gen_gov, dict):
        moved = len(gen_gov)
    if missing or moved:
        return ["V2 PROTOCOL-LOCK: lock history violates append-only "
                "genesis " + _GENESIS_COMMIT[:12] + f" ({missing} old "
                f"amendment entr{'y' if missing == 1 else 'ies'} "
                f"removed or rewritten, {moved} governed roots moved; "
                f"old entries are immutable — append new entries, never "
                f"rewrite history)"]
    return []


def validate_lock_global(lock):
    """A12d slice D8.2: lock-global hygiene (pure function of the lock
    bytes — no git, no disk reads). Returns findings (empty = green);
    every finding names the offending key or file literally.

    The `governed` key set must be EXACTLY the seven
    PROTOCOL_GOVERNED files (an extra key such as TYPO.md fails), and
    every amendment entry's `file` must name a governed file (a
    TYPO.md, missing, or None file fails).

    A12i slice D9.2: malformed containers fail closed with a named
    finding, never a traceback. A non-object lock, a non-object
    `governed`, or a non-list `amendments` each fail naming the
    container; a non-object amendment entry fails naming its index.
    Container types are normalized BEFORE any `.get()` is reached.
    """
    out = []
    if not isinstance(lock, dict):
        return ["V2 PROTOCOL-LOCK: lock is not an object (the lock top "
                "level must be a JSON object carrying governed and "
                "amendments)"]
    governed = lock.get("governed", {})
    if not isinstance(governed, dict):
        return ["V2 PROTOCOL-LOCK: lock governed map is not an object"]
    for key in sorted(set(governed) - set(PROTOCOL_GOVERNED)):
        out.append(f"V2 PROTOCOL-LOCK: governed carries an ungoverned "
                   f"key {key!r} (the governed set must be exactly the "
                   f"seven PROTOCOL_GOVERNED files)")
    amendments = lock.get("amendments", [])
    if not isinstance(amendments, list):
        return out + ["V2 PROTOCOL-LOCK: lock amendments list is not a "
                      "list (every forward amendment must be an object "
                      "in the amendments list)"]
    for idx, a in enumerate(amendments):
        if not isinstance(a, dict):
            out.append(f"V2 PROTOCOL-LOCK: amendment entry #{idx} is "
                       f"not an object (every amendment entry must be "
                       f"an object naming a governed file)")
            continue
        fn = a.get("file")
        if fn not in PROTOCOL_GOVERNED:
            out.append(f"V2 PROTOCOL-LOCK: amendment names an ungoverned "
                       f"file {fn!r} (every amendment file must name a "
                       f"governed file)")
    return out


def validate_file_chain(fn, frozen_sha, amendments, disk_sha,
                        governed_sha, branch_seq=None,
                        lock_authority_ok=None):
    """A12d slice D7: the unique-linear-lineage rule for ONE governed
    file. Pure function of its arguments (no git, no disk reads): the
    hermetic unit under test, and the exact code path validate_protocol
    runs per file. Returns (findings, tip).

    `amendments` is the file's amendment-entry list in lock order;
    `frozen_sha` is the git-resolved frozen content sha (None when the
    file postdates the freeze); `governed_sha` is the lock's governed
    entry for the file. Findings are all prefixed
    "V2 PROTOCOL-LOCK: {fn} ..." (every finding names its file).
    `tip` is the validator-computed unique tip (None when no root is
    determinable); on a green file disk_sha == tip (equality with the
    tip, not mere reachability).

    The rule: the amendments for the file form ONE path from the
    frozen (or post-freeze genesis) node to exactly one tip —
    exactly one edge out of the root, at most one incoming and at
    most one outgoing edge per node, no dead-end node other than the
    single tip (every recorded edge is walked from the root), and the
    on-disk bytes equal that tip. Deleting any single predecessor
    edge, reverting a from_sha, or retargeting a to_sha off-chain
    fails here naming the file.

    A12d slice D8.2 (same pure function, tightened): every recorded
    non-genesis from_sha and every to_sha must be 64-lowercase-hex
    (malformed shas fail naming the file), and for a post-freeze file
    the lock's governed sha must EQUAL the genesis node — a governed
    sha moved to any descendant (even the current tip) fails.

    A12i slice D9.1 (same pure function, tightened): when the caller
    passes `branch_seq` — the file's ORDERED distinct committed
    content states on the experiment branch, oldest -> newest, derived
    by the git-aware layer — the recorded root -> tip node sequence
    must satisfy Rule A (every recorded node appears in `branch_seq`;
    this replaces the old all-refs retrievability membership test) and
    Rule B (the recorded sequence is a SUBSEQUENCE of `branch_seq` in
    that order: collapsing several real commits into one recorded
    edge stays legal, reordering two real states fails as
    non-monotonic). Both fail closed naming the file. A
    `branch_seq` of None selects the hermetic topology-only mode (the
    historical unit-test surface); the git-aware caller
    `protocol_tips` always derives the sequence and fails closed with
    a named finding when derivation is impossible, so production
    never silently skips Rule A/B.

    A12l slice D11.1 (same pure function, tightened): when the
    caller passes `lock_authority_ok` — the git-aware layer's byte
    verdict on the lock itself (see `_lock_authority_findings`),
    passed in exactly like `branch_seq` — a False refuses with the
    named lock-authority finding and no tip. None (the default)
    selects the hermetic mode, which evaluates the chain on its
    merits without the lock-bytes verdict.
    """
    pre = f"V2 PROTOCOL-LOCK: {fn} "
    if lock_authority_ok is False:
        return (["V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json differs from "
                 "committed experiment-HEAD authority"], None)
    for a in amendments:
        _f, _t = (a.get("from_sha") if isinstance(a, dict) else None,
                  a.get("to_sha") if isinstance(a, dict) else None)
        if _f is not None and not (isinstance(_f, str)
                                   and _HEX64.match(_f)):
            return ([pre + f"amendment carries a malformed from_sha "
                     f"{_f!r} (every recorded node sha must be "
                     f"64-lowercase-hex; the sole null allowed is a "
                     f"post-freeze genesis from_sha)"], None)
        if not (isinstance(_t, str) and _HEX64.match(_t)):
            return ([pre + f"amendment carries a malformed to_sha "
                     f"{_t!r} (every recorded node sha must be "
                     f"64-lowercase-hex)"], None)
    links = [(a.get("from_sha"), a.get("to_sha")) for a in amendments]
    genesis = [a for a in amendments if a.get("from_sha") is None]
    if frozen_sha is not None:
        if frozen_sha != governed_sha:
            return ([pre + "lock frozen-sha != git truth (lock edited?)"],
                    None)
        stray = [a for a in genesis]
        if stray:
            return ([pre + "amendment chain is not a unique linear chain: "
                     "a frozen file carries a post-freeze genesis "
                     "amendment (unlisted root?)"], None)
        root, root_label = frozen_sha, "frozen"
        walk_edges = links
    else:
        if len(genesis) != 1 or genesis[0].get(
                "added_after_freeze") is not True:
            if not genesis:
                return ([pre + "frozen bytes unresolvable at freeze and "
                         "no post-freeze genesis amendment governs it"],
                        None)
            return ([pre + "amendment chain is not a unique linear "
                     "chain: a post-freeze file needs exactly one "
                     "genesis amendment (from_sha null + "
                     "added_after_freeze)"], None)
        root = genesis[0].get("to_sha")
        root_label = "genesis"
        walk_edges = [(f, t) for (f, t) in links if f is not None]
        # A12d slice D8.2: a post-freeze anchor is immovable — the
        # governed sha must EQUAL the genesis node, never any
        # descendant (moving it to the current tip fails, lock edited?).
        if governed_sha != root:
            return ([pre + "lock governed-sha "
                     f"{str(governed_sha)[:12]} != the post-freeze "
                     f"genesis node {root[:12]} (a post-freeze anchor "
                     f"must equal its genesis node, never a descendant; "
                     f"lock edited?)"], None)
    if not walk_edges:
        if disk_sha == root:
            return ([], root)
        return ([pre + f"drifted with no listed forward amendment "
                 f"(disk {disk_sha[:12]} not in "
                 f"{{{root_label},0 amendment(s)}})"], root)
    out_of_root = [e for e in walk_edges if e[0] == root]
    if not out_of_root:
        return ([pre + "amendment chain is not a unique linear chain: "
                 f"no edge continues the {root_label} node "
                 f"{root[:12]} (an amendment from_sha outside the "
                 f"chain?)"], None)
    if len(out_of_root) > 1:
        return ([pre + "amendment chain is not a unique linear chain: "
                 f"{len(out_of_root)} edges leave the {root_label} "
                 f"node {root[:12]} (exactly one edge may leave the "
                 f"root)"], None)
    indeg, outdeg = {}, {}
    for (f, t) in walk_edges:
        outdeg[f] = outdeg.get(f, 0) + 1
        indeg[t] = indeg.get(t, 0) + 1
    for node in sorted(indeg):
        if node != root and indeg[node] > 1:
            return ([pre + "amendment chain is not a unique linear "
                     f"chain: node {node[:12]} has "
                     f"{indeg[node]} incoming amendment edges "
                     f"(no branching/merging)"], None)
    if indeg.get(root, 0):
        return ([pre + "amendment chain is not a unique linear chain: "
                 f"an edge points back into the {root_label} node "
                 f"{root[:12]}"], None)
    for node in sorted(outdeg):
        if outdeg[node] > 1:
            return ([pre + "amendment chain is not a unique linear "
                     f"chain: node {node[:12]} has "
                     f"{outdeg[node]} outgoing amendment edges "
                     f"(no forks)"], None)
    by_from = {}
    for (f, t) in walk_edges:
        by_from.setdefault(f, []).append(t)
    seen, cur = set(), root
    while cur in by_from:
        nxt = by_from[cur][0]
        if (cur, nxt) in seen:
            return ([pre + "amendment chain is not a unique linear "
                     "chain: amendment cycle "
                     f"at {cur[:12]}"], None)
        seen.add((cur, nxt))
        cur = nxt
    if len(seen) != len(walk_edges):
        return ([pre + "amendment chain is not a unique linear chain: "
                 f"{len(walk_edges) - len(seen)} recorded edge(s) "
                 f"never continue to the single tip (a dead-end or "
                 f"disconnected edge: every non-tip node must be "
                 f"continued)"], cur)
    tip = cur
    if branch_seq is not None:
        if not isinstance(branch_seq, list):
            return ([pre + "experiment-branch lineage is not a "
                     "sequence (fail closed: the recorded chain must "
                     "be provable on the experiment branch)"], None)
        recorded = [root]
        walk = root
        while walk in by_from:
            walk = by_from[walk][0]
            recorded.append(walk)
        on_branch = set(branch_seq)
        for node in recorded:
            if node not in on_branch:
                return ([pre + f"records node {node[:12]} with no "
                         f"retrievable bytes on the experiment-HEAD "
                         f"lineage (protocol history must be committed "
                         f"on the experiment branch, not another ref)"],
                        None)
        pos, prev = -1, None
        for node in recorded:
            nxt = -1
            for i in range(pos + 1, len(branch_seq)):
                if branch_seq[i] == node:
                    nxt = i
                    break
            if nxt == -1:
                after = "" if prev is None else f" after {prev[:12]}"
                return ([pre + f"records a non-monotonic protocol "
                         f"lineage ({node[:12]}{after} on the "
                         f"experiment branch)"], None)
            pos, prev = nxt, node
    if disk_sha != tip:
        return ([pre + f"drifted with no listed forward amendment "
                 f"(disk {disk_sha[:12]} != the unique chain tip "
                 f"{tip[:12]}; {len(walk_edges)} amendment(s) "
                 f"chained)"], tip)
    return ([], tip)


def protocol_tips(fam_c_dir, freeze_commit):
    """A12d slice D7/D8.2, A12i slice D9.1: the validator-computed
    unique tip per governed file, through the real V2 chain path
    (git-resolved frozen bytes + validate_file_chain, plus the D8.2
    lock-global hygiene and the D9.1 experiment-branch chronology).
    Returns (tips, findings); `tips` maps each governed file to its
    unique tip (absent when that file's chain fails). A green file
    always satisfies sha256(disk bytes) == tips[file] — computed
    here, never asserted by callers.

    A12i slice D9.2: the lock containers are normalized BEFORE any
    `.get()` is reached on them, so a non-object `governed`, a
    non-list `amendments`, or a non-object amendment entry yields a
    named V2 finding (the canonical text rides with
    validate_lock_global), never a traceback.

    A12l slice D11.1: the lock's byte authority
    (`_lock_authority_findings`) is verified BEFORE the lock is
    parsed — a worktree lock that differs from the committed
    experiment-HEAD bytes yields the named lock-authority finding
    and NO lock-derived tips are certified (tips are withheld even
    though the component diagnostics below still run, so every
    refusal names its own defect)."""
    auth = _lock_authority_findings(fam_c_dir)
    try:
        lock = json.load(open(os.path.join(fam_c_dir,
                                           "PROTOCOL-LOCK.json")))
    except (ValueError, OSError) as e:
        return ({}, auth + [f"V2 PROTOCOL-LOCK: lock unparsable: {e}"])
    if not isinstance(lock, dict):
        return ({}, auth + ["V2 PROTOCOL-LOCK: lock is not an object (the "
                            "lock top level must be a JSON object carrying "
                            "governed and amendments)"])
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
    except RuntimeError as e:
        return ({}, auth + [f"V2 PROTOCOL-LOCK: git unavailable: {e}"])
    governed = lock.get("governed", {})
    if not isinstance(governed, dict):
        governed = {}
    amendments = lock.get("amendments", [])
    if not isinstance(amendments, list):
        amendments = []
    by_file = {}
    for a in amendments:
        if not isinstance(a, dict):
            continue
        by_file.setdefault(a.get("file"), []).append(a)
    tips, findings = {}, []
    if lock.get("freeze_commit") != freeze_commit:
        findings.append("V2 PROTOCOL-LOCK: lock freeze_commit != instance "
                        "freeze (locks disagree on the freeze)")
    for fn in PROTOCOL_GOVERNED:
        want = governed.get(fn)
        if not want:
            findings.append(f"V2 PROTOCOL-LOCK: {fn} not governed by lock")
            continue
        try:
            frozen_bytes = subprocess.run(
                ["git", "show", f"{freeze_commit}:benchmarks/fam-c/{fn}"],
                cwd=root, capture_output=True)
            if frozen_bytes.returncode != 0:
                raise RuntimeError("unresolvable at freeze")
            frozen_sha = hashlib.sha256(frozen_bytes.stdout).hexdigest()
        except RuntimeError:
            frozen_sha = None
        fp = os.path.join(fam_c_dir, fn)
        if not os.path.exists(fp):
            findings.append(f"V2 PROTOCOL-LOCK: {fn} missing on disk")
            continue
        disk = _sha(fp)
        # A12i slice D9.1: the branch sequence is derived here, in the
        # git-aware layer — validate_file_chain stays pure and
        # I/O-free. When the sequence cannot be derived, fail closed
        # with a named finding, never silently skip Rule A/B.
        try:
            seq = _branch_seq_shas(root, f"benchmarks/fam-c/{fn}")
        except RuntimeError as e:
            findings.append(
                f"V2 PROTOCOL-LOCK: {fn} experiment-branch lineage "
                f"underivable ({e}; fail closed — the recorded chain "
                f"must be provable on the experiment branch)")
            seq = None
        # A12l slice D11.1: the per-file chain is evaluated on its
        # merits (None: hermetic chain mode), so the D7/D8/D9
        # component diagnostics still name their own defect (file,
        # node, container) even on a lock that fails its byte
        # authority. The authority itself is enforced at this layer
        # (named finding leads, tips withheld below) — threading
        # False in here would replace those diagnostics with seven
        # copies of one finding. The `lock_authority_ok` parameter
        # stays the direct/unit enforcement point for callers that
        # own the verdict.
        f_find, tip = validate_file_chain(fn, frozen_sha,
                                          by_file.get(fn, []), disk,
                                          want, seq)
        findings.extend(f_find)
        if tip is not None:
            tips[fn] = tip
    # A12d slice D8.2, A12i slice D9.2: lock-global hygiene (pure:
    # exact governed set, governed amendment files only, named
    # container failures).
    findings.extend(validate_lock_global(lock))
    if auth:
        # A12l slice D11.1: a lock that fails its own byte authority
        # certifies no tips — the contents are diagnosed, never
        # trusted — and the named authority finding leads.
        return ({}, auth + findings)
    return (tips, findings)


def _branch_seq_shas(repo_root, rel):
    """Ordered DISTINCT sha256(file bytes) sequence for the
    repo-relative path `rel` along the experiment branch: [sha256 of
    the file bytes at commit c for c in `git log --first-parent
    --format=%H -- <rel>` (first-parent HEAD lineage, oldest ->
    newest), consecutive duplicates collapsed]. A12i slice D9.1: this
    sequence is the lineage authority — the recorded node chain must
    be a subsequence of it (Rule A membership + Rule B chronology),
    replacing the old all-refs retrievability map. A12l slice D11.2
    (auditor D9-post P1): the walk is first-parent, so a state that
    lived only on a merged side branch can never satisfy the
    subsequence test — linearizing the DAG is refused. Non-regression
    measured at the D11 base: first-parent and the old walk yield
    IDENTICAL sequences for all seven governed files on this tree
    (PREREG.md 19, ORDER.md 5, LANES.md 5, HARNESS-READINESS.md 12,
    preflight.py 17, T4-SEMANTIC-IDS.json 1, T4-CONFORMANCE.json 7),
    so no chain repair was needed. Raises RuntimeError when the
    history is underivable — callers fail closed, never skip."""
    try:
        commits = _git(["log", "--first-parent", "--format=%H", "--",
                        rel], cwd=repo_root).split()
    except RuntimeError:
        raise RuntimeError(f"git log unreadable for {rel}")
    seq = []
    for commit in reversed(commits):
        proc = subprocess.run(["git", "show", f"{commit}:{rel}"],
                              cwd=repo_root, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"git show {commit[:12]}:{rel} "
                               f"unreadable")
        sha = hashlib.sha256(proc.stdout).hexdigest()
        if not seq or seq[-1] != sha:
            seq.append(sha)
    return seq


def validate_protocol(fam_c_dir, freeze_commit):
    """V2 PROTOCOL-LOCK. Returns findings list (empty = green)."""
    out = []
    lp = os.path.join(fam_c_dir, "PROTOCOL-LOCK.json")
    if not os.path.exists(lp):
        return ["V2 PROTOCOL-LOCK: PROTOCOL-LOCK.json missing"]
    # A12l slice D11.1: this consumer never parses the lock itself —
    # the single parse lives in protocol_tips, which verifies the
    # lock's byte authority BEFORE parsing (named finding plus
    # lock-derived tips withheld on mismatch). Every production
    # entry (CLI, validate_all, the runner) therefore refuses a
    # forged worktree lock before trusting a byte of it.
    # A12d slice D7: the per-file chain rule is the unique-linear-chain
    # (validate_file_chain via protocol_tips: exactly one edge out of
    # the frozen/genesis node, indegree/outdegree <= 1, no dead end but
    # the single tip, disk bytes equal to that tip). The old
    # reachable-set ("disk merely members of a set") is DELETED: branching,
    # dead ends and multiple tips no longer pass.
    # A12d slice D8.2: protocol_tips additionally enforces lock-global
    # hygiene (exact governed set, governed amendment files only,
    # 64-hex node shas, immovable post-freeze genesis anchor).
    # A12i slice D9.1: protocol_tips additionally enforces the
    # experiment-branch chronology (every recorded node on the HEAD
    # lineage in the recorded order; the all-refs retrievability test
    # is deleted) and D9.2 fails malformed lock containers closed
    # with a named finding instead of a traceback.
    # A12l slice D11.1: protocol_tips verifies the lock's byte
    # authority before parsing it (named finding, tips withheld).
    # A12l slice D11.2: the chronology walk is first-parent (a merged
    # side-branch state never enters the sequence).
    _tips, chain_findings = protocol_tips(fam_c_dir, freeze_commit)
    out += chain_findings
    # A12l slice D11.1, append-only history: even a re-committed lock
    # must carry every older amendment entry verbatim (new entries
    # only append). Synthetic universes skip silently here; the
    # instance lineage is always judged.
    out += validate_lock_history(fam_c_dir)
    # Item-7: the enumerated execution order is DERIVED from ORDER.md, so a
    # hand-edited or stale expansion is protocol drift by construction.
    for f in order_verify_expansion(fam_c_dir):
        out.append("V2 PROTOCOL-LOCK: " + f)
    # A12c C1-2 (auditor P0 #7): exact registry<->PREREG set equality is
    # a V2 gate, not a suite-only assertion — a missing/extra/renamed id
    # or key/value family mismatch refuses here, before any model call.
    out += validate_t4_registry(fam_c_dir)
    # A12c slice C2 (auditor P0 #6): the frozen limitation->T4-id bridge
    # is a V2 gate too — the governed map must exist and satisfy every
    # refusal condition, or nothing runs.
    out += validate_t4_conformance(fam_c_dir)
    return out


def validate_t4_registry(fam_c_dir):
    """V2 T4-REGISTRY (A12c C1-2, auditor P0 #7). Returns findings list.

    Exact registry<->PREREG set equality, enforced BEFORE any model
    call. V2 fails (nonzero) unless ALL of:
      - T4-SEMANTIC-IDS.json keys are EXACTLY fam01..fam06;
      - the registry value set equals the PREREG frozen id set EXACTLY
        (no missing, no extra);
      - every registry value appears verbatim in PREREG.md;
      - every value matches <family>.<snake_case> with its family
        prefix equal to its key.
    A missing id, an extra id, a renamed id, or a key/value family
    mismatch refuses here naming the offending id. Importable without
    git: needs only the two files in fam_c_dir (hermetic fixtures).
    Stdlib only; fails closed (an unreadable registry or PREREG block
    is a finding, never a pass)."""
    out = []
    reg, reg_err = None, None
    try:
        reg = t4_ids.frozen_set(fam_c_dir)
    except PermissionError as e:
        reg_err = str(e)
    frozen, frozen_err = None, None
    try:
        frozen = t4_ids.prereg_frozen_set(fam_c_dir)
    except PermissionError as e:
        frozen_err = str(e)
    if reg_err is not None:
        out.append("V2 PROTOCOL-LOCK: " + reg_err)
    if frozen_err is not None:
        out.append("V2 PROTOCOL-LOCK: " + frozen_err)
        return out
    if reg is None:
        # Malformed registry (frozen_set refused): still report the
        # set-equality directions best-effort from the raw bytes, so a
        # missing PREREG id is named alongside the malformed entry.
        try:
            raw = json.load(open(os.path.join(
                fam_c_dir, "T4-SEMANTIC-IDS.json")))
            raw_fams = raw.get("families")
            reg = dict(raw_fams) if isinstance(raw_fams, dict) else {}
        except (ValueError, OSError):
            return out
    want_keys = [f"fam0{i}" for i in range(1, 7)]
    if sorted(reg) != want_keys:
        out.append(f"V2 PROTOCOL-LOCK: T4-SEMANTIC-IDS.json keys "
                   f"{sorted(reg)} != exactly {want_keys} (a dropped "
                   f"or added family refuses before any model call)")
    reg_vals = set(v for v in reg.values() if isinstance(v, str))
    for tid in sorted(reg_vals - frozen):
        out.append(f"V2 PROTOCOL-LOCK: T4 registry id {tid!r} is not "
                   f"frozen in PREREG.md ## Conformance semantic IDs "
                   f"(frozen) (register an id only by forward PREREG "
                   f"amendment before the runs it governs)")
    for tid in sorted(frozen - reg_vals):
        out.append(f"V2 PROTOCOL-LOCK: PREREG frozen T4 id {tid!r} is "
                   f"missing from T4-SEMANTIC-IDS.json (registry and "
                   f"PREREG must agree exactly)")
    try:
        text = open(os.path.join(fam_c_dir, "PREREG.md")).read()
    except OSError as e:
        return out + [f"V2 PROTOCOL-LOCK: PREREG.md unreadable: {e}"]
    for fam in sorted(reg):
        tid = reg[fam]
        if not isinstance(tid, str):
            out.append(f"V2 PROTOCOL-LOCK: T4 registry entry {fam!r} "
                       f"is not a string id: {tid!r}")
            continue
        if tid not in text:
            out.append(f"V2 PROTOCOL-LOCK: T4 registry id {tid!r} "
                       f"does not appear verbatim in PREREG.md")
        if not tid.startswith(fam + "."):
            out.append(f"V2 PROTOCOL-LOCK: T4 registry key/value "
                       f"family mismatch: key {fam!r} maps to id "
                       f"{tid!r} (the id prefix must equal its key)")
    return out


def validate_t4_conformance(fam_c_dir):
    """V2 T4-CONFORMANCE (A12c slice C2, auditor P0 #6). Returns findings.

    The frozen limitation->T4-id bridge must exist and satisfy every
    C2-3 refusal condition BEFORE any model call: missing file,
    unparsable JSON, version/rule mismatch, wrong family keys, a
    `t4_semantic_id` outside the registry resolver's value, empty
    predicate lists, or a malformed predicate refuses here naming
    T4-CONFORMANCE.json. A map edited without re-minting
    PROTOCOL-LOCK refuses via the governed-chain check above (never a
    silent substitution). Importable without git: needs only the map
    (+ the registry + PREREG for the resolver cross-check) in
    fam_c_dir (hermetic fixtures). Stdlib only; fails closed."""
    try:
        conformance.load(fam_c_dir)
    except Exception as e:                                # noqa: BLE001
        return [f"V2 PROTOCOL-LOCK: T4-CONFORMANCE.json refuses: {e}"]
    return []


def _harness_closure(root, entry_rel):
    """Harness modules reachable from the runner by import (repo-relative).
    Only harness/*.py candidates count; governed/operational paths are
    owned by their own authority."""
    seen, todo = set(), [entry_rel]
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            continue
        try:
            tree = ast.parse(open(fp).read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            elif isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            else:
                continue
            for m in mods:
                cand = f"harness/{m.split('.')[0]}.py"
                if os.path.exists(os.path.join(root, cand)):
                    todo.append(cand)
    return seen


def validate_execution(fam_c_dir):
    """V3 EXECUTION-LOCK. Returns findings list (empty = green)."""
    out = []
    lp = os.path.join(fam_c_dir, "EXECUTION-LOCK.json")
    if not os.path.exists(lp):
        return ["V3 EXECUTION-LOCK: EXECUTION-LOCK.json missing"]
    try:
        lock = json.load(open(lp))
    except ValueError as e:
        return [f"V3 EXECUTION-LOCK: lock unparsable: {e}"]
    try:
        root = _git(["rev-parse", "--show-toplevel"], cwd=fam_c_dir)
    except RuntimeError as e:
        return [f"V3 EXECUTION-LOCK: git unavailable: {e}"]
    for rel, want in sorted(lock.get("harness_files", {}).items()):
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            out.append(f"V3 EXECUTION-LOCK: harness file missing: {rel} "
                       "(re-mint via explicit amendment, never skip)")
        elif _sha(fp) != want:
            out.append(f"V3 EXECUTION-LOCK: harness bytes changed: {rel} "
                       "(re-mint via explicit amendment commit)")
    if not lock.get("harness_files"):
        out.append("V3 EXECUTION-LOCK: lock lists no harness files")
    # Item-7 completeness: the lock must cover every harness module the
    # runner actually executes (import closure), so a new/smuggled module
    # cannot ride outside the execution authority.
    listed = set(lock.get("harness_files", {}))
    entry = next((r for r in listed if r.startswith("benchmarks/fam-c/"
                                                   "harness-run/")), None)
    if entry:
        for rel in sorted(_harness_closure(root, entry)):
            if rel not in listed:
                out.append(f"V3 EXECUTION-LOCK: unlisted harness module in "
                           f"the runner's import closure: {rel} (add it to "
                           "the lock via an explicit amendment)")
    # Item-7 closure, package-wide: the trust boundary is the harness package
    # ROOT, not just the runner's import graph. A governance module that the
    # runner does not import (harness/promotion.py mints locks and promotion
    # receipts) would otherwise execute outside the execution authority.
    # harness/tests/** stays out: the closure rule maps a module name to
    # harness/<name>.py, so test modules are never candidates.
    hdir = os.path.join(root, "harness")
    if os.path.isdir(hdir):
        for name in sorted(os.listdir(hdir)):
            if not name.endswith(".py"):
                continue
            rel = f"harness/{name}"
            if rel not in listed:
                out.append(f"V3 EXECUTION-LOCK: harness module not listed in "
                           f"the execution lock: {rel} (the lock must cover "
                           "the whole harness package root; re-mint via an "
                           "explicit amendment)")
    return out


def validate_all(fam_c_dir=None):
    """Run all three validators. Returns findings list (empty = green)."""
    fam_c_dir = fam_c_dir or HERE
    freeze = load_freeze(fam_c_dir)["freeze_commit"]
    findings = []
    findings += validate_instance(fam_c_dir, freeze)
    findings += validate_protocol(fam_c_dir, freeze)
    findings += validate_execution(fam_c_dir)
    return findings


def main():
    findings = validate_all()
    for f in findings:
        print("FAIL:", f)
    v1 = [f for f in findings if f.startswith("V1")]
    v2 = [f for f in findings if f.startswith("V2")]
    v3 = [f for f in findings if f.startswith("V3")]
    print(f"preflight: V1-instance {len(v1)} finding(s), "
          f"V2-protocol {len(v2)} finding(s), "
          f"V3-execution {len(v3)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
