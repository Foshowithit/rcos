#!/usr/bin/env python3
"""Fam-C execution order: mechanical expansion of the frozen ORDER.md into
an enumerated cell list, and pre-call authorization of a requested cell.

Audit round-2 item 7. A "cell" is one measured model invocation:
(block, family, downstream task, arm letter). ORDER.md is the authority;
ORDER-EXPANSION.json is its mechanical expansion (never hand-edited), and
the runner refuses to start on anything that is not the next authorized
cell in that sequence. Stdlib only.
"""
import hashlib
import json
import os
import re

BLOCKS = ("PQ", "QP")
ARM_LETTERS = ("A", "B", "C", "D")
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
            "tasks": tasks, "sequences": seqs}


def expand(order_text):
    """Mechanical expansion -> the enumerated, ordered cell list."""
    p = parse_order(order_text)
    downstream = [t for t in p["tasks"] if re.fullmatch(r"T[2-4]", t)]
    if not downstream:
        raise ValueError("ORDER-PARSE: no downstream tasks T2-T4")
    cells = []
    for block in p["block_order"]:
        for fam in p["families"]:
            per_task = p["sequences"].get((block, fam))
            if per_task is None:
                raise ValueError(
                    f"ORDER-PARSE: block {block} has no entry for {fam}")
            for task in downstream:
                letters = per_task.get(task)
                if letters is None:
                    raise ValueError(
                        f"ORDER-PARSE: {block}/{fam}/{task} has no arm order")
                for letter in letters:
                    lane = CONSUMER[block][letter]
                    cap = CAPABILITY[letter]
                    cells.append({
                        "index": len(cells),
                        "cell_id": cell_id(block, fam, task, letter),
                        "block": block, "family": fam, "task": task,
                        "letter": letter, "lane": lane,
                        "arm": ARM_NAME[cap], "capability": cap,
                        "primed": block == "QP",
                        "lane_key": LANE_KEY[letter] + (
                            " (primed)" if block == "QP" else "")})
    for i, c in enumerate(cells):
        c["index"] = i
    return {
        "order_file": "ORDER.md",
        "order_sha256": hashlib.sha256(order_text.encode()).hexdigest(),
        "seed": p["seed"], "blocks": p["block_order"],
        "families": p["families"], "tasks": p["tasks"],
        "downstream_tasks": downstream, "arm_letters": list(ARM_LETTERS),
        "consumer_map": CONSUMER, "capability_map": CAPABILITY,
        "cells": cells, "total_cells": len(cells)}


def expected_cell(expansion, block, family, task, lane, arm):
    """Resolve a runner request to its cell, or None if not authorized."""
    for c in expansion["cells"]:
        if (c["block"] == block and c["family"] == family
                and c["task"] == task and c["lane"] == lane
                and c["arm"] == arm):
            return c
    return None


def completed_cells(runs_dir):
    """Cell ids of COMPLETED wired (non-dev) runs, from their manifests.
    An unwired/dev manifest never counts toward the estimand sequence."""
    done = {}
    if not os.path.isdir(runs_dir):
        return done
    for name in sorted(os.listdir(runs_dir)):
        fp = os.path.join(runs_dir, name, "H1-RUN-MANIFEST.json")
        if not os.path.isfile(fp):
            continue
        try:
            m = json.load(open(fp))
        except ValueError:
            continue
        if m.get("wired") is not True or m.get("dev_mode") is True:
            continue
        cid = m.get("cell_id")
        if cid:
            done[cid] = name
    return done


def authorize(expansion, block, family, task, lane, arm, done_ids):
    """Pre-call authorization. Returns (cell, findings). Empty findings =
    authorized to start. Every finding is a concrete refusal reason."""
    out = []
    if block not in expansion["blocks"]:
        out.append(f"ORDER-DENY: unknown block {block!r} "
                   f"(authorized: {expansion['blocks']})")
    if family not in expansion["families"]:
        out.append(f"ORDER-DENY: family {family!r} is outside the frozen "
                   f"universe {expansion['families']}")
    if task not in expansion["downstream_tasks"]:
        out.append(f"ORDER-DENY: task {task!r} is outside the frozen "
                   f"downstream universe {expansion['downstream_tasks']}")
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
            f"{m['cell_id']} ({m['block']}/{m['family']}/{m['task']}/"
            f"{m['letter']}, lane {m['lane']}, arm {m['arm']})")
    return cell, out


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
    for key in ("families", "blocks", "downstream_tasks", "seed",
                "order_sha256", "total_cells"):
        if stored.get(key) != fresh[key]:
            out.append(f"ORDER-EXPANSION.json {key} differs from ORDER.md "
                       f"({stored.get(key)!r} != {fresh[key]!r})")
    return out
