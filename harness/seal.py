#!/usr/bin/env python3
"""H1 evaluator sealing: agent-visible roots contain ONLY VISIBLE-declared
files; seal audit probes every forbidden path from inside the sandbox.
Stdlib only.
"""
import os
import shutil

SEALED_BASENAMES = {"truth.json", "check.py", "K.md", "DESIGN-T4.md",
                    "T4NOTE.md", "registry.json", "PROMOTION.md"}


def build_visible_root(task_dir, dest_root):
    """Copy ONLY prompt.md + VISIBLE-declared fixtures into dest_root.
    Returns (copied_paths, refused_paths)."""
    vis = os.path.join(task_dir, "VISIBLE.md")
    declared = set()
    for line in open(vis):
        if "task fixtures:" in line:
            declared.update(line.split("task fixtures:", 1)[1].split())
    declared.add("prompt.md")
    if os.path.exists(dest_root):
        shutil.rmtree(dest_root)
    os.makedirs(dest_root, exist_ok=True)
    copied, refused = [], []
    for name in sorted(os.listdir(task_dir)):
        src = os.path.join(task_dir, name)
        if os.path.isdir(src):
            # fixture dirs (pages/, sub/) ship whole iff declared
            if name in declared:
                shutil.copytree(src, os.path.join(dest_root, name))
                copied.append(name + "/")
            else:
                refused.append(name + "/")
        elif name in declared:
            shutil.copy2(src, os.path.join(dest_root, name))
            copied.append(name)
        else:
            refused.append(name)
    return copied, refused


def seal_probe(sandbox, visible_root, family_root, task_id):
    """Attempt forbidden opens from INSIDE the sandbox jail.
    Returns list of failures (empty = sealed). Each probe expects
    DENIED/NOT-FOUND; any readable hit is a finding."""
    findings = []
    # 1. sealed basenames must not exist under the visible root at all
    for base in sorted(SEALED_BASENAMES):
        p = os.path.join(visible_root, base)
        ok, why = sandbox.attempt_read(p)
        if ok:
            findings.append(f"sealed file reachable in visible root: {base}")
    # 2. sibling task dirs + family root must be outside the jail.
    #    Simulate by asking the sandbox about absolute outside paths.
    for outside in (os.path.join(family_root, "truth.json"),
                    os.path.join(family_root, "check.py"),
                    os.path.join(family_root, "K.md"),
                    os.path.join(os.path.dirname(family_root),
                                 "nonexistent-sibling-check")):
        ok, why = sandbox.attempt_read(outside)
        if ok:
            findings.append(f"outside path readable from jail: {outside}")
    # 3. traversal attack: visible_root/../truth.json must not resolve in.
    trav = os.path.join(visible_root, "..", "truth.json")
    ok, why = sandbox.attempt_read(trav)
    if ok:
        findings.append("traversal escape readable: ../truth.json")
    _ = task_id
    return findings
