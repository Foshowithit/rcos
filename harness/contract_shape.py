#!/usr/bin/env python3
"""A12d slice D8.1 — ONE pure producer-contract-shape authority (auditor
D7-post P0).

The exact three-key producer contract schema (frozen in D7) has exactly
ONE implementation: this module. It is called by BOTH
harness/promotion.py::_producer_contract and harness/order.py's
PROMOTION-receipt provenance check, so the same malformed T0
declaration produces the same finding text through both authorities.

Pure function of its argument: no I/O, no globals, no vocabulary
knowledge. This module never imports, reads, or consults any
recognition table (an unknown atomic token is NOT a shape defect —
D6 semantics kept); it knows only the structural shape.

Rules (today's promotion rules, unchanged — the change is that BOTH
authorities now apply them):

  1. the declaration must be a dict; absent/None (including the
     retired `payload["contract"]` alias shape, which arrives here as
     a non-dict) is refused;
  2. top-level keys EXACTLY {semantic_core, preconditions,
     limitations}: a missing key is refused naming that key; an extra
     key is refused naming that key literally, never silently dropped;
  3. `semantic_core`: a nonempty str (whitespace-only refused);
  4. `preconditions`: a list (MAY be empty); each item a dict with
     EXACTLY the key `requires_all` carrying a list of >=1 atomic
     tokens matching ^[a-z0-9_.-]+$ with no duplicates. A bare
     string, the retired `requires` key, an extra precondition key,
     an empty list, a non-atomic or uppercase token, or a duplicate
     is refused;
  5. `limitations`: a list of strings (MAY be empty).

`validate()` returns the ordered finding list (empty = well-formed).
Callers prefix the transport ("PROMOTION-DENY " in the controller,
"promotion provenance: " in the order validator); the finding text
itself is identical. Stdlib only (`re` for the atomic predicate).
"""
import re
_ATOMIC_RE = re.compile(r"^[a-z0-9_.-]+$")

_WANT = ("semantic_core", "preconditions", "limitations")


def validate(declared):
    """Validate ONE producer capability contract declaration.

    Returns [finding, ...] in deterministic fail-fast order (the same
    order the D7 controller raised them); [] means well-formed. Never
    raises, never reads, never consults a vocabulary.
    """
    out = []
    if not isinstance(declared, dict):
        return ["T0 arrival declares no producer capability contract "
                "(execution_payload.capability_contract "
                "{semantic_core, preconditions, limitations} is required; "
                "the promoted contract is producer-authored, never "
                "synthesized)"]
    got = set(declared)
    want = set(_WANT)
    missing = sorted(want - got)
    if missing:
        return ["producer capability contract is missing the required "
                f"top-level key {missing[0]!r} (the exact three-key "
                "shape {semantic_core, preconditions, limitations} is "
                "required; nothing is defaulted, nothing is dropped)"]
    extra = sorted(got - want)
    if extra:
        return ["producer capability contract carries an extra "
                f"top-level key {extra[0]!r} (the exact three-key "
                "shape {semantic_core, preconditions, limitations} is "
                "required; unlisted keys are refused, never silently "
                "dropped)"]
    core = declared.get("semantic_core")
    pre = declared.get("preconditions")
    lim = declared.get("limitations")
    if not isinstance(core, str) or not core.strip():
        out.append("producer capability contract has an empty "
                   "semantic_core")
        return out
    if not isinstance(pre, list):
        out.append("producer capability contract preconditions must be "
                   "an atomic-conjunction-v5 shape list of "
                   "{\"requires_all\": [atomic tokens]} objects "
                   "(possibly empty)")
        return out
    for entry in pre:
        if isinstance(entry, str):
            out.append("producer capability contract carries a "
                       f"bare-string precondition {entry[:60]!r}: the "
                       "atomic-conjunction-v5 shape requires "
                       "{\"requires_all\": [atomic tokens]} objects "
                       "(a bare string cannot carry the structural "
                       "conjunction, so a conditional clause could smuggle "
                       "a branching claim past conformance)")
            return out
        if not isinstance(entry, dict) or set(entry) != {"requires_all"}:
            out.append("producer capability contract carries a "
                       f"malformed precondition {str(entry)[:80]!r}: the "
                       "atomic-conjunction-v5 shape is exactly "
                       "{\"requires_all\": [atomic tokens]} (the retired "
                       "\"requires\" key and every unknown key are refused)")
            return out
        toks = entry.get("requires_all")
        if not isinstance(toks, list) or not toks:
            out.append("producer capability contract carries a "
                       "precondition with an empty requires_all list (each "
                       "{\"requires_all\": [tokens]} must name >=1 atomic "
                       "applicability token)")
            return out
        for tok in toks:
            if not isinstance(tok, str) or not _ATOMIC_RE.match(tok):
                out.append("producer capability contract carries a "
                           f"non-atomic requires_all token {tok!r}: the "
                           "atomic-conjunction-v5 shape admits only "
                           "^[a-z0-9_.-]+$ tokens (a conditional clause "
                           "is structurally unrepresentable as conformance "
                           "evidence)")
                return out
        if len(set(toks)) != len(toks):
            dup = next(t for t in toks if toks.count(t) > 1)
            out.append("producer capability contract carries "
                       "a duplicate requires_all token "
                       f"{dup!r}: the "
                       "atomic-conjunction-v5 shape admits no duplicates")
            return out
    if not isinstance(lim, list) or not all(isinstance(x, str)
                                            for x in lim):
        out.append("producer capability contract limitations must be a "
                   "list of strings (possibly empty; free prose, recorded "
                   "verbatim, never conformance evidence)")
        return out
    return out


def precondition_token_lists(declared):
    """The declaration's preconditions[*].requires_all token lists.

    Pure extraction through the SAME authority (no second
    approximation): the lists, or None when the declaration is not
    shape-valid. Callers needing the conformance candidate lists use
    this — never a private re-derivation of the shape.
    """
    if validate(declared):
        return None
    return [list(p["requires_all"]) for p in declared["preconditions"]]
