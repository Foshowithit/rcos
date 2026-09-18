'use strict';
// The invocation kernel's own contract, pinned: name a capability explicitly,
// hand it input, get back one of four mechanical states plus a sealed artifact.
// These tests build their own capabilities on purpose — what they pin is the
// kernel's rules (rejection before execution, exit 0 with unacceptable output
// is a failure, write-once artifacts, status gating), not the two shipped
// adapters, which evalrunner.test.js exercises end-to-end.

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const REPO = path.join(__dirname, '..');
const BIN = path.join(REPO, 'bin', 'rcos');
const I = require('../lib/invocation');

const CONTRACT = {
  schema: 'rcos-capability-contract/1',
  input: {
    type: 'object', required: ['name'], additionalProperties: false,
    properties: { name: { type: 'string', minLength: 1 } }
  },
  output: {
    type: 'object', required: ['schema', 'greeting'], additionalProperties: false,
    properties: {
      schema: { type: 'string', enum: ['echo/1'] },
      greeting: { type: 'string', minLength: 1 }
    }
  }
};

// The kernel spawns the entrypoint directly, so a fixture adapter is a real
// executable with a shebang. Each one drops a marker in the invocation work dir
// when it runs: whether that marker exists is how these tests tell "refused
// before execution" from "executed".
function adapter(...lines) {
  return ['#!/usr/bin/env node', ...lines, ''].join('\n');
}

const SCRIPTS = {
  echo: adapter(
    "const fs = require('node:fs');",
    "const input = JSON.parse(fs.readFileSync(process.env.RCOS_INPUT, 'utf8'));",
    "fs.writeFileSync('ran.marker', 'yes');",
    "fs.writeFileSync(process.env.RCOS_EVIDENCE_DIR + '/note.txt', 'written by the adapter\\n');",
    "fs.writeFileSync(process.env.RCOS_OUTPUT, JSON.stringify({ schema: 'echo/1', greeting: 'hello ' + input.name }) + '\\n');"
  ),
  extraField: adapter(
    "const fs = require('node:fs');",
    "fs.writeFileSync('ran.marker', 'yes');",
    "fs.writeFileSync(process.env.RCOS_OUTPUT, JSON.stringify({ schema: 'echo/1', greeting: 'hi', extra: true }) + '\\n');"
  ),
  silent: adapter(
    "const fs = require('node:fs');",
    "fs.writeFileSync('ran.marker', 'yes');"
  ),
  crash: adapter(
    "const fs = require('node:fs');",
    "fs.writeFileSync('ran.marker', 'yes');",
    'process.exit(3);'
  ),
  cannotRun: adapter(
    "const fs = require('node:fs');",
    "fs.writeFileSync('ran.marker', 'yes');",
    'process.exit(4);'
  )
};

function capability(id, opts = {}) {
  const status = opts.status || 'promoted';
  const c = {
    id, name: 'fixture ' + id, kind: 'script', version: '1.0.0', status,
    admitted_after: [], evals: [], reuse_count: opts.reuse_count || 0, last_eval: null
  };
  if (status === 'promoted') {
    c.evals = [
      { task_id: 't-a', verdict: 'ship', run_id: '20260901T000000Z-aaaaaa' },
      { task_id: 't-b', verdict: 'ship', run_id: '20260901T000001Z-bbbbbb' }
    ];
    c.admitted_after = ['t-a', 't-b'];
    c.retirement = {
      armed_at: '2026-09-01', policy_version: 'rcos-retire/1',
      decay: { window: 5, threshold: null }, neglect: { n: 20, threshold: null }
    };
  }
  if (status === 'retired') c.retire_reason = 'fixture: retired on purpose';
  if (!opts.noAdapter) {
    c.adapter = {
      type: 'command',
      entrypoint: opts.entrypoint || ('capabilities/' + id + '/adapter/run.js'),
      timeout_seconds: 30
    };
    if (opts.contract || opts.contractMissing) c.adapter.contract = 'capabilities/' + id + '/contract.json';
  }
  return c;
}

