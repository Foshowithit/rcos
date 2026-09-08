#!/usr/bin/env python3
"""H1 adversarial smoke: every probe below must FAIL CLOSED.
Exit 0 + table only if all green. Stdlib only. No network, no models."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from sandbox import Sandbox
from isolation import Run, scan_outputs_for_canaries, symlink_escape_attempt
from symmetry import build_context, diff_contexts
from seal import build_visible_root, seal_probe

BASE = "/tmp/h1-smoke"
results = []


def check(name, fail_closed):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name)


def main():
    os.system("rm -rf " + BASE)
    fam = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam01"
    task = os.path.join(fam, "T0")

    # --- H-BD-001: capability + network + secrets denied ---
    ra = Run(BASE, "laneA", "t0")
    cap = os.path.join(fam, "..", "..", "..")  # outside jail regardless
    ok, _ = ra.sandbox.attempt_read(
        "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam01/truth.json")
    check("B/D cannot read truth.json from jail", not ok)
    ok, _ = ra.sandbox.attempt_read("/etc/hostname")
    check("B/D cannot read outside paths", not ok)
    p = ra.sandbox.run(
        [sys.executable, "-c",
         "import socket;socket.create_connection(('example.com',80),timeout=5)"])
    check("B/D network egress denied",
          p.returncode != 0 and "SANDBOX-DENY" in (p.stderr or ""))
    p = ra.sandbox.run(
        [sys.executable, "-c",
         "import os;print([k for k in os.environ if 'KEY' in k.upper() or 'TOKEN' in k.upper()])"])
    check("B/D env carries no secrets", p.stdout.strip() == "[]")

    # --- H-CTX-002: symmetry + injected asymmetry ---
    t, _ = build_context("t", "do X", ["read"], {"cap": "K"})
    c, _ = build_context("t", "do X", ["read"], None)
    check("identical-except-capability passes", diff_contexts(t, c) == [])
    t2, _ = build_context("t", "do X please", ["read"], {"cap": "K"})
    check("injected asymmetry fails", diff_contexts(t2, c) != [])

    # --- H-SES-003: sessions, canaries, symlink ---
    rb = Run(BASE, "laneB", "t0")
    check("session ids unique", ra.session_id != rb.session_id)
    ca, cb = ra.plant_canary(), rb.plant_canary()
    check("clean outputs scan clean",
          scan_outputs_for_canaries(
              {"A": ["did work"], "B": ["did other work"]},
              {"A": ca, "B": cb}) == [])
    check("planted leak detected",
          scan_outputs_for_canaries({"A": ["did work"], "B": [f"saw {ca}"]},
                                    {"A": ca, "B": cb}) != [])
    check("symlink escape blocked",
          symlink_escape_attempt(ra.sandbox, "/etc/hostname"))

    # --- H-EVAL-004: seal on a real family task ---
    vis = os.path.join(BASE, "visible-T0")
    copied, refused = build_visible_root(task, vis)
    vroot = os.path.join(ra.sandbox.root, "task")
    os.system(f"cp -r {vis} {vroot}")
    check("visible root built", len(copied) > 0)
    findings = seal_probe(ra.sandbox, vroot, fam, "T0")
    check("seal probes all denied: " +
          ("clean" if not findings else str(findings)), not findings)

    bad = [n for n, ok_ in results if not ok_]
    print(f"\nH1 smoke: {len(results) - len(bad)}/{len(results)} closed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
