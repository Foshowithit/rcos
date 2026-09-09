#!/usr/bin/env python3
"""A12c slice C2 (auditor P0 #6) — the frozen limitation->T4-id conformance
bridge.

Auditor finding: `non_discriminating = not bool(limitations)` is wrong in
general. It happens to be right for fam05's empty contract, but a producer
returning `limitations: ['requires Python 3']` would lock a discriminating
T4 while the actual limitation has nothing to do with the T4's
applicability condition. The bridge from the producer's ACTUAL limitation
to the hidden T4 semantic id is therefore frozen here, before execution:
a limitation supports a T4 only if it names the T4's applicability
condition, per the governed map `benchmarks/fam-c/T4-CONFORMANCE.json`
under the frozen rule `normalize-token-all-present-v1`.

Frozen rule (implement exactly, do not redesign):
  1. normalize(text): lowercase; replace every character not in
     `[a-z0-9_.-]` with a space; collapse whitespace runs; token list =
     split on spaces.
  2. a predicate matches a limitation iff EVERY token in the predicate is
     present as a whole token in the limitation's token list (order
     irrelevant, no stemming, no synonyms, no substring matching).
  3. a family's T4 is SUPPORTED by a contract iff ANY of the contract's
     limitations matches ANY of that family's predicates.
  4. `supported_t4_ids(limitations)` = the sorted set of family T4 ids
     supported by the contract.
  5. `non_discriminating(family) = t4_semantic_id(family) not in
     supported_t4_ids`.
  6. `limitation_present = bool(limitations)` (unchanged, presence only).
  7. Cause text when non-discriminating names: the T4 id, the number of
     locked limitations, and that no frozen predicate for that id
     matched. When discriminating, the cause names the matched predicate
     and the matched limitation (auditor-side only).

This module is AUDITOR-SIDE: it reads the governed map and the producer's
T0 arrival declaration only — never K.md (no hidden-contract reader
lives here), never consumer artifacts — and it never asserts: every
refusal raises. FAIL CLOSED: `load` refuses (raises) on a missing file,
unparsable JSON, a version/rule mismatch, wrong family keys, a
`t4_semantic_id` that is not the registry resolver's value for that
family, empty predicate lists, or a malformed predicate; `verdict`
raises on an unknown family or a map that was not loaded here (no sha).
Stdlib only.
"""
import hashlib
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import t4_ids as _t4_ids  # noqa: E402  (the SINGLE registry resolver)

MAP_FILE = "T4-CONFORMANCE.json"
VERSION = "t4-conformance-v1"
RULE = "normalize-token-all-present-v1"
WANT_FAMILIES = tuple(f"fam0{i}" for i in range(1, 7))
_SHA_KEY = "conformance_map_sha256"

_TOKEN_RE = re.compile(r"[a-z0-9_.-]+")
_NONTOKEN_RE = re.compile(r"[^a-z0-9_.-]+")


def _refuse(what):
    return ValueError(f"CONFORMANCE-REFUSE: {what}")


def normalize(text):
    """Lowercase, blank every non-token character, split on whitespace."""
    if not isinstance(text, str):
        raise _refuse(f"normalize() needs a string, got "
                      f"{type(text).__name__}")
    return [tok for tok in _NONTOKEN_RE.sub(" ", text.lower()).split()
            if tok]


def matches(predicate, tokens):
    """Every predicate token present as a whole token (order irrelevant,
    no stemming, no synonyms, no substring matching)."""
    toks = set(tokens)
    return all(tok in toks for tok in predicate)


def _check_map_shape(cmap, where):
    if not isinstance(cmap, dict):
        raise _refuse(f"governed map at {where} is not a JSON object")
    if cmap.get("version") != VERSION:
        raise _refuse(f"governed map at {where} has version "
                      f"{cmap.get('version')!r} != {VERSION!r} "
                      f"(map shape is frozen)")
    if cmap.get("rule") != RULE:
        raise _refuse(f"governed map at {where} has rule "
                      f"{cmap.get('rule')!r} != {RULE!r} "
                      f"(the conformance rule is frozen)")
    fams = cmap.get("families")
    if not isinstance(fams, dict) or sorted(fams) != sorted(WANT_FAMILIES):
        got = sorted(fams) if isinstance(fams, dict) else type(
            fams).__name__
        raise _refuse(f"governed map at {where} has family keys {got} "
                      f"!= exactly {list(WANT_FAMILIES)}")
    try:
        reg = _t4_ids.frozen_set(os.path.dirname(where))
    except PermissionError as e:
        raise _refuse(f"T4 registry resolver refuses behind the "
                      f"conformance map at {where}: {e}") from None
    for fam in WANT_FAMILIES:
        entry = fams.get(fam)
        if not isinstance(entry, dict):
            raise _refuse(f"governed map entry {fam!r} at {where} is not "
                          f"an object")
        if entry.get("t4_semantic_id") != reg.get(fam):
            raise _refuse(f"governed map entry {fam!r} names "
                          f"{entry.get('t4_semantic_id')!r} but the "
                          f"registry resolver (harness/t4_ids.py) says "
                          f"{reg.get(fam)!r} (one source of truth; the "
                          f"map never carries a second literal table)")
        preds = entry.get("limitation_predicates")
        if not isinstance(preds, list) or not preds:
            raise _refuse(f"governed map entry {fam!r} at {where} "
                          f"carries no limitation_predicates")
        for pred in preds:
            if not isinstance(pred, list) or not pred or not all(
                    isinstance(t, str) and t and t == t.lower()
                    and _TOKEN_RE.fullmatch(t) for t in pred):
                raise _refuse(f"governed map entry {fam!r} at {where} "
                              f"carries a malformed predicate {pred!r} "
                              f"(predicates are non-empty lists of "
                              f"non-empty lowercase [a-z0-9_.-]+ tokens)")
    return reg


