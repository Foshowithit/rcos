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

Progress algebra (EPOCH-2, ruling recorded in benchmarks/fam-c/
EPOCH-1-CLOSURE.md — "TERMINAL-OUTCOME PROGRESS SEMANTICS"): the prefix
walk advances on EVENT-SPECIFIC validated terminal states. Model cells
(T0..T4) progress on COMPLETE only; a PROMOTION cell progresses on
validated COMPLETE or validated NOT-PROMOTED; a CAPABILITY_LOCK cell on
validated COMPLETE or validated NOT-LOCKED; a downstream (T2/T3/T4) cell
of a capability universe whose acquisition validly failed progresses only
as validated NOT-EVALUABLE. INCOMPLETE and INADMISSIBLE are never
progress-valid. The non-COMPLETE terminals are produced by the strict
validators only, are never converted to COMPLETE anywhere, and authorize
nothing: no promotion, no lock creation, no capability consumption, no
retry — they exist so a lawful failed-acquisition terminal advances the
frozen prefix instead of deadlocking it (the epoch-1 defect). See
progress_valid().

Epoch-2 lineage: state namespaces are derived under the ACTIVE epoch's
state root (harness/epoch.py: state/epoch2/** once the explicit epoch-2
transition record exists), so epoch-1 evidence is never scanned or
written by epoch-2 machinery. Stdlib only.
"""
import hashlib
import json
import os
import re
import stat
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import epoch as _epoch  # noqa: E402  (epoch-2 lineage: state root + locks)

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


def authorize(expansion, block, family, task, lane, arm, done_ids,
                fam_c_dir=None):
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
    # A12d D1-B5 (needs fam_c_dir): a downstream cell of a NOT-PROMOTED
    # universe is NOT-EVALUABLE — refuse with the named acquisition
    # denial before any scheduling-order finding. The failed-acquisition
    # predicate derives from the committed chains, so the denial holds
    # whether or not the outcome has been recorded yet.
    if fam_c_dir is not None and cell.get("universe") in \
            CAPABILITY_UNIVERSES:
        _failed, _cause = acquisition_failed(
            fam_c_dir, block, family, cell["universe"])
        if _failed:
            out.append(
                f"ACQUISITION-FAILED-DENY: universe {block}/{family}/"
                f"{cell['universe']} T1 candidate validation failed "
                f"({_cause}); downstream {task}/"
                f"{cell['universe']} is NOT-EVALUABLE (no retry: the "
                f"failed validation is an experimental outcome)")
            return cell, out
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


def authorize_event(expansion, block, family, event, universe, done_ids,
                      fam_c_dir=None):
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
    # A12d D1-B3/B5 (needs fam_c_dir): a recorded NOT-PROMOTED outcome is
    # terminal. Re-entering PROMOTION refuses as already-recorded (no
    # repromotion, no deadlock); entering CAPABILITY_LOCK refuses the LOCK
    # path because no lock may ever exist for a NOT-PROMOTED universe (the
    # lock event completes as its recorded NOT-LOCKED terminal instead —
    # see emit_capability_lock_outcome(), never through this entry point).
    if fam_c_dir is not None and event in ("PROMOTION", "CAPABILITY_LOCK"):
        _oc = promotion_outcome(fam_c_dir, block, family, universe)
        if isinstance(_oc, dict) and _oc.get("outcome") == "NOT-PROMOTED":
            if event == "PROMOTION":
                out.append(
                    f"PROMOTION-DENY: outcome already recorded for "
                    f"{block}/{family}/{universe} (NOT-PROMOTED: "
                    f"{_oc.get('reason')}); no repromotion of a failed "
                    f"acquisition")
            else:
                out.append(
                    f"LOCK-DENY: universe {block}/{family}/{universe} is "
                    f"NOT-PROMOTED ({_oc.get('reason')}); no "
                    f"CAPABILITY_LOCK may exist for it (the event "
                    f"completes only as its recorded NOT-LOCKED terminal)")
            return cell, out
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
    surface (registry, runs, logs). No lane may read another's.

    Epoch 2 prefixes the whole surface with state/epoch2/ (harness/
    epoch.py): epoch-1 state is historical evidence, never scanned or
    written once the transition record exists."""
    return os.path.join(_epoch.state_root(fam_c_dir), block, universe, family)


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
    # EPOCH-2: the epoch state root is state/epoch2, so the historical
    # state/ dir is itself a namespace ANCESTOR that must satisfy the same
    # lstat rules (a symlinked state/ must never be traversed, epoch 1 or 2).
    _comps = ((_epoch.STATE_SUBDIR,) if _epoch.is_epoch2(fam_c_dir) else ()) \
        + (block, universe, family) + tuple(tail)
    for comp in _comps:
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
    p = _epoch.state_root(fam_c_dir)
    if not os.path.lexists(p):
        # The epoch state root may sit one level below the historical
        # state/ dir (state/epoch2 under epoch 2): create every missing
        # component explicitly at 0755, no-follow — verify_namespace_ancestry
        # already refused any symlinked component above.
        _parent = os.path.dirname(p)
        if not os.path.lexists(_parent):
            os.mkdir(_parent, 0o755)    # fam_c_dir itself must already exist
        elif not stat.S_ISDIR(os.lstat(_parent).st_mode):
            raise PermissionError(
                f"NAMESPACE-TYPE-DENY: {_parent} exists but is not a "
                f"directory")
        os.mkdir(p, 0o755)
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


def progress_valid(cell, status):
    """The event-specific progress algebra (EPOCH-2 ruling, EPOCH-1-CLOSURE.md
    "TERMINAL-OUTCOME PROGRESS SEMANTICS"): the VALIDATED terminal states
    that advance the frozen prefix walk, per cell kind/event.

      model cells (T0..T4 acquisition-solve/model-call) COMPLETE only;
      PROMOTION                                      COMPLETE | NOT-PROMOTED;
      CAPABILITY_LOCK                                COMPLETE | NOT-LOCKED;
      downstream T2/T3/T4 of a capability universe
        (A/C) whose acquisition validly failed       NOT-EVALUABLE.

    INCOMPLETE and INADMISSIBLE are never progress-valid. Every
    non-COMPLETE status here is produced by the STRICT validators (never
    assumed from file presence), is never converted to COMPLETE, and
    authorizes nothing: no promotion, no lock creation, no capability
    consumption, no retry. It only lets the lawful terminal boundary of a
    failed acquisition advance the prefix (the epoch-1 deadlock repair)."""
    if status == "COMPLETE":
        return True
    # EPOCH-3: a model cell carrying a VALIDATED MODEL-OUTPUT-INVALID
    # terminal is progress-valid — model cells only (never a governance
    # cell), and only through the strict validator of _terminal_state().
    if status == MODEL_OUTPUT_INVALID_STATUS and \
            cell.get("kind") in MODEL_RUN_KINDS:
        return True
    event = cell.get("event")
    if event == "PROMOTION":
        return status == "NOT-PROMOTED"
    if event == "CAPABILITY_LOCK":
        return status == "NOT-LOCKED"
    if event == "T1" and cell.get("universe") in CAPABILITY_UNIVERSES:
        # EPOCH-3 (§3): the T1 of a universe whose T0 carries a validated
        # MODEL-OUTPUT-INVALID terminal is NOT-EVALUABLE (no candidate ever
        # existed). The status is produced ONLY by the strict terminal
        # validator path in _local_state(), never assumed from presence.
        return status == "NOT-EVALUABLE"
    if event in DOWNSTREAM_EVENTS and \
            cell.get("universe") in CAPABILITY_UNIVERSES:
        return status == "NOT-EVALUABLE"
    return False


def cell_state(fam_c_dir, cell, freeze_commit=None, _exp=None):
    """Validate ONE cell's completion. Returns
    {"status": "COMPLETE"|"INCOMPLETE"|"INADMISSIBLE"|terminal, "reasons": [...]}.

    A12.1 (audit round-2 #11): completion is ALSO order-admissible — a cell
    whose artifacts validate is still NOT COMPLETE if any earlier cell in the
    frozen expansion is not progress-valid, so a preplanted future
    promotion/lock (or another family's governance artifact minted out of
    turn) can never satisfy state. `_local_state()` holds the kind dispatch
    below.

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

    Terminal states (A12d D1-B3 + the EPOCH-2 ruling; all ride the strict
    validators, none is ever COMPLETE):
      * a PROMOTION cell with a recorded, re-validated failed-acquisition
        outcome is NOT-PROMOTED;
      * the CAPABILITY_LOCK event of that same universe is NOT-LOCKED (the
        recorded terminal refusal: no lock may exist for a failed
        acquisition);
      * any downstream (T2/T3/T4) cell of that universe is NOT-EVALUABLE
        with the reason naming the failed acquisition.

    The order guard accepts earlier cells that are progress-valid
    (progress_valid()), so one lawfully failed universe no longer
    deadlocks the whole frozen order — while authorizing none of the
    behaviors a COMPLETE cell would.
    """
    st = _local_state(fam_c_dir, cell, freeze_commit, _exp)
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
        earlier = _local_state(fam_c_dir, c, freeze_commit, exp)
        if not progress_valid(c, earlier["status"]):
            blockers.append(f"{c['cell_id']} "
                            f"({c['block']}/{c['family']}/{c['event']}/"
                            f"{c['universe']})={earlier['status']}")
    if blockers:
        return _result(cell, [
            "ORDER-INADMISSIBLE: cell " + cell["cell_id"] + " validates "
            "locally but cannot be COMPLETE while " + str(len(blockers))
            + " earlier cell(s) are not: " + "; ".join(blockers[:3])], True)
    return st


def _local_state(fam_c_dir, cell, freeze_commit=None, _exp=None):
    """Kind-dispatched validation of ONE cell, WITHOUT the order guard.
    Governance validators (promotion/lock) use this for their T0/T1 source
    cells so order recursion terminates.

    EPOCH-2: this is ALSO where a downstream (T2/T3/T4) cell of a
    capability universe whose acquisition validly failed resolves to its
    validated terminal NOT-EVALUABLE state (the same status/reason
    cell_state() has always produced for those cells — it must be visible
    to the prefix walk, which consumes _local_state()) and where the
    CAPABILITY_LOCK event of a NOT-PROMOTED universe resolves
    outcome-first to NOT-LOCKED, exactly like _promotion_state()'s
    outcome-first dispatch."""
    kind = cell.get("kind")
    event = cell.get("event")
    # EPOCH-2 terminal: a downstream cell of a failed-acquisition universe
    # is NOT-EVALUABLE (validated against the committed chains). Checked
    # before the kind dispatch and before any per-cell artifact read, so
    # the terminal derives from the SAME predicate everywhere (any
    # undecidable evidence makes acquisition_failed() False and the normal
    # fail-closed path below applies).
    if kind in MODEL_CALL_KINDS and event in DOWNSTREAM_EVENTS and \
            cell.get("universe") in CAPABILITY_UNIVERSES:
        _failed, _cause = acquisition_failed(
            fam_c_dir, cell["block"], cell["family"], cell["universe"],
            _exp=_exp)
        if _failed:
            # EPOCH-3: the failed-acquisition cause names the branch — the
            # T1 candidate-validation failure, or the MODEL-OUTPUT-INVALID
            # terminal of T0/T1 (whose downstream algebra is identical).
            if _cause.startswith("T0 MODEL-OUTPUT-INVALID") or \
                    _cause.startswith("T1 MODEL-OUTPUT-INVALID"):
                _why = (f"carries a validated MODEL-OUTPUT-INVALID "
                        f"acquisition terminal ({_cause})")
            else:
                _why = (f"T1 cell is COMPLETE but its candidate validation "
                        f"failed ({_cause})")
            return {"cell_id": cell["cell_id"], "status": "NOT-EVALUABLE",
                    "reasons": [
                        f"ACQUISITION-FAILED-DENY: universe "
                        f"{cell['block']}/{cell['family']}/"
                        f"{cell['universe']} {_why}; "
                        f"downstream {cell['event']}/"
                        f"{cell['universe']} is NOT-EVALUABLE with "
                        f"reason acquisition-failed (no retry: the "
                        f"failed acquisition is an experimental outcome, "
                        f"not an infrastructure-invalid run)"]}
    # EPOCH-3 (§3): the T1 of a universe whose T0 cell carries a VALIDATED
    # MODEL-OUTPUT-INVALID terminal is NOT-EVALUABLE — no candidate ever
    # existed (no synthesized arrival, no partial arrival), so T1 cannot be
    # run at all. Checked before the kind dispatch and before any per-cell
    # artifact read; the strict validator of the T0 terminal is the same one
    # the prefix walk uses.
    if kind in MODEL_CALL_KINDS and event == "T1" and \
            cell.get("universe") in CAPABILITY_UNIVERSES:
        _tev = acquisition_failure_terminal(fam_c_dir, cell["block"],
                                            cell["family"],
                                            cell["universe"], _exp)
        if _tev is not None and _tev["failure_event"] == "T0":
            return {"cell_id": cell["cell_id"], "status": "NOT-EVALUABLE",
                    "reasons": [
                        f"ACQUISITION-FAILED-DENY: universe "
                        f"{cell['block']}/{cell['family']}/"
                        f"{cell['universe']} T0 cell carries the validated "
                        f"MODEL-OUTPUT-INVALID terminal "
                        f"{_tev['acquisition_evidence']['terminal_sha256'][:12]} "
                        f"(candidate absent: no arrival, no synthesized "
                        f"candidate); T1 is NOT-EVALUABLE with reason "
                        f"acquisition-failed (no retry: a malformed model "
                        f"output is an experimental outcome)"],
                    "terminal_class": MODEL_OUTPUT_INVALID_CLASS}
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
        return _model_run_state(fam_c_dir, cell, freeze_commit, _exp)
    if kind == "harness-event":
        if event == "PROMOTION":
            return _promotion_state(fam_c_dir, cell, freeze_commit)
        if event == "CAPABILITY_LOCK":
            # EPOCH-2 outcome-first dispatch (mirrors _promotion_state): a
            # recorded CAPABILITY-LOCK-OUTCOME.json is judged ONLY on that
            # terminal record, re-validated against the committed chains —
            # never on the lock-minting path.
            _oc = lock_outcome(fam_c_dir, cell["block"], cell["family"],
                               cell["universe"])
            if _oc is not None:
                return _not_locked_state(fam_c_dir, cell, _oc, freeze_commit)
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


def _model_run_state(fam_c_dir, cell, freeze_commit=None, _exp=None):
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
    # EPOCH-3: the pre-frozen no-arrival terminal. A cell carrying one is
    # judged ONLY by the strict terminal validator (never by the manifest
    # path): a forbidden companion beside a terminal is a defect, not a
    # manifest.
    if os.path.lexists(os.path.join(d, MODEL_OUTPUT_INVALID_FILE)):
        return _terminal_state(fam_c_dir, cell, freeze_commit, _exp)
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
        order_sha = (_exp if _exp is not None else
                     load_expansion(fam_c_dir))["order_sha256"]
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


def _not_promoted_state(fam_c_dir, cell, outcome, freeze_commit=None):
    """A12d D1-B3: validate ONE recorded failed-acquisition outcome.

    NOT-PROMOTED only when — with no fabricated model-run record and no
    promotion receipt — the two REAL acquisition runs of the SAME (block,
    family, universe) are each validated COMPLETE, the T1 chain carries
    EXACTLY ONE candidate-validation event with validated=false, the
    outcome's tips equal the REAL chain tips, the outcome's candidate
    equals the event's candidate equals the frozen T0 arrival candidate,
    and no CAPABILITY_LOCK exists for the universe. Any defect =>
    INADMISSIBLE (artifact present but invalid)."""
    reasons = []
    d = run_dir(fam_c_dir, cell)
    if os.path.islink(d) or not os.path.isdir(d):
        return {"cell_id": cell["cell_id"], "status": "INCOMPLETE",
                "reasons": [f"promotion run dir absent at the derived path "
                            f"{d}"]}
    if os.path.exists(os.path.join(d, "H1-RUN-MANIFEST.json")):
        reasons.append("promotion event must not fabricate a model-run "
                       "manifest (no identity/usage/chain is demanded of a "
                       "promotion, and none may be forged)")
    if os.path.exists(os.path.join(d, PROMOTION_RECEIPT_FILE)):
        reasons.append("promotion conflict: a promotion receipt and a "
                       "NOT-PROMOTED outcome both exist for this cell (a "
                       "validated promotion cannot also be NOT-PROMOTED)")
    # EPOCH-3 (§3.1): an acquisition-failed universe may terminate through
    # a MODEL-OUTPUT-INVALID acquisition terminal instead of a failed
    # candidate validation. That record carries the exact evidence union
    # (failure_event + acquisition_evidence + candidate_sha256); epoch-2
    # records (no failure_event key) keep the chain-tip shape unchanged.
    _union = ("failure_event" in outcome) or ("acquisition_evidence" in outcome)
    for key, want in (("event", "PROMOTION"),
                      ("cell_id", cell["cell_id"]),
                      ("block", cell["block"]),
                      ("family", cell["family"]),
                      ("universe", cell["universe"]),
                      ("outcome", "NOT-PROMOTED"),
                      ("reason", ACQ_FAILURE_REASON if _union
                       else "candidate-validation-failed"),
                      ("created_from", "frozen-evidence")):
        if outcome.get(key) != want:
            reasons.append(f"not-promoted outcome {key} "
                           f"{outcome.get(key)!r} != {want!r}")
    if _union:
        reasons.extend(_acquisition_evidence_reasons(fam_c_dir, outcome,
                                                     cell))
        if outcome.get("acquisition_chain_tips"):
            reasons.append("not-promoted outcome carries acquisition_chain_"
                           "tips beside a MODEL-OUTPUT-INVALID failure_event "
                           "(a terminal branch has no chain to bind; a null "
                           "tip is never equivalent to a chain)")
    tips, runs = {}, {}
    if not _union:
        for ev in ("T0", "T1"):
            acq = _cell_for_event(fam_c_dir, cell, ev)
            if acq is None:
                reasons.append(f"no {ev} cell in the order for "
                               f"{cell['block']}/{cell['family']}/"
                               f"{cell['universe']}")
                continue
            st = _local_state(fam_c_dir, acq, freeze_commit)
            if st["status"] != "COMPLETE":
                reasons.append(f"not-promoted rule: {ev} acquisition cell "
                               f"{acq['cell_id']} not validated COMPLETE "
                               f"({st['status']}: {st['reasons'][:1]})")
                continue
            runs[ev] = run_dir(fam_c_dir, acq)
            try:
                tips[ev] = _chain_tip(os.path.join(runs[ev],
                                                   "EVIDENCE-CHAIN.jsonl"))
            except (ValueError, OSError, json.JSONDecodeError) as e:
                reasons.append(f"not-promoted rule: {ev} chain tip unreadable: "
                               f"{e}")
    for ev in ("T0", "T1"):
        if ev in tips and outcome.get(ev.lower() + "_tip") != tips[ev]:
            reasons.append(f"not-promoted outcome {ev.lower()}_tip "
                           f"{str(outcome.get(ev.lower() + '_tip'))[:12]} "
                           f"!= the validated {ev} chain tip "
                           f"{tips[ev][:12]}")
    want_sha = None
    if "T0" in runs:
        try:
            arrival = _read_json(os.path.join(runs["T0"], "arrival.json"))
            s = (arrival.get("execution_payload") or {}).get("solver_py")
            if not isinstance(s, str) or not s.strip():
                reasons.append("not-promoted rule: T0 arrival carries no "
                               "execution_payload.solver_py candidate")
            else:
                want_sha = hashlib.sha256(s.encode()).hexdigest()
        except (ValueError, OSError) as e:
            reasons.append(f"not-promoted rule: T0 arrival unreadable: {e}")
    if "T1" in runs:
        try:
            _links = [json.loads(line)
                      for line in open(os.path.join(
                          runs["T1"], "EVIDENCE-CHAIN.jsonl"))
                      if line.strip()]
        except (ValueError, OSError) as e:
            reasons.append("not-promoted rule: T1 evidence chain "
                           f"unreadable: {e}")
            _links = None
        if _links is not None:
            _cvs = [l for l in _links
                    if l.get("kind") == "candidate-validation"]
            if len(_cvs) != 1:
                reasons.append(f"not-promoted rule: T1 chain carries "
                               f"{len(_cvs)} candidate-validation events, "
                               f"need exactly one failed one "
                               f"(validated=false)")
            else:
                _cv = _cvs[0].get("payload") or {}
                if _cv.get("validated") is not False:
                    reasons.append(
                        "not-promoted rule: T1 candidate-validation event "
                        f"is not a failed validation "
                        f"(validated={_cv.get('validated')!r}; a passing "
                        f"validation promotes, it is never NOT-PROMOTED)")
                if want_sha is not None and \
                        _cv.get("candidate_sha256") != want_sha:
                    reasons.append(
                        "not-promoted rule: T1 validated candidate "
                        f"{str(_cv.get('candidate_sha256'))[:12]} != the "
                        f"frozen T0 candidate {want_sha[:12]}")
                if want_sha is not None and \
                        outcome.get("candidate_sha256") != want_sha:
                    reasons.append(
                        "not-promoted rule: outcome candidate_sha256 "
                        f"{str(outcome.get('candidate_sha256'))[:12]} != "
                        f"the frozen T0 candidate {want_sha[:12]}")
    capdir = capability_dir(fam_c_dir, cell["block"], cell["universe"],
                            cell["family"])
    if os.path.exists(os.path.join(capdir, "CAPABILITY_LOCK.json")):
        reasons.append("not-promoted rule: a CAPABILITY_LOCK exists for a "
                       "NOT-PROMOTED universe (no lock may ever exist for "
                       "a failed acquisition)")
    if reasons:
        return _result(cell, reasons, True)
    cause = _failed_acquisition_cause(fam_c_dir, cell["block"],
                                      cell["family"], cell["universe"])
    if cause.startswith("T0 MODEL-OUTPUT-INVALID") or \
            cause.startswith("T1 MODEL-OUTPUT-INVALID"):
        _why = (f"carries a validated MODEL-OUTPUT-INVALID acquisition "
                f"terminal ({cause})")
    else:
        _why = (f"T1 cell is COMPLETE but its candidate validation failed "
                f"({cause})")
    return {"cell_id": cell["cell_id"], "status": "NOT-PROMOTED",
            "reasons": [f"NOT-PROMOTED: universe {cell['block']}/"
                        f"{cell['family']}/{cell['universe']} {_why}; no "
                        f"CAPABILITY_LOCK may exist for it, "
                        f"every downstream cell of that universe (T2/T3/"
                        f"T4) is NOT-EVALUABLE with reason "
                        f"acquisition-failed, and there is no retry (the "
                        f"failed acquisition is an experimental outcome, "
                        f"not an infrastructure-invalid run)"]}


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
    cell_state() for the full contract.

    A12d D1-B3: a recorded failed-acquisition outcome is TERMINAL. When
    the promotion run dir carries PROMOTION-OUTCOME.json, the cell is
    judged ONLY on that outcome (re-validated against the committed
    chains) — never on the receipt path below."""
    # A12d D1-B3: outcome-first dispatch (terminal, not an exception).
    # A recorded outcome is validated strictly; with no outcome file the
    # terminal status still derives from the committed chains (a failed
    # validation is NOT-PROMOTED whether or not the controller has
    # recorded it yet).
    _oc = promotion_outcome(fam_c_dir, cell["block"], cell["family"],
                            cell["universe"])
    if _oc is not None:
        return _not_promoted_state(fam_c_dir, cell, _oc, freeze_commit)
    _failed, _cause = acquisition_failed(
        fam_c_dir, cell["block"], cell["family"], cell["universe"])
    if _failed:
        return {"cell_id": cell["cell_id"], "status": "NOT-PROMOTED",
                "reasons": [f"NOT-PROMOTED: universe {cell['block']}/"
                            f"{cell['family']}/{cell['universe']} T1 cell "
                            f"is COMPLETE but its candidate validation "
                            f"failed ({_cause}); no CAPABILITY_LOCK may "
                            f"exist for it, every downstream cell of that "
                            f"universe (T2/T3/T4) is NOT-EVALUABLE with "
                            f"reason acquisition-failed, and there is no "
                            f"retry (the failed validation is an "
                            f"experimental outcome, not an "
                            f"infrastructure-invalid run)"]}
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
            # A12c D3 + A12d D1-C3: re-derive the same eleven-field
            # fail-closed predicate from the committed chain (no trust in
            # the receipt).
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
                           "validated", "candidate_input_manifest_sha256",
                           "candidate_input_tree_sha256"):
                    if _cv.get(_f) is None:
                        _cv_reasons.append(f"no {_f}")
                for _f in ("candidate_sha256", "executed_sha256",
                           "adapter_sha256", "candidate_output_sha256",
                           "checker_sha256", "truth_sha256",
                           "candidate_input_manifest_sha256",
                           "candidate_input_tree_sha256"):
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
                           "validated", "candidate_input_manifest_sha256",
                           "candidate_input_tree_sha256"):
                    if _rec_cv.get(_k) != _cv.get(_k):
                        out.append("promotion provenance: receipt candidate "
                                   f"t1_validation[{_k}] != the committed "
                                   "T1 chain event "
                                   f"({_rec_cv.get(_k)!r} != {_cv.get(_k)!r})")
                        break
                else:
                    # A12d D1-C3: the input lineage is re-derived from the
                    # COMMITTED artifacts (the persisted manifest file +
                    # the chain event), never from the receipt. Any
                    # mismatch denies naming the field.
                    for _lr in candidate_input_lineage_reasons(
                            runs["T1"], _cv):
                        out.append("promotion provenance: " + _lr)
    # A12c slice B: the producer authors its own contract text from
    # visible information, so the receipt's contract is cross-checked
    # against the FROZEN T0 arrival declaration — verbatim equality on
    # semantic_core/preconditions/limitations, the same declaration the
    # promotion controller used (one source of truth) — never against
    # hidden capability text. A receipt that rewrites the producer's declared text
    # is refused here, exactly as a non-frozen contract was before.
    # A12c slice C2 re-derives the conformance verdict from the same
    # frozen declaration below (`_t0_pre_lists`); A12d slice D5 maps
    # ONLY the structural preconditions[*].requires_all token lists
    # (never limitations).
    # A12d slice D8.1 (auditor D7-post P0): the declaration shape
    # verdict comes from the SINGLE shared authority
    # (harness/contract_shape.py — no I/O, no globals, no vocabulary
    # knowledge), the same module the promotion controller calls. The
    # receipt's own contract triple rides the same authority (no second
    # approximation of the shape); the receipt-vs-declaration verbatim
    # equality below is a cross-check, not a shape rule. A malformed T0
    # declaration is INADMISSIBLE here with the same finding text the
    # controller raises, even when the receipt mirrors it field for
    # field.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from contract_shape import validate as _contract_validate
    from contract_shape import \
        precondition_token_lists as _contract_pre_lists
    _t0_pre_lists = None
    sc = r.get("semantic_core")
    _rc_triple = {"semantic_core": r.get("semantic_core"),
                  "preconditions": r.get("preconditions"),
                  "limitations": r.get("limitations")}
    for _finding in _contract_validate(_rc_triple):
        out.append("promotion provenance: receipt contract " + _finding)
    if "T0" not in runs:
        out.append("promotion provenance: T0 acquisition run not "
                   "validated (contract cross-check not derivable)")
    else:
        try:
            _t0_arrival = _read_json(os.path.join(runs["T0"],
                                                  "arrival.json"))
            _t0_declared = ((_t0_arrival.get("execution_payload") or {})
                            .get("capability_contract"))
            _t0_unreadable = None
        except (ValueError, OSError) as e:
            _t0_declared = None
            _t0_unreadable = (f"promotion provenance: T0 arrival "
                              f"unreadable for the contract cross-check: "
                              f"{e}")
            out.append(_t0_unreadable)
        if _t0_unreadable is None:
            _decl_findings = _contract_validate(_t0_declared)
            for _finding in _decl_findings:
                out.append("promotion provenance: " + _finding)
            if isinstance(_t0_declared, dict):
                if not _decl_findings:
                    _t0_pre_lists = _contract_pre_lists(_t0_declared)
                for _k in ("semantic_core", "preconditions", "limitations"):
                    if r.get(_k) != _t0_declared.get(_k):
                        out.append(
                            f"promotion provenance: receipt {_k} is not "
                            f"the frozen T0 arrival declaration (the "
                            f"promoted contract must be the producer's "
                            f"own declared text, verbatim)")
                        break
    if isinstance(sc, str) and r.get("semantic_core_sha256") != \
            hashlib.sha256(sc.encode()).hexdigest():
        out.append("promotion provenance: semantic_core_sha256 mismatch")
    # A12d slice D8.1: no second approximation of the contract shape
    # lives here — the receipt's own contract triple was already judged
    # by the shared authority above (any malformed receipt contract is
    # refused there naming the defect).
    # A12b.6 actual-contract conformance: the receipt carries the
    # producer's ACTUAL contract plus the derived verdict (the lock
    # records exactly these; the conformance check reads the lock only,
    # never hidden capability text). declared_limitations_present must
    # equal bool(limitations). A12d slice D5: discrimination rides the
    # structural requires_all token lists, never limitations — so an
    # empty limitations list alongside a discriminating verdict is
    # legitimate (limitations are free prose); only the re-derived set
    # membership below judges the claim.
    _lim = r.get("limitations")
    _lp = r.get("declared_limitations_present")
    _nd = r.get("non_discriminating")
    _cause = r.get("conformance_cause")
    if not isinstance(_lp, bool) or _lp != bool(_lim):
        out.append("promotion provenance: declared_limitations_present "
                   "must be bool(limitations)")
    if not isinstance(_nd, bool):
        out.append("promotion provenance: non_discriminating must be a "
                   "boolean")
    if not (isinstance(_cause, str) and _cause.strip()):
        out.append("promotion provenance: conformance_cause must be a "
                   "nonempty committed reason")
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
    elif _t0_pre_lists is None:
        out.append("promotion provenance: T0 arrival declares no v4 "
                   "preconditions list (conformance verdict not "
                   "re-derivable)")
    else:
        try:
            _re = _conf_verdict(cell["family"], _t0_pre_lists, _cmap)
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
    # A12d slice D5: a symlinked capability dir at this DERIVED (hence
    # expected) path stays legal — the D1-era jail / named-volume seam.
    # os.path.isdir follows the link, so a dangling symlink still reads
    # as absent; an unexpected symlink anywhere beneath state/ is still
    # a readiness FAILURE via the specificity stray walk (which never
    # follows links).
    if not os.path.isdir(capdir):
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
        # A12d slice D5: the receipt<->lock binding never consults
        # declared_limitations_present (observed specificity must not
        # consult the field at all: a flipped bit with everything else
        # valid leaves readiness unchanged).
        for key in ("protocol_lock_sha256", "execution_lock_sha256",
                    "evidence_grade", "semantic_core", "t4_semantic_id",
                    "non_discriminating",
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
    # A12d slice D5: order-level state never consults
    # declared_limitations_present (the decorative presence bit): it is
    # masked to its consistent value before validation, so a flipped
    # bit with everything else valid leaves the cell COMPLETE.
    # lock.verify_lock itself still enforces the bit's hygiene
    # directly (a lying lock is LOCK-INADMISSIBLE there).
    _state_lock = dict(lock)
    if "declared_limitations_present" in _state_lock and isinstance(
            _state_lock.get("limitations"), list):
        _state_lock["declared_limitations_present"] = bool(
            _state_lock["limitations"])
    reasons.extend(_verify_lock(_state_lock, expect=expect,
                                fam_c_dir=fam_c_dir))
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


def _not_locked_state(fam_c_dir, cell, outcome, freeze_commit=None):
    """EPOCH-2 (EPOCH-1-CLOSURE.md ruling) + A12d D1-B3: validate ONE
    recorded terminal NOT-LOCKED outcome of a CAPABILITY_LOCK event whose
    universe's acquisition validly failed.

    NOT-LOCKED only when — with no fabricated model-run record, no real
    lock, and no conflicting governance artifact in the lock cell's run
    dir — the outcome fields are EXACT on the authorized cell, the
    outcome binds the RECORDED PROMOTION-OUTCOME.json BYTES
    (`promotion_outcome_sha256` + `promotion_cell_id`), its cited
    acquisition chain tips equal the REAL validated T0/T1 chain tips, the
    PROMOTION cell of the SAME (block, family, universe) re-validates as
    NOT-PROMOTED (which itself re-derives the failed T1
    candidate-validation event, the frozen candidate and the chain tips
    from committed evidence), and NO CAPABILITY_LOCK exists for the
    universe. Any defect => INADMISSIBLE (artifact present but invalid).
    Never COMPLETE: a NOT-LOCKED terminal authorizes no promotion, no
    lock, no capability consumption and no retry."""
    reasons = []
    d = run_dir(fam_c_dir, cell)
    if os.path.islink(d) or not os.path.isdir(d):
        return {"cell_id": cell["cell_id"], "status": "INCOMPLETE",
                "reasons": [f"lock event run dir absent at the derived path "
                            f"{d}"]}
    if os.path.exists(os.path.join(d, "H1-RUN-MANIFEST.json")):
        reasons.append("CAPABILITY_LOCK terminal outcome must not fabricate "
                       "a model-run manifest (no identity/usage/chain is "
                       "demanded of a lock event, and none may be forged)")
    for stray in (PROMOTION_RECEIPT_FILE, PROMOTION_OUTCOME_FILE):
        if os.path.exists(os.path.join(d, stray)):
            reasons.append(f"lock event run dir carries a conflicting "
                           f"{stray} (the promotion's governance records "
                           f"belong to the PROMOTION cell; a NOT-LOCKED "
                           f"terminal is judged only on its own outcome)")
    for key, want in (("event", "CAPABILITY_LOCK"),
                      ("cell_id", cell["cell_id"]),
                      ("block", cell["block"]),
                      ("family", cell["family"]),
                      ("universe", cell["universe"]),
                      ("capability_id", cell["capability_id"]),
                      ("outcome", LOCK_OUTCOME_STATUS),
                      ("reason", LOCK_OUTCOME_REASON),
                      ("created_from", "frozen-evidence")):
        if outcome.get(key) != want:
            reasons.append(f"not-locked outcome {key} "
                           f"{outcome.get(key)!r} != {want!r}")
    # EPOCH-3 (§3.1): the lock terminal binds the SAME acquisition evidence
    # union as the promotion outcome; an epoch-2 record (no failure_event)
    # keeps the chain-tip shape unchanged.
    _union = ("failure_event" in outcome) or ("acquisition_evidence" in outcome)
    prom = _cell_for_event(fam_c_dir, cell, "PROMOTION")
    tips = {}
    if prom is None:
        reasons.append(f"no PROMOTION cell in the order for "
                       f"{cell['block']}/{cell['family']}/"
                       f"{cell['universe']}")
    else:
        pst = _local_state(fam_c_dir, prom, freeze_commit)
        if pst["status"] != "NOT-PROMOTED":
            reasons.append(f"not-locked rule: PROMOTION cell "
                           f"{prom['cell_id']} is not validated "
                           f"NOT-PROMOTED ({pst['status']}: "
                           f"{pst['reasons'][:1]})")
        elif _union:
            if outcome.get("acquisition_chain_tips"):
                reasons.append("not-locked outcome carries "
                               "acquisition_chain_tips beside a "
                               "MODEL-OUTPUT-INVALID failure_event (a "
                               "terminal branch has no chain to bind; a null "
                               "tip is never equivalent to a chain)")
        else:
            for ev in ("T0", "T1"):
                acq = _cell_for_event(fam_c_dir, cell, ev)
                if acq is None:
                    reasons.append(f"not-locked rule: no {ev} cell in the "
                                   f"order for {cell['block']}/"
                                   f"{cell['family']}/{cell['universe']}")
                    continue
                try:
                    tips[ev] = _chain_tip(os.path.join(
                        run_dir(fam_c_dir, acq), "EVIDENCE-CHAIN.jsonl"))
                except (ValueError, OSError, json.JSONDecodeError) as e:
                    reasons.append(f"not-locked rule: {ev} chain tip "
                                   f"unreadable: {e}")
            got = outcome.get("acquisition_chain_tips")
            if not isinstance(got, dict):
                reasons.append("not-locked outcome carries no "
                               "acquisition_chain_tips binding the "
                               "validated T0/T1 chains")
            else:
                for ev in ("T0", "T1"):
                    if ev in tips and got.get(ev) != tips[ev]:
                        reasons.append(
                            f"not-locked outcome {ev.lower()}_tip "
                            f"{str(got.get(ev))[:12]} != the validated "
                            f"{ev} chain tip {tips[ev][:12]}")
        # the outcome must bind the RECORDED promotion outcome BYTES
        _oc = promotion_outcome(fam_c_dir, cell["block"], cell["family"],
                                cell["universe"])
        if not isinstance(_oc, dict):
            reasons.append("not-locked rule: no recorded NOT-PROMOTED "
                           "promotion outcome to bind (the terminal must "
                           "cite the promotion outcome bytes)")
        else:
            op = os.path.join(run_dir(fam_c_dir, prom),
                              PROMOTION_OUTCOME_FILE)
            try:
                got_sha = _sha256_file(op)
            except OSError as e:
                got_sha = None
                reasons.append(f"not-locked rule: recorded promotion "
                               f"outcome unreadable: {e}")
            if outcome.get("promotion_cell_id") != prom["cell_id"]:
                reasons.append("not-locked outcome promotion_cell_id "
                               f"{outcome.get('promotion_cell_id')!r} != "
                               f"the PROMOTION cell {prom['cell_id']!r}")
            if got_sha is not None and \
                    outcome.get("promotion_outcome_sha256") != got_sha:
                reasons.append(
                    "not-locked outcome promotion_outcome_sha256 "
                    f"{str(outcome.get('promotion_outcome_sha256'))[:12]} "
                    f"!= the recorded PROMOTION-OUTCOME.json sha256 "
                    f"{got_sha[:12]}")
            if _union:
                for key in ("failure_event", "candidate_sha256",
                            "acquisition_evidence"):
                    if outcome.get(key) != _oc.get(key):
                        reasons.append(
                            f"not-locked outcome {key} does not equal the "
                            f"recorded PROMOTION-OUTCOME.json {key} (the "
                            f"lock terminal binds the SAME §3.1 acquisition "
                            f"evidence union)")
                reasons.extend(_acquisition_evidence_reasons(fam_c_dir,
                                                             outcome, cell))
    capdir = capability_dir(fam_c_dir, cell["block"], cell["universe"],
                            cell["family"])
    if os.path.exists(os.path.join(capdir, "CAPABILITY_LOCK.json")):
        reasons.append("not-locked rule: a CAPABILITY_LOCK exists for a "
                       "NOT-PROMOTED universe (a real lock and a "
                       "NOT-LOCKED terminal are mutually exclusive)")
    if reasons:
        return _result(cell, reasons, True)
    return {"cell_id": cell["cell_id"], "status": "NOT-LOCKED",
            "reasons": [f"NOT-LOCKED: universe {cell['block']}/"
                        f"{cell['family']}/{cell['universe']} acquisition "
                        f"validly failed (NOT-PROMOTED promotion); the "
                        f"CAPABILITY_LOCK event completes as a recorded "
                        f"terminal refusal (no lock, no capability "
                        f"consumption, no retry; every downstream cell of "
                        f"that universe is NOT-EVALUABLE)"]}


# ---------------------------------------------------------------------------
# A12d D1 — failed-acquisition terminal outcomes (auditor A12d.2) and
# candidate-input lineage re-derivation (auditor A12d.7).
# ---------------------------------------------------------------------------

PROMOTION_OUTCOME_FILE = "PROMOTION-OUTCOME.json"
PROMOTION_RECEIPT_FILE = "PROMOTION-RECEIPT.json"
# EPOCH-2 (EPOCH-1-CLOSURE.md ruling): the CAPABILITY_LOCK event of a
# NOT-PROMOTED universe completes as the recorded terminal NOT-LOCKED
# outcome — never a lock. The record lives in the lock cell's derived run
# dir and is bound to the promotion outcome bytes + the real chain tips.
CAPABILITY_LOCK_OUTCOME_FILE = "CAPABILITY-LOCK-OUTCOME.json"
LOCK_OUTCOME_STATUS = "NOT-LOCKED"
LOCK_OUTCOME_REASON = "no-promotion-no-lock"


def promotion_outcome(fam_c_dir, block, family, universe):
    """Read the recorded PROMOTION outcome for one universe, or None.

    Returns the parsed PROMOTION-OUTCOME.json dict when the promotion run
    dir carries one, else None (absent, unreadable, or unparsable — the
    strict validators, not this reader, judge malformed outcomes). Never
    raises for missing/corrupt files: callers treat None as "no recorded
    outcome" and the cell-state validators fail closed on defects."""
    try:
        exp = load_expansion(fam_c_dir)
    except (ValueError, OSError):
        return None
    prom = expected_event(exp, block, family, "PROMOTION", universe)
    if prom is None:
        return None
    try:
        denial = verify_namespace_ancestry(fam_c_dir, block, universe,
                                           family,
                                           tail=("runs", prom["cell_id"]))
        if denial:
            return None
        op = os.path.join(run_dir(fam_c_dir, prom), PROMOTION_OUTCOME_FILE)
        if os.path.islink(op) or not os.path.isfile(op):
            return None
        obj = _read_json(op)
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def not_promoted_recorded(fam_c_dir, block, family, universe):
    """True iff the universe's RECORDED promotion outcome is the terminal
    NOT-PROMOTED record. EPOCH-2: the DERIVED NOT-PROMOTED terminal (the
    committed chains' failed validation) is progress-valid before the
    record exists, but the governance act that WRITES the record is still
    owed — promotion.next_event() keeps deriving PROMOTION for such a
    universe until this predicate is true."""
    oc = promotion_outcome(fam_c_dir, block, family, universe)
    return isinstance(oc, dict) and oc.get("outcome") == "NOT-PROMOTED"


def lock_outcome(fam_c_dir, block, family, universe):
    """Read the recorded CAPABILITY_LOCK terminal outcome for one universe,
    or None. Mirrors promotion_outcome(): absent, unreadable or unparsable
    yields None — the strict validators, not this reader, judge malformed
    outcomes, and callers treat None as "no recorded outcome" while the
    cell-state validators fail closed on defects."""
    try:
        exp = load_expansion(fam_c_dir)
    except (ValueError, OSError):
        return None
    lc = expected_event(exp, block, family, "CAPABILITY_LOCK", universe)
    if lc is None:
        return None
    try:
        denial = verify_namespace_ancestry(fam_c_dir, block, universe,
                                           family,
                                           tail=("runs", lc["cell_id"]))
        if denial:
            return None
        op = os.path.join(run_dir(fam_c_dir, lc),
                          CAPABILITY_LOCK_OUTCOME_FILE)
        if os.path.islink(op) or not os.path.isfile(op):
            return None
        obj = _read_json(op)
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _failed_acquisition_cause(fam_c_dir, block, family, universe):
    """Best-effort validation_failure cause of a NOT-PROMOTED universe's T1
    chain event (for NOT-EVALUABLE reasons). Falls back to the outcome's
    own reason, then to the fixed outcome reason."""
    try:
        exp = load_expansion(fam_c_dir)
        t1 = expected_event(exp, block, family, "T1", universe)
        if t1 is not None:
            cp = os.path.join(run_dir(fam_c_dir, t1), "EVIDENCE-CHAIN.jsonl")
            if not os.path.islink(cp) and os.path.isfile(cp):
                links = [json.loads(line) for line in open(cp)
                         if line.strip()]
                cvs = [l for l in links
                       if l.get("kind") == "candidate-validation"]
                if len(cvs) == 1:
                    vf = (cvs[0].get("payload") or {}).get(
                        "validation_failure")
                    if isinstance(vf, str) and vf.strip():
                        return vf
    except (OSError, ValueError):
        pass
    oc = promotion_outcome(fam_c_dir, block, family, universe)
    if isinstance(oc, dict) and isinstance(oc.get("reason"), str) \
            and oc["reason"].strip():
        return oc["reason"]
    # EPOCH-3: no candidate-validation event exists on a terminal branch —
    # name the terminal failure event instead of the chain vocabulary.
    _tev = acquisition_failure_terminal(fam_c_dir, block, family, universe)
    if _tev is not None:
        if _tev["failure_event"] == "T0":
            return ("T0 MODEL-OUTPUT-INVALID (no candidate exists; "
                    "T1 NOT-EVALUABLE)")
        return ("T1 MODEL-OUTPUT-INVALID (the real T0 candidate exists but "
                "was never validly validated)")
    return "candidate-validation-failed"


def acquisition_failed(fam_c_dir, block, family, universe, _exp=None):
    """A12d D1-B3/B4: the failed-acquisition predicate, derived from
    COMMITTED evidence (never from the outcome file alone).

    Returns (failed, cause): failed is True iff the universe's T0 and T1
    acquisition runs are each validated COMPLETE, the T1 chain carries
    EXACTLY ONE candidate-validation event with validated=false, and the
    event's candidate_sha256 equals the frozen T0 arrival candidate. cause
    is the event's validation_failure (or the fixed outcome reason).
    Never raises: undecidable (missing/unreadable evidence) is (False,
    reason). The recorded PROMOTION-OUTCOME.json corroborates this
    predicate but never substitutes for it."""
    try:
        return _acquisition_failed_inner(fam_c_dir, block, family,
                                         universe, _exp)
    except Exception:                               # noqa: BLE001
        return False, "candidate-validation-failed"


def _acquisition_failed_inner(fam_c_dir, block, family, universe, _exp=None):
    """The predicate below is a conjunction, so the CHEAP committed-artifact
    reads run FIRST and the full T0/T1 COMPLETE validations (chain
    re-verification + admissibility classification) LAST: a healthy
    universe short-circuits on its T1 chain carrying no failed
    candidate-validation event, while a genuinely failed one still demands
    both acquisitions validated COMPLETE before the predicate can hold.
    Identical semantics, bounded cost on the prefix-walk hot path."""
    try:
        exp = _exp if _exp is not None else load_expansion(fam_c_dir)
    except (ValueError, OSError):
        return False, "candidate-validation-failed"
    t0 = expected_event(exp, block, family, "T0", universe)
    t1 = expected_event(exp, block, family, "T1", universe)
    if t0 is None or t1 is None:
        return False, "candidate-validation-failed"
    # EPOCH-3 terminal disjuncts (§3): a validated MODEL-OUTPUT-INVALID
    # terminal on the T0 cell (no candidate ever existed) or on the T1 cell
    # (T0 COMPLETE, the real candidate was never validly validated) fails
    # the acquisition exactly like a failed T1 candidate validation — the
    # universe still yields NOT-EVALUABLE downstream and the runner's
    # pre-call ACQUISITION-FAILED-DENY still fires.
    _tev = acquisition_failure_terminal(fam_c_dir, block, family, universe,
                                       exp)
    if _tev is not None:
        if _tev["failure_event"] == "T0":
            return True, ("T0 MODEL-OUTPUT-INVALID (no candidate exists; "
                          "T1 NOT-EVALUABLE)")
        return True, ("T1 MODEL-OUTPUT-INVALID (the real T0 candidate "
                      "exists but was never validly validated)")
    try:
        cp = os.path.join(run_dir(fam_c_dir, t1), "EVIDENCE-CHAIN.jsonl")
        if os.path.islink(cp) or not os.path.isfile(cp):
            return False, "candidate-validation-failed"
        links = [json.loads(line) for line in open(cp) if line.strip()]
    except (OSError, ValueError):
        return False, "candidate-validation-failed"
    cvs = [l for l in links if l.get("kind") == "candidate-validation"]
    if len(cvs) != 1:
        return False, "candidate-validation-failed"
    pay = cvs[0].get("payload") or {}
    if pay.get("validated") is not False:
        return False, "candidate-validation-failed"
    try:
        arrival = _read_json(os.path.join(run_dir(fam_c_dir, t0),
                                          "arrival.json"))
        s = (arrival.get("execution_payload") or {}).get("solver_py")
        if not isinstance(s, str) or not s.strip():
            return False, "candidate-validation-failed"
        frozen = hashlib.sha256(s.encode()).hexdigest()
    except (OSError, ValueError):
        return False, "candidate-validation-failed"
    if pay.get("candidate_sha256") != frozen:
        return False, "candidate-validation-failed"
    if _local_state(fam_c_dir, t0, None, exp)["status"] != "COMPLETE":
        return False, "candidate-validation-failed"
    if _local_state(fam_c_dir, t1, None, exp)["status"] != "COMPLETE":
        return False, "candidate-validation-failed"
    vf = pay.get("validation_failure")
    cause = vf if isinstance(vf, str) and vf.strip() \
        else "candidate-validation-failed"
    return True, cause


def candidate_input_lineage_reasons(t1_run_dir, pay):
    """A12d D1-C3: re-derive the candidate-input lineage from the COMMITTED
    artifacts — the persisted CANDIDATE-INPUT-MANIFEST.json file bytes plus
    the chain event — never from the receipt. Returns reasons (empty =
    verified); every mismatch names the exact field:
      manifest bytes sha256 != event `candidate_input_manifest_sha256`;
      manifest recomputed tree hash != event `candidate_input_tree_sha256`.
    The tree hash is recomputed exactly per C1 (sha256 of json.dumps of
    the manifest WITHOUT tree_sha256, sort_keys=True, indent=1, plus a
    trailing newline)."""
    out = []
    want_file = pay.get("candidate_input_manifest_sha256")
    want_tree = pay.get("candidate_input_tree_sha256")
    if not (isinstance(want_file, str) and len(want_file) == 64):
        out.append("candidate_input_manifest_sha256 is not a 64-hex "
                   f"lineage hash (got {want_file!r})")
        return out
    try:
        int(want_file, 16)
    except ValueError:
        out.append("candidate_input_manifest_sha256 is not 64-hex "
                   f"(got {want_file!r})")
        return out
    mf = os.path.join(t1_run_dir, "CANDIDATE-INPUT-MANIFEST.json")
    try:
        raw = open(mf, "rb").read()
    except OSError as e:
        out.append(f"candidate_input_manifest_sha256 unverifiable: the "
                   f"persisted candidate-input manifest is absent or "
                   f"unreadable at {mf} ({e})")
        return out
    if hashlib.sha256(raw).hexdigest() != want_file:
        out.append(f"candidate_input_manifest_sha256 "
                   f"{want_file[:12]} != sha256 of the persisted "
                   f"CANDIDATE-INPUT-MANIFEST.json bytes "
                   f"{hashlib.sha256(raw).hexdigest()[:12]} (tamper the "
                   f"persisted manifest -> deny)")
        return out
    try:
        manifest = json.loads(raw.decode())
    except ValueError as e:
        out.append(f"candidate_input_manifest_sha256 manifest unparsable "
                   f"(file hash matches but content is not JSON: {e})")
        return out
    if not isinstance(manifest, dict) or manifest.get("schema") != \
            "candidate-input-manifest-v1" or not isinstance(
                manifest.get("entries"), list):
        out.append("candidate_input_manifest_sha256 manifest is not a "
                   "candidate-input-manifest-v1 object with an entries "
                   "list (file hash matches but content is not a lineage "
                   "manifest)")
        return out
    if not (isinstance(want_tree, str) and len(want_tree) == 64):
        out.append("candidate_input_tree_sha256 is not a 64-hex lineage "
                   f"hash (got {want_tree!r})")
        return out
    try:
        int(want_tree, 16)
    except ValueError:
        out.append("candidate_input_tree_sha256 is not 64-hex "
                   f"(got {want_tree!r})")
        return out
    canonical = json.dumps({"schema": manifest["schema"],
                            "entries": manifest["entries"]},
                           sort_keys=True, indent=1) + "\n"
    recomputed = hashlib.sha256(canonical.encode()).hexdigest()
    if recomputed != want_tree:
        out.append(f"candidate_input_tree_sha256 {want_tree[:12]} != the "
                   f"recomputed tree hash {recomputed[:12]} of the "
                   f"persisted manifest entries (tamper one entry's sha "
                   f"-> deny)")
    return out


# ---------------------------------------------------------------------------
# EPOCH-3 (EPOCH-3-PROTOCOL-SPEC.md, frozen at 28cdf2a2…): the
# MODEL-OUTPUT-INVALID terminal, its STRICT validator (including the
# deterministic replay of the preserved response through the frozen parse
# gate), the attempt ledger (the enumeration authority for the two
# lane-reliability statistics) and the §3.1 governance evidence union.
#
# The terminal is the ONE lawful ordered-path representation of "provider
# call exists + response bytes returned + contract denial + no arrival".
# Progress status is not experimental correctness: a COMPLETE-FAILURE
# terminal is progress-valid but its experimental task outcome is FAIL /
# non-SHIP, and it authorizes nothing (no promotion, no lock, no
# consumption, no retry, no verdict).
# ---------------------------------------------------------------------------

MODEL_OUTPUT_INVALID_FILE = "MODEL-OUTPUT-INVALID.json"
MODEL_OUTPUT_INVALID_SCHEMA = "famc-model-output-invalid-v1"
MODEL_OUTPUT_INVALID_STATUS = "COMPLETE-FAILURE"
MODEL_OUTPUT_INVALID_CLASS = "MODEL-OUTPUT-INVALID"
MODEL_OUTPUT_INVALID_CREATED_BY = "benchmarks/fam-c/harness-run/run_arm_h1.py"
ATTEMPT_LEDGER_FILE = "ATTEMPT-LEDGER.jsonl"
ATTEMPT_LEDGER_SCHEMA = "famc-attempt-ledger-v1"
ATTEMPT_NO_SAMPLE = "NO-MODEL-SAMPLE-INFRASTRUCTURE"
ATTEMPT_ADMISSIBLE = "ADMISSIBLE"
ACQ_FAILURE_REASON = "acquisition-failed"
# The eligible contract_error set: exactly the named contract errors raised
# by extract()/_validate_arrival() at the parse gate. CONTRACT-DECISION-DENY
# raised LATER by execute_arrival() (arm illegality) is NOT eligible.
ELIGIBLE_CONTRACT_PREFIXES = ("CONTRACT-PARSE-DENY",
                              "CONTRACT-DECISION-DENY")
PARSER_AUTHORITY = [
    "benchmarks/fam-c/harness-run/run_arm_h1.py:extract",
    "benchmarks/fam-c/harness-run/run_arm_h1.py:_validate_arrival"]
# Forbidden companions (§1): a lawful terminal coexists with none of these.
TERMINAL_FORBIDDEN_COMPANIONS = (
    "arrival.json", "H1-RUN-MANIFEST.json", "EVIDENCE-CHAIN.jsonl",
    "OUTPUT.json", "adapter.py", "candidate.py",
    "CANDIDATE-INPUT-MANIFEST.json", "CANDIDATE-OUTPUT.json",
    "frozen-evaluator", "A13-SEAL.json", "A13-CAUSAL-RECEIPT.json",
    "A13-GRADING.json", "A13-GRADING-PLAN.json", "A13-JOURNAL.json")
# cell-identity surface: terminal field -> expansion cell key (order_sha256
# is compared against the expansion's own order hash).
_TERMINAL_IDENTITY_FIELDS = (
    ("cell_id", "cell_id"), ("cell_index", "index"), ("block", "block"),
    ("family", "family"), ("task", "task"), ("cell_event", "event"),
    ("cell_kind", "kind"), ("cell_universe", "universe"),
    ("cell_letter", "letter"), ("lane", "lane"), ("arm", "arm"),
    ("capability_id", "capability_id"))
_TERMINAL_AUTHORITY_BINDINGS = (
    "protocol_lock_sha256", "execution_lock_sha256",
    "execution_harness_manifest_sha256", "epoch3_protocol_spec_sha256")
_HEX_DIGITS = frozenset("0123456789abcdef")


def _is_hex(value, n):
    """64/16-lowercase-hex shape check WITHOUT a module-level shape
    predicate (the atomic/token shape authority lives in one place;
    D8.1 static rule)."""
    return (isinstance(value, str) and len(value) == n
            and all(ch in _HEX_DIGITS for ch in value))
_PARSER_CACHE = {}


def eligible_contract_error(message):
    """True iff `message` is one of the ELIGIBLE named contract errors
    (§1): a CONTRACT-PARSE-DENY, or the CONTRACT-DECISION-DENY raised by
    _validate_arrival() for an unknown decision value."""
    return (isinstance(message, str)
            and message.startswith(ELIGIBLE_CONTRACT_PREFIXES))


def _runner_module(fam_c_dir):
    """The FROZEN parse gate (harness-run/run_arm_h1.py) loaded from the
    tree under validation, so the replay judges the preserved response with
    exactly the bytes the run used. Fail closed (RuntimeError)."""
    path = os.path.join(os.path.abspath(fam_c_dir), "harness-run",
                        "run_arm_h1.py")
    key = os.path.realpath(path)
    mod = _PARSER_CACHE.get(key)
    if mod is not None:
        return mod
    if not os.path.isfile(path):
        raise RuntimeError(f"PARSER-UNAVAILABLE: {path} missing (the "
                           f"terminal replay requires the frozen parse gate)")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_famc_run_arm_h1_replay_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"PARSER-UNAVAILABLE: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _PARSER_CACHE[key] = mod
    return mod


def replay_parse_gate(fam_c_dir, raw_text):
    """Replay preserved response TEXT through the frozen extract().

    Returns {"arrived": bool, "arrival": obj|None, "parse_mode": str|None,
    "error": <message>|None, "eligible": bool}. A11b.2 is deterministic: a
    lawful terminal's replay must raise the SAME eligible named error; an
    arrival (or a different error) makes the terminal INADMISSIBLE."""
    extract = getattr(_runner_module(fam_c_dir), "extract", None)
    if not callable(extract):
        raise RuntimeError("PARSER-UNAVAILABLE: extract() not found in the "
                           "frozen parse gate")
    try:
        arrival, parse_mode = extract(raw_text)
    except ValueError as e:
        msg = str(e)
        return {"arrived": False, "arrival": None, "parse_mode": None,
                "error": msg, "eligible": eligible_contract_error(msg)}
    except Exception as e:                                  # noqa: BLE001
        return {"arrived": False, "arrival": None, "parse_mode": None,
                "error": f"{type(e).__name__}: {e}", "eligible": False}
    return {"arrived": True, "arrival": arrival, "parse_mode": parse_mode,
            "error": None, "eligible": False}


def _active_lock_files(fam_c_dir):
    """(execution, protocol) lock FILE NAMES of the ACTIVE epoch."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import epoch as _E
    return _E.active_lock_names(fam_c_dir)


def terminal_bindings(fam_c_dir):
    """The execution authority a lawful terminal is minted under: the
    ACTIVE epoch's execution + protocol lock bytes, the execution lock's
    recorded harness manifest, and the frozen epoch-3 spec bytes. The spec
    hash comes from the ACTIVE epoch-3 transition citation when epoch 3 is
    active (never from a live re-read of mutable bytes alone), and the
    on-disk spec must still hash to it."""
    ex_name, pr_name = _active_lock_files(fam_c_dir)
    out = {}
    for key, name in (("protocol_lock_sha256", pr_name),
                      ("execution_lock_sha256", ex_name)):
        try:
            out[key] = _sha256_file(os.path.join(fam_c_dir, name))
        except OSError:
            out[key] = None
    try:
        out["execution_harness_manifest_sha256"] = _read_json(
            os.path.join(fam_c_dir, ex_name)).get("harness_manifest_sha256")
    except (OSError, ValueError):
        out["execution_harness_manifest_sha256"] = None
    want = None
    try:
        _tr = _read_json(os.path.join(fam_c_dir, "EPOCH-3-TRANSITION.json"))
        if isinstance(_tr, dict):
            want = _tr.get("epoch3_protocol_spec_sha256")
    except (OSError, ValueError):
        want = None
    got = None
    try:
        got = _sha256_file(os.path.join(fam_c_dir, "EPOCH-3-PROTOCOL-SPEC.md"))
    except OSError:
        got = None
    out["epoch3_protocol_spec_sha256"] = got if (want is not None
                                                 and want == got) else None
    return out


def frozen_t0_candidate_sha256(fam_c_dir, t0_cell):
    """sha256 of the REAL frozen T0 candidate (arrival.json
    execution_payload.solver_py), or None when the T0 arrival carries no
    candidate string."""
    try:
        arrival = _read_json(os.path.join(run_dir(fam_c_dir, t0_cell),
                                          "arrival.json"))
        s = (arrival.get("execution_payload") or {}).get("solver_py")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(s, str) or not s.strip():
        return None
    return hashlib.sha256(s.encode()).hexdigest()


def attempt_ledger_rows(run_dir_):
    """Parse one cell's ATTEMPT-LEDGER.jsonl. Returns (rows, findings);
    each row must be a JSON object."""
    p = os.path.join(run_dir_, ATTEMPT_LEDGER_FILE)
    if os.path.islink(p) or not os.path.isfile(p):
        return None, [f"attempt ledger absent at {p}"]
    rows, findings = [], []
    try:
        with open(p) as f:
            raw = f.read()
    except OSError as e:
        return None, [f"attempt ledger unreadable: {e}"]
    for i, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError as e:
            findings.append(f"attempt ledger row {i} unparsable: {e}")
            continue
        if not isinstance(obj, dict):
            findings.append(f"attempt ledger row {i} is not a JSON object")
            continue
        rows.append(obj)
    return rows, findings


def attempt_ledger_reasons(fam_c_dir, cell, terminal_obj=None,
                          terminal_pending=False):
    """§4 ledger rules, fail closed. The ledger is the ENUMERATION
    AUTHORITY: one row per authorized provider invocation, in call order.

      * every row carries schema + a 64-hex request_body_sha256;
      * response_text_sha256 / response_bytes / usage_receipt_sha256 /
        identity_record_sha256 may be null ONLY for the named
        no-model-sample infrastructure outcome;
      * present hashes MUST cross-check the actual files on disk;
      * a lawful MODEL-OUTPUT-INVALID terminal corresponds to exactly one
        authorized ledger row, and vice versa.

    `terminal_pending` is the WRITER's pre-create self-check: the ledger row
    is already durable and the terminal is about to be created by the same
    call, so the "denial row without a terminal" direction is skipped here
    and re-asserted by the full validation immediately after the atomic
    create (a post-create failure leaves the terminal INADMISSIBLE and
    blocks the walk — fail closed, never silently accepted)."""
    d = run_dir(fam_c_dir, cell)
    rows, findings = attempt_ledger_rows(d)
    out = list(findings)
    if rows is None:
        return out
    if not rows:
        return out + [f"attempt ledger at {d} enumerates no provider "
                      f"invocation (the ledger is the enumeration "
                      f"authority; an empty ledger implies no call)"]
    want_idx = 0
    for i, row in enumerate(rows, 1):
        pre = f"attempt ledger row {i}"
        if row.get("schema") != ATTEMPT_LEDGER_SCHEMA:
            out.append(f"{pre}: schema {row.get('schema')!r} != "
                       f"{ATTEMPT_LEDGER_SCHEMA!r}")
        ai = row.get("attempt_index")
        if ai != want_idx + 1:
            out.append(f"{pre}: attempt_index {ai!r} != {want_idx + 1} "
                       f"(rows enumerate provider invocations in call "
                       f"order, one per invocation)")
        want_idx += 1
        call_id = row.get("provider_call_id")
        if not isinstance(call_id, str) or not call_id:
            out.append(f"{pre}: provider_call_id missing/empty")
        rb = row.get("request_body_sha256")
        if not _is_hex(rb, 64):
            out.append(f"{pre}: request_body_sha256 {rb!r} is not 64-hex "
                       f"(required on EVERY row)")
        outcome = row.get("outcome")
        no_sample = (outcome == ATTEMPT_NO_SAMPLE)
        rsha, rbytes = row.get("response_text_sha256"), row.get("response_bytes")
        urc, ids = row.get("usage_receipt_sha256"), row.get("identity_record_sha256")
        nulls = [k for k, v in (("response_text_sha256", rsha),
                                ("response_bytes", rbytes),
                                ("usage_receipt_sha256", urc),
                                ("identity_record_sha256", ids))
                 if v is None]
        if nulls and not no_sample:
            out.append(f"{pre}: {', '.join(nulls)} null without the named "
                       f"no-sample infrastructure outcome {ATTEMPT_NO_SAMPLE!r} "
                       f"(got outcome {outcome!r}); null response/usage/"
                       f"identity fields are lawful ONLY for a true "
                       f"no-model-sample infrastructure failure")
        if no_sample and len(nulls) != 4:
            out.append(f"{pre}: outcome {ATTEMPT_NO_SAMPLE!r} requires ALL "
                       f"of response_text_sha256/response_bytes/"
                       f"usage_receipt_sha256/identity_record_sha256 null")
        if not isinstance(call_id, str) or not call_id:
            continue
        receipt = os.path.join(d, f"call-{call_id}.json")
        req = os.path.join(d, f"call-{call_id}.request.json")
        nu = os.path.join(d, f"call-{call_id}.normalized.json")
        idp = os.path.join(d, "identity.json")
        # request_body_sha256 is required on EVERY row and must cross-check
        # the persisted request bytes (present on every path, including a
        # true no-sample infrastructure invocation).
        if isinstance(rb, str):
            if os.path.islink(req) or not os.path.isfile(req):
                out.append(f"{pre}: no persisted request body "
                           f"{os.path.basename(req)} (every row's "
                           f"request_body_sha256 must cross-check the bytes "
                           f"on disk)")
            else:
                try:
                    got_req = _sha256_file(req)
                except OSError as e:
                    out.append(f"{pre}: request body unreadable: {e}")
                else:
                    if rb != got_req:
                        out.append(f"{pre}: request_body_sha256 {rb[:12]} != "
                                   f"the persisted "
                                   f"{os.path.basename(req)} sha256 "
                                   f"{got_req[:12]}")
        if not no_sample:
            rawp = os.path.join(d, f"raw-{call_id}.txt")
            try:
                raw_bytes = open(rawp, "rb").read()
            except OSError as e:
                out.append(f"{pre}: preserved response {os.path.basename(rawp)} "
                           f"missing/unreadable: {e} (per-attempt response "
                           f"preservation is required on every path)")
            else:
                got = hashlib.sha256(raw_bytes).hexdigest()
                if rsha != got:
                    out.append(f"{pre}: response_text_sha256 {str(rsha)[:12]} "
                               f"!= sha256 of {os.path.basename(rawp)} "
                               f"{got[:12]}")
                if rbytes != len(raw_bytes):
                    out.append(f"{pre}: response_bytes {rbytes!r} != the "
                               f"preserved response length {len(raw_bytes)}")
            for key, path in (("usage_receipt_sha256", receipt),
                              ("identity_record_sha256", idp)):
                val = row.get(key)
                try:
                    got = _sha256_file(path)
                except OSError:
                    continue    # the terminal validator names missing files
                if val != got:
                    out.append(f"{pre}: {key} {str(val)[:12]} != sha256 of "
                               f"{os.path.basename(path)} {got[:12]}")
        try:
            rc = _read_json(receipt)
        except (OSError, ValueError):
            rc = None
        if isinstance(rc, dict):
            if rc.get("request_body_sha256") != rb:
                out.append(f"{pre}: request_body_sha256 {str(rb)[:12]} != the "
                           f"receipt's recorded "
                           f"{str(rc.get('request_body_sha256'))[:12]} "
                           f"(read back from the receipt, never recomputed)")
            if rc.get("call_id") != call_id:
                out.append(f"{pre}: provider_call_id {call_id!r} != the "
                           f"receipt's call_id {rc.get('call_id')!r}")
        if row.get("authorized_estimand_attempt") is not True:
            out.append(f"{pre}: authorized_estimand_attempt "
                       f"{row.get('authorized_estimand_attempt')!r} != True "
                       f"(N=1: every epoch-3 ledger row is the authorized "
                       f"first sample; there is no lawful diagnostic "
                       f"repeat)")
    # terminal <-> row correspondence (both directions)
    tp = os.path.join(d, MODEL_OUTPUT_INVALID_FILE)
    has_terminal = os.path.lexists(tp)
    terminal_rows = [r for r in rows
                     if eligible_contract_error(r.get("outcome"))]
    if has_terminal:
        obj = terminal_obj
        if obj is None:
            try:
                obj = _read_json(tp)
            except (OSError, ValueError):
                obj = None
        if len(rows) != 1 or len(terminal_rows) != 1:
            out.append(f"a lawful {MODEL_OUTPUT_INVALID_FILE} corresponds to "
                       f"exactly ONE authorized ledger row; the ledger "
                       f"enumerates {len(rows)} row(s) and "
                       f"{len(terminal_rows)} contract-denial row(s)")
        elif isinstance(obj, dict):
            row = terminal_rows[0]
            if row.get("provider_call_id") != obj.get("provider_call_id"):
                out.append("the terminal's provider_call_id != the ledger "
                           "row's provider_call_id")
            if row.get("outcome") != obj.get("contract_error"):
                out.append(f"ledger outcome {row.get('outcome')!r} != the "
                           f"terminal's contract_error "
                           f"{obj.get('contract_error')!r}")
            if row.get("response_text_sha256") != obj.get("response_text_sha256"):
                out.append("ledger response_text_sha256 != the terminal's "
                           "response_text_sha256")
    elif not terminal_pending:
        for r in terminal_rows:
            out.append(f"a ledger row records the contract denial "
                       f"{r.get('outcome')!r} but no "
                       f"{MODEL_OUTPUT_INVALID_FILE} exists (the terminal and "
                       f"the ledger row are two halves of one record)")
    return out


def validate_model_output_invalid(fam_c_dir, cell, freeze_commit=None,
                                  _exp=None):
    """STRICT §1 validator of ONE MODEL-OUTPUT-INVALID terminal. Returns
    findings (empty = lawful). Fail closed: every hash is re-derived from
    the bytes on disk, the cell identity is the production surface, the
    execution-authority bindings must match the ACTIVE authority, no
    forbidden companion may exist, and the preserved response is replayed
    through the frozen extract() — which must raise the SAME eligible named
    error recorded in contract_error."""
    d = run_dir(fam_c_dir, cell)
    tp = os.path.join(d, MODEL_OUTPUT_INVALID_FILE)
    if os.path.islink(tp):
        return [f"{MODEL_OUTPUT_INVALID_FILE} is a symlink ({tp}); refused"]
    if not os.path.isfile(tp):
        return [f"no {MODEL_OUTPUT_INVALID_FILE} at {tp}"]
    try:
        obj = _read_json(tp)
    except (OSError, ValueError) as e:
        return [f"{MODEL_OUTPUT_INVALID_FILE} unreadable: {e}"]
    return model_output_invalid_reasons(fam_c_dir, cell, obj, d, _exp=_exp)


def model_output_invalid_reasons(fam_c_dir, cell, obj, d, _exp=None,
                                 terminal_pending=False):
    """The finding set behind validate_model_output_invalid(), given an
    already-parsed terminal object (split out so a fresh write can be
    self-checked before it becomes durable)."""
    out = []
    if not isinstance(obj, dict):
        return [f"{MODEL_OUTPUT_INVALID_FILE} is not a JSON object"]
    for key, want in (("schema", MODEL_OUTPUT_INVALID_SCHEMA),
                      ("epoch", 3),
                      ("terminal_status", MODEL_OUTPUT_INVALID_STATUS),
                      ("experimental_outcome", True),
                      ("experimental_task_outcome", "FAIL"),
                      ("cell_event", cell["event"]),
                      ("parser_authority", PARSER_AUTHORITY),
                      ("contract_rule", "A11b.2"),
                      ("authorized_estimand_attempt", True),
                      ("attempt_index", 1),
                      ("created_by", MODEL_OUTPUT_INVALID_CREATED_BY)):
        if obj.get(key) != want:
            out.append(f"terminal {key} {obj.get(key)!r} != {want!r}")
    try:
        exp = _exp if _exp is not None else load_expansion(fam_c_dir)
        order_sha = exp["order_sha256"]
    except (ValueError, KeyError, OSError) as e:
        out.append(f"order expansion unreadable: {e}")
        order_sha = None
    for key, src in _TERMINAL_IDENTITY_FIELDS:
        want = cell.get(src)
        if obj.get(key) != want:
            out.append(f"terminal {key} {obj.get(key)!r} != the authorized "
                       f"cell's {src} {want!r}")
    if order_sha is not None and obj.get("order_sha256") != order_sha:
        out.append(f"terminal order_sha256 {str(obj.get('order_sha256'))[:12]} "
                   f"!= the frozen order hash {order_sha[:12]}")
    cid = obj.get("cell_id")
    if not _is_hex(cid, 16):
        out.append(f"terminal cell_id {cid!r} is not the frozen "
                   f"ORDER-EXPANSION 16-hex cell id")
    # no machine-local paths in the machine schema
    for k, v in obj.items():
        _win_abs = (isinstance(v, str) and len(v) > 2 and v[0].isalpha()
                    and v[1] == ":"
                    and (v[2] == "/" or v[2] == "\\"))
        if isinstance(v, str) and (v.startswith("/") or _win_abs):
            out.append(f"terminal field {k} carries a machine-local path "
                       f"({v[:40]!r}); the portable terminal schema carries "
                       f"no local filesystem paths")
    # forbidden companions
    for name in TERMINAL_FORBIDDEN_COMPANIONS:
        if os.path.lexists(os.path.join(d, name)):
            out.append(f"forbidden companion {name} beside "
                       f"{MODEL_OUTPUT_INVALID_FILE} (a lawful terminal "
                       f"coexists with no arrival, no manifest, no chain, "
                       f"no candidate/adapter artifact and no reuse ledger)")
    try:
        for name in sorted(os.listdir(d)):
            if name.startswith("reuse") and name.endswith(".json"):
                out.append(f"forbidden companion {name} beside "
                           f"{MODEL_OUTPUT_INVALID_FILE} (reuse ledger)")
    except OSError:
        pass
    call_id = obj.get("provider_call_id")
    if not isinstance(call_id, str) or not call_id:
        out.append("terminal provider_call_id missing/empty; the call "
                   "receipt call-<id>.json must exist in the same run dir")
        return out
    receipt = os.path.join(d, f"call-{call_id}.json")
    req = os.path.join(d, f"call-{call_id}.request.json")
    nu = os.path.join(d, f"call-{call_id}.normalized.json")
    rawp = os.path.join(d, f"raw-{call_id}.txt")
    idp = os.path.join(d, "identity.json")
    for label, p in (("call receipt", receipt),
                     ("request body", req),
                     ("normalized usage", nu),
                     ("preserved response", rawp),
                     ("identity record", idp)):
        if os.path.islink(p):
            out.append(f"terminal {label} is a symlink ({p}); refused")
        elif not os.path.isfile(p):
            out.append(f"terminal {label} missing at {p}")
    try:
        rc = _read_json(receipt)
    except (OSError, ValueError) as e:
        rc = None
        out.append(f"call receipt unparsable: {e}")
    if isinstance(rc, dict):
        if rc.get("call_id") != call_id:
            out.append(f"call receipt call_id {rc.get('call_id')!r} != the "
                       f"terminal's provider_call_id {call_id!r}")
        if rc.get("request_body_sha256") != obj.get("request_body_sha256"):
            out.append(f"terminal request_body_sha256 "
                       f"{str(obj.get('request_body_sha256'))[:12]} != the "
                       f"receipt's recorded "
                       f"{str(rc.get('request_body_sha256'))[:12]} (read back "
                       f"from the receipt, never recomputed)")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from usage import verify_request_binding, verify_normalized_usage
        verify_request_binding(receipt, idp)
        verify_normalized_usage(nu)
    except (ValueError, OSError, ImportError) as e:
        out.append(f"request/adapter/usage/identity binding invalid: {e}")
    raw_bytes = None
    if os.path.isfile(rawp) and not os.path.islink(rawp):
        try:
            raw_bytes = open(rawp, "rb").read()
        except OSError as e:
            out.append(f"preserved response unreadable: {e}")
    if raw_bytes is not None:
        got = hashlib.sha256(raw_bytes).hexdigest()
        if obj.get("response_text_sha256") != got:
            out.append(f"terminal response_text_sha256 "
                       f"{str(obj.get('response_text_sha256'))[:12]} != the "
                       f"preserved raw-{call_id}.txt sha256 {got[:12]}")
        if obj.get("response_bytes") != len(raw_bytes):
            out.append(f"terminal response_bytes {obj.get('response_bytes')!r} "
                       f"!= the preserved response length "
                       f"{len(raw_bytes)}")
    for key, p in (("usage_receipt_sha256", receipt),
                   ("normalized_usage_sha256", nu),
                   ("identity_record_sha256", idp)):
        val = obj.get(key)
        if not _is_hex(val, 64):
            out.append(f"terminal {key} {val!r} is not 64-hex"
                       + (" (identity is REQUIRED and non-null on a lawful "
                          "terminal: a sample whose provider/lane identity "
                          "cannot be established is inadmissible/missing "
                          "evidence, never MODEL-OUTPUT-INVALID)"
                          if key == "identity_record_sha256" else ""))
            continue
        try:
            got = _sha256_file(p)
        except OSError:
            continue
        if val != got:
            out.append(f"terminal {key} {val[:12]} != sha256 of "
                       f"{os.path.basename(p)} {got[:12]}")
    act = terminal_bindings(fam_c_dir)
    for key in _TERMINAL_AUTHORITY_BINDINGS:
        if obj.get(key) != act.get(key):
            out.append(f"terminal {key} {str(obj.get(key))[:12]} != the "
                       f"ACTIVE authority {str(act.get(key))[:12]} "
                       f"(lock/manifest/spec bindings must match at "
                       f"validation time)")
    err = obj.get("contract_error")
    if not eligible_contract_error(err):
        out.append(f"terminal contract_error {err!r} is not an eligible "
                   f"named contract error ({ELIGIBLE_CONTRACT_PREFIXES}); "
                   f"errors raised only after a lawful arrival exists are "
                   f"ordinary recorded outcomes, not this terminal")
    if raw_bytes is not None and eligible_contract_error(err):
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            text = None
            out.append(f"preserved response is not UTF-8 text: {e}")
        if text is not None:
            try:
                rep = replay_parse_gate(fam_c_dir, text)
            except RuntimeError as e:
                out.append(f"deterministic replay unavailable: {e}")
            else:
                if rep["arrived"]:
                    out.append("deterministic replay of the preserved "
                               "response produced an ARRIVAL through the "
                               "frozen extract(): A11b.2 is deterministic, "
                               "so this terminal is INADMISSIBLE")
                elif rep["error"] != err:
                    out.append(f"deterministic replay raised "
                               f"{str(rep['error'])[:80]!r} != the recorded "
                               f"contract_error {str(err)[:80]!r} "
                               f"(a different error means the recorded "
                               f"denial is not re-derivable)")
    out += attempt_ledger_reasons(fam_c_dir, cell, terminal_obj=obj,
                                  terminal_pending=terminal_pending)
    return out


def _terminal_state(fam_c_dir, cell, freeze_commit=None, _exp=None):
    """Cell-state result for a run dir carrying a MODEL-OUTPUT-INVALID
    terminal: COMPLETE-FAILURE when the strict validator is green (a
    recorded experimental outcome, progress-valid, authorizing nothing),
    INADMISSIBLE on any defect (the walk blocks; no advance)."""
    d = run_dir(fam_c_dir, cell)
    tp = os.path.join(d, MODEL_OUTPUT_INVALID_FILE)
    try:
        sha = _sha256_file(tp)
    except OSError as e:
        return _result(cell, [f"terminal unreadable: {e}"], True)
    reasons = validate_model_output_invalid(fam_c_dir, cell, freeze_commit,
                                            _exp)
    if reasons:
        return _result(cell, reasons, True)
    return {"cell_id": cell["cell_id"],
            "status": MODEL_OUTPUT_INVALID_STATUS,
            "terminal_class": MODEL_OUTPUT_INVALID_CLASS,
            "terminal_record_sha256": sha,
            "reasons": [
                f"{MODEL_OUTPUT_INVALID_CLASS}: the authorized first sample "
                f"of {cell['block']}/{cell['family']}/{cell['event']}/"
                f"{cell['universe']} returned model-generated response text "
                f"that the frozen A11b.2 contract refused; the cell "
                f"completed as a recorded experimental FAILURE "
                f"(experimental_task_outcome FAIL / non-SHIP) — no arrival, "
                f"no verdict, no promotion, no lock, no retry"]}


def acquisition_failure_terminal(fam_c_dir, block, family, universe,
                                 _exp=None):
    """§3.1 — the acquisition-failure evidence union for a universe whose
    T0 or T1 cell carries a VALIDATED MODEL-OUTPUT-INVALID terminal.
    Returns {"failure_event", "acquisition_evidence", "candidate_sha256"}
    or None (no terminal, or the terminal does not validate). Both
    acquisition branches are mechanized:
      T0 terminal -> no candidate ever existed (candidate_sha256 null);
      T1 terminal -> the REAL T0 candidate exists but was never validly
                     validated (no candidate-validation event exists)."""
    try:
        exp = _exp if _exp is not None else load_expansion(fam_c_dir)
    except (ValueError, OSError):
        return None
    t0 = expected_event(exp, block, family, "T0", universe)
    t1 = expected_event(exp, block, family, "T1", universe)
    if t0 is None or t1 is None:
        return None
    for cell, fe in ((t0, "T0"), (t1, "T1")):
        tp = os.path.join(run_dir(fam_c_dir, cell), MODEL_OUTPUT_INVALID_FILE)
        if not os.path.lexists(tp):
            continue
        if validate_model_output_invalid(fam_c_dir, cell, _exp=exp):
            return None
        try:
            sha = _sha256_file(tp)
        except OSError:
            return None
        if fe == "T0":
            # The T1 of a T0-terminal universe must NEVER have run: with no
            # candidate there is nothing for T1 to see. Read the T1 run dir
            # DIRECTLY (never through _local_state, which consults this
            # predicate for its own NOT-EVALUABLE terminal — that would
            # recurse); any T1 artifact means the cell ran past the
            # terminal, which is invalid and yields no union.
            t1d = run_dir(fam_c_dir, t1)
            for art in ("arrival.json", "H1-RUN-MANIFEST.json",
                        MODEL_OUTPUT_INVALID_FILE, "EVIDENCE-CHAIN.jsonl"):
                if os.path.lexists(os.path.join(t1d, art)):
                    return None
            if os.path.isdir(t1d):
                for _n in os.listdir(t1d):
                    if _n.startswith("call-") or _n.startswith("raw"):
                        return None
            return {"failure_event": "T0",
                    "acquisition_evidence": {
                        "kind": MODEL_OUTPUT_INVALID_CLASS,
                        "terminal_sha256": sha},
                    "candidate_sha256": None}
        if _local_state(fam_c_dir, t0, None, exp)["status"] != "COMPLETE":
            return None
        cand = frozen_t0_candidate_sha256(fam_c_dir, t0)
        if cand is None:
            return None
        return {"failure_event": "T1",
                "acquisition_evidence": {
                    "kind": MODEL_OUTPUT_INVALID_CLASS,
                    "terminal_sha256": sha},
                "candidate_sha256": cand}
    return None


def _acquisition_evidence_reasons(fam_c_dir, outcome, cell, _exp=None):
    """§3.1 — re-derive the governance evidence union from disk and return
    findings (empty = lawful). A null chain tip is NEVER equivalent to an
    existing chain: the terminal sha256 is re-derived from the validated
    terminal bytes, the candidate from the frozen T0 arrival, and a wrong
    branch shape is refused."""
    out = []
    fe = outcome.get("failure_event")
    if fe not in ("T0", "T1"):
        return [f"governance record failure_event {fe!r} is not 'T0' or 'T1'"]
    ev = outcome.get("acquisition_evidence")
    if not isinstance(ev, dict):
        return ["governance record carries no acquisition_evidence object "
                "(the §3.1 evidence union is required for an "
                "acquisition-failed universe)"]
    ev = acquisition_failure_terminal(fam_c_dir, cell["block"], cell["family"],
                                      cell["universe"], _exp)
    if ev is None:
        return ["acquisition-failed universe carries no VALIDATED "
                "MODEL-OUTPUT-INVALID acquisition terminal; the §3.1 "
                "evidence union cannot be re-derived from disk"]
    got_ev = outcome.get("acquisition_evidence")
    if got_ev.get("kind") != MODEL_OUTPUT_INVALID_CLASS:
        out.append(f"acquisition_evidence kind {got_ev.get('kind')!r} != "
                   f"{MODEL_OUTPUT_INVALID_CLASS!r}")
    if outcome.get("failure_event") != ev["failure_event"]:
        out.append(f"governance record failure_event "
                   f"{outcome.get('failure_event')!r} != the validated "
                   f"terminal's {ev['failure_event']!r}")
    want_sha = ev["acquisition_evidence"]["terminal_sha256"]
    if got_ev.get("terminal_sha256") != want_sha:
        out.append(f"acquisition_evidence terminal_sha256 "
                   f"{str(got_ev.get('terminal_sha256'))[:12]} != the "
                   f"validated {ev['failure_event']} terminal sha256 "
                   f"{want_sha[:12]}")
    if "chain_tip" in got_ev and got_ev.get("chain_tip") is not None:
        out.append("acquisition_evidence carries a chain_tip beside a "
                   "MODEL-OUTPUT-INVALID terminal (a null tip is never "
                   "equivalent to a chain, and a terminal branch has no "
                   "chain tip)")
    if outcome.get("candidate_sha256") != ev["candidate_sha256"]:
        if ev["candidate_sha256"] is None:
            out.append("governance record candidate_sha256 "
                       f"{str(outcome.get('candidate_sha256'))[:12]} != null: "
                       "the T0 terminal branch has NO candidate (no "
                       "synthesized arrival/candidate exists)")
        else:
            out.append(f"governance record candidate_sha256 "
                       f"{str(outcome.get('candidate_sha256'))[:12]} != the "
                       f"real frozen T0 candidate "
                       f"{ev['candidate_sha256'][:12]}")
    return out


def terminal_evidence_row(fam_c_dir, cell, freeze_commit=None):
    """§4.1 — the PREREG §24 evidence row of a terminal cell (fail closed:
    an invalid terminal yields no row). A terminal is a NON-SHIP
    correctness failure, not missing evidence: ship False, checker fields
    null, run_manifest_hash null, evidence_hash = terminal_record_sha256,
    model_calls 1, retries 0, terminal_class MODEL-OUTPUT-INVALID;
    capability_available is DERIVED from the frozen cell / validated lock,
    while selection/load/invocation/consumption/material_contribution are
    False because no parseable decision existed."""
    reasons = validate_model_output_invalid(fam_c_dir, cell, freeze_commit)
    if reasons:
        raise ValueError("TERMINAL-EVIDENCE-DENY: " + reasons[0])
    d = run_dir(fam_c_dir, cell)
    tp = os.path.join(d, MODEL_OUTPUT_INVALID_FILE)
    obj = _read_json(tp)
    tsha = _sha256_file(tp)
    cap_available = False
    if cell.get("universe") in CAPABILITY_UNIVERSES:
        capdir = capability_dir(fam_c_dir, cell["block"], cell["universe"],
                                cell["family"])
        lockp = os.path.join(capdir, "CAPABILITY_LOCK.json")
        if os.path.isfile(lockp) and not os.path.islink(lockp):
            cap_available = True
    usage = None
    try:
        usage = _read_json(os.path.join(
            d, f"call-{obj['provider_call_id']}.normalized.json"))
    except (OSError, ValueError, KeyError):
        usage = None
    row = {"cell_id": cell["cell_id"], "cell_index": cell["index"],
           "block": cell["block"], "family": cell["family"],
           "task": cell["task"], "lane": cell["lane"], "arm": cell["arm"],
           "capability_id": cell["capability_id"],
           "ship": False, "hidden_tests_passed": None,
           "checker_verdict": None, "checker_returncode": None,
           "run_manifest_hash": None,
           "terminal_class": MODEL_OUTPUT_INVALID_CLASS,
           "terminal_record_sha256": tsha,
           "evidence_hash": tsha,
           "model_calls": 1, "retries": 0,
           "experimental_task_outcome": "FAIL",
           "contract_error": obj.get("contract_error"),
           "request_body_sha256": obj.get("request_body_sha256"),
           "response_text_sha256": obj.get("response_text_sha256"),
           "response_bytes": obj.get("response_bytes"),
           "identity_record_sha256": obj.get("identity_record_sha256"),
           "usage": usage.get("usage") if isinstance(usage, dict) else None,
           "normalized_usage_sha256": obj.get("normalized_usage_sha256"),
           "capability_available": cap_available,
           "capability_selected": False, "capability_loaded": False,
           "capability_invoked": False, "capability_consumed": False,
           "material_contribution": False,
           "authorized_estimand_attempt": True, "attempt_index": 1,
           "per_attempt_outcome": obj.get("contract_error")}
    return row


def terminal_gate_consequences(cell):
    """§4.1 gate consequences of a terminal cell: a T2/T3 terminal is a
    non-SHIP correctness failure and can NEVER create an efficiency win by
    failing cheaply; a treatment T4 terminal is NEVER a correct specificity
    rejection."""
    downstream = cell.get("event") in DOWNSTREAM_EVENTS
    return {"ship": False,
            "correctness": "FAIL",
            "efficiency_win": False,
            "specificity_rejection": False,
            "reason": ("a model-output failure is an experimental outcome, "
                       "not a harness-validation pass"
                       if downstream else
                       "an acquisition failure is a recorded terminal "
                       "outcome, not a measurement")}


def contract_admissibility_statistics(fam_c_dir, expansion=None):
    """§4 — the two lane-reliability statistics, reported SEPARATELY, never
    collapsed, with the required denominator decomposition.

      first_attempt_contract_admissibility
        = admissible first authorized samples / all authorized first samples
      all_provider_call_contract_admissibility
        = admissible model responses / all provider calls actually made

    Both are enumerated from the per-cell attempt ledgers — the ENUMERATION
    AUTHORITY (never from receipts, which a no-sample invocation does not
    have). `ADMISSIBLE` means the frozen A11b.2 contract returned an
    arrival; an eligible CONTRACT-* error is inadmissible. The
    decomposition separates CONTRACT DENIALS from INFRASTRUCTURE /
    NO-SAMPLE events so an outage is never rhetorically presented as a
    model JSON-contract failure."""
    exp = expansion if expansion is not None else load_expansion(fam_c_dir)
    first_num = first_den = all_num = all_den = 0
    contract_denials = no_sample = 0
    for cell in exp["cells"]:
        if cell.get("kind") not in MODEL_RUN_KINDS:
            continue
        rows, _findings = attempt_ledger_rows(run_dir(fam_c_dir, cell))
        if not rows:
            continue
        all_den += len(rows)
        for r in rows:
            outcome = r.get("outcome")
            if outcome == ATTEMPT_ADMISSIBLE:
                all_num += 1
            elif eligible_contract_error(outcome):
                contract_denials += 1
            elif outcome == ATTEMPT_NO_SAMPLE:
                no_sample += 1
        first = rows[0]
        if first.get("authorized_estimand_attempt") is True:
            first_den += 1
            if first.get("outcome") == ATTEMPT_ADMISSIBLE:
                first_num += 1

    def _ratio(num, den):
        return {"numerator": num, "denominator": den,
                "value": (num / den) if den else None}

    return {
        "first_attempt_contract_admissibility":
            _ratio(first_num, first_den),
        "all_provider_call_contract_admissibility":
            _ratio(all_num, all_den),
        "denominator_decomposition": {
            "contract_denials": contract_denials,
            "infrastructure_no_sample": no_sample,
            "admissible": all_num,
            "other": all_den - all_num - contract_denials - no_sample},
        "note": ("the two statistics are reported separately and are never "
                 "collapsed into one number; a no-sample infrastructure "
                 "event is never presented as a model JSON-contract "
                 "failure")}


def terminal_exit_code():
    """§4.1 — runner exit code for a successfully recorded terminal: 0 (the
    cell completed as a recorded experimental outcome, exactly as a
    committed failed candidate validation exits 0 today). Non-zero stays
    reserved for infrastructure / refusal paths."""
    return 0


def _frozen_spec_and_stop_citations(fam_c_dir):  # pragma: no cover - audit
    """The epoch-3 lineage citations the transition record must carry (the
    frozen spec bytes + the corrected stop record). Read-only helper for
    certification output."""
    out = {}
    for key, name in (("epoch3_protocol_spec_sha256",
                       "EPOCH-3-PROTOCOL-SPEC.md"),
                      ("epoch2_stop_record_sha256",
                       "EPOCH-2-STOP-RECORD.md")):
        try:
            out[key] = _sha256_file(os.path.join(fam_c_dir, name))
        except OSError:
            out[key] = None
    return out


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


def emit_promotion_outcome(fam_c_dir, cell, t0_tip, t1_tip,
                           candidate_sha256, failure_event=None,
                           acquisition_evidence=None):
    """Record the TERMINAL failed-acquisition outcome of (block, universe,
    family) (A12d D1-B3): the universe's acquisition validly failed, so
    promotion completes as RECORDED NOT-PROMOTED — not an exception, not a
    deadlock, and never a lock. Writes PROMOTION-OUTCOME.json once in the
    promotion run dir (fail closed on repromotion or on a conflicting
    receipt).

    Two lawful shapes:
      * epoch-2 chain shape: `t0_tip`/`t1_tip` are the REAL chain-link tips
        of the two validated acquisition runs and `candidate_sha256` is the
        frozen T0 candidate the failed validation tested;
      * epoch-3 §3.1 terminal shape (`failure_event` T0/T1 +
        `acquisition_evidence`): the acquisition terminated through a
        validated MODEL-OUTPUT-INVALID terminal. The evidence union is
        re-derived from disk BEFORE the record is written (fail closed);
        `candidate_sha256` must be null for a T0 terminal (no candidate ever
        existed) and the real frozen T0 candidate for a T1 terminal.
    Returns the outcome path."""
    _union = (failure_event is not None) or (acquisition_evidence is not None)
    if _union:
        if failure_event not in ("T0", "T1") or \
                not isinstance(acquisition_evidence, dict):
            raise ValueError("PROMOTION-DENY an epoch-3 failed-acquisition "
                             "outcome requires failure_event T0|T1 AND an "
                             "acquisition_evidence object")
        if t0_tip is not None or t1_tip is not None:
            raise ValueError("PROMOTION-DENY an epoch-3 terminal-branch "
                             "outcome binds no chain tips (a terminal "
                             "branch has no chain; a null tip is never "
                             "equivalent to a chain)")
        probe = {"event": "PROMOTION", "cell_id": cell["cell_id"],
                 "block": cell["block"], "family": cell["family"],
                 "universe": cell["universe"], "outcome": "NOT-PROMOTED",
                 "reason": ACQ_FAILURE_REASON,
                 "failure_event": failure_event,
                 "acquisition_evidence": acquisition_evidence,
                 "candidate_sha256": candidate_sha256}
        _findings = _acquisition_evidence_reasons(fam_c_dir, probe, cell)
        if _findings:
            raise ValueError("PROMOTION-DENY the §3.1 acquisition evidence "
                             "union does not re-derive from disk: "
                             + _findings[0])
    else:
        for tag, tip in (("T0", t0_tip), ("T1", t1_tip)):
            if not isinstance(tip, str) or len(tip) != 64:
                raise ValueError(f"PROMOTION-DENY {tag} chain tip must be a "
                                 f"64-hex link_hash, got {tip!r}")
        if not (isinstance(candidate_sha256, str)
                and len(candidate_sha256) == 64):
            raise ValueError("PROMOTION-DENY candidate sha256 must be 64-hex, "
                             f"got {candidate_sha256!r}")
        try:
            int(candidate_sha256, 16)
        except ValueError:
            raise ValueError("PROMOTION-DENY candidate sha256 must be 64-hex, "
                             f"got {candidate_sha256!r}") from None
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
        # EPOCH-2: the DERIVED NOT-PROMOTED terminal is progress-valid
        # before the record exists, but recording it IS the act owed here —
        # the cell's own derived presence is therefore not a duplicate for
        # THIS writer. A cell that validates COMPLETE is untouched: the
        # duplicate refusal below still fires (a validated promotion cannot
        # become NOT-PROMOTED).
        if _local_state(fam_c_dir, cell, None)["status"] == "NOT-PROMOTED":
            done.pop(cell["cell_id"], None)
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
    rp = os.path.join(d, PROMOTION_RECEIPT_FILE)
    if os.path.exists(rp):
        raise PermissionError("PROMOTION-DENY promotion receipt already "
                              "exists (a validated promotion cannot become "
                              "NOT-PROMOTED)")
    op = os.path.join(d, PROMOTION_OUTCOME_FILE)
    if os.path.exists(op):
        raise PermissionError("PROMOTION-DENY outcome already recorded "
                              "(no repromotion of a failed acquisition)")
    outcome = {"event": "PROMOTION", "cell_id": cell["cell_id"],
               "block": cell["block"], "family": cell["family"],
               "universe": cell["universe"], "outcome": "NOT-PROMOTED",
               "reason": ACQ_FAILURE_REASON if _union
               else "candidate-validation-failed",
               "created_from": "frozen-evidence",
               "candidate_sha256": candidate_sha256}
    if _union:
        outcome["failure_event"] = failure_event
        outcome["acquisition_evidence"] = acquisition_evidence
    else:
        outcome["t0_tip"] = t0_tip
        outcome["t1_tip"] = t1_tip
    with open(op, "w") as f:
        json.dump(outcome, f, indent=1)
    return op


def emit_capability_lock_outcome(fam_c_dir, cell, freeze_commit=None):
    """Record the TERMINAL NOT-LOCKED outcome of the CAPABILITY_LOCK event
    (EPOCH-1-CLOSURE.md epoch-2 ruling: PROMOTION NOT-PROMOTED => the lock
    event completes as NOT-LOCKED, never a lock, never a deadlock).

    The record binds the RECORDED NOT-PROMOTED promotion outcome BYTES
    (`promotion_outcome_sha256`) and cell (`promotion_cell_id`) plus the
    REAL validated T0/T1 chain tips (`acquisition_chain_tips`), and is
    written ONCE in the lock cell's DERIVED run dir. Fail closed on: a real
    CAPABILITY_LOCK, a conflicting promotion receipt, a PROMOTION cell
    that is not validated NOT-PROMOTED, stray governance artifacts in the
    lock run dir, an out-of-order prefix, and re-invocation (idempotent
    refusal — no relock, no retry). Returns the outcome path."""
    if cell.get("event") != "CAPABILITY_LOCK":
        raise ValueError(f"LOCK-DENY cell event {cell.get('event')!r} is "
                         f"not CAPABILITY_LOCK")
    want = capability_id(cell["block"], cell["universe"], cell["family"])
    if cell["capability_id"] != want:
        raise ValueError(f"LOCK-DENY cell capability_id "
                         f"{cell['capability_id']!r} != derived {want!r}")
    try:
        exp = load_expansion(fam_c_dir)
    except (ValueError, OSError) as e:
        raise PermissionError(f"LOCK-DENY order unreadable: {e}")
    exp_cell = expected_event(exp, cell["block"], cell["family"],
                              "CAPABILITY_LOCK", cell["universe"])
    if exp_cell is None or exp_cell["cell_id"] != cell["cell_id"]:
        raise PermissionError("LOCK-DENY cell is not the enumerated "
                              "CAPABILITY_LOCK event of "
                              f"{cell['block']}/{cell['family']}/"
                              f"{cell['universe']}")
    capdir = capability_dir(fam_c_dir, cell["block"], cell["universe"],
                            cell["family"])
    if os.path.exists(os.path.join(capdir, "CAPABILITY_LOCK.json")):
        raise PermissionError(
            f"LOCK-DENY a CAPABILITY_LOCK exists for "
            f"{cell['block']}/{cell['family']}/{cell['universe']}: a real "
            f"lock and a NOT-LOCKED terminal are mutually exclusive")
    prom = expected_event(exp, cell["block"], cell["family"], "PROMOTION",
                          cell["universe"])
    if prom is None:
        raise PermissionError("LOCK-DENY no PROMOTION cell in the order for "
                              f"{cell['block']}/{cell['family']}/"
                              f"{cell['universe']}")
    rp = os.path.join(run_dir(fam_c_dir, prom), PROMOTION_RECEIPT_FILE)
    if os.path.exists(rp):
        raise PermissionError(
            f"LOCK-DENY a promotion receipt exists for "
            f"{cell['block']}/{cell['family']}/{cell['universe']} (a "
            f"validated promotion can never be NOT-LOCKED; conflicting "
            f"receipt)")
    # the promotion must BE the validated terminal NOT-PROMOTED state —
    # re-derived here, never taken from the caller's claim.
    done = completed_cells(fam_c_dir, freeze_commit, exp)
    missing = [c for c in exp["cells"]
               if c["index"] < cell["index"] and c["cell_id"] not in done]
    if missing:
        m = missing[0]
        raise PermissionError(
            f"LOCK-DENY out of order — the CAPABILITY_LOCK event "
            f"{cell['cell_id']} cannot complete before {len(missing)} "
            f"earlier cell(s); earliest missing is {m['cell_id']} "
            f"({m['block']}/{m['family']}/{m['event']}/{m['universe']})")
    pst = _local_state(fam_c_dir, prom, freeze_commit)
    if pst["status"] != "NOT-PROMOTED":
        raise PermissionError(
            f"LOCK-DENY the PROMOTION cell {prom['cell_id']} of "
            f"{cell['block']}/{cell['family']}/{cell['universe']} is "
            f"{pst['status']}, not validated NOT-PROMOTED "
            f"({pst['reasons'][:1]}); a NOT-LOCKED terminal requires a "
            f"validated failed acquisition")
    op = os.path.join(run_dir(fam_c_dir, prom), PROMOTION_OUTCOME_FILE)
    try:
        _oc, _oc_sha = _read_json(op), _sha256_file(op)
    except (OSError, ValueError) as e:
        raise PermissionError(f"LOCK-DENY recorded promotion outcome "
                              f"unreadable at {op}: {e}")
    # EPOCH-3 (§3.1): a promotion outcome recorded under the terminal
    # evidence union (failure_event + acquisition_evidence) has no chain to
    # bind; the lock terminal then binds the SAME union, re-derived from
    # disk, instead of chain tips.
    _union = ("failure_event" in _oc) or ("acquisition_evidence" in _oc)
    tips = {}
    if _union:
        _u = _acquisition_evidence_reasons(fam_c_dir, _oc, cell, exp)
        if _u:
            raise PermissionError(
                "LOCK-DENY the recorded promotion outcome's §3.1 "
                "acquisition evidence union does not re-derive from disk: "
                + _u[0])
    else:
        for ev in ("T0", "T1"):
            acq = expected_event(exp, cell["block"], cell["family"], ev,
                                 cell["universe"])
            if acq is None:
                raise PermissionError(f"LOCK-DENY no {ev} cell in the order "
                                      f"for {cell['block']}/"
                                      f"{cell['family']}/"
                                      f"{cell['universe']}")
            try:
                tips[ev] = _chain_tip(os.path.join(run_dir(fam_c_dir, acq),
                                                   "EVIDENCE-CHAIN.jsonl"))
            except (ValueError, OSError, json.JSONDecodeError) as e:
                raise PermissionError(f"LOCK-DENY {ev} chain tip unreadable: "
                                      f"{e}")
        for ev in ("T0", "T1"):
            if _oc.get(ev.lower() + "_tip") != tips[ev]:
                raise PermissionError(
                    f"LOCK-DENY promotion outcome {ev.lower()}_tip "
                    f"{str(_oc.get(ev.lower() + '_tip'))[:12]} != the "
                    f"validated {ev} chain tip {tips[ev][:12]} (the outcome "
                    f"being bound no longer matches the committed chains)")
    d = ensure_namespace(fam_c_dir, cell["block"], cell["universe"],
                         cell["family"], tail=("runs", cell["cell_id"]))
    for stray in ("H1-RUN-MANIFEST.json", PROMOTION_RECEIPT_FILE,
                  PROMOTION_OUTCOME_FILE):
        if os.path.exists(os.path.join(d, stray)):
            raise PermissionError(
                f"LOCK-DENY lock event run dir already carries {stray}; "
                f"refusing to write a NOT-LOCKED outcome beside a "
                f"conflicting governance artifact")
    op = os.path.join(d, CAPABILITY_LOCK_OUTCOME_FILE)
    if os.path.exists(op):
        raise PermissionError("LOCK-DENY outcome already recorded (no "
                              "relock of a not-promoted universe)")
    outcome = {"event": "CAPABILITY_LOCK", "cell_id": cell["cell_id"],
               "block": cell["block"], "family": cell["family"],
               "universe": cell["universe"],
               "capability_id": cell["capability_id"],
               "outcome": LOCK_OUTCOME_STATUS,
               "reason": LOCK_OUTCOME_REASON,
               "created_from": "frozen-evidence",
               "promotion_cell_id": prom["cell_id"],
               "promotion_outcome_sha256": _oc_sha}
    if _union:
        outcome["failure_event"] = _oc.get("failure_event")
        outcome["acquisition_evidence"] = _oc.get("acquisition_evidence")
        outcome["candidate_sha256"] = _oc.get("candidate_sha256")
    else:
        outcome["acquisition_chain_tips"] = dict(tips)
    with open(op, "w") as f:
        json.dump(outcome, f, indent=1)
    return op


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
            "declared_limitations_present", "non_discriminating",
            "conformance_cause",
            "supported_t4_ids", "conformance_map_sha256",
            "t4_semantic_id", "evidence_grade", "producer_identity",
            "protocol_lock_sha256", "execution_lock_sha256")
    missing = [k for k in need if k not in receipt or receipt[k] is None]
    empty = [k for k in need if k not in ("preconditions", "limitations",
                                         "declared_limitations_present",
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
        declared_limitations_present=receipt[
            "declared_limitations_present"],
        non_discriminating=receipt["non_discriminating"],
        conformance_cause=receipt["conformance_cause"],
        supported_t4_ids=receipt["supported_t4_ids"],
        conformance_map_sha256=receipt["conformance_map_sha256"],
        t4_semantic_id=receipt["t4_semantic_id"],
        evidence_grade=receipt["evidence_grade"],
        candidate_sha256=receipt["candidate"]["sha256"],
        candidate_provenance_sha256=receipt_sha)


def completed_cells(fam_c_dir, freeze_commit=None, expansion=None):
    """A11.6 + EPOCH-2 algebra: cell ids of cells whose VALIDATED state is
    progress-valid (progress_valid(): COMPLETE, or the event-specific
    validated terminal of a failed acquisition — PROMOTION/NOT-PROMOTED,
    CAPABILITY_LOCK/NOT-LOCKED, downstream/NOT-EVALUABLE).

    Consumes the strict validators, never manifest presence: a malformed,
    tampered, dangling, dev or inadmissible run does not advance the frozen
    order. The walk is a strict PREFIX — the first cell that is not
    progress-valid ends the ledger (later completions never advance a
    broken prefix), so the scan stops there. Scans the universe state
    trees of the ACTIVE epoch only (the derived namespace), so a stray
    manifest elsewhere — including any epoch-1 evidence — cannot mark a
    cell done.
    """
    exp = expansion if expansion is not None else load_expansion(fam_c_dir)
    done = {}
    for c in exp["cells"]:
        st = _local_state(fam_c_dir, c, freeze_commit, exp)
        if not progress_valid(c, st["status"]):
            break
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
