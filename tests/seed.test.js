'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SEED = path.join(__dirname, '..', 'registry', 'capability-registry.json');

test('seed registry parses and holds the 8 honest candidates', () => {
  const reg = JSON.parse(fs.readFileSync(SEED, 'utf8'));
  assert.equal(reg.registry_version, 'v1');
  assert.equal(reg.capabilities.length, 8);
  for (const c of reg.capabilities) {
    assert.match(c.id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    assert.ok(c.name.length > 0);
    assert.equal(c.status, 'candidate');
    assert.deepEqual(c.evals, []);
    assert.ok(typeof c.lineage === 'string' && c.lineage.length > 0);
  }
});
