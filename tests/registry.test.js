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

test('retire requires a reason; reuse increments', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'demo-cap', name: 'Demo', kind: 'script' });
  assert.throws(() => R.retireCapability(reg, 'demo-cap', '  '), /reason is required/);
  R.retireCapability(reg, 'demo-cap', 'superseded by demo-cap-2');
  assert.equal(reg.capabilities[0].status, 'retired');
  R.logReuse(reg, 'demo-cap');
  R.logReuse(reg, 'demo-cap');
  assert.equal(reg.capabilities[0].reuse_count, 2);
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

test('query filters by status and kind', () => {
  const reg = R.loadRegistry(makeHome());
  R.proposeCapability(reg, { id: 'a-one', name: 'A', kind: 'skill' });
  R.proposeCapability(reg, { id: 'b-two', name: 'B', kind: 'script' });
  assert.equal(R.queryCapabilities(reg, { kind: 'skill' }).length, 1);
  assert.equal(R.queryCapabilities(reg, { status: 'candidate' }).length, 2);
  assert.equal(R.queryCapabilities(reg, { status: 'promoted' }).length, 0);
});