function fx(id, opts = {}) { return Object.assign({}, opts, { cap: capability(id, opts) }); }

// One home per test: a hand-written registry plus the capability dirs its
// declarations point at. Nothing here is copied from the shipped registry, so a
// failure names a kernel rule rather than a fixture drift.
function makeHome(fixtures) {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-invocation-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  for (const f of fixtures) {
    const dir = path.join(home, 'capabilities', f.cap.id);
    fs.mkdirSync(path.join(dir, 'adapter'), { recursive: true });
    if (f.script !== undefined) {
      const p = path.join(dir, 'adapter', 'run.js');
      fs.writeFileSync(p, f.script);
      fs.chmodSync(p, f.mode === undefined ? 0o755 : f.mode);
    }
    if (f.contract !== undefined) {
      fs.writeFileSync(path.join(dir, 'contract.json'), JSON.stringify(f.contract, null, 2) + '\n');
    }
  }
  fs.writeFileSync(path.join(home, 'registry', 'capability-registry.json'),
    JSON.stringify({ registry_version: 'v1', capabilities: fixtures.map((f) => f.cap) }, null, 2) + '\n');
  return home;
}

function run(home, ...argv) {
  const r = spawnSync(BIN, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

test('kernel: an eligible capability runs once and leaves a sealed, self-describing artifact', () => {
  const home = makeHome([fx('echo-cap', { script: SCRIPTS.echo, contract: CONTRACT })]);
  const res = I.invokeCapability(home, 'echo-cap', { input: { name: 'ada' } });
  assert.equal(res.ok, true, res.error);
  assert.equal(res.status, 'completed');
  assert.match(res.basis, /satisfied the declared contract/);

  const m = res.manifest;
  assert.equal(m.schema, 'rcos-invocation/1');
  assert.equal(m.capability_id, 'echo-cap');
  assert.equal(m.capability_version, '1.0.0');
  assert.equal(m.registry_status, 'promoted');
  assert.equal(m.mode, 'normal');
  assert.equal(m.adapter.type, 'command');
  assert.equal(m.adapter.exit_code, 0);
  assert.equal(m.contract.input.status, 'pass');
  assert.equal(m.contract.output.status, 'pass');

  for (const name of ['manifest.json', 'input.json', 'output.json', 'stdout.txt', 'stderr.txt', 'evidence/note.txt']) {
    assert.ok(fs.existsSync(path.join(res.dir, name)), name + ' exists');
  }
  // The hashes describe the bytes that are actually on disk.
  assert.equal(m.input.sha256, I.sha256(fs.readFileSync(path.join(res.dir, 'input.json'))));
  assert.equal(m.output.sha256, I.sha256(fs.readFileSync(path.join(res.dir, 'output.json'))));
  assert.equal(m.evidence.length, 1);
  assert.equal(m.evidence[0].path, 'evidence/note.txt');
  assert.ok(fs.existsSync(path.join(res.dir, 'work', 'ran.marker')), 'the adapter actually ran');

  const v = I.verifyInvocation(home, res.invocation_id);
  assert.equal(v.ok, true, v.problems.join('; '));
  assert.ok(v.checked >= 5, 'checked ' + v.checked + ' artifacts');

  const rows = I.listInvocations(home);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].invocation_id, res.invocation_id);
  assert.equal(rows[0].status, 'completed');
  assert.equal(rows[0].capability_id, 'echo-cap');
});

test('kernel: input the declared contract refuses is rejected before the adapter runs', () => {
  const home = makeHome([fx('echo-cap', { script: SCRIPTS.echo, contract: CONTRACT })]);
  const cases = [
    ['wrong type', { name: 7 }, /expected string, got integer/],
    ['unknown field', { name: 'ada', extra: 1 }, /unknown field/],
    ['missing required', {}, /input\.name: required/],
    ['nothing at all', null, /input: expected object, got null/]
  ];
  for (const [label, input, expect] of cases) {
    const res = I.invokeCapability(home, 'echo-cap', { input });
    assert.equal(res.ok, true, label);
    assert.equal(res.status, 'rejected', label + ': ' + res.basis);
    assert.match(res.basis, expect, label);
    assert.equal(res.manifest.adapter.exit_code, null, label + ': the adapter was never spawned');
    assert.equal(res.manifest.contract.input.status, 'fail', label);
    assert.ok(!fs.existsSync(path.join(res.dir, 'work', 'ran.marker')), label + ': no adapter side effect');
    assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true, label + ': a refusal is still a sealed artifact');
  }
});