def load(fam_c_dir):
    """Parse and freeze-check the governed map. Returns the map dict with
    its file sha attached under `conformance_map_sha256`. REFUSES
    (raises) on: missing file, unparsable JSON, version/rule mismatch,
    wrong family keys, a `t4_semantic_id` outside the registry
    resolver's value for that family, empty `limitation_predicates`, or
    a malformed predicate — never a silent default."""
    p = os.path.join(fam_c_dir, MAP_FILE)
    if not os.path.isfile(p) or os.path.islink(p):
        raise _refuse(f"governed map missing at {p} (a promotion rooted "
                      f"in a missing conformance map must never silently "
                      f"default)")
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise _refuse(f"governed map unreadable at {p}: {e}") from None
    try:
        cmap = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise _refuse(f"governed map unparsable at {p}: {e}") from None
    _check_map_shape(cmap, p)
    cmap = {"version": cmap["version"], "rule": cmap["rule"],
            "families": {fam: {
                "t4_semantic_id": cmap["families"][fam]["t4_semantic_id"],
                "limitation_predicates": [
                    list(pred) for pred in
                    cmap["families"][fam]["limitation_predicates"]]}
                for fam in WANT_FAMILIES},
            _SHA_KEY: hashlib.sha256(raw).hexdigest()}
    return cmap


def _require_loaded(cmap):
    if not isinstance(cmap, dict) or not isinstance(
            cmap.get("families"), dict):
        raise _refuse("no loaded conformance map (load() the governed "
                      "map first; verdicts are never derived without it)")
    sha = cmap.get(_SHA_KEY)
    if not (isinstance(sha, str) and len(sha) == 64):
        raise _refuse("conformance map carries no file sha (load() the "
                      "governed map first; verdicts never default it)")
    try:
        int(sha, 16)
    except ValueError:
        raise _refuse("conformance map carries no 64-hex file sha") \
            from None
    return sha


def supported_t4_ids(limitations, cmap):
    """The sorted set of family T4 ids supported by this contract: a
    family's T4 is supported iff ANY limitation matches ANY of its
    frozen predicates."""
    _require_loaded(cmap)
    if not isinstance(limitations, list) or not all(
            isinstance(x, str) for x in limitations):
        raise _refuse("supported_t4_ids() needs limitations as a list "
                      "of strings")
    fams = cmap["families"]
    tokenized = [set(normalize(lim)) for lim in limitations]
    out = set()
    for fam in WANT_FAMILIES:
        for pred in fams[fam]["limitation_predicates"]:
            if any(matches(pred, toks) for toks in tokenized):
                out.add(fams[fam]["t4_semantic_id"])
                break
    return sorted(out)


def verdict(family, limitations, cmap):
    """The frozen conformance verdict for one family over the producer's
    ACTUAL limitations. Returns {"t4_semantic_id", "limitation_present",
    "matched", "supported_t4_ids", "non_discriminating",
    "conformance_cause", "conformance_map_sha256"}. RAISES on an unknown
    family or a map that was not loaded here — never a silent default in
    either discriminating direction."""
    sha = _require_loaded(cmap)
    fams = cmap["families"]
    if family not in fams:
        raise _refuse(f"unknown family {family!r} (governed families: "
                      f"{list(WANT_FAMILIES)}; an unlisted family never "
                      f"defaults to discriminating or non-discriminating)")
    if not isinstance(limitations, list) or not all(
            isinstance(x, str) for x in limitations):
        raise _refuse(f"verdict({family}) needs limitations as a list "
                      f"of strings")
    tid = fams[family]["t4_semantic_id"]
    matched = []
    for lim in limitations:
        toks = set(normalize(lim))
        for pred in fams[family]["limitation_predicates"]:
            if matches(pred, toks):
                matched.append({"predicate": list(pred),
                                "limitation": lim})
    matched.sort(key=lambda m: (m["limitation"], m["predicate"]))
    supported = supported_t4_ids(limitations, cmap)
    non_disc = tid not in supported
    if non_disc:
        n = len(limitations)
        cause = (
            f"family T4 {tid} is non-discriminating for this contract: "
            f"the locked contract carries {n} limitation(s) "
            f"({'none' if n == 0 else 'none of which matched'}) and no "
            f"frozen predicate for {tid} matched any of them "
            f"(rule {RULE})")
    else:
        first = matched[0]
        cause = (
            f"family T4 {tid} is discriminating for this contract: "
            f"frozen predicate {first['predicate']} matched limitation "
            f"{first['limitation']!r} (rule {RULE})")
    return {"t4_semantic_id": tid,
            "limitation_present": bool(limitations),
            "matched": matched,
            "supported_t4_ids": supported,
            "non_discriminating": non_disc,
            "conformance_cause": cause,
            "conformance_map_sha256": sha}
