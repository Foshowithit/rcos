#!/usr/bin/env python3
"""Step 3 migration: make two registered capabilities directly executable.

Adds `reuse-ledger` and `agents-md-compactor` as CANDIDATE entries that declare
a runnable adapter (`type: command`) and a capability contract. Both are new
entries: the twenty legacy promoted capabilities are left byte-for-byte alone,
because step 3 does not invent adapters or evidence for historical entries.

Idempotent: re-running changes nothing once the entries exist. The registry is
re-serialized exactly as lib/registry.js does (JSON.stringify(reg, null, 2)+"\\n"),
and the round-trip is asserted byte-identical before anything is written.
"""
import hashlib
import json
import sys

REGISTRY = 'registry/capability-registry.json'

NEW_ENTRIES = [
    {
        'id': 'reuse-ledger',
        'name': 'Reuse ledger invariant',
        'kind': 'script',
        'version': '0.1.0',
        'status': 'candidate',
        'admitted_after': [],
        'evals': [],
        'reuse_count': 0,
        'last_eval': None,
        'lineage': ('step-1 invariant repair (057ac62, a5c6818): the stored reuse_count is a trace-derived '
                    'cache with no manual increment path; the adapter re-proves the four invariants in a sandbox home'),
        'adapter': {
            'type': 'command',
            'entrypoint': 'capabilities/reuse-ledger/adapter/run.js',
            'timeout_seconds': 120,
            'contract': 'capabilities/reuse-ledger/contract.json',
        },
    },
    {
        'id': 'agents-md-compactor',
        'name': 'AGENTS.md compactor',
        'kind': 'script',
        'version': '0.1.0',
        'status': 'candidate',
        'admitted_after': [],
        'evals': [],
        'reuse_count': 0,
        'last_eval': None,
        'lineage': ('~/.agents/tools/compact_agents_md.py frozen 2026-09-17 '
                    '(sha256 0955ad78cd4808dae85c5b74818839c2f1e1f5f4f4dfccdd0fa5a7cce85cc1e9), vendored under '
                    'capabilities/agents-md-compactor/tool/ so the adapter and the evaluation execute the same bytes'),
        'adapter': {
            'type': 'command',
            'entrypoint': 'capabilities/agents-md-compactor/adapter/run.js',
            'timeout_seconds': 120,
            'contract': 'capabilities/agents-md-compactor/contract.json',
        },
    },
]


def main():
    raw = open(REGISTRY, 'rb').read()
    reg = json.loads(raw.decode('utf-8'))
    # The serializer must be the same one the tool uses, or "byte-stable" is a
    # claim about a different file than the one on disk.
    if (json.dumps(reg, indent=2, ensure_ascii=False) + '\n').encode('utf-8') != raw:
        print('REFUSING: python re-serialization is not byte-identical to the file on disk', file=sys.stderr)
        return 1

    before = len(reg['capabilities'])
    existing = {c['id'] for c in reg['capabilities']}
    added = []
    for entry in NEW_ENTRIES:
        if entry['id'] in existing:
            print('present, unchanged: ' + entry['id'])
            continue
        reg['capabilities'].append(entry)
        added.append(entry['id'])
    if not added:
        print('nothing to do: %d capabilities, registry unchanged' % before)
        return 0

    out = (json.dumps(reg, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    with open(REGISTRY, 'wb') as fh:
        fh.write(out)
    print('added as candidates: ' + ', '.join(added))
    print('capabilities: %d -> %d' % (before, len(reg['capabilities'])))
    print('sha256 %s -> %s' % (hashlib.sha256(raw).hexdigest()[:12], hashlib.sha256(out).hexdigest()[:12]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
