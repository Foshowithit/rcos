#!/usr/bin/env python3
"""Fam-C execution order: mechanical expansion of the frozen ORDER.md into
the FULL enumerated event universe, pre-call authorization of a requested
cell, scheduler-derived per-universe namespaces, and validated cell state.

Audit round-2 item 7 + round-3 A11.4-A11.6.

ORDER.md is the authority. It states the per-family event sequence
    T0, T1, PROMOTION, CAPABILITY_LOCK, T2, T3, T4
and PREREG §2 defines the A/B/C/D universes. The earlier expansion started
at T2 and therefore enumerated downstream cells whose capability had never
been acquired or promoted — it could not instantiate the prereg. This
module now expands, per (block, family):

  A universe acquisition:  T0, T1, PROMOTION, CAPABILITY_LOCK   (A first)
  C universe acquisition:  T0, T1, PROMOTION, CAPABILITY_LOCK
  downstream model calls:  T2, T3, T4 x [A,B,C,D] (flipped per family)

B and D carry no capability (no K), so they have no acquisition/promotion
events: PREREG §2 requires C to create and promote its OWN capability with
its own producer runs, never to inherit A's.

Namespace (A11.5): every cell's capability registry and run directory are
DERIVED here from the authorized cell — state/<block>/<universe>/<family>/
... — never accepted as a free operator path.

Cell state (A11.6): order progress consumes validated cell_state(), not raw
manifest presence: a manifest alone can no longer advance the frozen order.
Stdlib only.
"""
import hashlib
import json
import os
import re
import stat
import sys
import time

BLOCKS = ("PQ", "QP")
ARM_LETTERS = ("A", "B", "C", "D")
# PREREG §2: A/B/C/D are separate experimental universes.
UNIVERSES = ("A", "B", "C", "D")
# Only the capability-bearing universes acquire/promote/lock K. B and D
# solve fresh by design and never hold a registry.
CAPABILITY_UNIVERSES = ("A", "C")
ACQ_EVENTS = ("T0", "T1", "PROMOTION", "CAPABILITY_LOCK")
DOWNSTREAM_EVENTS = ("T2", "T3", "T4")
EVENT_KIND = {"T0": "acquisition-solve", "T1": "acquisition-solve",
              "PROMOTION": "harness-event",
              "CAPABILITY_LOCK": "harness-event",
              "T2": "model-call", "T3": "model-call", "T4": "model-call"}
MODEL_CALL_KINDS = ("acquisition-solve", "model-call")
PRODUCER = {"PQ": "P", "QP": "Q"}
OTHER_LANE = {"P": "Q", "Q": "P"}
# Letter -> (consumer lane, capability present). "Primed" blocks swap the
# producer/consumer roles, so the same letter maps to the other lane.
CONSUMER = {"PQ": {"A": "P", "B": "P", "C": "Q", "D": "Q"},
            "QP": {"A": "Q", "B": "Q", "C": "P", "D": "P"}}
CAPABILITY = {"A": True, "B": False, "C": True, "D": False}
ARM_NAME = {True: "correct", False: "disabled"}
LANE_KEY = {"A": "P->P + K", "B": "P->P no K",
            "C": "P->Q + K", "D": "P->Q no K"}


def cell_id(block, family, task, letter):
    return hashlib.sha256(
        f"{block}|{family}|{task}|{letter}".encode()).hexdigest()[:16]


def parse_order(text):
    """Parse the frozen ORDER.md into its structural facts (no guessing:
    a missing or malformed line raises ORDER-PARSE)."""
    def one(pat, what):
        m = re.search(pat, text)
        if not m:
            raise ValueError(f"ORDER-PARSE: {what} not found in ORDER.md")
        return m

    families = one(r"Family order:\s*([^\n.]+)", "family order").group(1)
    families = [f.strip() for f in families.split(",") if f.strip()]
    bl = one(r"Block order:\s*(\w+)\s*first,\s*(\w+)\s*second", "block order")
    block_order = [bl.group(1).upper(), bl.group(2).upper()]
    if sorted(block_order) != sorted(BLOCKS):
        raise ValueError(f"ORDER-PARSE: unexpected blocks {block_order}")
    tasks = one(r"Within each family:\s*([^\n.]+)", "task order").group(1)
    tasks = [t.strip() for t in tasks.split(",") if t.strip()]
    seed = one(r"seed\s+(\d+)", "seed").group(1)
    # per-block, per-family letter sequences
    seqs = {}
    for block in BLOCKS:
        m = re.search(rf"Block {block}\b(.*?)(?=\nBlock \w+\b|\Z)",
                      text, re.S)
        if not m:
            raise ValueError(f"ORDER-PARSE: block {block} section missing")
        section = m.group(1)
        for fm in re.finditer(r"-\s*(\w+):\s*(.+)", section):
            fam, rest = fm.group(1), fm.group(2)
            per_task = {}
            for tm in re.finditer(r"(\w+)\s*\[([A-D',\s]+)\]", rest):
                task = tm.group(1)
                letters = [x.strip().strip("'")
                           for x in tm.group(2).split(",") if x.strip()]
                base = [x.strip("'") for x in letters]
                if sorted(base) != sorted(ARM_LETTERS):
                    raise ValueError(
                        f"ORDER-PARSE: {block}/{fam}/{task} letters {letters} "
                        "are not a permutation of A,B,C,D")
                per_task[task] = base
            if not per_task:
                raise ValueError(f"ORDER-PARSE: no tasks for {block}/{fam}")
            seqs[(block, fam)] = per_task
    return {"seed": int(seed), "families": families, "block_order": block_order,
            "events": tasks,
            "tasks": tasks, "sequences": seqs}


