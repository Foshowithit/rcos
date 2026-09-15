'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const V = require('../lib/validate');

const SEED = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'registry', 'capability-registry.json'), 'utf8'));

function good() {
  return {
    id: 'demo-cap', name: 'Demo', kind: 'script', version: '1.2.0',
    status: 'candidate', admitted_after: [],
    evals: [{ task_id: 't-1', verdict: 'ship', run_id: 'r-1' }],
    reuse_count: 3, last_eval: '2026-09-14'
  };
}

test('seed registry validates clean', () => {
  assert.deepEqual(V.validateRegistry(SEED), []);
});

test('rejects bad id, kind, version, retired-without-reason, duplicate ids', () => {
  const badId = good(); badId.id = 'Bad_ID';
  assert.match(V.validateRegistry({ registry_version: 'v1', capabilities: [badId] })[0], /id/);
  const badKind = good(); badKind.kind = 'vibes';
  assert.match(V.validateRegistry({ registry_version: 'v1', capabilities: [badKind] })[0], /kind/);
  const badVer = good(); badVer.version = '1.2';
  assert.match(V.validateRegistry({ registry_version: 'v1', capabilities: [badVer] })[0], /version/);
  const badRet = good(); badRet.status = 'retired';
  assert.match(V.validateRegistry({ registry_version: 'v1', capabilities: [badRet] })[0], /retire_reason/);
  const dup = { registry_version: 'v1', capabilities: [good(), good()] };
  assert.match(V.validateRegistry(dup).join('\n'), /duplicate/);
});

test('shipCount counts ship verdicts only', () => {
  const c = good();
  c.evals.push({ task_id: 't-2', verdict: 'fix', run_id: 'r-2' });
  assert.equal(V.shipCount(c), 1);
});

test('isValidDate accepts YYYY-MM-DD real dates only', () => {
  assert.equal(V.isValidDate('2026-09-14'), true);
  assert.equal(V.isValidDate('14-09-2026'), false);
  assert.equal(V.isValidDate('2026-13-40'), false);
});
