"""Seal canonicalization -- the SINGLE definition of the seal content hash.

THE FROZEN RULE (ruled by the auditor; do not redesign)
-------------------------------------------------------
A seal document carries three digest names that cannot cover themselves:

    SEAL_DIGEST_FIELDS = ("seal_content_sha256", "seal_file_sha256",
                          "seal_sha256")

The CONTENT hash is defined over the canonical form of the seal document with
those three names removed:

    body = {k: v for k, v in doc.items() if k not in SEAL_DIGEST_FIELDS}
    canonical_bytes = (json.dumps(body, sort_keys=True, indent=1)
                       + "\\n").encode("utf-8")

and the content hash itself is ``sha256(canonical_bytes).hexdigest()``.

Canonicalization IS the definition of the content hash, not an
implementation detail of it. That is why this module exists exactly ONCE, in
the versioned public repo, SHA-pinned by EXECUTION-LOCK.json, and used by
BOTH the producer (benchmarks/fam-c/harness-run/run_arm_h1.py) and the
verifier (a12r_real_receipt_gate.py). Two independent inline copies of this
rule are a permanent false-red drift risk: the producer would emit a
receipt whose content hash the verifier recomputes from different bytes, and
a correctly serialized seal would read as a mismatch. This module is the one
definition; there is no second copy to drift from.

The LEGACY rule
---------------
``legacy_sha256`` implements the older self-hash rule, which excludes ONLY
"seal_sha256" (so it DOES cover seal_content_sha256). It is retained because
the producer still emits ``seal_sha256`` for backward compatibility. The
verifier deliberately never compares the legacy self-hash against the raw
file bytes: by construction the self-hash cannot cover the bytes that carry
it, so that comparison cannot accept a correctly serialized seal.

PURITY CONTRACT
---------------
Pure ``dict -> bytes`` / ``dict -> str``. This module performs no filesystem
access, reads no environment, imports nothing but ``json`` and ``hashlib``
(and ``typing`` for annotations), logs nothing, and makes no assertion about
any producer. It has no side effects of any kind: importing it cannot fail on
a missing file, and calling it cannot fail on a missing directory. Callers own
all I/O -- in particular the verifier hashes this FILE's bytes and checks the
resulting digest against its frozen pin BEFORE importing and using it.
"""
import hashlib
import json
from typing import Any, Dict, Tuple

__all__ = [
    "SEAL_DIGEST_FIELDS",
    "LEGACY_EXCLUDED_FIELD",
    "canonical_bytes",
    "content_sha256",
    "legacy_sha256",
]

#: The three digest fields that cannot participate in the content hash.
SEAL_DIGEST_FIELDS: Tuple[str, str, str] = (
    "seal_content_sha256", "seal_file_sha256", "seal_sha256")

#: The single name excluded by the legacy self-hash rule.
LEGACY_EXCLUDED_FIELD: str = "seal_sha256"


def canonical_bytes(doc: Dict[str, Any]) -> bytes:
    """Canonical bytes of a seal document under the FROZEN rule.

    THE definition of the content hash: the JSON canonical form of ``doc``
    with all three :data:`SEAL_DIGEST_FIELDS` removed, serialized with
    ``sort_keys=True, indent=1`` and terminated by exactly one newline, encoded
    UTF-8. Pure: returns bytes, touches nothing.
    """
    body = {k: v for k, v in doc.items() if k not in SEAL_DIGEST_FIELDS}
    return (json.dumps(body, sort_keys=True, indent=1) + "\n").encode("utf-8")


def content_sha256(doc: Dict[str, Any]) -> str:
    """SHA256 hexdigest of :func:`canonical_bytes` -- the seal CONTENT hash."""
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def legacy_sha256(doc: Dict[str, Any]) -> str:
    """The LEGACY self-hash: excludes ONLY :data:`LEGACY_EXCLUDED_FIELD`.

    Covers every other key, including ``seal_content_sha256``, so call it
    AFTER the content hash has been stamped if the legacy bytes are meant to
    bind it (the producer does exactly that). Pure, like the rest of this
    module.
    """
    body = {k: v for k, v in doc.items() if k != LEGACY_EXCLUDED_FIELD}
    return hashlib.sha256(
        (json.dumps(body, sort_keys=True, indent=1) + "\n").encode("utf-8")
    ).hexdigest()
