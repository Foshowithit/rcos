'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SEED = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'registry', 'capability-registry.json'), 'utf8'));

test('every registry capability has a dir with README.md and a matching EVAL.json', () => {
  for (const c of SEED.capabilities) {
    const dir = path.join(__dirname, '..', 'capabilities', c.id);
    const readme = fs.readFileSync(path.join(dir, 'README.md'), 'utf8');
    assert.ok(readme.includes(c.name), c.id + ' README names the capability');
    const evalJson = JSON.parse(fs.readFileSync(path.join(dir, 'EVAL.json'), 'utf8'));
    assert.equal(evalJson.capability, c.id);
    assert.ok(Array.isArray(evalJson.gates) && evalJson.gates.length >= 2, c.id + ' has >= 2 gates');
    for (const g of evalJson.gates) {
      assert.ok(g.id && (g.kind === 'deterministic' || g.kind === 'llm') && g.check, c.id + ' gate is well-formed');
    }
  }
});
