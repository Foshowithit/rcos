'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { renderDashboard } = require('../lib/render');

const SEED = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'registry', 'capability-registry.json'), 'utf8'));

test('dashboard is deterministic and summarizes the registry', () => {
  const a = renderDashboard(SEED);
  const b = renderDashboard(JSON.parse(JSON.stringify(SEED)));
  assert.equal(a, b);
  assert.match(a, /8 candidates/);
  assert.match(a, /filmstrip-verify/);
  assert.match(a, /muse-image-lane/);
  assert.match(a, /<!doctype html>/i);
});

test('promoted capabilities sort first with eval dots', () => {
  const reg = JSON.parse(JSON.stringify(SEED));
  reg.capabilities[0].status = 'promoted';
  reg.capabilities[0].admitted_after = ['t-1', 't-2'];
  reg.capabilities[0].evals = [
    { task_id: 't-1', verdict: 'ship', run_id: 'r-1' },
    { task_id: 't-2', verdict: 'ship', run_id: 'r-2' }
  ];
  const html = renderDashboard(reg);
  assert.match(html, /1 promoted/);
  assert.ok(html.indexOf('filmstrip-verify') < html.indexOf('muse-image-lane'));
});
