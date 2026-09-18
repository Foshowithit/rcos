#!/usr/bin/env python3
"""Priority 1 migration: give ONE legacy promoted capability a runnable adapter.

Authority: the round-2 implementation authorization (capability-audit/
GPT-VERDICT-20260918-ROUND2.md, "IMPLEMENTATION AUTHORIZED — staged, not blanket
mutation"), invariant 1 — "executed grounding first, no historical rewrites, new
executed receipts link backward, prioritize the 20 promoted assertions".

What this changes: exactly one field on exactly one existing entry —
`preview-server-verify` gains an `adapter` block naming how to invoke an artifact
that already exists on disk (capabilities/preview-server-verify/adapter/
serve_verify.py) and that the entry's own historical eval run_ids already name.
An adapter declaration is an invocation path, not evidence: it invents no run,
no verdict and no provenance.

What this does NOT touch, deliberately:
  - no eval entry is added, removed, reordered or reworded; the four historical
    assertions stay byte-for-byte as their authors wrote them;
  - no `provenance` field is written here — the executed receipt comes later,
    from `rcos eval-run --submit`, which is the only thing entitled to mint one;
  - no status, version, lineage, retirement, reuse_count or last_eval change;
  - no other capability entry is read or written.

Step 3's "do not invent adapters for historical entries" still holds for the
other nineteen: an entry earns an adapter when there is a concrete, runnable,
deterministic artifact to point at AND an evaluation that exercises it. This
file is the first of those, not a blanket re-opening.

Idempotent: re-running changes nothing once the block is present and equal. The
registry is re-serialized exactly as lib/registry.js does
(JSON.stringify(reg, null, 2)+"\\n"), and the round-trip is asserted
byte-identical before anything is written.
"""
import hashlib
import json
import sys

REGISTRY = 'registry/capability-registry.json'
CAPABILITY_ID = 'preview-server-verify'

ADAPTER = {
    'type': 'command',
    'entrypoint': 'capabilities/preview-server-verify/adapter/run.js',
    'timeout_seconds': 120,
    'contract': 'capabilities/preview-server-verify/contract.json',
}


def main():
    raw = open(REGISTRY, 'rb').read()
    reg = json.loads(raw.decode('utf-8'))
    # The serializer must be the same one the tool uses, or "byte-stable" is a
    # claim about a different file than the one on disk.
    if (json.dumps(reg, indent=2, ensure_ascii=False) + '\n').encode('utf-8') != raw:
        print('REFUSING: python re-serialization is not byte-identical to the file on disk', file=sys.stderr)
        return 1

    entry = next((c for c in reg['capabilities'] if c['id'] == CAPABILITY_ID), None)
    if entry is None:
        print('REFUSING: no capability %r in the registry' % CAPABILITY_ID, file=sys.stderr)
        return 1

    existing = entry.get('adapter')
    if existing is not None:
        if existing == ADAPTER:
            print('present, unchanged: %s (registry untouched)' % CAPABILITY_ID)
            return 0
        print('REFUSING: %s already declares a different adapter; this script does not overwrite'
              % CAPABILITY_ID, file=sys.stderr)
        print('  on disk:   ' + json.dumps(existing, sort_keys=True), file=sys.stderr)
        print('  intended:  ' + json.dumps(ADAPTER, sort_keys=True), file=sys.stderr)
        return 1

    evals_before = json.dumps(entry.get('evals'), sort_keys=True)
    entry['adapter'] = ADAPTER

    # The only permitted difference is the new key.
    assert json.dumps(entry.get('evals'), sort_keys=True) == evals_before
    assert 'provenance' not in json.dumps(entry.get('evals'))

    out = (json.dumps(reg, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    with open(REGISTRY, 'wb') as fh:
        fh.write(out)
    print('added adapter to promoted capability: ' + CAPABILITY_ID)
    print('  entrypoint %s (timeout %ds)' % (ADAPTER['entrypoint'], ADAPTER['timeout_seconds']))
    print('  contract   %s' % ADAPTER['contract'])
    print('  evals unchanged: %d (all still asserted)' % len(entry['evals']))
    print('sha256 %s -> %s' % (hashlib.sha256(raw).hexdigest()[:12], hashlib.sha256(out).hexdigest()[:12]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
