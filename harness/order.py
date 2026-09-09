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


def cell_state(fam_c_dir, cell, freeze_commit=None, _exp=None):
    """Validate ONE cell's completion. Returns
    {"status": "COMPLETE"|"INCOMPLETE"|"INADMISSIBLE", "reasons": [...]}.

    A12.1 (audit round-2 #11): completion is ALSO order-admissible — a cell
    whose artifacts validate is still NOT COMPLETE if any earlier cell in the
    frozen expansion is not COMPLETE, so a preplanted future promotion/lock
    (or another family's governance artifact minted out of turn) can never
    satisfy state. `_local_state()` holds the kind dispatch below.

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
    st = _local_state(fam_c_dir, cell, freeze_commit)
    if st["status"] != "COMPLETE":
        return st
    try:
        exp = _exp if _exp is not None else load_expansion(fam_c_dir)
    except (ValueError, OSError) as e:
        return _result(cell, [f"ORDER-DENY expansion unreadable: {e}"], True)
    blockers = []
    for c in exp["cells"]:
        if c["index"] >= cell["index"]:
            break
        if c["cell_id"] == cell["cell_id"]:
            continue
        earlier = _local_state(fam_c_dir, c, freeze_commit)
        if earlier["status"] != "COMPLETE":
            blockers.append(f"{c['cell_id']} "
                            f"({c['block']}/{c['family']}/{c['event']}/"
                            f"{c['universe']})={earlier['status']}")
    if blockers:
        return _result(cell, [
            "ORDER-INADMISSIBLE: cell " + cell["cell_id"] + " validates "
            "locally but cannot be COMPLETE while " + str(len(blockers))
            + " earlier cell(s) are not: " + "; ".join(blockers[:3])], True)
    return st


def _local_state(fam_c_dir, cell, freeze_commit=None):
    """Kind-dispatched validation of ONE cell, WITHOUT the order guard.
    Governance validators (promotion/lock) use this for their T0/T1 source
    cells so order recursion terminates."""
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


def _reuse_ledger_reasons(run_dir, m, fam_c_dir=None, cell=None):
    """A12.3 (audit round-2 #13): the reuse ledger is EVIDENCE, not a claim.

    A wired run's reuse record must exist and agree with the arrival's own
    `decision` and with the path the runtime actually executed. A record
    that reports reuse when the arrival chose fresh (or fresh when it chose
    the capability) is refused; a fresh decision made WITH a capability
    available must be recorded as an explicit REJECT with a reason.

    Grade-aware consumption (A12.2): a lock minted at `estimand` grade may
    only be consumed by a run that itself declares estimand grade. H1
    harness-validation runs are never estimand data, so an estimand-grade
    lock is not consumable on the current surface (estimand runs = 0)."""
    out = []
    ap = os.path.join(run_dir, "arrival.json")
    try:
        arrival = _read_json(ap)
    except (ValueError, OSError) as e:
        return [f"reuse-ledger: arrival unreadable: {e}"]
    decision = arrival.get("decision")
    if decision not in ("use_capability", "fresh"):
        return [f"reuse-ledger: arrival decision {decision!r} is not a "
                "contract decision; no ledger semantics derivable"]
    name = m.get("reuse_record")
    if not isinstance(name, str) or not name:
        return [f"reuse-ledger: wired run with decision {decision!r} has no "
                "reuse_record; every wired cell must record its decision"]
    p = os.path.join(run_dir, os.path.basename(name))
    if os.path.islink(p) or not os.path.isfile(p):
        return [f"reuse-ledger: record {name} absent at {p}"]
    try:
        r = _read_json(p)
    except ValueError as e:
        return [f"reuse-ledger: record unparsable: {e}"]
    missing = [f for f in ("capability_available", "capability_selected",
                           "capability_loaded", "capability_invoked",
                           "capability_output_consumed", "reuse_rejected")
               if f not in r]
    if missing:
        return ["reuse-ledger: record missing field(s): "
                + ", ".join(missing)]
    if decision == "use_capability":
        if r.get("capability_selected") is not True:
            out.append("reuse-ledger: arrival chose use_capability but the "
                       "record reports capability_selected=false (ledger "
                       "contradicts the executed path)")
        for f in ("capability_available", "capability_loaded",
                  "capability_invoked", "capability_output_consumed"):
            if r.get(f) is not True:
                out.append(f"reuse-ledger: use_capability requires {f}=true")
        if r.get("reuse_rejected") is True:
            out.append("reuse-ledger: use_capability cannot be "
                       "reuse_rejected")
        want_id = m.get("capability_id")
        if r.get("selected_capability_id") != want_id:
            out.append("reuse-ledger: selected_capability_id "
                       f"{r.get('selected_capability_id')!r} != the cell's "
                       f"capability {want_id!r}")
        cap = m.get("capability") or {}
        if cap.get("engine_sha256") and \
                r.get("selected_capability_hash") != cap["engine_sha256"]:
            out.append("reuse-ledger: selected_capability_hash "
                       f"{r.get('selected_capability_hash')!r} != the locked "
                       f"engine hash {cap['engine_sha256']!r} the run consumed")
    else:  # fresh
        if (r.get("capability_selected") is True
                or r.get("capability_loaded") is True
                or r.get("capability_invoked") is True
                or r.get("capability_output_consumed") is True):
            out.append("reuse-ledger: arrival chose fresh but the record "
                       "reports the capability was selected/loaded/invoked/"
                       "consumed (ledger contradicts the executed path)")
        if r.get("capability_available") is True:
            if r.get("reuse_rejected") is not True:
                out.append("reuse-ledger: a fresh decision with a capability "
                           "available must be recorded as reuse_rejected "
                           "(the REJECT path, never a silent fresh)")
            elif not (isinstance(r.get("reuse_rejection_reason"), str)
                      and r["reuse_rejection_reason"].strip()):
                out.append("reuse-ledger: reuse_rejected requires a recorded "
                           "rejection reason")
        elif r.get("reuse_rejected") is True:
            out.append("reuse-ledger: no capability was available, so the run "
                       "cannot be reuse_rejected")
    if fam_c_dir is not None and cell is not None and \
            r.get("capability_output_consumed") is True:
        lp = os.path.join(capability_dir(fam_c_dir, cell["block"],
                                         cell["universe"], cell["family"]),
                          "CAPABILITY_LOCK.json")
        try:
            grade = _read_json(lp).get("evidence_grade")
        except (ValueError, OSError):
            grade = None
        if grade == "estimand" and m.get("evidence_grade") != "estimand":
            out.append(
                "reuse-ledger: capability consumed from an estimand-grade "
                "lock by a run that does not declare estimand grade "
                f"({m.get('evidence_grade', 'harness-validation')}); H1 runs "
                "are harness-validation evidence, never estimand data")
    return out


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
    # A12.3: the reuse ledger must agree with the arrival's executed decision
    # (and A12.2 grade-aware consumption: an estimand-grade lock is not
    # consumable by a harness-validation run).
    reasons.extend(_reuse_ledger_reasons(d, m, fam_c_dir=fam_c_dir, cell=cell))
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
    """A12.1: completion of ONE PROMOTION harness-event cell.

    COMPLETE only when — with no fabricated model-run record — the two REAL
    acquisition runs of the SAME (block, family, universe) (its T0 and T1,
    each validated COMPLETE by the model-run contract) produced exactly the
    chain tips the receipt binds, AND the receipt carries full causal
    provenance: the candidate sha256 is RE-DERIVED here from the T0 run's own
    arrival payload, the receipt-named artifact hashes verify on disk, the
    semantic core / contract / lock SHAs / source cells / authorization
    record are all cross-checked against the frozen instance. See
    cell_state() for the full contract."""
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
    tips, runs = {}, {}
    for ev in ("T0", "T1"):
        acq = _cell_for_event(fam_c_dir, cell, ev)
        if acq is None:
            reasons.append(f"no {ev} cell in the order for "
                           f"{cell['block']}/{cell['family']}/"
                           f"{cell['universe']}")
            continue
        st = _local_state(fam_c_dir, acq, freeze_commit)
        if st["status"] != "COMPLETE":
            reasons.append(f"promotion rule: {ev} acquisition cell "
                           f"{acq['cell_id']} not validated COMPLETE "
                           f"({st['status']}: {st['reasons'][:1]})")
            continue
        runs[ev] = run_dir(fam_c_dir, acq)
        try:
            tips[ev] = _chain_tip(os.path.join(runs[ev],
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
    reasons.extend(_promotion_provenance_reasons(fam_c_dir, cell, r, runs))
    return _result(cell, reasons, True)


def _promotion_provenance_reasons(fam_c_dir, cell, r, runs):
    """A12.1 causal-provenance gate. Everything the lock will later bind is
    re-derived HERE from committed evidence; a receipt that merely asserts
    provenance (or names artifacts copied in from elsewhere) is refused."""
    out = []
    src = r.get("source_cells")
    if not isinstance(src, dict) or set(src) != {"T0", "T1"}:
        out.append("promotion provenance: receipt names no T0/T1 source cells")
    else:
        for ev in ("T0", "T1"):
            if ev in runs and src.get(ev) != os.path.basename(runs[ev]):
                out.append(f"promotion provenance: source_cells[{ev}] "
                           f"{src.get(ev)!r} != the validated {ev} run "
                           f"{os.path.basename(runs[ev])!r}")
    cand = r.get("candidate") or {}
    want_sha = None
    if "T0" in runs:
        try:
            arrival = _read_json(os.path.join(runs["T0"], "arrival.json"))
            payload = arrival.get("execution_payload") or {}
            s = payload.get("solver_py")
            if not isinstance(s, str) or not s.strip():
                out.append("promotion provenance: T0 arrival carries no "
                           "execution_payload.solver_py candidate")
            else:
                want_sha = hashlib.sha256(s.encode()).hexdigest()
                if arrival.get("decision") != "fresh":
                    out.append("promotion provenance: T0 decision "
                               f"{arrival.get('decision')!r} != 'fresh'")
                if cand.get("arrival_sha256") != _sha256_file(
                        os.path.join(runs["T0"], "arrival.json")):
                    out.append("promotion provenance: candidate "
                               "arrival_sha256 does not match the T0 "
                               "arrival artifact")
        except (ValueError, OSError) as e:
            out.append(f"promotion provenance: T0 arrival unreadable: {e}")
    if want_sha is not None and cand.get("sha256") != want_sha:
        out.append("promotion provenance: receipt candidate "
                   f"{str(cand.get('sha256'))[:12]} != the sha256 of the T0 "
                   f"arrival payload {want_sha[:12]} (candidate must be "
                   "causally rooted in this universe's own acquisition)")
    if want_sha is None and not out:
        out.append("promotion provenance: candidate sha256 not derivable")
    # A12b.2: the T1 chain must commit exactly one candidate-validation
    # event for this SAME frozen candidate — re-derived HERE from the
    # committed chain, never trusted from the receipt. A T1 that never
    # validated can never promote, even with a well-formed candidate
    # root (the controller enforces the same rule; this validator
    # re-checks it so a forged receipt cannot pass cell state).
    if "T1" not in runs:
        out.append("promotion provenance: T1 acquisition run not "
                   "validated (candidate validation not re-derivable)")
    elif want_sha is not None:
        try:
            _t1_links = [json.loads(line)
                         for line in open(os.path.join(
                             runs["T1"], "EVIDENCE-CHAIN.jsonl"))
                         if line.strip()]
        except (ValueError, OSError) as e:
            out.append("promotion provenance: T1 evidence chain "
                       f"unreadable: {e}")
            _t1_links = None
        if _t1_links is not None:
            _cvs = [l for l in _t1_links
                    if l.get("kind") == "candidate-validation"]
            _cv = _cvs[0].get("payload") or {} if len(_cvs) == 1 else {}
            # A12c D3: re-derive the same nine-field fail-closed predicate
            # from the committed chain (no trust in the receipt).
            _cv_reasons = []
            if len(_cvs) != 1:
                _cv_reasons.append(
                    f"need exactly one candidate-validation event, got "
                    f"{len(_cvs)}")
            else:
                for _f in ("candidate_sha256", "executed_sha256",
                           "adapter_sha256", "candidate_output_sha256",
                           "checker_sha256", "truth_sha256",
                           "checker_returncode", "validation_verdict",
                           "validated"):
                    if _cv.get(_f) is None:
                        _cv_reasons.append(f"no {_f}")
                for _f in ("candidate_sha256", "executed_sha256",
                           "adapter_sha256", "candidate_output_sha256",
                           "checker_sha256", "truth_sha256"):
                    _v = _cv.get(_f)
                    if _v is not None and not (
                            isinstance(_v, str) and len(_v) == 64):
                        _cv_reasons.append(f"no 64-hex {_f}")
                    elif isinstance(_v, str) and len(_v) == 64:
                        try:
                            int(_v, 16)
                        except ValueError:
                            _cv_reasons.append(f"no 64-hex {_f}")
                if (_cv.get("candidate_sha256") is not None
                        and _cv.get("candidate_sha256") != want_sha):
                    _cv_reasons.append("candidate_sha256 != frozen T0 sha")
                if (_cv.get("executed_sha256") is not None
                        and _cv.get("executed_sha256") != want_sha):
                    _cv_reasons.append("executed_sha256 != frozen T0 sha")
                if (_cv.get("checker_returncode") is not None
                        and _cv.get("checker_returncode") != 0):
                    _cv_reasons.append("checker_returncode != 0")
                if (_cv.get("validation_verdict") is not None
                        and _cv.get("validation_verdict") != "ship"):
                    _cv_reasons.append("validation_verdict != ship")
                if (_cv.get("validated") is not None
                        and _cv.get("validated") is not True):
                    _cv_reasons.append("validated is not True")
            if _cv_reasons:
                out.append("promotion provenance: T1 chain carries no "
                           "valid candidate-validation event for the "
                           "frozen candidate "
                           f"({'; '.join(_cv_reasons)[:220]}; a T1 with no "
                           "candidate-validation event can never promote)")
            else:
                _rec_cv = cand.get("t1_validation") or {}
                for _k in ("candidate_sha256", "executed_sha256",
                           "adapter_sha256", "candidate_output_sha256",
                           "checker_sha256", "truth_sha256",
                           "checker_returncode", "validation_verdict",
                           "validated"):
                    if _rec_cv.get(_k) != _cv.get(_k):
                        out.append("promotion provenance: receipt candidate "
                                   f"t1_validation[{_k}] != the committed "
                                   "T1 chain event "
                                   f"({_rec_cv.get(_k)!r} != {_cv.get(_k)!r})")
                        break
    # A12c slice B: the producer authors its own contract text from
    # visible information, so the receipt's contract is cross-checked
    # against the FROZEN T0 arrival declaration — verbatim equality on
    # semantic_core/preconditions/limitations, the same declaration the
    # promotion controller used (one source of truth) — never against
    # hidden capability text. A receipt that rewrites the producer's declared text
    # is refused here, exactly as a non-frozen contract was before.
    # A12c slice C2 re-derives the conformance verdict from the same
    # frozen declaration below (`_t0_lim`).
    _t0_lim = None
    sc = r.get("semantic_core")
    if not isinstance(sc, str) or not sc.strip():
        out.append("promotion provenance: receipt has no semantic_core")
    elif "T0" not in runs:
        out.append("promotion provenance: T0 acquisition run not "
                   "validated (contract cross-check not derivable)")
    else:
        try:
            _t0_arrival = _read_json(os.path.join(runs["T0"],
                                                  "arrival.json"))
            _t0_declared = ((_t0_arrival.get("execution_payload") or {})
                            .get("capability_contract"))
        except (ValueError, OSError) as e:
            _t0_declared = None
            out.append("promotion provenance: T0 arrival unreadable for "
                       f"the contract cross-check: {e}")
        if isinstance(_t0_declared, dict):
            _t0_lim = _t0_declared.get("limitations")
            for _k in ("semantic_core", "preconditions", "limitations"):
                if r.get(_k) != _t0_declared.get(_k):
                    out.append(f"promotion provenance: receipt {_k} is not "
                               f"the frozen T0 arrival declaration (the "
                               f"promoted contract must be the producer's "
                               f"own declared text, verbatim)")
                    break
        elif _t0_declared is not None:
            out.append("promotion provenance: the frozen T0 arrival "
                       "declares no producer capability contract")
    if isinstance(sc, str) and r.get("semantic_core_sha256") != \
            hashlib.sha256(sc.encode()).hexdigest():
        out.append("promotion provenance: semantic_core_sha256 mismatch")
    for f in ("preconditions", "limitations"):
        if not isinstance(r.get(f), list) or not all(
                isinstance(x, str) for x in r[f]):
            out.append(f"promotion provenance: {f} must be a list of strings")
    # A12b.6 actual-contract conformance: the receipt carries the
    # producer's ACTUAL limitations plus the derived verdict (the lock
    # records exactly these; the conformance check reads the lock only,
    # never hidden capability text). limitation_present must equal
    # bool(limitations); a receipt that claims discrimination
    # (non_discriminating False) while the limitation is absent is
    # refused — empty limitations never silently lock as discriminating.
    _lim = r.get("limitations")
    _lp = r.get("limitation_present")
    _nd = r.get("non_discriminating")
    _cause = r.get("conformance_cause")
    if not isinstance(_lp, bool) or _lp != bool(_lim):
        out.append("promotion provenance: limitation_present must be "
                   "bool(limitations)")
    if not isinstance(_nd, bool):
        out.append("promotion provenance: non_discriminating must be a "
                   "boolean")
    if not (isinstance(_cause, str) and _cause.strip()):
        out.append("promotion provenance: conformance_cause must be a "
                   "nonempty committed reason")
    if isinstance(_lim, list) and not _lim and _nd is False:
        out.append("promotion provenance: receipt claims a discriminating "
                   "T4 while the locked contract carries no limitations")
    # A12c slice C2 (auditor P0 #6): RE-DERIVE the conformance verdict
    # from the T0 arrival declaration + the governed map (never trust
    # the receipt): recomputed non_discriminating, supported_t4_ids,
    # and conformance_map_sha256 must all equal the receipt's;
    # mismatch -> deny naming the field. Both surfaces resolve through
    # the SINGLE shared implementation (harness/conformance.py); there
    # is no private predicate table here.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conformance import load as _conf_load
    from conformance import verdict as _conf_verdict
    try:
        _cmap = _conf_load(fam_c_dir)
        _cmap_err = None
    except Exception as e:                                # noqa: BLE001
        _cmap, _cmap_err = None, str(e)
    if _cmap_err is not None:
        out.append("promotion provenance: governed T4-CONFORMANCE.json "
                   f"refuses: {_cmap_err}")
    elif _t0_lim is None:
        out.append("promotion provenance: T0 arrival declares no "
                   "limitation list (conformance verdict not "
                   "re-derivable)")
    else:
        try:
            _re = _conf_verdict(cell["family"], _t0_lim, _cmap)
            _re_err = None
        except Exception as e:                            # noqa: BLE001
            _re, _re_err = None, str(e)
        if _re_err is not None:
            out.append("promotion provenance: conformance re-derivation "
                       f"refuses: {_re_err}")
        else:
            if r.get("non_discriminating") != _re["non_discriminating"]:
                out.append(
                    "promotion provenance: receipt non_discriminating "
                    f"{r.get('non_discriminating')!r} != re-derived "
                    f"{_re['non_discriminating']!r} (recomputed "
                    f"supported_t4_ids {_re['supported_t4_ids']!r} from "
                    f"the T0 arrival declaration + governed map do not "
                    f"support {cell['family']}'s T4 as claimed)")
            if r.get("supported_t4_ids") != _re["supported_t4_ids"]:
                out.append(
                    "promotion provenance: receipt supported_t4_ids "
                    f"{r.get('supported_t4_ids')!r} != recomputed "
                    f"{_re['supported_t4_ids']!r} from the T0 arrival "
                    f"declaration + governed map")
            if r.get("conformance_map_sha256") != \
                    _re["conformance_map_sha256"]:
                out.append(
                    "promotion provenance: receipt "
                    f"conformance_map_sha256 "
                    f"{str(r.get('conformance_map_sha256'))[:12]} != the "
                    f"live governed map "
                    f"{_re['conformance_map_sha256'][:12]} (the map was "
                    f"edited without re-minting the promotion)")
    if r.get("evidence_grade") not in ("estimand", "harness-validation"):
        out.append("promotion provenance: evidence_grade "
                   f"{r.get('evidence_grade')!r} invalid")
    if r.get("evidence_grade") == "estimand" and r.get("t4_ratified") is not True:
        out.append("promotion provenance: estimand promotion requires a "
                   "RATIFIED auditor T4 semantic id")
    if not (isinstance(r.get("t4_semantic_id"), str)
            and r["t4_semantic_id"].strip()):
        out.append("promotion provenance: t4_semantic_id missing")
    # t4_ratified is DERIVED from the frozen governed registry, never
    # asserted: flipping the flag on an unratified id must not upgrade the
    # receipt. Both surfaces resolve through the SINGLE shared resolver
    # (harness/t4_ids.py); there is no private registry read here.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from t4_ids import resolve as _t4_resolve
    try:
        reg_id, _reg_ratified = _t4_resolve(
            fam_c_dir, cell["family"], r.get("semantic_core_sha256") or "",
            r.get("evidence_grade"))
        reg_err = None
    except PermissionError as e:
        reg_id, reg_err = None, str(e)
    if r.get("t4_ratified") not in (True, False):
        out.append("promotion provenance: t4_ratified must be a boolean")
    elif reg_err is not None:
        out.append("promotion provenance: " + reg_err)
    elif r["t4_ratified"]:
        if not reg_id or r.get("t4_semantic_id") != reg_id:
            out.append("promotion provenance: t4_ratified claims a RATIFIED "
                       "auditor T4 semantic id but none is registered for "
                       f"{cell['capability_id']} in T4-SEMANTIC-IDS.json")
    elif isinstance(r.get("t4_semantic_id"), str) and \
            not r["t4_semantic_id"].startswith("T4-UNRATIFIED-"):
        out.append("promotion provenance: t4_ratified is false but "
                   f"t4_semantic_id {r['t4_semantic_id']!r} is not marked "
                   "T4-UNRATIFIED-")
    # frozen lock SHAs must be the locks actually on disk
    for key, name in (("protocol_lock_sha256", "PROTOCOL-LOCK.json"),
                      ("execution_lock_sha256", "EXECUTION-LOCK.json")):
        p = os.path.join(fam_c_dir, name)
        if not os.path.isfile(p):
            out.append(f"promotion provenance: frozen {name} absent")
        elif r.get(key) != _sha256_file(p):
            out.append(f"promotion provenance: {key} does not match the "
                       f"on-disk {name}")
    # the receipt's artifact map must verify against the capability dir
    arts = r.get("artifacts")
    capdir = capability_dir(fam_c_dir, cell["block"], cell["universe"],
                            cell["family"])
    if not isinstance(arts, dict) or not arts:
        out.append("promotion provenance: receipt names no artifacts")
    else:
        for name, sha in sorted(arts.items()):
            if os.path.basename(name) != name:
                out.append(f"promotion provenance: artifact {name!r} is not a "
                           f"bare filename")
                continue
            p = os.path.join(capdir, name)
            if os.path.islink(p) or not os.path.isfile(p):
                out.append(f"promotion provenance: receipt names {name} but "
                           f"it is absent from the capability dir")
            elif _sha256_file(p) != sha:
                out.append(f"promotion provenance: artifact {name} hash "
                           f"{str(sha)[:12]} != present "
                           f"{_sha256_file(p)[:12]}")
    # the authorization record: this receipt was emitted at the frozen event
    # index for this cell (a preplanted future receipt names another index)
    auth = r.get("authorization")
    if not isinstance(auth, dict):
        out.append("promotion provenance: no authorization record")
    else:
        if auth.get("event_index") != cell["index"]:
            out.append("promotion provenance: authorization event_index "
                       f"{auth.get('event_index')!r} != this cell's frozen "
                       f"index {cell['index']!r}")
        try:
            exp_sha = _sha256_file(os.path.join(fam_c_dir,
                                                "ORDER-EXPANSION.json"))
            if auth.get("order_sha256") != exp_sha:
                out.append("promotion provenance: authorization order_sha256 "
                           "does not match the frozen expansion")
        except OSError as e:
            out.append(f"promotion provenance: expansion unreadable: {e}")
        done = auth.get("done_cells_at_emit")
        if not isinstance(done, list) or cell["cell_id"] in done:
            out.append("promotion provenance: authorization "
                       "done_cells_at_emit malformed (or already contains "
                       "this cell)")
    return out


def _lock_state(fam_c_dir, cell, freeze_commit=None):
    """A12.2: completion of ONE CAPABILITY_LOCK harness-event cell.

    COMPLETE only when the immutable CAPABILITY_LOCK.json passes the FULL
    estimand-aware contract (lock.verify_lock: block/universe/family,
    capability id/version, T0+T1 chain tips, source cells, producer
    identity, protocol/execution lock SHAs, artifact hashes,
    semantic_core/preconditions/limitations, auditor T4 semantic id,
    evidence grade, candidate root + provenance sha) — a legacy lock is
    LOCK-INADMISSIBLE, never silently reusable — AND the lock binds the
    PROMOTION receipt of the SAME universe with an artifact map IDENTICAL to
    the receipt's (the lock writer may only lock hashes the validated
    promotion named)."""
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
    rec, want_sha = None, None
    prom = _cell_for_event(fam_c_dir, cell, "PROMOTION")
    if prom is None:
        reasons.append("no PROMOTION cell in the order for "
                       f"{cell['block']}/{cell['family']}/"
                       f"{cell['universe']}")
    else:
        pst = _local_state(fam_c_dir, prom, freeze_commit)
        if pst["status"] != "COMPLETE":
            reasons.append("lock rule: PROMOTION cell not validated "
                           f"COMPLETE ({pst['status']}: "
                           f"{pst['reasons'][:1]})")
        else:
            rp = os.path.join(run_dir(fam_c_dir, prom),
                              "PROMOTION-RECEIPT.json")
            want_sha = _sha256_file(rp)
            try:
                rec = _read_json(rp)
            except ValueError as e:
                reasons.append(f"lock rule: promotion receipt unreadable: {e}")
    expect = {"capability_id": cell["capability_id"],
              "block": cell["block"], "universe": cell["universe"],
              "family": cell["family"]}
    if want_sha:
        expect["promotion_receipt_sha256"] = want_sha
    if isinstance(rec, dict):
        cand = (rec.get("candidate") or {}).get("sha256")
        if isinstance(cand, str):
            expect["candidate_sha256"] = cand
            if lock.get("candidate_provenance_sha256") != want_sha:
                reasons.append("lock rule: candidate_provenance_sha256 "
                               f"{lock.get('candidate_provenance_sha256')!r} "
                               f"!= the promotion receipt sha {want_sha!r}")
        for key in ("protocol_lock_sha256", "execution_lock_sha256",
                    "evidence_grade", "semantic_core", "t4_semantic_id",
                    "limitation_present", "non_discriminating",
                    "conformance_cause", "supported_t4_ids",
                    "conformance_map_sha256"):
            if key in rec:
                expect[key] = rec[key]
        for key in ("acquisition_chain_tips", "source_cells"):
            if key in rec:
                expect[key] = rec[key]
        if lock.get("preconditions") != rec.get("preconditions") or \
                lock.get("limitations") != rec.get("limitations"):
            reasons.append("lock rule: preconditions/limitations differ from "
                           "the validated promotion receipt")
        rec_arts = rec.get("artifacts") or {}
        lock_arts = lock.get("artifacts") or {}
        if set(rec_arts) != set(lock_arts):
            reasons.append("lock rule: locked artifact set "
                           f"{sorted(lock_arts)} != receipt-named set "
                           f"{sorted(rec_arts)} (a lock may only lock hashes "
                           "the validated promotion named)")
        else:
            for name in sorted(rec_arts):
                if lock_arts.get(name) != rec_arts.get(name):
                    reasons.append(f"lock rule: artifact {name} hash differs "
                                   "from the receipt")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lock import verify_lock as _verify_lock
    # A12c slice C2: bind the lock's conformance verdict to the LIVE
    # governed map bytes (a map edited without re-minting the lock
    # refuses here, naming the sha mismatch).
    reasons.extend(_verify_lock(lock, expect=expect, fam_c_dir=fam_c_dir))
    # the immutable lock: every locked artifact hash verifies against the
    # bytes present in that capability dir.
    for name, want in sorted((lock.get("artifacts") or {}).items()):
        ap = os.path.join(capdir, name)
        if os.path.islink(ap) or not os.path.isfile(ap):
            reasons.append(f"locked artifact missing at {ap}")
        elif _sha256_file(ap) != want:
            reasons.append(f"locked artifact {name} hash mismatch: locked "
                           f"{str(want)[:12]} vs present "
                           f"{_sha256_file(ap)[:12]}")
    return _result(cell, reasons, True)


# ---------------------------------------------------------------------------
# A11.5 — production governance-event writers. The harness records a
# PROMOTION and a CAPABILITY_LOCK through these writers (once each, fail
# closed), so fixtures exercise the real machinery instead of hand-written
# JSON.
# ---------------------------------------------------------------------------

def emit_promotion_receipt(fam_c_dir, cell, t0_tip, t1_tip,
                           builder_identity=None, provenance=None):
    """Record the promotion of (block, universe, family)'s capability after
    its T0 and T1 acquisition runs validated COMPLETE. `t0_tip`/`t1_tip`
    are the REAL link_hash tips of those two evidence chains, taken from
    the validated runs; the receipt binds them so the validator can
    re-derive the same tips from the on-disk chains. Writes once: a second
    promotion of the same cell refuses (promotion + locked reuse under
    workflow control, never a re-promotion). Returns the receipt path.

    A12.1: the writer itself calls authorize_event() with the REAL
    completed-cell set, so a governance artifact can never be minted out of
    frozen order (audit round-2 #11). `provenance` is the controller-derived
    causal record (candidate root, artifact hashes, contract, lock SHAs,
    authorization); without it the receipt is a bare tip binding and the
    promotion validator will refuse it."""
    for tag, tip in (("T0", t0_tip), ("T1", t1_tip)):
        if not isinstance(tip, str) or len(tip) != 64:
            raise ValueError(f"PROMOTION-DENY {tag} chain tip must be a "
                             f"64-hex link_hash, got {tip!r}")
    want = capability_id(cell["block"], cell["universe"], cell["family"])
    if cell["capability_id"] != want:
        raise ValueError(f"PROMOTION-DENY cell capability_id "
                         f"{cell['capability_id']!r} != derived {want!r}")
    if cell.get("event") != "PROMOTION":
        raise ValueError(f"PROMOTION-DENY cell event {cell.get('event')!r} "
                         "is not PROMOTION")
    try:
        exp = load_expansion(fam_c_dir)
        done = completed_cells(fam_c_dir, None, exp)
        auth_cell, reasons = authorize_event(
            exp, cell["block"], cell["family"], "PROMOTION",
            cell["universe"], done)
    except (ValueError, OSError) as e:
        raise PermissionError(f"PROMOTION-DENY authorization unreadable: {e}")
    if reasons:
        raise PermissionError(reasons[0])
    if auth_cell is None or auth_cell["cell_id"] != cell["cell_id"]:
        raise PermissionError("PROMOTION-DENY authorize_event resolved a "
                              "different cell")
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
    if provenance:
        for k, v in provenance.items():
            if k in ("event", "cell_id", "block", "family", "universe",
                     "capability_id", "acquisition_chain_tips"):
                continue  # never let provenance overwrite the bound fields
            receipt[k] = v
    with open(rp, "w") as f:
        json.dump(receipt, f, indent=1)
    return rp


def emit_capability_lock(fam_c_dir, cell, artifact_paths=(),
                         version="1.0.0", manifest_obj=None,
                         training_receipts=(), builder_identity=None,
                         receipt=None, receipt_path=None):
    """Seal (block, universe, family)'s capability: write the immutable
    estimand-aware CAPABILITY_LOCK.json in the derived capability dir.

    A12.2: every lock field is taken from the VALIDATED PROMOTION receipt
    (`receipt`/`receipt_path`) — block/universe/family, capability id,
    acquisition chain tips, source cells, producer identity, protocol and
    execution lock SHAs, semantic core / preconditions / limitations, the
    auditor T4 semantic id, evidence grade, candidate root and the
    provenance sha — and `artifact_paths` must name exactly the artifacts
    that receipt names. The operator cannot widen the lock: a file merely
    present in the capability dir is not lockable. Refuses once the lock
    exists. Returns the lock path."""
    want = capability_id(cell["block"], cell["universe"], cell["family"])
    if cell["capability_id"] != want:
        raise ValueError(f"LOCK-DENY cell capability_id "
                         f"{cell['capability_id']!r} != derived {want!r}")
    if receipt is None:
        prom = _cell_for_event(fam_c_dir, cell, "PROMOTION")
        if prom is None:
            raise ValueError("LOCK-DENY no PROMOTION cell in the order for "
                             f"{cell['block']}/{cell['universe']}/"
                             f"{cell['family']}")
        rp = receipt_path or os.path.join(run_dir(fam_c_dir, prom),
                                          "PROMOTION-RECEIPT.json")
        if os.path.islink(rp) or not os.path.isfile(rp):
            raise PermissionError(f"LOCK-DENY no promotion receipt at {rp} "
                                  "(promote the universe before locking it)")
        receipt, receipt_path = _read_json(rp), rp
    # A12.1: the lock may only be minted from a receipt whose provenance
    # RE-VALIDATES here. Without this gate, a receipt forged for this cell
    # plus artifact bytes copied in from another universe (hash-matching, so
    # the artifact check below cannot tell) would mint a lock.
    prom_cell = _cell_for_event(fam_c_dir, cell, "PROMOTION")
    if prom_cell is not None:
        runs = {}
        for ev in ("T0", "T1"):
            acq = _cell_for_event(fam_c_dir, cell, ev)
            if acq is None:
                continue
            if _local_state(fam_c_dir, acq, None)["status"] == "COMPLETE":
                runs[ev] = run_dir(fam_c_dir, acq)
        prov = _promotion_provenance_reasons(fam_c_dir, prom_cell, receipt, runs)
        if prov:
            raise PermissionError("LOCK-INADMISSIBLE: promotion receipt "
                                  "provenance does not re-validate: "
                                  + " | ".join(prov[:3]))
    # Presence is not truthiness: a frozen contract may legitimately declare
    # NO limitations (fam05's hidden contract declares none), so an empty list is a real
    # value. The fields that must carry content are checked separately, so
    # an empty provenance map can never pass as "present".
    need = ("acquisition_chain_tips", "source_cells", "candidate",
            "artifacts", "semantic_core", "preconditions", "limitations",
            "limitation_present", "non_discriminating", "conformance_cause",
            "supported_t4_ids", "conformance_map_sha256",
            "t4_semantic_id", "evidence_grade", "producer_identity",
            "protocol_lock_sha256", "execution_lock_sha256")
    missing = [k for k in need if k not in receipt or receipt[k] is None]
    empty = [k for k in need if k not in ("preconditions", "limitations",
                                         "limitation_present",
                                         "non_discriminating",
                                         "supported_t4_ids")
             and not receipt.get(k)]
    if missing or empty:
        raise PermissionError("LOCK-INADMISSIBLE: promotion receipt lacks "
                              "estimand provenance field(s): "
                              + ", ".join(missing or empty))
    capdir = ensure_namespace(fam_c_dir, cell["block"], cell["universe"],
                              cell["family"], tail=("capability",))
    named = receipt["artifacts"]
    if artifact_paths:
        given = {os.path.basename(p) for p in artifact_paths}
        if given != set(named):
            raise PermissionError(
                "LOCK-DENY artifact set differs from the receipt-named set "
                f"({sorted(given)} != {sorted(named)}); a lock may only lock "
                "hashes the validated promotion named")
    arts = []
    for name, want_sha in sorted(named.items()):
        if os.path.basename(name) != name:
            raise PermissionError(f"LOCK-DENY artifact name {name!r} is not a "
                                  "bare filename")
        p = os.path.join(capdir, name)
        if os.path.islink(p) or not os.path.isfile(p):
            raise PermissionError(f"LOCK-DENY receipt-named artifact {name} "
                                  f"absent from {capdir}")
        if _sha256_file(p) != want_sha:
            raise PermissionError(f"LOCK-DENY receipt-named artifact {name} "
                                  f"hash {want_sha[:12]} != present "
                                  f"{_sha256_file(p)[:12]}")
        arts.append(p)
    if receipt_path is None:
        prom = _cell_for_event(fam_c_dir, cell, "PROMOTION")
        receipt_path = os.path.join(run_dir(fam_c_dir, prom),
                                    "PROMOTION-RECEIPT.json")
    receipt_sha = _sha256_file(receipt_path)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lock import promote as _lock_promote
    return _lock_promote(
        capdir, cell["capability_id"], version, arts,
        manifest_obj if manifest_obj is not None else {},
        training_receipts or [], builder_identity or {},
        promotion_receipt_sha256=receipt_sha,
        block=cell["block"], universe=cell["universe"],
        family=cell["family"],
        acquisition_chain_tips=receipt["acquisition_chain_tips"],
        source_cells=receipt["source_cells"],
        producer_identity=receipt["producer_identity"],
        protocol_lock_sha256=receipt["protocol_lock_sha256"],
        execution_lock_sha256=receipt["execution_lock_sha256"],
        semantic_core=receipt["semantic_core"],
        preconditions=receipt["preconditions"],
        limitations=receipt["limitations"],
        limitation_present=receipt["limitation_present"],
        non_discriminating=receipt["non_discriminating"],
        conformance_cause=receipt["conformance_cause"],
        supported_t4_ids=receipt["supported_t4_ids"],
        conformance_map_sha256=receipt["conformance_map_sha256"],
        t4_semantic_id=receipt["t4_semantic_id"],
        evidence_grade=receipt["evidence_grade"],
        candidate_sha256=receipt["candidate"]["sha256"],
        candidate_provenance_sha256=receipt_sha)


def completed_cells(fam_c_dir, freeze_commit=None, expansion=None):
    """A11.6: cell ids of cells whose VALIDATED state is COMPLETE.

    Consumes cell_state(), never manifest presence: a malformed, tampered,
    dangling, dev or inadmissible run does not advance the frozen order.
    Scans the universe state trees only (the derived namespace), so a stray
    manifest elsewhere in Fam-C cannot mark a cell done.
    """
    exp = expansion if expansion is not None else load_expansion(fam_c_dir)
    done = {}
    prefix_ok = True
    for c in exp["cells"]:
        # A12.1: completion is order-admissible, so ONE local validation per
        # cell plus a prefix walk gives the same answer as calling the
        # order-aware cell_state() per cell — without the quadratic blow-up
        # of re-validating every earlier cell on every call.
        st = _local_state(fam_c_dir, c, freeze_commit)
        if prefix_ok and st["status"] == "COMPLETE":
            done[c["cell_id"]] = os.path.basename(run_dir(fam_c_dir, c))
        else:
            prefix_ok = False
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
