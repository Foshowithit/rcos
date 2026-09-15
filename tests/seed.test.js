'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SEED = path.join(__dirname, '..', 'registry', 'capability-registry.json');

test('seed registry parses and holds 7 candidates + 1 promoted (Phase 2 evolution)', () => {
  const reg = JSON.parse(fs.readFileSync(SEED, 'utf8'));
  assert.equal(reg.registry_version, 'v1');
  assert.equal(reg.capabilities.length, 8);
  const candidates = reg.capabilities.filter((c) => c.status === 'candidate');
  const promoted = reg.capabilities.filter((c) => c.status === 'promoted');
  assert.equal(candidates.length, 7);
  assert.equal(promoted.length, 1);
  for (const c of reg.capabilities) {
    assert.match(c.id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    assert.ok(c.name.length > 0);
    assert.ok(typeof c.lineage === 'string' && c.lineage.length > 0);
  }
  for (const c of candidates) {
    assert.deepEqual(c.evals, []);
  }
  assert.equal(promoted[0].id, 'operator-ui-contract-test');
  assert.equal(promoted[0].admitted_after.length, 2);
});
