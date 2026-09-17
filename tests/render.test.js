'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { renderDashboard } = require('../lib/render');

const SEED = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'registry', 'capability-registry.json'), 'utf8'));
const counts = (reg) => ({
  promoted: reg.capabilities.filter((c) => c.status === 'promoted').length,
  candidate: reg.capabilities.filter((c) => c.status === 'candidate').length
});

test('dashboard is deterministic and summarizes the registry', () => {
  const a = renderDashboard(SEED);
  const b = renderDashboard(JSON.parse(JSON.stringify(SEED)));
  assert.equal(a, b);
  const c = counts(SEED);
  assert.match(a, new RegExp(c.candidate + ' candidates'));
  assert.match(a, new RegExp(c.promoted + ' promoted'));
  assert.match(a, /filmstrip-verify/);
  assert.match(a, /muse-image-lane/);
  assert.match(a, /<!doctype html>/i);
});

test('promoted capabilities sort first with eval dots', () => {
  const reg = JSON.parse(JSON.stringify(SEED));
  const idx = reg.capabilities.findIndex((c) => c.status === 'candidate');
  reg.capabilities[idx].status = 'promoted';
  reg.capabilities[idx].admitted_after = ['t-1', 't-2'];
  reg.capabilities[idx].evals = [
    { task_id: 't-1', verdict: 'ship', run_id: 'r-1' },
    { task_id: 't-2', verdict: 'ship', run_id: 'r-2' }
  ];
  const html = renderDashboard(reg);
  assert.match(html, new RegExp(counts(reg).promoted + ' promoted'));
  // the just-promoted capability renders before any remaining candidate
  const stillCandidate = reg.capabilities.find((c) => c.status === 'candidate');
  assert.ok(stillCandidate, 'registry keeps at least one candidate');
  assert.ok(html.indexOf(reg.capabilities[idx].id) < html.indexOf(stillCandidate.id));
});