def _cell(index, block, family, event, universe, kind):
    """One enumerated event. `universe` is the A/B/C/D universe it belongs
    to; for acquisition events the universe IS the capability universe."""
    lane = PRODUCER[block]
    consumer = CONSUMER[block][universe] if universe in CONSUMER[block] \
        else lane
    c = {"index": index,
         "cell_id": cell_id(block, family, event, universe),
         "block": block, "family": family, "event": event, "kind": kind,
         "universe": universe,
         "primed": block == "QP",
         "producer_lane": lane, "lane": consumer,
         "capability_id": capability_id(block, universe, family)}
    if kind == "model-call":
        cap = CAPABILITY[universe]
        c.update({"task": event, "letter": universe,
                  "arm": ARM_NAME[cap], "capability": cap,
                  "lane_key": LANE_KEY[universe] + (
                      " (primed)" if block == "QP" else "")})
    else:
        c.update({"task": event, "letter": universe,
                  "arm": "acquisition" if kind == "acquisition-solve"
                         else "harness",
                  "capability": False, "lane_key": LANE_KEY[universe] +
                  (" (primed)" if block == "QP" else "")})
    return c


def expand(order_text):
    """Mechanical expansion -> the enumerated, ordered event list.

    Order (per block, per family), straight from ORDER.md + PREREG §2:
      A: T0, T1, PROMOTION, CAPABILITY_LOCK
      C: T0, T1, PROMOTION, CAPABILITY_LOCK
      T2/T3/T4 x arm letters
    so the A-vs-C acquisition order is resolved explicitly:
    PQ/A/fam05/T0 precedes PQ/C/fam05/T0.
    """
    p = parse_order(order_text)
    events = p["events"]
    downstream = [t for t in events if re.fullmatch(r"T[2-4]", t)]
    if not downstream:
        raise ValueError("ORDER-PARSE: no downstream tasks T2-T4")
    acq = [t for t in events if t in ACQ_EVENTS]
    if acq != list(ACQ_EVENTS):
        raise ValueError(f"ORDER-PARSE: acquisition/promotion sequence "
                         f"{acq} is not {list(ACQ_EVENTS)}")
    cells = []
    for block in p["block_order"]:
        for fam in p["families"]:
            per_task = p["sequences"].get((block, fam))
            if per_task is None:
                raise ValueError(
                    f"ORDER-PARSE: block {block} has no entry for {fam}")
            for universe in CAPABILITY_UNIVERSES:
                for event in acq:
                    cells.append(_cell(len(cells), block, fam, event,
                                       universe, EVENT_KIND[event]))
            for task in downstream:
                letters = per_task.get(task)
                if letters is None:
                    raise ValueError(
                        f"ORDER-PARSE: {block}/{fam}/{task} has no arm order")
                for letter in letters:
                    cells.append(_cell(len(cells), block, fam, task,
                                       letter, EVENT_KIND[task]))
    for i, c in enumerate(cells):
        c["index"] = i
    return {
        "order_file": "ORDER.md",
        "order_sha256": hashlib.sha256(order_text.encode()).hexdigest(),
        "seed": p["seed"], "blocks": p["block_order"],
        "families": p["families"], "events": p["tasks"],
        "acquisition_events": list(ACQ_EVENTS),
        "downstream_tasks": downstream, "arm_letters": list(ARM_LETTERS),
        "universes": list(UNIVERSES),
        "capability_universes": list(CAPABILITY_UNIVERSES),
        "consumer_map": CONSUMER, "capability_map": CAPABILITY,
        "cells": cells, "total_cells": len(cells),
        "total_model_calls": len([c for c in cells
                                  if c["kind"] in MODEL_CALL_KINDS])}


def expected_cell(expansion, block, family, task, lane, arm):
    """Resolve a downstream model-call request to its cell, or None."""
    for c in expansion["cells"]:
        if (c["kind"] == "model-call" and c["block"] == block
                and c["family"] == family and c["task"] == task
                and c["lane"] == lane and c["arm"] == arm):
            return c
    return None


def expected_event(expansion, block, family, event, universe):
    """Resolve an acquisition/harness event to its cell, or None."""
    for c in expansion["cells"]:
        if (c["block"] == block and c["family"] == family
                and c["event"] == event and c["universe"] == universe):
            return c
    return None