test('kernel: exit 0 with output the contract does not accept is a failure, never a completion', () => {
  const home = makeHome([
    fx('extra-field-cap', { script: SCRIPTS.extraField, contract: CONTRACT }),
    fx('silent-cap', { script: SCRIPTS.silent, contract: CONTRACT })
  ]);
  const extra = I.invokeCapability(home, 'extra-field-cap', { input: { name: 'ada' } });
  assert.equal(extra.status, 'failed', extra.basis);
  assert.match(extra.basis, /violates the declared output contract/);
  assert.match(extra.basis, /output\.extra: unknown field/);
  assert.equal(extra.manifest.contract.output.status, 'fail');
  assert.equal(extra.manifest.adapter.exit_code, 0, 'the adapter itself succeeded');
  assert.ok(fs.existsSync(path.join(extra.dir, 'work', 'ran.marker')));

  const silent = I.invokeCapability(home, 'silent-cap', { input: { name: 'ada' } });
  assert.equal(silent.status, 'failed', silent.basis);
  assert.match(silent.basis, /wrote no output at \$RCOS_OUTPUT/);
  assert.equal(silent.manifest.adapter.exit_code, 0);
});

test('kernel: a declaration RCOS cannot execute is blocked, and says exactly why', () => {
  const home = makeHome([
    fx('no-adapter-cap', { noAdapter: true }),
    fx('missing-entry-cap', { script: SCRIPTS.echo, entrypoint: 'capabilities/missing-entry-cap/adapter/absent.js' }),
    fx('not-executable-cap', { script: SCRIPTS.echo, mode: 0o644 }),
    fx('absent-contract-cap', { script: SCRIPTS.echo, contractMissing: true }),
    fx('malformed-contract-cap', { script: SCRIPTS.echo, contract: { schema: 'not-a-contract' } })
  ]);
  const cases = [
    ['no-adapter-cap', /declares no adapter/],
    ['missing-entry-cap', /entrypoint is missing/],
    ['not-executable-cap', /entrypoint is not executable/],
    ['absent-contract-cap', /declared contract is not usable: declared contract is missing/],
    ['malformed-contract-cap', /declared contract is not usable: contract\.schema/]
  ];
  for (const [id, expect] of cases) {
    const res = I.invokeCapability(home, id, { input: { name: 'ada' } });
    assert.equal(res.ok, true, id);
    assert.equal(res.status, 'blocked', id + ': ' + res.basis);
    assert.match(res.basis, expect, id);
    assert.equal(res.manifest.adapter.exit_code, null, id);
    assert.ok(!fs.existsSync(path.join(res.dir, 'work', 'ran.marker')), id + ': nothing executed');
    assert.equal(I.verifyInvocation(home, res.invocation_id).ok, true, id + ': blocked is still a sealed artifact');
  }
});

