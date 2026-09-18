'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SEED = path.join(__dirname, '..', 'registry', 'capability-registry.json');
const T = require('../lib/traces');

// Registry-derived assertions: the registry is a living artifact (capabilities
// are added every RCOS round), so tests assert INVARIANTS plus a seed floor,
// never fixed counts. Fixed counts broke this suite the moment the registry
// grew past the phase-1 seed (found red on 2026-09-17, fixed the same day).
test('registry parses and holds the seed invariants (statuses, lineage, promotion gate)', () => {
  const reg = JSON.parse(fs.readFileSync(SEED, 'utf8'));
  assert.equal(reg.registry_version, 'v1');
  assert.ok(reg.capabilities.length >= 8, 'registry keeps at least the 8 seed capabilities');

  const ids = new Set();
  for (const c of reg.capabilities) {
    assert.match(c.id, /^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    assert.ok(!ids.has(c.id), 'duplicate id: ' + c.id);
    ids.add(c.id);
    assert.ok(c.name.length > 0, c.id + ' has a name');
    assert.ok(typeof c.lineage === 'string' && c.lineage.length > 0, c.id + ' has lineage');
    assert.ok(['candidate', 'promoted', 'retired'].includes(c.status), c.id + ' status is valid');
    assert.ok(Array.isArray(c.evals), c.id + ' evals is an array');
    assert.equal(typeof c.reuse_count, 'number', c.id + ' reuse_count is a number');
    if (c.status === 'promoted') {
      const ships = c.evals.filter((e) => e.verdict === 'ship').length;
      assert.ok(ships >= 2, c.id + ' promoted with >= 2 shipped evals (x2-ship gate)');
      assert.ok(c.admitted_after.length >= 2, c.id + ' promoted with >= 2 admitted_after');
      const taskIds = new Set(c.evals.filter((e) => e.verdict === 'ship').map((e) => e.task_id));
      assert.ok(taskIds.size >= 2, c.id + ' promoted on 2 DISTINCT ship task ids — same-task repeats do not count');
      for (const e of c.evals) {
        assert.ok(typeof e.run_id === 'string' && e.run_id.trim().length > 0, c.id + '/' + e.task_id + ' has a run id — no run id, no admission');
      }
      assert.ok(c.retirement, c.id + ' promoted with retirement armed (arm at admission, never later)');
      assert.equal(c.retirement.policy_version, 'rcos-retire/1', c.id + ' retirement policy version');
    }
  }

  const op = reg.capabilities.find((c) => c.id === 'operator-ui-contract-test');
  assert.equal(op.status, 'promoted');
  assert.equal(op.admitted_after.length, 2);
});

// The hard invariant of the derived-reuse rule: what the registry stores must
// equal what the trace log says. If this fails, run `bin/rcos sync`.
test('stored reuse_count equals the trace-derived count for every capability', () => {
  const reg = JSON.parse(fs.readFileSync(SEED, 'utf8'));
  const counts = T.deriveReuseCounts(T.loadTraces(path.join(__dirname, '..')));
  for (const c of reg.capabilities) {
    assert.equal(c.reuse_count, counts[c.id] || 0, c.id + ' reuse_count is trace-derived, not hand-edited');
  }
});