def authorize(expansion, block, family, task, lane, arm, done_ids):
    """Pre-call authorization for a downstream model call. Returns
    (cell, findings). Empty findings = authorized to start. Because the
    expansion now starts at T0, a T2 cell cannot start before BOTH
    capability universes of its block/family have acquired, validated,
    promoted and locked their own K."""
    out = []
    if block not in expansion["blocks"]:
        out.append(f"ORDER-DENY: unknown block {block!r} "
                   f"(authorized: {expansion['blocks']})")
    if family not in expansion["families"]:
        out.append(f"ORDER-DENY: family {family!r} is outside the frozen "
                   f"universe {expansion['families']}")
    if task not in expansion["downstream_tasks"]:
        out.append(f"ORDER-DENY: task {task!r} is outside the frozen "
                   f"downstream universe {expansion['downstream_tasks']} "
                   f"(acquisition/promotion events are not model calls "
                   f"through this entry point)")
    if arm not in ("correct", "disabled"):
        out.append(f"ORDER-DENY: unknown arm {arm!r}")
    if out:
        return None, out
    cell = expected_cell(expansion, block, family, task, lane, arm)
    if cell is None:
        out.append(f"ORDER-DENY: no authorized cell for block={block} "
                   f"family={family} task={task} lane={lane} arm={arm} "
                   "(wrong lane for this arm/block)")
        return None, out
    cid = cell["cell_id"]
    if cid in done_ids:
        out.append(f"ORDER-DENY: duplicate cell {cid} "
                   f"({block}/{family}/{task}/{cell['letter']}) already "
                   f"completed as run {done_ids[cid]}")
        return cell, out
    missing = [c for c in expansion["cells"]
               if c["index"] < cell["index"] and c["cell_id"] not in done_ids]
    if missing:
        m = missing[0]
        out.append(
            f"ORDER-DENY: out of order — cell {cid} "
            f"({block}/{family}/{task}/{cell['letter']}) cannot start before "
            f"{len(missing)} earlier cell(s); earliest missing is "
            f"{m['cell_id']} ({m['block']}/{m['family']}/{m['event']}/"
            f"{m['universe']}, lane {m['lane']}, arm {m['arm']}, "
            f"kind {m['kind']})")
    return cell, out


def authorize_event(expansion, block, family, event, universe, done_ids):
    """Authorization for an acquisition/promotion/lock event."""
    out = []
    if event not in ACQ_EVENTS:
        out.append(f"ORDER-DENY: unknown acquisition event {event!r} "
                   f"(authorized: {list(ACQ_EVENTS)})")
    if universe not in CAPABILITY_UNIVERSES:
        out.append(f"ORDER-DENY: universe {universe!r} carries no capability "
                   f"acquisition (capability universes: "
                   f"{list(CAPABILITY_UNIVERSES)}; B and D solve fresh)")
    if out:
        return None, out
    cell = expected_event(expansion, block, family, event, universe)
    if cell is None:
        out.append(f"ORDER-DENY: no authorized event for block={block} "
                   f"family={family} event={event} universe={universe}")
        return None, out
    if cell["cell_id"] in done_ids:
        out.append(f"ORDER-DENY: duplicate cell {cell['cell_id']}")
        return cell, out
    missing = [c for c in expansion["cells"]
               if c["index"] < cell["index"]
               and c["cell_id"] not in done_ids]
    if missing:
        m = missing[0]
        out.append(f"ORDER-DENY: out of order — event {cell['cell_id']} "
                   f"({block}/{family}/{event}/{universe}) cannot start "
                   f"before {len(missing)} earlier cell(s); earliest missing "
                   f"is {m['cell_id']} ({m['block']}/{m['family']}/"
                   f"{m['event']}/{m['universe']})")
    return cell, out


# ---------------------------------------------------------------------------
# A11.5 — scheduler-derived per-universe namespaces. The operator never
# passes a capability or run path for an estimand cell: both are derived
# from the authorized cell, so a C run cannot be pointed at A's registry.
# ---------------------------------------------------------------------------

def capability_id(block, universe, family):
    """Per-universe capability id (PREREG §2: separate capability IDs)."""
    return f"{family}-{block}-{universe}-K"


def state_dir(fam_c_dir, block, universe, family):
    """state/<block>/<universe>/<family> — the universe's whole persistent
    surface (registry, runs, logs). No lane may read another's."""
    return os.path.join(fam_c_dir, "state", block, universe, family)


def capability_dir(fam_c_dir, block, universe, family):
    return os.path.join(state_dir(fam_c_dir, block, universe, family),
                        "capability")


def run_dir(fam_c_dir, cell):
    """The run directory of one cell, derived from the cell itself."""
    return os.path.join(state_dir(fam_c_dir, cell["block"],
                                  cell["universe"], cell["family"]),
                        "runs", cell["cell_id"])


def derive_paths(fam_c_dir, cell):
    """The only sanctioned (capability_dir, run_dir) pair for a cell.

    A11.6: derivation first verifies BOTH derived chains with lstat
    (state/<block>/<universe>/<family>[/capability] and
    state/<block>/<universe>/<family>/runs/<cell_id>). Any EXISTING
    component that is a symlink, not a directory, foreign-owned, or
    group/world writable raises PermissionError with a specific named
    denial BEFORE the runner can create or use a run directory — a
    symlinked namespace parent must never be traversed or created
    through.
    """
    block, universe, family = cell["block"], cell["universe"], cell["family"]
    for tail in (("capability",), ("runs", cell["cell_id"])):
        denial = verify_namespace_ancestry(fam_c_dir, block, universe,
                                           family, tail=tail)
        if denial:
            raise PermissionError(denial)
    return (capability_dir(fam_c_dir, block, universe, family),
            run_dir(fam_c_dir, cell))


