#!/usr/bin/env node
'use strict';

// Gates for the reuse-ledger invariant. Each gate reads the adapter's frozen
// ledger snapshot (ledger-after.json in the run's work dir) — never live state,
// never the registry. Exit 0 = pass, 3 = fail, 4 = evidence unavailable.

const fs = require('node:fs');
const path = require('node:path');

const id = process.argv[2];
const ledgerPath = path.join(process.cwd(), 'ledger-after.json');
if (!fs.existsSync(ledgerPath)) {
  console.error('missing ledger-after.json — the adapter did not produce evidence');
  process.exit(4);
}
const L = JSON.parse(fs.readFileSync(ledgerPath, 'utf8'));
const step = (name) => L.steps.find((s) => s.name === name);

const checks = {
  // sync must not zero a cache it cannot verify. Exit 2 is the refusal code.
  sync_refuses_without_trace_log() {
    const s = step('sync_without_trace_log');
    if (!s) return { ok: false, detail: 'step missing' };
    const ok = s.result.status === 2 && s.stored_after === 0 && s.registry_sha256 === L.initial_registry_sha256;
    return { ok, detail: 'exit ' + s.result.status + ' (want 2), reuse_count ' + s.stored_after + ' (want 0), registry ' + (s.registry_sha256 === L.initial_registry_sha256 ? 'untouched' : 'MUTATED') };
  },

  // A logged reuse appends a trace line and the stored count follows it.
  trace_append_moves_count() {
    const s = step('reuse_log_first');
    if (!s) return { ok: false, detail: 'step missing' };
    const rows = L.traces.filter((t) => t.capability === 'fixture-cap' && t.task_id === 't-adapter-1');
    const ok = s.result.status === 0 && s.stored_after === 1 && rows.length === 1 &&
      rows[0].source === 'reuse' && rows[0].backfilled === false;
    return { ok, detail: 'exit ' + s.result.status + ', reuse_count ' + s.stored_after + ' (want 1), trace rows for t-adapter-1: ' + rows.length + (rows[0] ? ' source=' + rows[0].source : '') };
  },

  // The failed append must leave the registry byte-identical: no trace line,
  // no count movement. This is the trace-first ordering, not a convention.
  append_failure_leaves_registry_untouched() {
    const before = step('reuse_log_first');
    const s = step('reuse_log_append_blocked');
    if (!before || !s) return { ok: false, detail: 'step missing' };
    const ok = s.result.status !== 0 && s.stored_after === before.stored_after && s.registry_sha256 === before.registry_sha256;
    return { ok, detail: 'exit ' + s.result.status + ' (want non-zero), reuse_count ' + s.stored_after + ' (want ' + before.stored_after + '), registry ' + (s.registry_sha256 === before.registry_sha256 ? 'untouched' : 'MUTATED') };
  },

  // Nothing left to derive: sync reports agreement and writes nothing.
  sync_reconverges_read_only() {
    const before = step('reuse_log_first');
    const s = step('sync_reconverges');
    if (!before || !s) return { ok: false, detail: 'step missing' };
    const ok = s.result.status === 0 && /already matches/.test(s.result.stdout) &&
      s.stored_after === 1 && s.registry_sha256 === before.registry_sha256;
    return { ok, detail: 'exit ' + s.result.status + ', stdout "' + s.result.stdout + '", reuse_count ' + s.stored_after + ', registry ' + (s.registry_sha256 === before.registry_sha256 ? 'untouched' : 'MUTATED') };
  }
};

if (!id || !checks[id]) {
  console.error('unknown gate id: ' + id + ' (known: ' + Object.keys(checks).join(', ') + ')');
  process.exit(4);
}
const res = checks[id]();
console.log((res.ok ? 'PASS ' : 'FAIL ') + id + ': ' + res.detail);
process.exit(res.ok ? 0 : 3);
