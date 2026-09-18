'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const R = require('../lib/registry');

function makeHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-test-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  fs.writeFileSync(
    path.join(home, 'registry', 'capability-registry.json'),
    JSON.stringify({ registry_version: 'v1', capabilities: [] })
  );
  return home;
}

test('propose -> eval x2 -> promote happy path', () => {
  const home = makeHome();
  const reg = R.loadRegistry(home);
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'skill' });
  assert.equal(reg.capabilities[0].status, 'candidate');
  assert.throws(() => R.promoteCapability(reg, 'demo-cap'), /x2-ship/);
  R.submitEval(reg, 'demo-cap', { task_id: 't-1', verdict: 'ship', run_id: 'r-1', date: '2026-09-14' });
  assert.throws(() => R.promoteCapability(reg, 'demo-cap'), /x2-ship/);
  R.submitEval(reg, 'demo-cap', { task_id: 't-2', verdict: 'ship', run_id: 'r-2', date: '2026-09-14' });
  R.promoteCapability(reg, 'demo-cap');
  assert.equal(reg.capabilities[0].status, 'promoted');
  assert.deepEqual(reg.capabilities[0].admitted_after, ['t-1', 't-2']);
  R.saveRegistry(home, reg);
  assert.equal(R.loadRegistry(home).capabilities[0].status, 'promoted');
});

test('propose rejects duplicates and bad kinds; eval rejects bad verdicts and unknown ids', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'skill' });
  assert.throws(() => R.proposeCapability(reg, { id: 'demo-cap', name: 'Dup', kind: 'skill' }), /already exists/);
  assert.throws(() => R.proposeCapability(reg, { id: 'other', name: 'O', kind: 'vibes' }), /kind must be/);
  assert.throws(() => R.submitEval(reg, 'nope', { task_id: 't', verdict: 'ship', run_id: 'r' }), /unknown capability/);
  assert.throws(() => R.submitEval(reg, 'demo-cap', { task_id: 't', verdict: 'maybe', run_id: 'r' }), /verdict must be/);
});

test('retire requires a reason; reuse has no manual increment path', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'script' });
  assert.throws(() => R.retireCapability(reg, 'demo-cap', '  '), /reason is required/);
  R.retireCapability(reg, 'demo-cap', 'superseded by demo-cap-2');
  assert.equal(reg.capabilities[0].status, 'retired');
  // the old counter-bump API is gone on purpose: the only way to move the
  // number is to append a trace and re-derive
  assert.equal(typeof R.logReuse, 'undefined');
  const traces = [
    { capability: 'demo-cap', task_id: 't-1', source: 'reuse', backfilled: false },
    { capability: 'demo-cap', task_id: 't-2', source: 'reuse', backfilled: false },
    { capability: 'demo-cap', task_id: 't-3', source: 'reuse', backfilled: true },        // reconstructed FROM the registry — must not count
    { capability: 'demo-cap', task_id: 't-4', source: 'synthesize', backfilled: false },  // not a reuse
    { capability: 'demo-cap', task_id: 't-5', source: null, backfilled: false }           // no provenance
  ];
  assert.deepEqual(R.reuseDeltas(reg, traces), [{ id: 'demo-cap', stored: 0, derived: 2 }]);
  R.syncDerivedReuse(reg, traces);
  assert.equal(reg.capabilities[0].reuse_count, 2);
  assert.deepEqual(R.reuseDeltas(reg, traces), []); // idempotent
});

test('promotion refuses same-task repeats and a blank run id', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'skill' });
  R.submitEval(reg, 'demo-cap', { task_id: 'same-task', verdict: 'ship', run_id: 'r-1', date: '2026-09-14' });
  R.submitEval(reg, 'demo-cap', { task_id: 'same-task', verdict: 'ship', run_id: 'r-2', date: '2026-09-14' });
  assert.throws(() => R.promoteCapability(reg, 'demo-cap'), /DISTINCT task ids/);
  // a whitespace run id is not an id: "no run id, no admission"
  const cap = reg.capabilities[0];
  cap.evals[1].task_id = 'other-task';
  cap.evals[1].run_id = '   ';
  assert.throws(() => R.promoteCapability(reg, 'demo-cap'), /no run id, no admission/);
  cap.evals[1].run_id = 'r-2';
  R.promoteCapability(reg, 'demo-cap');
  assert.deepEqual(cap.admitted_after, ['same-task', 'other-task']);
});