def verify_namespace_ancestry(fam_c_dir, block, universe, family, tail=()):
    """A11.6: verify the derived namespace chain with lstat, no realpath.

    Every EXISTING component from `state/` downward — state root, block,
    universe, family, then any `tail` components (capability, or runs /
    run cell) — must satisfy all four rules:
      (a) is a directory,
      (b) is NOT a symlink,
      (c) is harness-owned (uid == os.geteuid()),
      (d) is NOT group/world writable.
    Absent components are allowed (the harness creates them afterwards
    with no-follow semantics). Returns None when the chain is clean, else
    a specific named denial string (NAMESPACE-SYMLINK-DENY /
    NAMESPACE-TYPE-DENY / NAMESPACE-OWNERSHIP-DENY /
    NAMESPACE-WRITABLE-DENY). Fail closed: never assert, never let
    realpath() normalize a symlinked parent into acceptance.
    """
    p = os.path.join(fam_c_dir, "state")
    parts = [p]
    for comp in (block, universe, family) + tuple(tail):
        p = os.path.join(p, comp)
        parts.append(p)
    for part in parts:
        try:
            st = os.lstat(part)
        except OSError:
            continue  # absent: nothing to traverse, created later no-follow
        mode = st.st_mode
        if stat.S_ISLNK(mode):
            return (f"NAMESPACE-SYMLINK-DENY: {part} is a symlink; refuse "
                    f"to derive or traverse a namespace through it")
        if not stat.S_ISDIR(mode):
            return (f"NAMESPACE-TYPE-DENY: {part} exists but is not a "
                    f"directory")
        if st.st_uid != os.geteuid():
            return (f"NAMESPACE-OWNERSHIP-DENY: {part} is owned by uid "
                    f"{st.st_uid}, expected harness uid {os.geteuid()}")
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            return (f"NAMESPACE-WRITABLE-DENY: {part} is group/world "
                    f"writable (mode {oct(stat.S_IMODE(mode))})")
    return None


