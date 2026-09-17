'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const BIN = path.join(__dirname, '..', 'bin', 'rcos');
const SEED = path.join(__dirname, '..', 'registry', 'capability-registry.json');
const T = require('../lib/traces');

function makeHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-traces-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  fs.copyFileSync(SEED, path.join(home, 'registry', 'capability-registry.json'));
  return home;
}

function run(home, ...argv) {
  const r = spawnSync(BIN, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

test('appendTrace writes valid JSONL; loadTraces round-trips', () => {
  const home = makeHome();
  const rec = T.appendTrace(home, {
    capability: 'filmstrip-verify', task_id: 't-1', verdict: 'ship',
    context: 'verify a chalk short build', source: 'reuse', seconds: 90
  });
  assert.equal(rec.schema, T.TRACE_SCHEMA);
  assert.equal(rec.backfilled, false);
  const rows = T.loadTraces(home);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].context, 'verify a chalk short build');
  assert.equal(rows[0].source, 'reuse');
  assert.equal(rows[0].seconds, 90);
});

test('appendTrace validates verdict/source and defaults nulls honestly', () => {
  const home = makeHome();
  assert.throws(() => T.appendTrace(home, { capability: 'x', task_id: 't', verdict: 'maybe' }), /verdict must be/);
  assert.throws(() => T.appendTrace(home, { capability: 'x', task_id: 't', verdict: 'ship', source: 'vibes' }), /source must be/);
  assert.throws(() => T.appendTrace(home, { capability: 'x', verdict: 'ship' }), /task_id/);
  T.appendTrace(home, { capability: 'x', task_id: 't', verdict: 'blocked' });
  const rec = T.loadTraces(home)[0];
  assert.equal(rec.context, null);
  assert.equal(rec.source, null);
  assert.equal(rec.seconds, null);
  assert.equal(rec.backfilled, false);
});

test('traceGaps: every seed eval missing before backfill, none after', () => {
  const home = makeHome();
  const reg = JSON.parse(fs.readFileSync(SEED, 'utf8'));
  const totalEvals = reg.capabilities.reduce((n, c) => n + c.evals.length, 0);
  assert.ok(totalEvals > 0, 'seed has evals to check against');
  assert.equal(T.traceGaps(reg, T.loadTraces(home)).length, totalEvals);
  assert.equal(run(home, 'backfill-traces').status, 0);
  assert.equal(T.traceGaps(reg, T.loadTraces(home)).length, 0);
  // idempotent: a second backfill is a no-op
  const out = run(home, 'backfill-traces');
  assert.match(out.stdout, /no trace gaps/);
  // backfilled rows are flagged, so the learnable fraction stays honest
  const rows = T.loadTraces(home);
  assert.ok(rows.every((t) => t.backfilled === true));
});

test('cli eval-submit appends one trace; --context/--source/--seconds recorded; bad source exits 2', () => {
  const home = makeHome();
  const ok = run(home, 'eval-submit', '--id', 'filmstrip-verify', '--task', 'trace-t-1', '--verdict', 'ship',
    '--run', 'r', '--context', 'six-frame strip before rebuild', '--source', 'reuse', '--seconds', '42');
  assert.equal(ok.status, 0);
  assert.match(ok.stdout, /\(\+trace\)/);
  const rows = T.loadTraces(home).filter((t) => t.task_id === 'trace-t-1');
  assert.equal(rows.length, 1);
  assert.equal(rows[0].context, 'six-frame strip before rebuild');
  assert.equal(rows[0].source, 'reuse');
  assert.equal(rows[0].seconds, 42);
  assert.equal(rows[0].backfilled, false);
  const bad = run(home, 'eval-submit', '--id', 'filmstrip-verify', '--task', 'trace-t-2', '--verdict', 'ship',
    '--run', 'r', '--source', 'vibes');
  assert.equal(bad.status, 2);
  // failed submit must not leave a registry eval or a trace line behind
  const reg = JSON.parse(fs.readFileSync(path.join(home, 'registry', 'capability-registry.json'), 'utf8'));
  const cap = reg.capabilities.find((c) => c.id === 'filmstrip-verify');
  assert.equal(cap.evals.some((e) => e.task_id === 'trace-t-2'), false);
  assert.equal(T.loadTraces(home).some((t) => t.task_id === 'trace-t-2'), false);
});

test('cli traces reader filters and reports; audit warns on trace gaps until backfilled', () => {
  const home = makeHome();
  const a1 = run(home, 'audit');
  assert.equal(a1.status, 0); // gaps are WARN, not ERROR
  assert.match(a1.stdout, /trace gap/);
  assert.equal(run(home, 'backfill-traces').status, 0);
  const a2 = run(home, 'audit');
  assert.equal(a2.status, 0);
  assert.doesNotMatch(a2.stdout, /trace gap/);
  const tj = JSON.parse(run(home, 'traces', '--json').stdout);
  assert.ok(Array.isArray(tj) && tj.length > 0);
  const one = run(home, 'traces', '--capability', 'filmstrip-verify');
  assert.match(one.stdout, /for 'filmstrip-verify'/);
});