test('promotion arms retirement; the armed policy carries no invented thresholds', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'skill' });
  R.submitEval(reg, 'demo-cap', { task_id: 't-1', verdict: 'ship', run_id: 'r-1', date: '2026-09-14' });
  R.submitEval(reg, 'demo-cap', { task_id: 't-2', verdict: 'ship', run_id: 'r-2', date: '2026-09-14' });
  R.promoteCapability(reg, 'demo-cap', '2026-09-17');
  assert.deepEqual(reg.capabilities[0].retirement, {
    armed_at: '2026-09-17',
    policy_version: 'rcos-retire/1',
    decay: { window: 5, threshold: null },
    neglect: { n: 20, threshold: null }
  });
  // arming is idempotent and never overwrites an existing policy
  R.armRetirement(reg.capabilities[0], '2026-12-31');
  assert.equal(reg.capabilities[0].retirement.armed_at, '2026-09-17');
});

test('audit flags promoted-without-gate, decay, and staleness', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'shady', name: 'Shady', kind: 'script' });
  reg.capabilities[0].status = 'promoted';
  R.proposeCapability(reg, { id: 'decayer', name: 'Decayer', kind: 'runbook' });
  R.submitEval(reg, 'decayer', { task_id: 't-1', verdict: 'fix', run_id: 'r-1', date: '2026-09-01' });
  R.submitEval(reg, 'decayer', { task_id: 't-2', verdict: 'blocked', run_id: 'r-2', date: '2026-09-02' });
  R.proposeCapability(reg, { id: 'oldie', name: 'Oldie', kind: 'script' });
  R.submitEval(reg, 'oldie', { task_id: 't-1', verdict: 'ship', run_id: 'r-1', date: '2026-01-01' });
  R.submitEval(reg, 'oldie', { task_id: 't-2', verdict: 'ship', run_id: 'r-2', date: '2026-01-02' });
  reg.capabilities.find((c) => c.id === 'oldie').status = 'promoted';
  const res = R.auditRegistry(reg, new Date('2026-09-14T00:00:00Z'));
  assert.equal(res.ok, false);
  assert.match(res.errors.join('\n'), /shady.*x2-ship/);
  assert.match(res.warnings.join('\n'), /decayer.*decaying/);
  assert.match(res.warnings.join('\n'), /oldie.*stale/);
});

test('audit errors on promoted-without-retirement and warns on a stale reuse cache', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'skill' });
  R.submitEval(reg, 'demo-cap', { task_id: 't-1', verdict: 'ship', run_id: 'r-1', date: '2026-09-14' });
  R.submitEval(reg, 'demo-cap', { task_id: 't-2', verdict: 'ship', run_id: 'r-2', date: '2026-09-14' });
  R.promoteCapability(reg, 'demo-cap', '2026-09-17');
  delete reg.capabilities[0].retirement;
  const res = R.auditRegistry(reg, new Date('2026-09-17T00:00:00Z'));
  assert.equal(res.ok, false);
  assert.match(res.errors.join('\n'), /demo-cap.*promoted without retirement armed/);

  R.armRetirement(reg.capabilities[0], '2026-09-17');
  reg.capabilities[0].reuse_count = 7; // a hand-edit, which is exactly what the cache must not silently tolerate
  const withTraces = R.auditRegistry(reg, new Date('2026-09-17T00:00:00Z'), [{ capability: 'demo-cap', source: 'reuse', backfilled: false }]);
  assert.equal(withTraces.ok, true);
  assert.match(withTraces.warnings.join('\n'), /demo-cap.*reuse cache stale — stored 7, trace-derived 1/);
  // no trace file at all = unverifiable, not wrong: the check is skipped
  const noTraces = R.auditRegistry(reg, new Date('2026-09-17T00:00:00Z'), null);
  assert.doesNotMatch(noTraces.warnings.join('\n'), /reuse cache stale/);
});

test('query filters by status and kind', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'a-one', name: 'A', kind: 'skill' });
  R.proposeCapability(reg, { id: 'b-two', name: 'B', kind: 'script' });
  assert.equal(R.queryCapabilities(reg, { kind: 'skill' }).length, 1);
  assert.equal(R.queryCapabilities(reg, { status: 'candidate' }).length, 2);
  assert.equal(R.queryCapabilities(reg, { status: 'promoted' }).length, 0);
});