test('kernel: the adapter can refuse (exit 4) or fail (any other non-zero), and an unknown id is a refusal', () => {
  const home = makeHome([
    fx('cannot-run-cap', { script: SCRIPTS.cannotRun }),
    fx('crash-cap', { script: SCRIPTS.crash })
  ]);
  const cant = I.invokeCapability(home, 'cannot-run-cap', { input: { name: 'ada' } });
  assert.equal(cant.status, 'blocked', cant.basis);
  assert.match(cant.basis, /adapter reported it could not run \(exit 4\)/);
  assert.equal(cant.manifest.adapter.exit_code, 4);

  const crash = I.invokeCapability(home, 'crash-cap', { input: { name: 'ada' } });
  assert.equal(crash.status, 'failed', crash.basis);
  assert.match(crash.basis, /adapter exited 3/);
  assert.equal(crash.manifest.adapter.exit_code, 3);

  // A caller naming something the registry does not hold gets a structured
  // refusal, not an exception: nothing is invented for a capability that does
  // not exist, and no invocation artifact is created for it.
  const ghost = I.invokeCapability(home, 'ghost-cap', { input: {} });
  assert.equal(ghost.ok, false);
  assert.match(ghost.error, /no such capability 'ghost-cap' in the registry/);
  assert.equal(I.listInvocations(home).length, 2, 'no artifact for a capability that does not exist');

  const yolo = I.invokeCapability(home, 'crash-cap', { input: {}, mode: 'yolo' });
  assert.equal(yolo.ok, false);
  assert.match(yolo.error, /unknown mode 'yolo'/);
});

test('kernel: invocations are write-once, and an edited artifact is detectable', () => {
  const home = makeHome([fx('echo-cap', { script: SCRIPTS.echo, contract: CONTRACT })]);
  const id = 'inv_20260917T120000Z-abcdef';
  const first = I.invokeCapability(home, 'echo-cap', { input: { name: 'ada' }, invocationId: id });
  assert.equal(first.invocation_id, id);
  assert.throws(() => I.invokeCapability(home, 'echo-cap', { input: { name: 'ada' }, invocationId: id }),
    /already exists — invocations are write-once and never rewritten/);
  assert.throws(() => I.invokeCapability(home, 'echo-cap', { input: { name: 'ada' }, invocationId: 'nope' }),
    /bad invocation id/);

  fs.appendFileSync(path.join(first.dir, 'stdout.txt'), 'tampered\n');
  let v = I.verifyInvocation(home, id);
  assert.equal(v.ok, false);
  assert.ok(v.problems.some((p) => /artifact changed since the invocation was written: stdout\.txt/.test(p)), v.problems.join('; '));

  fs.writeFileSync(path.join(first.dir, 'stray.json'), '{}\n');
  v = I.verifyInvocation(home, id);
  assert.ok(v.problems.some((p) => /present but not listed in the manifest: stray\.json/.test(p)), v.problems.join('; '));

  const mPath = path.join(first.dir, 'manifest.json');
  const m = JSON.parse(fs.readFileSync(mPath, 'utf8'));
  m.basis = 'looks fine to me';
  fs.writeFileSync(mPath, JSON.stringify(m, null, 2) + '\n');
  v = I.verifyInvocation(home, id);
  assert.ok(v.problems.some((p) => /manifest integrity mismatch/.test(p)), v.problems.join('; '));

  const gone = I.verifyInvocation(home, 'inv_20260917T120000Z-ffffff');
  assert.equal(gone.ok, false);
  assert.deepEqual(gone.problems, ['invocation not found: inv_20260917T120000Z-ffffff']);
});

test('kernel: executing a capability moves no reuse counter and no registry byte', () => {
  const home = makeHome([fx('echo-cap', { script: SCRIPTS.echo, contract: CONTRACT, reuse_count: 3 })]);
  const regPath = path.join(home, 'registry', 'capability-registry.json');
  const before = fs.readFileSync(regPath);
  const res = I.invokeCapability(home, 'echo-cap', { input: { name: 'ada' } });
  assert.equal(res.status, 'completed', res.basis);
  assert.ok(fs.readFileSync(regPath).equals(before), 'the registry is byte-identical after a run');
  assert.equal(JSON.parse(fs.readFileSync(regPath, 'utf8')).capabilities[0].reuse_count, 3);
  assert.ok(!fs.existsSync(path.join(home, 'traces')), 'execution writes no trace — reuse semantics belong to `rcos reuse`');
});

