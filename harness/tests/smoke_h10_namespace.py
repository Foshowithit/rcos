#!/usr/bin/env python3
"""H10 namespace smoke — A11.6 no-symlink namespace ancestry.

Round-3 A11.6 hardening: `check_namespace()` used to compare realpath()
values, so a symlink state/PQ/C -> state/PQ/A resolved into A's tree and was
ACCEPTED (realpath normalized the attack instead of detecting it), and
os.path.islink(run_dir) only caught the leaf.

Every EXISTING component of a derived namespace chain — state root, block,
universe, family, capability, runs, run cell — must satisfy all four rules:
(a) is a directory, (b) is NOT a symlink, (c) is harness-owned
(uid == os.geteuid()), (d) is NOT group/world writable. Any violation
refuses (specific named NAMESPACE-*-DENY) BEFORE any run directory could be
created or used, and the legitimate derived flow stays unchanged.

All probes are real filesystem probes on a throwaway temp tree. Stdlib only,
no network, no model, no docker.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAMC = "/home/chow/chow-work/rcos/benchmarks/fam-c"
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import order as ORD  # noqa: E402

BASE = "/tmp/h10-smoke"
if os.path.lexists(BASE):  # stale leftovers from an aborted earlier run
    shutil.rmtree(BASE)
os.makedirs(BASE)
results = []
skips = []


def check(name, ok, extra=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not ok else ""))


def skip(name, reason):
    skips.append((name, reason))
    print(f"SKIP {name} [{reason}]")


ORDER_TEXT = open(os.path.join(FAMC, "ORDER.md")).read()
EXP = ORD.expand(ORDER_TEXT)
CELLS = EXP["cells"]


def cell(block, family, event, universe):
    for c in CELLS:
        if (c["block"] == block and c["family"] == family
                and c["event"] == event and c["universe"] == universe):
            return c
    return None


A_CELL = cell("PQ", "fam05", "T2", "A")
C_CELL = cell("PQ", "fam05", "T2", "C")
TMP = None  # the per-probe fam-c root


def fresh():
    """A clean per-probe fam-c root (umask-independent: everything the
    probe intends to be clean is chmodded 0755 explicitly)."""
    global TMP
    TMP = os.path.join(BASE, "famc")
    if os.path.lexists(TMP):
        if os.path.isdir(TMP) and not os.path.islink(TMP):
            shutil.rmtree(TMP)
        else:
            os.unlink(TMP)
    os.makedirs(TMP)
    os.chmod(TMP, 0o755)
    return TMP


def mkd(rel):
    """mkdir a real directory chain under the probe root, every component
    clean 0755 (the session umask may otherwise leave 0775 intermediates)."""
    p = os.path.join(TMP, rel)
    os.makedirs(p)
    chmod_clean(rel)
    return p


def chmod_clean(rel):
    """chmod every EXISTING component of rel under the probe root to 0755
    (so only the probe's intended defect can trigger a denial)."""
    acc = TMP
    for comp in rel.split(os.sep):
        acc = os.path.join(acc, comp)
        if os.path.lexists(acc):
            os.chmod(acc, 0o755)


def deny_derive(rel_probe, name, expect="NAMESPACE-SYMLINK-DENY", tcell=None):
    """Run derive_paths against the probe root; a PermissionError carrying
    the expected named denial is the only PASS."""
    tcell = tcell if tcell is not None else C_CELL
    try:
        ORD.derive_paths(TMP, tcell)
    except PermissionError as e:
        check(name, expect in str(e), str(e)[:160])
        return
    except Exception as e:                                 # noqa: BLE001
        check(name, False, type(e).__name__ + ": " + str(e)[:160])
        return
    check(name, False, "no denial")


# ---------------------------------------------------------------------------
# DENY: symlinked components on the derived chain.
# ---------------------------------------------------------------------------

# 1. state/PQ/C -> state/PQ/A  (the exact audit hole: realpath() would
#    normalize C into A and the old code would ACCEPT the derived path).
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05"))
os.symlink(os.path.join("A"), os.path.join(TMP, "state", "PQ", "C"))
deny_derive(None, "DENY state/PQ/C symlink->A via derive_paths",
            "NAMESPACE-SYMLINK-DENY")
cap_c = ORD.capability_dir(TMP, "PQ", "C", "fam05")
d = ORD.check_namespace(TMP, C_CELL, cap_c)
check("DENY state/PQ/C symlink->A via check_namespace",
      d is not None and "NAMESPACE-SYMLINK-DENY" in d, str(d)[:160])

# 2. state/PQ/C/fam05 -> A/fam05 (symlinked family component).
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05"))
mkd(os.path.join("state", "PQ", "C"))
chmod_clean(os.path.join("state", "PQ", "C"))
os.symlink(os.path.join("..", "A", "fam05"),
           os.path.join(TMP, "state", "PQ", "C", "fam05"))
deny_derive(None, "DENY state/PQ/C/fam05 symlink->A/fam05 via derive_paths",
            "NAMESPACE-SYMLINK-DENY")
d = ORD.check_namespace(TMP, C_CELL,
                        ORD.capability_dir(TMP, "PQ", "C", "fam05"))
check("DENY state/PQ/C/fam05 symlink->A/fam05 via check_namespace",
      d is not None and "NAMESPACE-SYMLINK-DENY" in d, str(d)[:160])

# 3. capability component itself is a symlink.
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05", "capability"))
mkd(os.path.join("state", "PQ", "C", "fam05"))
chmod_clean(os.path.join("state", "PQ", "C", "fam05"))
os.symlink(os.path.join("..", "..", "A", "fam05", "capability"),
           os.path.join(TMP, "state", "PQ", "C", "fam05", "capability"))
deny_derive(None, "DENY capability symlink via derive_paths",
            "NAMESPACE-SYMLINK-DENY")
d = ORD.check_namespace(TMP, C_CELL,
                        ORD.capability_dir(TMP, "PQ", "C", "fam05"))
check("DENY capability symlink via check_namespace",
      d is not None and "NAMESPACE-SYMLINK-DENY" in d, str(d)[:160])

# 4. runs parent (state/.../family/runs) is a symlink.
fresh()
tgt = os.path.join(BASE, "runs-target")
os.makedirs(tgt)
os.chmod(tgt, 0o755)
mkd(os.path.join("state", "PQ", "A", "fam05"))
os.symlink(tgt, os.path.join(TMP, "state", "PQ", "A", "fam05", "runs"))
deny_derive(None, "DENY runs-parent symlink via derive_paths",
            "NAMESPACE-SYMLINK-DENY", tcell=A_CELL)

# 5. the run cell itself is a symlink.
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05", "runs"))
os.symlink(tgt, os.path.join(TMP, "state", "PQ", "A", "fam05", "runs",
                             A_CELL["cell_id"]))
deny_derive(None, "DENY run-cell symlink via derive_paths",
            "NAMESPACE-SYMLINK-DENY", tcell=A_CELL)

# ---------------------------------------------------------------------------
# DENY: group-/world-writable components.
# ---------------------------------------------------------------------------

# 6. family component group-writable.
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05"))
os.chmod(os.path.join(TMP, "state", "PQ", "A", "fam05"), 0o770)
deny_derive(None, "DENY group-writable family component",
            "NAMESPACE-WRITABLE-DENY", tcell=A_CELL)

# 7. universe component world-writable.
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05"))
os.chmod(os.path.join(TMP, "state", "PQ", "A"), 0o707)
deny_derive(None, "DENY world-writable universe component",
            "NAMESPACE-WRITABLE-DENY", tcell=A_CELL)

# 8. state root writable — check_namespace also refuses it.
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05", "capability"))
os.chmod(os.path.join(TMP, "state"), 0o776)
deny_derive(None, "DENY writable state root via derive_paths",
            "NAMESPACE-WRITABLE-DENY", tcell=A_CELL)
fresh()
mkd(os.path.join("state", "PQ", "A", "fam05", "capability"))
os.chmod(os.path.join(TMP, "state"), 0o776)
d = ORD.check_namespace(TMP, A_CELL,
                        ORD.capability_dir(TMP, "PQ", "A", "fam05"))
check("DENY writable state root via check_namespace",
      d is not None and "NAMESPACE-WRITABLE-DENY" in d, str(d)[:160])

# ---------------------------------------------------------------------------
# DENY: foreign-owned component (only genuinely testable as root).
# ---------------------------------------------------------------------------
fresh()
p = mkd(os.path.join("state", "PQ", "A", "fam05"))
mkd(os.path.join("state", "PQ", "A", "fam05", "capability"))
if os.geteuid() == 0:
    os.chown(p, 54321, -1)
    deny_derive(None, "DENY foreign-owned family component",
                "NAMESPACE-OWNERSHIP-DENY", tcell=A_CELL)
else:
    try:
        os.chown(p, 54321, -1)
    except PermissionError:
        skip("DENY foreign-owned family component",
             "non-root euid cannot chown to another uid; "
             "not faked as a PASS")
    else:
        deny_derive(None, "DENY foreign-owned family component",
                    "NAMESPACE-OWNERSHIP-DENY", tcell=A_CELL)

# ---------------------------------------------------------------------------
# ALLOW: a correct, freshly created derived tree still passes, and the
# legitimate flow (absent tree, then real tree) is unchanged.
# ---------------------------------------------------------------------------

# 9. absent state tree: derivation is pure path math, no denial.
fresh()
ca, ra = ORD.derive_paths(TMP, A_CELL)
check("ALLOW derivation on an absent tree returns the derived pair",
      ca == ORD.capability_dir(TMP, "PQ", "A", "fam05")
      and ra == ORD.run_dir(TMP, A_CELL),
      f"{ca} | {ra}")

# 10. correct full tree: both universes pass derivation and namespace gate.
for bcell, letter in ((A_CELL, "A"), (C_CELL, "C")):
    mkd(os.path.join("state", "PQ", letter, "fam05", "capability"))
    mkd(os.path.join("state", "PQ", letter, "fam05", "runs"))
    os.makedirs(os.path.join(TMP, "state", "PQ", letter, "fam05", "runs",
                             bcell["cell_id"]))
    os.chmod(os.path.join(TMP, "state", "PQ", letter, "fam05", "runs",
                          bcell["cell_id"]), 0o755)
    cap, rdir = ORD.derive_paths(TMP, bcell)
    check(f"ALLOW correct derived tree for universe {letter}",
          cap == ORD.capability_dir(TMP, "PQ", letter, "fam05")
          and rdir == ORD.run_dir(TMP, bcell)
          and os.path.isdir(rdir) and not os.path.islink(rdir),
          f"{cap} | {rdir}")
    check(f"ALLOW check_namespace clean for universe {letter}",
          ORD.check_namespace(TMP, bcell, cap) is None)

# 11. the A11.5 cross-universe denial still works on a correct tree:
#     a C cell handed A's real registry is still refused.
check("C cell still refused A's registry (FOREIGN-REGISTRY-DENY)",
      ORD.check_namespace(TMP, C_CELL,
                          ORD.capability_dir(TMP, "PQ", "A", "fam05"))
      is not None)

# 12. the real Fam-C legitimate flow is unchanged (read-only probes; the
#     live fam-c has no state tree yet, exactly the absent-tree case).
cap, rdir = ORD.derive_paths(FAMC, C_CELL)
check("ALLOW real fam-c derivation unchanged",
      cap == ORD.capability_dir(FAMC, "PQ", "C", "fam05"))
check("ALLOW real fam-c check_namespace unchanged",
      ORD.check_namespace(FAMC, C_CELL, cap) is None)

bad = [n for n, ok_ in results if not ok_]
print(f"\nH10 namespace smoke: {len(results) - len(bad)}/{len(results)} "
      f"closed" + (f" ({len(skips)} skipped)" if skips else ""))
sys.exit(1 if bad else 0)
