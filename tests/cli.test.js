'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const BIN = path.join(__dirname, '..', 'bin', 'rcos');
const SEED = path.join(__dirname, '..', 'registry', 'capability-registry.json');
// counts derived from the live registry — fixed numbers broke this suite when
// the registry grew (found red 2026-09-17, fixed the same day)
const REG = JSON.parse(fs.readFileSync(SEED, 'utf8'));
const N_CAPS = REG.capabilities.length;
const N_PROMOTED = REG.capabilities.filter((c) => c.status === 'promoted').length;
const N_CANDIDATES = REG.capabilities.filter((c) => c.status === 'candidate').length;

function makeHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-cli-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  fs.copyFileSync(SEED, path.join(home, 'registry', 'capability-registry.json'));
  // A declared adapter is executable only if its entrypoint resolves under the
  // home, and audit checks exactly that — so the home carries the capability dirs.
  fs.cpSync(path.join(__dirname, '..', 'capabilities'), path.join(home, 'capabilities'), { recursive: true });
  return home;
}

function run(home, ...args) {
  return spawnSync(process.execPath, [BIN, ...args], {
    env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8'
  });
}

test('query lists seed candidates; --json parses', () => {
  const home = makeHome();
  const out = run(home, 'query');
  assert.equal(out.status, 0);
  assert.match(out.stdout, /filmstrip-verify/);
  const js = run(home, 'query', '--json');
  assert.equal(js.status, 0);
  assert.equal(JSON.parse(js.stdout).length, N_CAPS);
});

test('propose -> eval-submit x2 -> promote works end to end', () => {
  const home = makeHome();
  assert.equal(run(home, 'propose', '--id', 'cli-demo', '--name', 'CLI Demo', '--kind', 'skill').status, 0);
  // satisfy the promote EVAL.json gate: document the eval before promoting (Task 6 convention)
  fs.mkdirSync(path.join(home, 'capabilities', 'cli-demo'), { recursive: true });
  fs.writeFileSync(path.join(home, 'capabilities', 'cli-demo', 'EVAL.json'),
    JSON.stringify({ capability: 'cli-demo', gates: [{ id: 'g1', kind: 'deterministic', check: 'c1' }, { id: 'g2', kind: 'llm', check: 'c2' }] }, null, 2));
  assert.equal(run(home, 'query', '--kind', 'skill').status, 0);
  const early = run(home, 'promote', '--id', 'cli-demo');
  assert.equal(early.status, 2);
  assert.match(early.stderr, /x2-ship/);
  assert.equal(run(home, 'eval-submit', '--id', 'cli-demo', '--task', 't-1', '--verdict', 'ship', '--run', 'r-1', '--date', '2026-09-14').status, 0);
  assert.equal(run(home, 'eval-submit', '--id', 'cli-demo', '--task', 't-2', '--verdict', 'ship', '--run', 'r-2', '--date', '2026-09-14').status, 0);
  assert.equal(run(home, 'promote', '--id', 'cli-demo').status, 0);
  const q = run(home, 'query', '--status', 'promoted', '--json');
  // the seed's promoted set plus cli-demo
  assert.equal(JSON.parse(q.stdout).length, N_PROMOTED + 1);
});

test('usage and domain errors use exit codes 1 and 2', () => {
  const home = makeHome();
  assert.equal(run(home, 'frobnicate').status, 1);
  assert.equal(run(home, 'promote').status, 1);
  const bad = run(home, 'eval-submit', '--id', 'filmstrip-verify', '--task', 't', '--verdict', 'maybe', '--run', 'r');
  assert.equal(bad.status, 2);
  assert.match(bad.stderr, /verdict must be/);
  const retire = run(home, 'retire', '--id', 'filmstrip-verify');
  assert.equal(retire.status, 1);
});

test('audit exits 0 on the seed; render writes a deterministic dashboard', () => {
  const home = makeHome();
  const a = run(home, 'audit');
  assert.equal(a.status, 0);
  const r1 = run(home, 'render');
  assert.equal(r1.status, 0);
  assert.match(r1.stdout, /dashboard\.html/);
  const html1 = fs.readFileSync(path.join(home, 'dashboard.html'), 'utf8');
  assert.match(html1, /filmstrip-verify/);
  assert.match(html1, new RegExp(N_CANDIDATES + ' candidates'));
  assert.match(html1, new RegExp(N_PROMOTED + ' promoted'));
  const r2 = run(home, 'render');
  assert.equal(r2.status, 0);
  assert.equal(fs.readFileSync(path.join(home, 'dashboard.html'), 'utf8'), html1);
});
