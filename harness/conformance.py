#!/usr/bin/env python3
"""A12d slice D5 (auditor D4-post P0) — the STRUCTURAL atomic-conjunction
conformance bridge (v4).

Auditor finding D4-post P0: the v3 grammar is conditional-clause blind.
A text such as 'when local use v1 sha256 manifests; when remote use
blake3 manifests' carries no `or`/`,`/`/`/negation token, yet its token
set contains `local`+`v1`+`sha256`, so fam05 could be marked supported
although the contract also covers the remote branch. The auditor fix
(verbatim): don't grow another marker list — move the
conformance-bearing portion to a truly structural conjunction, one
positive atomic requirement object containing an explicit requires_all
list, with no alternatives/branching representation permitted. Free
prose stays consumer-visible separately (as `limitations`).

Frozen rule atomic-conjunction-grammar-v4 (implement exactly, do not
redesign):
  1. ONLY `preconditions[*].requires_all` token lists are conformance
     candidates. `limitations` remain free prose, recorded verbatim,
     and are NEVER conformance evidence. There is no free-text
     conformance channel at all.
  2. Contract shape (v4, exact): each precondition is an object with
     EXACTLY one key `requires_all`; its value is a list of >=1
     strings; every string must be an atomic token matching
     `^[a-z0-9_.-]+$` (no whitespace, no separators, already
     lowercase); no duplicates in the list; every token must be in
     the frozen `atomic_vocabulary`. Anything else (bare string, old
     `requires` key, extra key, empty list, non-atomic token,
     out-of-vocabulary token, duplicate) is PROMOTION-DENY at the
     promotion controller, naming the offending token/key.
  3. Admissibility (defense in depth): a precondition is INADMISSIBLE
     iff any of its tokens is a frozen `negation_markers` entry, a
     frozen `disjunction_markers` entry, or contains a frozen
     `structural_separators` character, or is outside
     `atomic_vocabulary`. (Rule 2 already refuses these at promotion;
     this layer re-checks and names the reason.) An INADMISSIBLE
     precondition contributes NO evidence.
  4. Matching: a family predicate matches an admissible precondition
     iff EVERY predicate token is present in that `requires_all` (set
     membership; order irrelevant).
  5. Supported set: family T4 supported iff ANY admissible
     precondition matches ANY of that family's `requires_predicates`;
     `supported_t4_ids` = sorted set over admissible preconditions
     only; no admissible precondition at all ->
     `non_discriminating: true`.
  6. Cause text: names the T4 id, the number of declared
     preconditions, the number of inadmissible ones, the matched
     predicate + `requires_all` when discriminating, and the grammar
     refusal `atomic-grammar-inadmissible: <reason>` (reason names the
     exact token/condition) when a precondition is refused.

The frozen `atomic_vocabulary` is exactly the sorted union of every
family's `requires_predicates` tokens (derived-and-frozen, so it can
never drift from the predicates): a conformance token can only be a
frozen T4 content token, so branching words (`when`, `if`, `else`,
`otherwise`, ...) are structurally unrepresentable as conformance
evidence — no growing marker list.

This module is AUDITOR-SIDE: it reads the governed map and the
producer's T0 arrival declaration only — never K.md (no hidden-contract
reader lives here), never consumer artifacts — and it never asserts:
every refusal raises. FAIL CLOSED: `load` refuses (raises) on a missing
file, unparsable JSON, a version/rule mismatch, a missing or malformed
`negation_markers` list, a missing or non-frozen `disjunction_markers`
/ `structural_separators` / `atomic_vocabulary` table, wrong family
keys, a `t4_semantic_id` that is not the registry resolver's value for
that family, empty `requires_predicates`, a malformed predicate, or an
unknown per-family key; `verdict` raises on an unknown family, on a
bare-string candidate (fail closed, never silently coerced), or on a
map that was not loaded here (no sha). Stdlib only.
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
VERSION = "t4-conformance-v4"
RULE = "atomic-conjunction-grammar-v4"
# A12d slice D5: the frozen atomic-conjunction tables (exact values; the
# loader refuses any other value — fail closed, never a silent table).
DISJUNCTION_MARKERS = ["either", "or"]
STRUCTURAL_SEPARATORS = ["/", ","]
# The frozen derived vocabulary: exactly sorted(set(union of every
# family's requires_predicates tokens)). Branching words are structurally
# unrepresentable as conformance evidence because no such word is a
# frozen T4 content token.
ATOMIC_VOCABULARY = ["acyclic", "acyclicity", "aggregate", "basis",
                     "common", "dedup", "disjoint", "duplicates",
                     "identical", "input", "local", "order", "pages",
                     "record", "repeats", "row", "same", "sha256",
                     "summary", "topological", "unit", "units", "v1"]
WANT_FAMILIES = tuple(f"fam0{i}" for i in range(1, 7))
# Per-family keys allowed in the governed map (exact shape; anything
# else refuses — a smuggled key must never silently ride the map).
WANT_ENTRY_KEYS = ("t4_semantic_id", "requires_predicates")
_SHA_KEY = "conformance_map_sha256"
_MARKERS_KEY = "negation_markers"
_DISJUNCTION_KEY = "disjunction_markers"
_SEPARATORS_KEY = "structural_separators"
_VOCAB_KEY = "atomic_vocabulary"

_TOKEN_RE = re.compile(r"[a-z0-9_.-]+")
_ATOMIC_RE = re.compile(r"^[a-z0-9_.-]+$")


def _refuse(what):
    return ValueError(f"CONFORMANCE-REFUSE: {what}")


def normalize(text):
    """Lowercase, blank every non-token character, split on whitespace.

    Kept for audit continuity (the v2/v3 text bridge normalized this
    way); the v4 structural bridge matches atomic token lists directly
    via matches(), never through this helper."""
    if not isinstance(text, str):
        raise _refuse(f"normalize() needs a string, got "
                      f"{type(text).__name__}")
    return [tok for tok in re.sub(r"[^a-z0-9_.-]+", " ", text.lower()).split()
            if tok]


def matches(predicate, tokens):
    """Every predicate token present as a whole token (order irrelevant,
    no stemming, no synonyms, no substring matching). `tokens` is any
    iterable of atomic tokens (a requires_all list or a set of one)."""
    toks = set(tokens)
    return all(tok in toks for tok in predicate)


def _markers(cmap):
    m = cmap.get(_MARKERS_KEY)
    if not isinstance(m, list) or not m:
        raise _refuse("conformance map carries no negation_markers list "
                      "(admissibility needs the frozen marker table)")
    return set(m)


def _disjunction(cmap):
    d = cmap.get(_DISJUNCTION_KEY)
    if d != DISJUNCTION_MARKERS:
        raise _refuse("conformance map carries no frozen "
                      f"disjunction_markers table {DISJUNCTION_MARKERS!r} "
                      f"(got {d!r}; the atomic grammar needs its frozen "
                      f"marker table)")
    return set(d)


def _separators(cmap):
    s = cmap.get(_SEPARATORS_KEY)
    if s != STRUCTURAL_SEPARATORS:
        raise _refuse("conformance map carries no frozen "
                      f"structural_separators table "
                      f"{STRUCTURAL_SEPARATORS!r} (got {s!r}; the atomic "
                      f"grammar needs its frozen separator table)")
    return list(s)


def _vocabulary(cmap):
    v = cmap.get(_VOCAB_KEY)
    if v != ATOMIC_VOCABULARY:
        raise _refuse("conformance map carries no frozen "
                      f"atomic_vocabulary table {ATOMIC_VOCABULARY!r} "
                      f"(got {v!r}; conformance tokens can only be "
                      f"frozen T4 content tokens)")
    return set(v)


def classify(requires_all, cmap):
    """Why a requires_all token list is INADMISSIBLE, or None when
    ADMISSIBLE. A candidate that is not a token list at all (e.g. a
    bare string) is not classified — it RAISES via _require_lists
    (fail closed, never silently coerced)."""
    if not isinstance(requires_all, list):
        raise _refuse("conformance needs a requires_all token list "
                      f"(got {type(requires_all).__name__}; a bare "
                      f"string cannot carry the structural conjunction)")
    if not requires_all:
        return "empty requires_all"
    marks = _markers(cmap)
    disj = _disjunction(cmap)
    seps = _separators(cmap)
    vocab = _vocabulary(cmap)
    for tok in requires_all:
        if not isinstance(tok, str) or not _ATOMIC_RE.match(tok):
            return f"non-atomic token {tok!r}"
        if tok in marks:
            return f"negation marker {tok!r}"
        if tok in disj:
            return f"disjunction marker {tok!r}"
        for sep in seps:
            if sep in tok:
                return f"structural separator {sep!r} in {tok!r}"
        if tok not in vocab:
            return f"out-of-vocabulary token {tok!r}"
    seen = set()
    for tok in requires_all:
        if tok in seen:
            return f"duplicate token {tok!r}"
        seen.add(tok)
    return None


def admissible(requires_all, cmap):
    """True iff a requires_all token list is an ADMISSIBLE conformance
    candidate: every token atomic, in-vocabulary, unduplicated, and
    outside the frozen negation/disjunction tables. An INADMISSIBLE
    list (e.g. a token-encoded conditional carrying `when`) contributes
    to NO family — reported, never silently matched. A bare string
    RAISES (fail closed, never coerced to a token list)."""
    return classify(requires_all, cmap) is None


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
    marks = cmap.get(_MARKERS_KEY)
    if not isinstance(marks, list) or not marks:
        raise _refuse(f"governed map at {where} carries no "
                      f"negation_markers list (polarity needs the frozen "
                      f"marker table)")
    for tok in marks:
        if not (isinstance(tok, str) and tok and tok == tok.lower()
                and _TOKEN_RE.fullmatch(tok)):
            raise _refuse(f"governed map at {where} carries a malformed "
                          f"negation marker {tok!r} (markers are "
                          f"non-empty lowercase [a-z0-9_.-]+ tokens)")
    if sorted(marks) != list(marks) or len(set(marks)) != len(marks):
        raise _refuse(f"governed map at {where} carries a negation_markers "
                      f"list that is not sorted-unique (the frozen table "
                      f"is a sorted list)")
    if cmap.get(_DISJUNCTION_KEY) != DISJUNCTION_MARKERS:
        raise _refuse(f"governed map at {where} carries "
                      f"disjunction_markers "
                      f"{cmap.get(_DISJUNCTION_KEY)!r} != the frozen "
                      f"atomic-grammar table {DISJUNCTION_MARKERS!r} "
                      f"(the disjunction table is frozen)")
    if cmap.get(_SEPARATORS_KEY) != STRUCTURAL_SEPARATORS:
        raise _refuse(f"governed map at {where} carries "
                      f"structural_separators "
                      f"{cmap.get(_SEPARATORS_KEY)!r} != the frozen "
                      f"atomic-grammar table {STRUCTURAL_SEPARATORS!r} "
                      f"(the separator table is frozen)")
    if cmap.get(_VOCAB_KEY) != ATOMIC_VOCABULARY:
        raise _refuse(f"governed map at {where} carries "
                      f"atomic_vocabulary "
                      f"{cmap.get(_VOCAB_KEY)!r} != the frozen "
                      f"atomic-conjunction table {ATOMIC_VOCABULARY!r} "
                      f"(the vocabulary is derived-and-frozen)")
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
        unknown = [k for k in entry if k not in WANT_ENTRY_KEYS]
        if unknown:
            raise _refuse(f"governed map entry {fam!r} at {where} "
                          f"carries unknown key(s) {sorted(unknown)!r} "
                          f"(per-family keys are exactly "
                          f"{list(WANT_ENTRY_KEYS)}; the v1 "
                          f"limitation_predicates key is gone)")
        if entry.get("t4_semantic_id") != reg.get(fam):
            raise _refuse(f"governed map entry {fam!r} names "
                          f"{entry.get('t4_semantic_id')!r} but the "
                          f"registry resolver (harness/t4_ids.py) says "
                          f"{reg.get(fam)!r} (one source of truth; the "
                          f"map never carries a second literal table)")
        preds = entry.get("requires_predicates")
        if not isinstance(preds, list) or not preds:
            raise _refuse(f"governed map entry {fam!r} at {where} "
                          f"carries no requires_predicates")
        for pred in preds:
            if not isinstance(pred, list) or not pred or not all(
                    isinstance(t, str) and t and t == t.lower()
                    and _TOKEN_RE.fullmatch(t) for t in pred):
                raise _refuse(f"governed map entry {fam!r} at {where} "
                              f"carries a malformed predicate {pred!r} "
                              f"(predicates are non-empty lists of "
                              f"non-empty lowercase [a-z0-9_.-]+ tokens)")
    derived = sorted({t for fam in WANT_FAMILIES
                      for p in fams[fam]["requires_predicates"]
                      for t in p})
    if list(cmap[_VOCAB_KEY]) != derived:
        raise _refuse(f"governed map at {where} carries an "
                      f"atomic_vocabulary that is not the sorted union "
                      f"of every family's requires_predicates tokens "
                      f"(got {cmap[_VOCAB_KEY]!r}, derived {derived!r}; "
                      f"the vocabulary can never drift from the "
                      f"predicates)")
    return reg


def load(fam_c_dir):
    """Parse and freeze-check the governed map. Returns the map dict with
    its file sha attached under `conformance_map_sha256`. REFUSES
    (raises) on: missing file, unparsable JSON, version/rule mismatch, a
    missing or malformed `negation_markers` list, a missing or
    non-frozen `disjunction_markers` / `structural_separators` /
    `atomic_vocabulary` table (the vocabulary must also equal the
    sorted union of every family's predicate tokens), wrong family
    keys, a `t4_semantic_id` outside the registry resolver's value for
    that family, empty `requires_predicates`, a malformed predicate, or
    an unknown per-family key — never a silent default."""
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
            _MARKERS_KEY: list(cmap[_MARKERS_KEY]),
            _DISJUNCTION_KEY: list(cmap[_DISJUNCTION_KEY]),
            _SEPARATORS_KEY: list(cmap[_SEPARATORS_KEY]),
            _VOCAB_KEY: list(cmap[_VOCAB_KEY]),
            "families": {fam: {
                "t4_semantic_id": cmap["families"][fam]["t4_semantic_id"],
                "requires_predicates": [
                    list(pred) for pred in
                    cmap["families"][fam]["requires_predicates"]]}
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
    _markers(cmap)
    _disjunction(cmap)
    _separators(cmap)
    _vocabulary(cmap)
    return sha


def _require_lists(requires_lists):
    if not isinstance(requires_lists, list):
        raise _refuse("conformance needs requires_all token lists as a "
                      "list of lists of atomic vocabulary tokens (pass "
                      "preconditions[*].requires_all — the producer's "
                      "structural applicability claims; limitations are "
                      "never conformance evidence)")
    for cand in requires_lists:
        if not isinstance(cand, list):
            raise _refuse(
                "conformance needs requires_all token lists (a bare "
                f"string {cand!r} cannot carry the structural "
                f"conjunction: pass preconditions[*].requires_all)")


def _split_admissible(requires_lists, cmap):
    """Partition requires_all token lists into (admissible, inadmissible)
    token sets. Inadmissible lists (non-atomic, out-of-vocabulary, or
    grammar-refused tokens) contribute to NO family."""
    good, bad = [], []
    for cand in requires_lists:
        if classify(cand, cmap) is None:
            good.append((cand, set(cand)))
        else:
            bad.append(cand)
    return good, bad


def _inadmissible_reasons(requires_lists, cmap):
    """The per-list refusal reasons, in declaration order, for the
    INADMISSIBLE subset (used to name the grammar refusal in the
    cause)."""
    out = []
    for cand in requires_lists:
        why = classify(cand, cmap)
        if why is not None:
            out.append(why)
    return out


def supported_t4_ids(requires_lists, cmap):
    """The sorted set of family T4 ids supported by this contract: a
    family's T4 is supported iff ANY ADMISSIBLE requires_all token list
    matches ANY of its frozen `requires_predicates` (set membership:
    every predicate token present in the list). Inadmissible lists and
    limitations contribute nothing. A bare-string candidate RAISES
    (fail closed, never coerced)."""
    _require_loaded(cmap)
    _require_lists(requires_lists)
    fams = cmap["families"]
    tokenized, _bad = _split_admissible(requires_lists, cmap)
    out = set()
    for fam in WANT_FAMILIES:
        for pred in fams[fam]["requires_predicates"]:
            if any(matches(pred, toks) for _cand, toks in tokenized):
                out.add(fams[fam]["t4_semantic_id"])
                break
    return sorted(out)


def verdict(family, requires_lists, cmap, *, limitations=None):
    """The frozen conformance verdict for one family over the producer's
    ACTUAL requires_all token lists (`preconditions[*].requires_all`).
    Returns {"t4_semantic_id", "declared_limitations_present",
    "matched", "supported_t4_ids", "non_discriminating",
    "conformance_cause", "conformance_map_sha256",
    "requires_declared", "requires_inadmissible", "inadmissible"}.
    `limitations`, when given, feeds ONLY the presence bit (free prose,
    never evidence); when omitted the presence bit falls back to
    whether any requires_all list was declared. TOTAL for well-typed
    candidates: an admissible-shaped but inadmissible token list (an
    out-of-vocabulary token, a disjunction marker, ...) yields
    `non_discriminating: true`, `supported_t4_ids: []`, and a
    `conformance_cause` naming the offending token — never a
    traceback, so the specificity CLI stays fail-closed on a tampered
    lock. RAISES on an unknown family, on a bare-string candidate, or
    on a map that was not loaded here — never a silent default in
    either discriminating direction."""
    sha = _require_loaded(cmap)
    fams = cmap["families"]
    if family not in fams:
        raise _refuse(f"unknown family {family!r} (governed families: "
                      f"{list(WANT_FAMILIES)}; an unlisted family never "
                      f"defaults to discriminating or non-discriminating)")
    _require_lists(requires_lists)
    tid = fams[family]["t4_semantic_id"]
    tokenized, inadmissible = _split_admissible(requires_lists, cmap)
    matched = []
    for cand, toks in tokenized:
        for pred in fams[family]["requires_predicates"]:
            if matches(pred, toks):
                matched.append({"predicate": list(pred),
                                "requires_all": list(cand)})
    matched.sort(key=lambda m: (m["requires_all"], m["predicate"]))
    supported = supported_t4_ids(requires_lists, cmap)
    non_disc = tid not in supported
    n, k = len(requires_lists), len(inadmissible)
    if limitations is None:
        lim_present = bool(requires_lists)
    else:
        if not isinstance(limitations, list) or not all(
                isinstance(x, str) for x in limitations):
            raise _refuse(f"verdict({family}) needs limitations as a list "
                          f"of strings when given (free prose, presence "
                          f"only)")
        lim_present = bool(limitations)
    if non_disc:
        cause = (
            f"family T4 {tid} is non-discriminating for this contract: "
            f"the contract declares {n} precondition(s) "
            f"({k} inadmissible, contributing to no family) and "
            f"no frozen predicate for {tid} matched any admissible "
            f"requires_all list (rule {RULE})")
        if k:
            reasons = _inadmissible_reasons(requires_lists, cmap)
            cause += (" atomic-grammar-inadmissible: "
                      f"{reasons[0]}")
    else:
        first = matched[0]
        cause = (
            f"family T4 {tid} is discriminating for this contract: "
            f"frozen predicate {first['predicate']} matched requires_all "
            f"{first['requires_all']!r} ({n} declared precondition(s), "
            f"{k} inadmissible) (rule {RULE})")
    return {"t4_semantic_id": tid,
            "declared_limitations_present": lim_present,
            "matched": matched,
            "supported_t4_ids": supported,
            "non_discriminating": non_disc,
            "conformance_cause": cause,
            "conformance_map_sha256": sha,
            "requires_declared": n,
            "requires_inadmissible": k,
            "inadmissible": [list(c) for c in inadmissible]}