def ensure_namespace(fam_c_dir, block, universe, family, tail=()):
    """Create the derived namespace with EXPLICIT 0755 components, one at a
    time, after proving the existing chain is clean (A11.6 "create the tree
    yourself with no-follow semantics").

    os.makedirs() applies its mode to the LEAF only: under a umask of 002
    every intermediate becomes 0775 and the ancestry rule above then
    refuses the tree it just created. mkdir-per-component at 0755 is
    umask-independent. An existing harness-owned component that is
    group/world writable is repaired to 0755 — never through a symlink,
    because verify_namespace_ancestry() has already refused those.
    Returns the leaf path."""
    denial = verify_namespace_ancestry(fam_c_dir, block, universe, family,
                                       tail=tail)
    if denial:
        raise PermissionError(denial)
    p = os.path.join(fam_c_dir, "state")
    if not os.path.lexists(p):
        os.mkdir(p, 0o755)          # fam_c_dir itself must already exist
    elif not stat.S_ISDIR(os.lstat(p).st_mode):
        raise PermissionError(f"NAMESPACE-TYPE-DENY: {p} exists but is not "
                              f"a directory")
    for comp in (block, universe, family) + tuple(tail):
        p = os.path.join(p, comp)
        if not os.path.lexists(p):
            os.mkdir(p, 0o755)
        else:
            st = os.lstat(p)
            if (stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                    and st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
                os.chmod(p, 0o755)
    denial = verify_namespace_ancestry(fam_c_dir, block, universe, family,
                                       tail=tail)
    if denial:
        raise PermissionError(denial)
    return p


def check_namespace(fam_c_dir, cell, capdir):
    """A11.5: the capability directory must be exactly the authorized
    universe's directory — inside Fam-C is NOT enough (a C cell pointed at
    A's registry is the §2 violation the round-3 audit found).

    A11.6: the DERIVED namespace chain (state/.../<family>/capability) is
    verified with lstat BEFORE the realpath comparison, so a symlinked
    parent (e.g. state/PQ/C -> state/PQ/A) is refused with a specific
    NAMESPACE-SYMLINK-DENY instead of being normalized away by realpath().
    Returns None or a named denial string; never asserts."""
    denial = verify_namespace_ancestry(
        fam_c_dir, cell["block"], cell["universe"], cell["family"],
        tail=("capability",))
    if denial:
        return denial
    want = os.path.realpath(capability_dir(
        fam_c_dir, cell["block"], cell["universe"], cell["family"]))
    got = os.path.realpath(capdir)
    if got != want:
        return (f"FOREIGN-REGISTRY-DENY: cell "
                f"{cell['block']}/{cell['universe']}/{cell['family']} "
                f"({cell['capability_id']}) may only use its own registry "
                f"{want}; got {got}")
    return None


# ---------------------------------------------------------------------------
# A11.6 — validated cell state. Order progress must not advance on raw
# manifest presence.
# ---------------------------------------------------------------------------

def _read_json(fp):
    with open(fp) as f:
        return json.load(f)


# A11.4/A11.5 — validated cell state, dispatched by cell kind. Order
# progress must not advance on raw manifest presence: a model-run cell is
# complete only when its production manifest equals the authorized cell on
# every order-bound field and its evidence chain + admissibility re-verify;
# a PROMOTION / CAPABILITY_LOCK harness-event cell is complete only on its
# governance artifacts (no fabricated model-run record). See cell_state().
MODEL_RUN_KINDS = ("acquisition-solve", "model-call")


def cell_state(fam_c_dir, cell, freeze_commit=None):
    """Validate ONE cell's completion. Returns
    {"status": "COMPLETE"|"INCOMPLETE"|"INADMISSIBLE", "reasons": [...]},
    dispatched by cell kind (A11.5):

      acquisition-solve / model-call -> _model_run_state(): a REAL model
          run — derived run dir, H1-RUN-MANIFEST.json with EXACT equality
          on every order-bound production field name (cell_id, cell_index,
          block, family, task, cell_event, cell_kind, cell_universe,
          cell_letter, lane, arm, capability_id, order_sha256), wired +
          non-dev, an evidence chain re-verified by the real module-level
          verifier, and harness admissibility ELIGIBLE;

      harness-event PROMOTION        -> _promotion_state(): promotion
          receipt binding the two REAL validated T0/T1 acquisition chain
          tips to the authorized per-universe capability id, with no
          fabricated model-run record;

      harness-event CAPABILITY_LOCK  -> _lock_state(): the immutable
          CAPABILITY_LOCK.json binding the promotion receipt, with every
          locked artifact hash verifying against the capability dir, with
          no fabricated model-run record.

    Any failure => not complete. INADMISSIBLE is used when the artifacts
    exist but fail validation (a distinction the retry machine needs).
    """
    kind = cell.get("kind")
    event = cell.get("event")
    # A11.6 defense in depth (TOCTOU): the runner derives paths through
    # derive_paths(), but a namespace parent could be replaced by a symlink
    # AFTER derivation. Every reader of cell state re-verifies the same
    # lstat ancestry before traversing it, so a symlinked parent can never
    # make another universe's run artifacts look like this cell's.
    denial = verify_namespace_ancestry(fam_c_dir, cell["block"],
                                       cell["universe"], cell["family"],
                                       tail=("runs", cell["cell_id"]))
    if denial:
        return _result(cell, [denial], True)
    if kind in MODEL_RUN_KINDS:
        return _model_run_state(fam_c_dir, cell, freeze_commit)
    if kind == "harness-event":
        if event == "PROMOTION":
            return _promotion_state(fam_c_dir, cell, freeze_commit)
        if event == "CAPABILITY_LOCK":
            return _lock_state(fam_c_dir, cell, freeze_commit)
        return _result(cell, [f"unsupported harness-event {event!r}"], False)
    return _result(cell, [f"unsupported cell kind {kind!r}"], False)


def _result(cell, reasons, artifact_present):
    status = ("INADMISSIBLE" if (reasons and artifact_present)
              else "INCOMPLETE" if reasons else "COMPLETE")
    return {"cell_id": cell["cell_id"], "status": status,
            "reasons": list(reasons)}


def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _model_run_state(fam_c_dir, cell, freeze_commit=None):
    """A11.4: completion of ONE real model-run cell (acquisition-solve or
    model-call) under the production manifest field names. A run is
    COMPLETE only when its directory exists at the DERIVED path, its
    manifest is a wired non-dev run whose order-bound fields equal the
    authorized cell's EXACTLY (13 fields — a manifest may not claim
    another cell, another universe, or an older order), its evidence chain
    re-verifies under the real verifier, and harness admissibility
    classifies it ELIGIBLE. See cell_state() for the full contract."""
    reasons = []
    d = run_dir(fam_c_dir, cell)
    if os.path.islink(d) or not os.path.isdir(d):
        return {"cell_id": cell["cell_id"], "status": "INCOMPLETE",
                "reasons": [f"run dir absent/not a real directory at the "
                            f"derived path {d}"]}
    mf = os.path.join(d, "H1-RUN-MANIFEST.json")
    if os.path.islink(mf) or not os.path.isfile(mf):
        return {"cell_id": cell["cell_id"], "status": "INCOMPLETE",
                "reasons": [f"no manifest at {mf}"]}
    try:
        m = _read_json(mf)
    except ValueError as e:
        return {"cell_id": cell["cell_id"], "status": "INADMISSIBLE",
                "reasons": [f"manifest unparsable: {e}"]}
    if m.get("wired") is not True or m.get("dev_mode") is True:
        reasons.append("manifest is not a wired, non-dev run")
    # A11.4: EXACT equality on the production order-bound field names. The
    # pre-A11.4 loop compared "kind"/"universe" (names the real runner
    # never writes) and tolerated a missing universe — both gone.
    try:
        order_sha = load_expansion(fam_c_dir)["order_sha256"]
    except (ValueError, KeyError, OSError) as e:
        reasons.append(f"order expansion unreadable: {e}")
        order_sha = None
    for key, want in (("cell_id", cell["cell_id"]),
                      ("cell_index", cell["index"]),
                      ("block", cell["block"]),
                      ("family", cell["family"]),
                      ("task", cell["task"]),
                      ("cell_event", cell["event"]),
                      ("cell_kind", cell["kind"]),
                      ("cell_universe", cell["universe"]),
                      ("cell_letter", cell["letter"]),
                      ("lane", cell["lane"]),
                      ("arm", cell["arm"]),
                      ("capability_id", cell["capability_id"]),
                      ("order_sha256", order_sha)):
        if m.get(key) != want:
            reasons.append(f"manifest {key} {m.get(key)!r} != authorized "
                           f"{want!r}")
    chain = os.path.join(d, "EVIDENCE-CHAIN.jsonl")
    if os.path.islink(chain) or not os.path.isfile(chain):
        reasons.append("EVIDENCE-CHAIN.jsonl absent")
    else:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from chain import verify_chain
            verify_chain(chain, m.get("instance_freeze_commit"), m)
        except Exception as e:                            # noqa: BLE001
            reasons.append(f"evidence chain invalid: {e}")
    try:
        from admissibility import classify_run_dir, ELIGIBLE
        status, why = classify_run_dir(d, freeze_commit or
                                       m.get("instance_freeze_commit"))
        if status != ELIGIBLE:
            reasons.append(f"admissibility {status}: {why}")
    except Exception as e:                                # noqa: BLE001
        reasons.append(f"admissibility check failed: {e}")
    return _result(cell, reasons, True)


def _cell_for_event(fam_c_dir, cell, event):
    """The expansion cell of the SAME (block, family, universe) that runs
    `event` (T0 / T1 acquisition, or PROMOTION), or None."""
    try:
        exp = load_expansion(fam_c_dir)
    except (ValueError, OSError):
        return None
    for c in exp["cells"]:
        if (c["block"] == cell["block"] and c["family"] == cell["family"]
                and c["universe"] == cell["universe"]
                and c["event"] == event):
            return c
    return None


def _chain_tip(chain_path):
    """link_hash of the LAST non-empty link of an evidence chain. Callers
    re-verify the chain first (cell_state()); this reader only extracts the
    recorded tip so the promotion receipt can be cross-bound to it."""
    tip = None
    for line in open(chain_path):
        line = line.strip()
        if not line:
            continue
        tip = json.loads(line).get("link_hash")
    if not isinstance(tip, str) or not tip:
        raise ValueError("chain tip missing link_hash")
    return tip


def _promotion_state(fam_c_dir, cell, freeze_commit=None):
    """A11.5: completion of ONE PROMOTION harness-event cell. A promotion
    is COMPLETE only when — with no fabricated model-run record — the two
    REAL acquisition runs of the SAME (block, family, universe) (its T0
    and T1, each validated COMPLETE by the model-run contract) produced
    exactly the chain tips the promotion receipt binds to the authorized
    per-universe capability id. See cell_state() for the full contract."""
    reasons = []
    d = run_dir(fam_c_dir, cell)
    if os.path.islink(d) or not os.path.isdir(d):
        return {"cell_id": cell["cell_id"], "status": "INCOMPLETE",
                "reasons": [f"promotion run dir absent at the derived path "
                            f"{d}"]}
    mf = os.path.join(d, "H1-RUN-MANIFEST.json")
    if os.path.exists(mf):
        reasons.append("promotion event must not fabricate a model-run "
                       "manifest (no identity/usage/chain is demanded of a "
                       "promotion, and none may be forged)")
    rp = os.path.join(d, "PROMOTION-RECEIPT.json")
    if os.path.islink(rp) or not os.path.isfile(rp):
        return _result(cell, reasons + [f"no promotion receipt at {rp}"],
                       os.path.exists(rp))
    try:
        r = _read_json(rp)
    except ValueError as e:
        return _result(cell, [f"promotion receipt unparsable: {e}"], True)
    for key, want in (("event", "PROMOTION"),
                      ("cell_id", cell["cell_id"]),
                      ("block", cell["block"]),
                      ("family", cell["family"]),
                      ("universe", cell["universe"]),
                      ("capability_id", cell["capability_id"])):
        if r.get(key) != want:
            reasons.append(f"promotion receipt {key} {r.get(key)!r} != "
                           f"authorized {want!r}")
    # rule compliance: the acquisition runs of THIS universe must be
    # genuinely complete, and the receipt must bind their REAL chain tips
    # in the right places (T0 under T0, T1 under T1 — never swapped).
    tips = {}
    for ev in ("T0", "T1"):
        acq = _cell_for_event(fam_c_dir, cell, ev)
        if acq is None:
            reasons.append(f"no {ev} cell in the order for "
                           f"{cell['block']}/{cell['family']}/"
                           f"{cell['universe']}")
            continue
        st = cell_state(fam_c_dir, acq, freeze_commit)
        if st["status"] != "COMPLETE":
            reasons.append(f"promotion rule: {ev} acquisition cell "
                           f"{acq['cell_id']} not validated COMPLETE "
                           f"({st['status']}: {st['reasons'][:1]})")
            continue
        try:
            tips[ev] = _chain_tip(os.path.join(run_dir(fam_c_dir, acq),
                                               "EVIDENCE-CHAIN.jsonl"))
        except (ValueError, OSError, json.JSONDecodeError) as e:
            reasons.append(f"promotion rule: {ev} chain tip unreadable: {e}")
    got = r.get("acquisition_chain_tips") or {}
    for ev in ("T0", "T1"):
        if ev not in tips:
            continue
        if not isinstance(got.get(ev), str) or got.get(ev) != tips[ev]:
            reasons.append(f"promotion receipt binds {ev} tip "
                           f"{got.get(ev)!r} but the validated {ev} chain "
                           f"ends at {tips[ev]!r}")
    if tips.get("T0") == tips.get("T1") and tips.get("T0"):
        reasons.append("promotion rule: T0 and T1 must be distinct runs "
                       "(identical chain tips)")
    return _result(cell, reasons, True)


def _lock_state(fam_c_dir, cell, freeze_commit=None):
    """A11.5: completion of ONE CAPABILITY_LOCK harness-event cell. The
    lock cell is COMPLETE only when the immutable CAPABILITY_LOCK.json in
    the derived capability dir names the authorized per-universe capability
    id, every locked artifact hash verifies against the file present in
    that capability dir, and the lock binds the PROMOTION receipt of the
    SAME (block, family, universe) — promotion + locked reuse under
    workflow control; never a fabricated model-run record. See
    cell_state() for the full contract."""
    reasons = []
    capdir = capability_dir(fam_c_dir, cell["block"], cell["universe"],
                            cell["family"])
    if os.path.islink(capdir) or not os.path.isdir(capdir):
        return {"cell_id": cell["cell_id"], "status": "INCOMPLETE",
                "reasons": [f"capability dir absent at the derived path "
                            f"{capdir}"]}
    lp = os.path.join(capdir, "CAPABILITY_LOCK.json")
    if os.path.islink(lp) or not os.path.isfile(lp):
        return _result(cell, [f"no CAPABILITY_LOCK.json at {lp}"],
                       os.path.exists(lp))
    try:
        lock = _read_json(lp)
    except ValueError as e:
        return _result(cell, [f"capability lock unparsable: {e}"], True)
    if lock.get("capability_id") != cell["capability_id"]:
        reasons.append(f"capability lock capability_id "
                       f"{lock.get('capability_id')!r} != authorized "
                       f"{cell['capability_id']!r}")
    prom = _cell_for_event(fam_c_dir, cell, "PROMOTION")
    if prom is None:
        reasons.append("no PROMOTION cell in the order for "
                       f"{cell['block']}/{cell['family']}/"
                       f"{cell['universe']}")
    else:
        pst = cell_state(fam_c_dir, prom, freeze_commit)
        if pst["status"] != "COMPLETE":
            reasons.append("lock rule: PROMOTION cell not validated "
                           f"COMPLETE ({pst['status']}: "
                           f"{pst['reasons'][:1]})")
        else:
            want_sha = _sha256_file(os.path.join(run_dir(fam_c_dir, prom),
                                                 "PROMOTION-RECEIPT.json"))
            got_sha = lock.get("promotion_receipt_sha256")
            if not isinstance(got_sha, str) or got_sha != want_sha:
                reasons.append("capability lock does not bind the promotion "
                               f"receipt (promotion_receipt_sha256 "
                               f"{got_sha!r} != {want_sha!r})")
    # the immutable lock: every locked artifact hash verifies against the
    # bytes present in that capability dir.
    for name, want_sha in sorted((lock.get("artifacts") or {}).items()):
        ap = os.path.join(capdir, name)
        if os.path.islink(ap) or not os.path.isfile(ap):
            reasons.append(f"locked artifact missing at {ap}")
        elif _sha256_file(ap) != want_sha:
            reasons.append(f"locked artifact {name} hash mismatch: locked "
                           f"{want_sha[:12]} vs present "
                           f"{_sha256_file(ap)[:12]}")
    return _result(cell, reasons, True)


# ---------------------------------------------------------------------------
# A11.5 — production governance-event writers. The harness records a
# PROMOTION and a CAPABILITY_LOCK through these writers (once each, fail
# closed), so fixtures exercise the real machinery instead of hand-written
# JSON.
# ---------------------------------------------------------------------------

def emit_promotion_receipt(fam_c_dir, cell, t0_tip, t1_tip,
                           builder_identity=None):
    """Record the promotion of (block, universe, family)'s capability after
    its T0 and T1 acquisition runs validated COMPLETE. `t0_tip`/`t1_tip`
    are the REAL link_hash tips of those two evidence chains, taken from
    the validated runs; the receipt binds them so the validator can
    re-derive the same tips from the on-disk chains. Writes once: a second
    promotion of the same cell refuses (promotion + locked reuse under
    workflow control, never a re-promotion). Returns the receipt path."""
    for tag, tip in (("T0", t0_tip), ("T1", t1_tip)):
        if not isinstance(tip, str) or len(tip) != 64:
            raise ValueError(f"PROMOTION-DENY {tag} chain tip must be a "
                             f"64-hex link_hash, got {tip!r}")
    want = capability_id(cell["block"], cell["universe"], cell["family"])
    if cell["capability_id"] != want:
        raise ValueError(f"PROMOTION-DENY cell capability_id "
                         f"{cell['capability_id']!r} != derived {want!r}")
    d = ensure_namespace(fam_c_dir, cell["block"], cell["universe"],
                         cell["family"],
                         tail=("runs", cell["cell_id"]))
    rp = os.path.join(d, "PROMOTION-RECEIPT.json")
    if os.path.exists(rp):
        raise PermissionError("PROMOTION-DENY receipt already exists "
                              "(no repromotion)")
    receipt = {"event": "PROMOTION", "cell_id": cell["cell_id"],
               "block": cell["block"], "family": cell["family"],
               "universe": cell["universe"],
               "capability_id": cell["capability_id"],
               "acquisition_chain_tips": {"T0": t0_tip, "T1": t1_tip},
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime())}
    if builder_identity:
        receipt["builder_identity"] = dict(builder_identity)
    with open(rp, "w") as f:
        json.dump(receipt, f, indent=1)
    return rp


