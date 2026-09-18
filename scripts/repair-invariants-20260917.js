#!/usr/bin/env node
'use strict';
// One-shot repair for the 2026-09-17 invariant change (GPT round-3, step 1):
//   (a) reuse_count becomes a CACHE of the trace log, so every stored value is
//       reset to its trace-derived value;
//   (b) retirement is armed on every promoted capability, at admission by rule
//       — for the caps admitted before the rule existed, at the date of this
//       repair, which is recorded in the receipt.
// Idempotent: running it twice prints an empty delta table and changes nothing.
//
// What this script deliberately does NOT do: write backfilled trace lines to
// justify the stored increments that left no evidence. Backfilled lines are
// excluded from derivation by design, and inventing evidence to preserve a
// number is the exact failure the derived-reuse rule exists to prevent.

const fs = require('node:fs');
const path = require('node:path');
const R = require('../lib/registry');
const T = require('../lib/traces');

const HOME = process.env.RCOS_HOME || path.join(__dirname, '..');
const ARMED_AT = '2026-09-17';
const REG_PATH = path.join(HOME, 'registry', 'capability-registry.json');

function main() {
  const reg = JSON.parse(fs.readFileSync(REG_PATH, 'utf8'));
  const traces = T.loadTraces(HOME);
  const counts = T.deriveReuseCounts(traces);

  const deltas = [];
  for (const c of reg.capabilities) {
    const derived = counts[c.id] || 0;
    if (c.reuse_count !== derived) deltas.push({ id: c.id, stored: c.reuse_count, derived });
    c.reuse_count = derived;
  }

  const armed = [];
  for (const c of reg.capabilities) {
    if (c.status !== 'promoted') continue;
    if (c.retirement) continue;
    R.armRetirement(c, ARMED_AT);
    armed.push(c.id);
  }

  console.log('traces: ' + traces.length + ' lines, ' +
    traces.filter((t) => t.source === 'reuse' && t.backfilled !== true).length + ' reusable ' +
    '(source=reuse, not backfilled)');
  console.log('reuse_count deltas: ' + deltas.length);
  for (const d of deltas) console.log('  ' + d.id + ': stored ' + d.stored + ' -> trace-derived ' + d.derived);
  console.log('retirement armed on ' + armed.length + ' promoted capability/capabilities (armed_at ' + ARMED_AT + ')');
  for (const id of armed) console.log('  ' + id);

  if (deltas.length === 0 && armed.length === 0) {
    console.log('nothing to do — registry already repaired');
    return;
  }
  R.saveRegistry(HOME, reg);
  console.log('wrote ' + REG_PATH);
}

main();
