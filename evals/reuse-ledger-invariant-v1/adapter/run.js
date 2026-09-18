#!/usr/bin/env node
'use strict';

// Adapter: exercise the reuse-ledger invariant against a SANDBOX home inside
// the run's work dir. It never touches the caller's RCOS_HOME — the invariant
// under test is about what happens to the registry when a trace append fails,
// and that requires being able to make the append fail on purpose.
//
// Evidence contract with the gates: this adapter writes ledger-after.json with
// one record per step (exit status, stored count, registry hash) and the final
// trace rows. Gates read that file only — they never re-run anything.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const work = process.env.RCOS_WORK_DIR;
const rcos = process.env.RCOS_BIN;
if (!work || !rcos) {
  console.error('adapter needs RCOS_WORK_DIR and RCOS_BIN in the environment');
  process.exit(4);
}

const home = path.join(work, 'sandbox-home');
const regPath = path.join(home, 'registry', 'capability-registry.json');
const tracesPath = path.join(home, 'traces', 'traces.jsonl');

function sha(p) { return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'); }
function storedCount() {
  const reg = JSON.parse(fs.readFileSync(regPath, 'utf8'));
  return reg.capabilities.find((c) => c.id === 'fixture-cap').reuse_count;
}
function traceRows() {
  if (!fs.existsSync(tracesPath)) return [];
  return fs.readFileSync(tracesPath, 'utf8').split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
}
function rcosRun(...argv) {
  const r = spawnSync(rcos, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: (r.stdout || '').trim(), stderr: (r.stderr || '').trim() };
}

fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
fs.copyFileSync(path.join(work, 'seed-registry.json'), regPath);
const initialRegistrySha = sha(regPath);

const steps = [];
function step(name, result) {
  steps.push({
    name,
    result,
    stored_after: storedCount(),
    registry_sha256: sha(regPath),
    trace_lines: traceRows().length
  });
  return steps[steps.length - 1];
}

// 1. No trace log yet: sync must REFUSE rather than zero the cache. A cache
//    with nothing to verify against is unverifiable, not empty.
step('sync_without_trace_log', rcosRun('sync'));

// 2. A reuse appends a trace line and the count follows the trace.
step('reuse_log_first', rcosRun('reuse-log', '--id', 'fixture-cap', '--task', 't-adapter-1',
  '--run', '20260917T120000Z-aaaaaa', '--verdict', 'ship'));

// 3. Freeze the trace log (read-only file): the append now fails. The registry
//    must be left exactly as it was — trace first, registry second.
fs.chmodSync(tracesPath, 0o444);
step('reuse_log_append_blocked', rcosRun('reuse-log', '--id', 'fixture-cap', '--task', 't-adapter-2',
  '--run', '20260917T120001Z-bbbbbb', '--verdict', 'ship'));
fs.chmodSync(tracesPath, 0o644);

// 4. With the trace log intact again, sync must find nothing to change: the
//    cache already equals the trace-derived count.
step('sync_reconverges', rcosRun('sync'));

fs.writeFileSync(path.join(work, 'ledger-after.json'), JSON.stringify({
  sandbox_home: home,
  initial_registry_sha256: initialRegistrySha,
  steps,
  traces: traceRows()
}, null, 2) + '\n');

console.log('sandbox home: ' + home);
for (const s of steps) console.log('  ' + s.name + ': exit ' + s.result.status + ', reuse_count ' + s.stored_after);
process.exit(0);