def emit_capability_lock(fam_c_dir, cell, artifact_paths=(),
                         version="1.0.0", manifest_obj=None,
                         training_receipts=(), builder_identity=None):
    """Seal (block, universe, family)'s capability: write the immutable
    CAPABILITY_LOCK.json in the derived capability dir, binding every
    artifact's exact hash, the capability manifest, and the sha256 of the
    PROMOTION receipt of the SAME universe (promotion + locked reuse under
    workflow control). `artifact_paths` are the capability files already
    present in the capability dir. Delegates to lock.promote (production
    machinery); refuses once the lock exists. Returns the lock path."""
    want = capability_id(cell["block"], cell["universe"], cell["family"])
    if cell["capability_id"] != want:
        raise ValueError(f"LOCK-DENY cell capability_id "
                         f"{cell['capability_id']!r} != derived {want!r}")
    capdir = ensure_namespace(fam_c_dir, cell["block"], cell["universe"],
                              cell["family"], tail=("capability",))
    prom = _cell_for_event(fam_c_dir, cell, "PROMOTION")
    if prom is None:
        raise ValueError("LOCK-DENY no PROMOTION cell in the order for "
                         f"{cell['block']}/{cell['universe']}/"
                         f"{cell['family']}")
    prp = os.path.join(run_dir(fam_c_dir, prom), "PROMOTION-RECEIPT.json")
    if os.path.islink(prp) or not os.path.isfile(prp):
        raise PermissionError(f"LOCK-DENY no promotion receipt at {prp} "
                              "(promote the universe before locking it)")
    arts = [os.path.join(capdir, os.path.basename(p)) for p in artifact_paths]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lock import promote as _lock_promote
    return _lock_promote(
        capdir, cell["capability_id"], version, arts,
        manifest_obj if manifest_obj is not None else {},
        training_receipts or [], builder_identity or {},
        promotion_receipt_sha256=_sha256_file(prp))