test('kernel: registry status decides which modes may invoke', () => {
  const home = makeHome([
    fx('candidate-cap', { status: 'candidate', script: SCRIPTS.echo, contract: CONTRACT }),
    fx('retired-cap', { status: 'retired', script: SCRIPTS.echo, contract: CONTRACT })
  ]);
  const normal = I.invokeCapability(home, 'candidate-cap', { input: { name: 'ada' } });
  assert.equal(normal.status, 'blocked', normal.basis);
  assert.match(normal.basis, /not eligible for normal invocation/);

  const evalMode = I.invokeCapability(home, 'candidate-cap', { input: { name: 'ada' }, mode: 'eval' });
  assert.equal(evalMode.status, 'completed', evalMode.basis);
  assert.equal(evalMode.manifest.mode, 'eval');
  assert.equal(evalMode.manifest.registry_status, 'candidate');

  const retiredEval = I.invokeCapability(home, 'retired-cap', { input: { name: 'ada' }, mode: 'eval' });
  assert.equal(retiredEval.status, 'blocked', retiredEval.basis);
  assert.match(retiredEval.basis, /not eligible for eval invocation/);

  const forensic = I.invokeCapability(home, 'retired-cap', {
    input: { name: 'ada' }, mode: 'forensic', forensicReason: 'audit 2026-09-17'
  });
  assert.equal(forensic.status, 'completed', forensic.basis);
  assert.equal(forensic.manifest.mode, 'forensic');
  assert.equal(forensic.manifest.forensic_reason, 'audit 2026-09-17');
});

test('cli: run / invocations / invocation-verify expose the kernel, exit codes mirror the state', () => {
  const home = makeHome([
    fx('echo-cap', { script: SCRIPTS.echo, contract: CONTRACT }),
    fx('crash-cap', { script: SCRIPTS.crash }),
    fx('candidate-cap', { status: 'candidate', script: SCRIPTS.echo, contract: CONTRACT })
  ]);
  const good = path.join(home, 'good.json');
  const empty = path.join(home, 'empty.json');
  fs.writeFileSync(good, JSON.stringify({ name: 'ada' }) + '\n');
  fs.writeFileSync(empty, '{}\n');

  const ok = run(home, 'run', 'echo-cap', '--input', good);
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
  assert.match(ok.stdout, /^inv_\d{8}T\d{6}Z-[0-9a-f]{6}\tcompleted\techo-cap\t0$/m);
  assert.match(ok.stdout, /basis: adapter exited 0/);
  const id = ok.stdout.split('\t')[0];

  const unreadable = run(home, 'run', 'echo-cap', '--input', path.join(home, 'nope.json'));
  assert.equal(unreadable.status, 2);
  assert.match(unreadable.stderr, /--input is not readable JSON/);

  const rejected = run(home, 'run', 'echo-cap', '--input', empty);
  assert.equal(rejected.status, 2);
  assert.match(rejected.stdout, /\trejected\techo-cap\t/);

  const failed = run(home, 'run', 'crash-cap', '--input', good);
  assert.equal(failed.status, 3);
  assert.match(failed.stdout, /\tfailed\tcrash-cap\t3$/m);

  const blocked = run(home, 'run', 'candidate-cap', '--input', good);
  assert.equal(blocked.status, 4);
  assert.match(blocked.stdout, /not eligible for normal invocation/);

  const ghost = run(home, 'run', 'ghost-cap', '--input', good);
  assert.equal(ghost.status, 2);
  assert.match(ghost.stderr, /no such capability 'ghost-cap' in the registry/);

  const listed = run(home, 'invocations');
  assert.equal(listed.status, 0);
  const rows = listed.stdout.trim().split('\n').filter((l) => l.trim());
  assert.equal(rows.length, 4);
  for (const row of rows) assert.equal(row.split('\t').length, 5, row);

  const verified = run(home, 'invocation-verify', '--invocation', id);
  assert.equal(verified.status, 0);
  assert.match(verified.stdout, /verified \(\d+ artifacts re-hashed\)/);

  fs.appendFileSync(path.join(home, 'invocations', id, 'output.json'), ' ');
  const tampered = run(home, 'invocation-verify', '--invocation', id);
  assert.equal(tampered.status, 3);
  assert.match(tampered.stdout, /PROBLEM artifact changed since the invocation was written: output\.json/);
});
