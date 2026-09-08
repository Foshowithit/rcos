#!/usr/bin/env python3
"""A12b.5 — frozen governed T4 semantic-ID registry (the SINGLE resolver).

Auditor rule: T4 conformance semantic IDs are set membership over a frozen
registry, never a hash-derived fallback; the registry is PROTOCOL-LOCK
governed, and fam01's ID arrives by forward PREREG amendment.

Both independent readers (`harness/promotion.py` and `harness/order.py`)
resolve through THIS module — never through a private registry read — so
the two surfaces cannot drift. `promotion` imports `order`, so the shared
resolver lives here (this module imports neither; stdlib only).

Registry shape (benchmarks/fam-c/T4-SEMANTIC-IDS.json, family-keyed):

    {"version": "t4-semantic-ids-v1",
     "prereg_source": "PREREG.md ## Conformance semantic IDs (frozen) + ...",
     "families": {"fam01": "fam01.rows_are_records", ...}}

`resolve()` enforces set-equality against the PREREG frozen block in the
refuse direction: a registry id that is NOT frozen in PREREG.md denies
every promotion (`PROMOTION-DENY`). The other direction (a PREREG id
missing from the registry) is a sealed-suite failure
(harness/tests/smoke_h17_t4ids.py asserts exact set equality), not a
runtime fallback — there is no fallback: an unregistered family gets an
explicitly UNRATIFIED id (harness-validation only), and an estimand
promotion for an unregistered family is refused.
"""
import json
import os
import re

REGISTRY_FILE = "T4-SEMANTIC-IDS.json"
PREREG_FILE = "PREREG.md"
VERSION = "t4-semantic-ids-v1"

_SEMANTIC_ID_RE = re.compile(r"fam0[1-6]\.[a-z0-9_]+")


def _read_json(p):
    with open(p) as f:
        return json.load(f)


def frozen_set(fam_c_dir):
    """Return the registry's {family: t4_semantic_id} mapping.

    Fail closed: an unreadable, unversioned, or malformed registry denies
    (a promotion rooted in a broken registry must never silently fall back
    to a hash-derived id)."""
    p = os.path.join(fam_c_dir, REGISTRY_FILE)
    try:
        d = _read_json(p)
    except (ValueError, OSError) as e:
        raise PermissionError(
            f"PROMOTION-DENY T4 semantic-id registry unreadable at {p}: "
            f"{e}")
    if not isinstance(d, dict) or d.get("version") != VERSION:
        raise PermissionError(
            f"PROMOTION-DENY T4 registry at {p} has version "
            f"{(d.get('version') if isinstance(d, dict) else type(d).__name__)!r} "
            f"!= {VERSION!r} (registry shape is frozen)")
    fams = d.get("families")
    if not isinstance(fams, dict) or not fams:
        raise PermissionError(
            f"PROMOTION-DENY T4 registry at {p} carries no family mapping")
    for fam, tid in sorted(fams.items()):
        if not (isinstance(tid, str) and tid.startswith(fam + ".")
                and _SEMANTIC_ID_RE.fullmatch(tid)):
            raise PermissionError(
                f"PROMOTION-DENY T4 registry entry {fam!r} -> {tid!r} is "
                f"not a frozen semantic id for that family")
    return dict(fams)


def prereg_frozen_set(fam_c_dir):
    """Return the set of semantic IDs frozen in PREREG.md's
    `## Conformance semantic IDs (frozen)` block.

    Scoped to the fenced frozen block (not a whole-file scan): prose
    elsewhere in PREREG must never mint membership. Fail closed when the
    block is absent or unreadable."""
    p = os.path.join(fam_c_dir, PREREG_FILE)
    try:
        text = open(p).read()
    except OSError as e:
        raise PermissionError(
            f"PROMOTION-DENY PREREG frozen semantic-id block unreadable "
            f"at {p}: {e}")
    head = text.find("## Conformance semantic IDs (frozen)")
    if head < 0:
        raise PermissionError(
            f"PROMOTION-DENY PREREG at {p} has no Conformance semantic IDs "
            f"(frozen) block")
    fence0 = text.find("```", head)
    fence1 = text.find("```", fence0 + 3) if fence0 >= 0 else -1
    if fence0 < 0 or fence1 < 0:
        raise PermissionError(
            f"PROMOTION-DENY PREREG frozen semantic-id block at {p} is "
            f"not a fenced list")
    return set(_SEMANTIC_ID_RE.findall(text[fence0:fence1]))


def resolve(fam_c_dir, family, semantic_core_sha256, evidence_grade):
    """Resolve (t4_semantic_id, ratified) for one family.

    * every registry id must be frozen in PREREG.md first — a registry id
      outside the PREREG frozen set refuses with PROMOTION-DENY (the
      registry can never smuggle an unratified id into a promotion);
    * a registered family resolves to its frozen id, ratified True, on
      ANY evidence grade (a harness-validation promotion of a registered
      family carries the real auditor id — the grade rides separately);
    * an unregistered family on harness-validation gets an explicitly
      UNRATIFIED id (ratified False), so a fixture can never masquerade
      as audited;
    * an unregistered family on estimand grade refuses with
      PROMOTION-DENY (estimand locks REQUIRE a ratified auditor id).
    """
    reg = frozen_set(fam_c_dir)
    frozen = prereg_frozen_set(fam_c_dir)
    extra = sorted(set(reg.values()) - frozen)
    if extra:
        raise PermissionError(
            f"PROMOTION-DENY T4 registry id(s) not frozen in "
            f"PREREG.md ## Conformance semantic IDs (frozen): {extra} "
            f"(register an id only by forward PREREG amendment before "
            f"the runs it governs; ids are never edited in place)")
    tid = reg.get(family)
    if tid is None:
        if evidence_grade == "estimand":
            raise PermissionError(
                f"PROMOTION-DENY no ratified auditor T4 semantic id for "
                f"{family} (register it in T4-SEMANTIC-IDS.json via "
                f"forward PREREG amendment before estimand promotion)")
        suffix = (semantic_core_sha256 or "")[:12]
        return "T4-UNRATIFIED-" + suffix, False
    return tid, True