def completed_cells(fam_c_dir, freeze_commit=None, expansion=None):
    """A11.6: cell ids of cells whose VALIDATED state is COMPLETE.

    Consumes cell_state(), never manifest presence: a malformed, tampered,
    dangling, dev or inadmissible run does not advance the frozen order.
    Scans the universe state trees only (the derived namespace), so a stray
    manifest elsewhere in Fam-C cannot mark a cell done.
    """
    exp = expansion if expansion is not None else load_expansion(fam_c_dir)
    done = {}
    for c in exp["cells"]:
        st = cell_state(fam_c_dir, c, freeze_commit)
        if st["status"] == "COMPLETE":
            done[c["cell_id"]] = os.path.basename(run_dir(fam_c_dir, c))
    return done


def load_expansion(fam_c_dir):
    fp = os.path.join(fam_c_dir, "ORDER-EXPANSION.json")
    if not os.path.exists(fp):
        raise ValueError("ORDER-DENY: ORDER-EXPANSION.json missing "
                         "(mint it from ORDER.md; never hand-edit)")
    exp = json.load(open(fp))
    for key in ("cells", "families", "downstream_tasks", "blocks"):
        if key not in exp:
            raise ValueError(f"ORDER-DENY: ORDER-EXPANSION.json lacks {key}")
    return exp


def verify_expansion(fam_c_dir):
    """Re-derive from ORDER.md and compare. Returns findings (empty=ok)."""
    fp = os.path.join(fam_c_dir, "ORDER-EXPANSION.json")
    op = os.path.join(fam_c_dir, "ORDER.md")
    if not os.path.exists(fp):
        return ["ORDER-EXPANSION.json missing (mint from ORDER.md)"]
    if not os.path.exists(op):
        return ["ORDER.md missing"]
    fresh = expand(open(op).read())
    stored = json.load(open(fp))
    out = []
    if stored.get("cells") != fresh["cells"]:
        out.append("ORDER-EXPANSION.json cells differ from ORDER.md "
                   "expansion (re-mint; never hand-edit)")
    for key in ("families", "blocks", "events", "acquisition_events",
                "downstream_tasks", "universes", "capability_universes",
                "seed", "order_sha256", "total_cells",
                "total_model_calls"):
        if stored.get(key) != fresh[key]:
            out.append(f"ORDER-EXPANSION.json {key} differs from ORDER.md "
                       f"({stored.get(key)!r} != {fresh[key]!r})")
    return out
