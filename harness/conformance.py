#!/usr/bin/env python3
"""A12d slice D4 (auditor D3-post P0) — the ATOMIC-requires->T4-id
conformance bridge (v3).

Auditor finding D3-post P0: the v2 bridge is disjunction-blind. A text
such as 'local or remote, v1 or v2, sha256 or blake3 manifests' could
mark `fam05.local_v1_sha256` supported: the token rule saw `local` +
`sha256` and ignored the `or`s and commas. False positives are worse
than false negatives, so ambiguous/disjunctive requirements FAIL
CONSERVATIVE under a tiny protocol amendment — a restricted
atomic-requirement grammar, not a growing prose marker list.

Frozen rule atomic-requirement-grammar-v3 (implement exactly, do not
redesign):
  1. ONLY `preconditions[*].requires` texts are candidates.
     `limitations` are NEVER consulted by conformance.
  2. ADMISSIBILITY: a requires text is INADMISSIBLE iff ANY of:
     (a) one of its normalized tokens (lowercase; every char not in
         `[a-z0-9_.-]` -> a space; collapse whitespace; split) is in
         the frozen top-level `negation_markers` list (fail closed,
         as in v2);
     (b) it contains a frozen `disjunction_markers` entry as a WHOLE
         WORD — TOKEN-level: split on whitespace, strip punctuation,
         compare (so `ordinary` and `for` never trip `or`);
     (c) it contains a frozen `structural_separators` entry as a RAW
         CHARACTER anywhere (`,` or `/`).
     An INADMISSIBLE text contributes NO conformance evidence: it
     never supports any T4 id and never acts as negation.
  3. A predicate matches an ADMISSIBLE requires text iff EVERY token
     in the predicate is present as a whole token (order irrelevant,
     no stemming, no substrings). Normalization of admissible texts
     is UNCHANGED from v2.
  4. A family's T4 is SUPPORTED iff ANY admissible requires text
     matches ANY of that family's `requires_predicates`.
     `supported_t4_ids` = sorted set (computed from admissible texts
     only; if none are admissible -> `non_discriminating: true`).
  5. `non_discriminating(family) = t4_semantic_id(family) not in
     supported_t4_ids`.
  6. Cause text names the T4 id, the number of declared preconditions,
     the number of INADMISSIBLE ones, the matched predicate+text when
     discriminating, and the grammar refusal
     (`atomic-grammar-inadmissible: ...`) when a disjunctive text is
     refused. Auditor-side only.

Auditor finding A12d.3: the frozen v1 bridge is polarity-blind. It
treated as supporting evidence texts such as 'not limited to local v1
sha256 manifests', 'DAG export is unsupported', 'does not require
acyclic input', or 'common unit basis is not required'. The v2 bridge
maps ONLY affirmative producer applicability claims: the producer
contract carries its requirements in the structurally positive form
`preconditions: [{"requires": "<text>"}]`, and the matcher consults
ONLY those requires texts — never limitations (which stay free prose,
recorded verbatim in the lock, and contribute nothing here).

Frozen rule atomic-requirement-grammar-v3 (superseding detail: the v2
affirmative shape is kept — ONLY `preconditions[*].requires` texts are
candidates and `limitations` stay free prose — with the D4 atomicity
refusal added: a disjunctive text is INADMISSIBLE and contributes to NO
family, fail conservative).

This module is AUDITOR-SIDE: it reads the governed map and the
producer's T0 arrival declaration only — never K.md (no hidden-contract
reader lives here), never consumer artifacts — and it never asserts:
every refusal raises. FAIL CLOSED: `load` refuses (raises) on a missing
file, unparsable JSON, a version/rule mismatch, a missing or malformed
`negation_markers` list, a missing or non-frozen `disjunction_markers`
or `structural_separators` table, wrong family keys, a
`t4_semantic_id` that is not the registry resolver's value for that
family, empty `requires_predicates`, a malformed predicate, or an
unknown per-family key; `verdict` raises on an unknown family, on
requires texts that are not strings, or on a map that was not loaded
here (no sha). Stdlib only.
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
VERSION = "t4-conformance-v3"
RULE = "atomic-requirement-grammar-v3"
# A12d slice D4: the frozen atomic-grammar tables (exact values; the
# loader refuses any other value — fail closed, never a silent table).
DISJUNCTION_MARKERS = ["either", "or"]
STRUCTURAL_SEPARATORS = ["/", ","]
WANT_FAMILIES = tuple(f"fam0{i}" for i in range(1, 7))
# Per-family keys allowed in the governed map (exact shape; anything
# else refuses — a smuggled key must never silently ride the map).
WANT_ENTRY_KEYS = ("t4_semantic_id", "requires_predicates")
_SHA_KEY = "conformance_map_sha256"
_MARKERS_KEY = "negation_markers"
_DISJUNCTION_KEY = "disjunction_markers"
_SEPARATORS_KEY = "structural_separators"

_TOKEN_RE = re.compile(r"[a-z0-9_.-]+")
_NONTTOKEN_RE = re.compile(r"[^a-z0-9_.-]+")


def _refuse(what):
    return ValueError(f"CONFORMANCE-REFUSE: {what}")


def normalize(text):
    """Lowercase, blank every non-token character, split on whitespace."""
    if not isinstance(text, str):
        raise _refuse(f"normalize() needs a string, got "
                      f"{type(text).__name__}")
    return [tok for tok in _NONTTOKEN_RE.sub(" ", text.lower()).split()
            if tok]


def matches(predicate, tokens):
    """Every predicate token present as a whole token (order irrelevant,
    no stemming, no synonyms, no substring matching)."""
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


_PUNCT_EDGE_RE = re.compile(r"^[^a-z0-9]+|[^a-z0-9]+$")


def _disjunction_hit(text, markers):
    """The frozen disjunction marker present as a WHOLE WORD, or None.
    TOKEN-level: split on whitespace, strip punctuation, compare — so
    `ordinary` and `for` never trip `or` (no substring matching)."""
    for raw in text.lower().split():
        if _PUNCT_EDGE_RE.sub("", raw) in markers:
            return _PUNCT_EDGE_RE.sub("", raw)
    return None


def _separator_hit(text, separators):
    """The frozen structural separator present as a RAW CHARACTER, or
    None. Any literal `,` or `/` anywhere refuses the text."""
    for sep in separators:
        if sep in text:
            return sep
    return None


def classify(text, cmap):
    """Why a requires text is INADMISSIBLE, or None when ADMISSIBLE.
    Refusal precedence: negation marker, then disjunction marker, then
    structural separator (every refusal contributes NO evidence)."""
    marks = _markers(cmap)
    toks = set(normalize(text))
    neg = sorted(tok for tok in toks if tok in marks)
    if neg:
        return f"negation marker {neg[0]!r}"
    dj = _disjunction_hit(text, _disjunction(cmap))
    if dj:
        return f"disjunction marker {dj!r}"
    sep = _separator_hit(text, _separators(cmap))
    if sep:
        return f"structural separator {sep!r}"
    return None


def admissible(text, cmap):
    """True iff a requires text is an ADMISSIBLE conformance candidate:
    no frozen negation marker token, no disjunction marker as a whole
    word, no structural separator character. An INADMISSIBLE text
    (e.g. 'not limited to ...', or 'local or remote, v1 or v2, ...')
    contributes to NO family — reported, never silently matched."""
    return classify(text, cmap) is None


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
    return reg


def load(fam_c_dir):
    """Parse and freeze-check the governed map. Returns the map dict with
    its file sha attached under `conformance_map_sha256`. REFUSES
    (raises) on: missing file, unparsable JSON, version/rule mismatch, a
    missing or malformed `negation_markers` list, a missing or
    non-frozen `disjunction_markers` / `structural_separators` table,
    wrong family keys, a `t4_semantic_id` outside the registry
    resolver's value for that family, empty `requires_predicates`, a
    malformed predicate, or an unknown per-family key — never a silent
    default."""
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
    return sha


def _require_texts(requires_texts):
    if not isinstance(requires_texts, list) or not all(
            isinstance(x, str) for x in requires_texts):
        raise _refuse("conformance needs requires texts as a list of "
                      "strings (pass preconditions[*].requires — the "
                      "producer's affirmative applicability claims; "
                      "limitations are never conformance evidence)")


def _split_admissible(requires_texts, cmap):
    """Partition requires texts into (admissible, inadmissible) token
    sets. Inadmissible (negated or grammar-refused) texts contribute
    to NO family."""
    good, bad = [], []
    for text in requires_texts:
        if classify(text, cmap) is None:
            good.append(set(normalize(text)))
        else:
            bad.append(text)
    return good, bad


def _inadmissible_reasons(requires_texts, cmap):
    """The per-text refusal reasons, in declaration order, for the
    INADMISSIBLE subset (used to name the grammar refusal in the
    cause)."""
    out = []
    for text in requires_texts:
        why = classify(text, cmap)
        if why is not None:
            out.append(why)
    return out


def supported_t4_ids(requires_texts, cmap):
    """The sorted set of family T4 ids supported by this contract: a
    family's T4 is supported iff ANY ADMISSIBLE requires text matches
    ANY of its frozen `requires_predicates`. Inadmissible texts
    (negated or atomic-grammar-refused) and limitations contribute
    nothing."""
    _require_loaded(cmap)
    _require_texts(requires_texts)
    fams = cmap["families"]
    tokenized, _bad = _split_admissible(requires_texts, cmap)
    out = set()
    for fam in WANT_FAMILIES:
        for pred in fams[fam]["requires_predicates"]:
            if any(matches(pred, toks) for toks in tokenized):
                out.add(fams[fam]["t4_semantic_id"])
                break
    return sorted(out)


def verdict(family, requires_texts, cmap, *, limitations=None):
    """The frozen conformance verdict for one family over the producer's
    ACTUAL requires texts (`preconditions[*].requires`). Returns
    {"t4_semantic_id", "limitation_present", "matched",
    "supported_t4_ids", "non_discriminating", "conformance_cause",
    "conformance_map_sha256", "requires_declared",
    "requires_inadmissible", "inadmissible"}. `limitations`, when given,
    feeds ONLY the presence bit (free prose, never evidence); when
    omitted the presence bit falls back to whether any requires text
    was declared. RAISES on an unknown family, on non-string requires
    texts, or on a map that was not loaded here — never a silent
    default in either discriminating direction."""
    sha = _require_loaded(cmap)
    fams = cmap["families"]
    if family not in fams:
        raise _refuse(f"unknown family {family!r} (governed families: "
                      f"{list(WANT_FAMILIES)}; an unlisted family never "
                      f"defaults to discriminating or non-discriminating)")
    _require_texts(requires_texts)
    tid = fams[family]["t4_semantic_id"]
    tokenized, inadmissible = _split_admissible(requires_texts, cmap)
    matched = []
    for text, toks in zip([t for t in requires_texts
                           if t not in inadmissible], tokenized):
        for pred in fams[family]["requires_predicates"]:
            if matches(pred, toks):
                matched.append({"predicate": list(pred),
                                "requires": text})
    matched.sort(key=lambda m: (m["requires"], m["predicate"]))
    supported = supported_t4_ids(requires_texts, cmap)
    non_disc = tid not in supported
    n, k = len(requires_texts), len(inadmissible)
    if limitations is None:
        lim_present = bool(requires_texts)
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
            f"requires text (rule {RULE})")
        if k:
            reasons = _inadmissible_reasons(requires_texts, cmap)
            gram = [r for r in reasons
                    if r.startswith(("disjunction", "structural"))]
            if gram:
                cause += (" atomic-grammar-inadmissible: "
                          f"{gram[0]}")
            elif reasons:
                cause += f" negation-inadmissible: {reasons[0]}"
    else:
        first = matched[0]
        cause = (
            f"family T4 {tid} is discriminating for this contract: "
            f"frozen predicate {first['predicate']} matched requires "
            f"{first['requires']!r} ({n} declared precondition(s), "
            f"{k} inadmissible) (rule {RULE})")
    return {"t4_semantic_id": tid,
            "limitation_present": lim_present,
            "matched": matched,
            "supported_t4_ids": supported,
            "non_discriminating": non_disc,
            "conformance_cause": cause,
            "conformance_map_sha256": sha,
            "requires_declared": n,
            "requires_inadmissible": k,
            "inadmissible": list(inadmissible)}
