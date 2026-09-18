'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const BIN = path.join(__dirname, '..', 'bin', 'rcos');
const REPO = path.join(__dirname, '..');
const SEED = path.join(REPO, 'registry', 'capability-registry.json');
const LEDGER_FIXTURE = path.join(REPO, 'evals', 'reuse-ledger-invariant-v1', 'fixtures', 'seed-registry.json');
const ER = require('../lib/evalrunner');
const R = require('../lib/registry');

// A home needs the capability dirs, not just the registry: a declared adapter is
// executable only if its entrypoint resolves under the home, and the /2 packages
// invoke the registered capability through the kernel.
function installCapabilities(home) {
  fs.cpSync(path.join(REPO, 'capabilities'), path.join(home, 'capabilities'), { recursive: true });
}

function makeHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-evalrunner-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  fs.copyFileSync(SEED, path.join(home, 'registry', 'capability-registry.json'));
  fs.mkdirSync(path.join(home, 'evals'), { recursive: true });
  installCapabilities(home);
  return home;
}

// Sandbox whose registry is the eval fixture (one promoted capability, zero
// reuse) — lets the submit path be exercised without touching the real registry.
// The /2 package names a REGISTERED capability to invoke, so the home carries
// that capability's real declaration, taken from the live registry rather than
// duplicated here: what the test pins is that the declaration RCOS ships is
// executable, not a copy of it.
function makeFixtureHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'rcos-evalrunner-fixture-'));
  fs.mkdirSync(path.join(home, 'registry'), { recursive: true });
  const fixture = JSON.parse(fs.readFileSync(LEDGER_FIXTURE, 'utf8'));
  const live = JSON.parse(fs.readFileSync(SEED, 'utf8')).capabilities.find((c) => c.id === 'reuse-ledger');
  fixture.capabilities.push(Object.assign({}, live, { evals: [], reuse_count: 0, last_eval: null }));
  fs.writeFileSync(path.join(home, 'registry', 'capability-registry.json'), JSON.stringify(fixture, null, 2) + '\n');
  fs.mkdirSync(path.join(home, 'evals'), { recursive: true });
  installCapabilities(home);
  return home;
}

function installEval(home, id, spec, fixtures) {
  const dir = path.join(home, 'evals', id);
  fs.mkdirSync(path.join(dir, 'fixtures'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'eval.json'), JSON.stringify(spec, null, 2) + '\n');
  for (const [name, body] of Object.entries(fixtures || {})) {
    fs.writeFileSync(path.join(dir, 'fixtures', name), body);
  }
  return dir;
}

function installRealEval(home, id) {
  fs.cpSync(path.join(REPO, 'evals', id), path.join(home, 'evals', id), { recursive: true });
}

// The kernel-invariant package names a capability the fixture registry does not
// hold, so `--submit` (correctly) refuses it before spending a run. The
// submit-path tests retarget a copy to see that refusal.
function installRetargetedEval(home, id, capabilityId) {
  installRealEval(home, id);
  const p = path.join(home, 'evals', id, 'eval.json');
  const spec = JSON.parse(fs.readFileSync(p, 'utf8'));
  spec.capability_id = capabilityId;
  fs.writeFileSync(p, JSON.stringify(spec, null, 2) + '\n');
}

function run(home, ...argv) {
  const r = spawnSync(BIN, argv, { env: { ...process.env, RCOS_HOME: home }, encoding: 'utf8' });
  return { status: r.status, stdout: r.stdout, stderr: r.stderr };
}

function minimalSpec(id, over) {
  return Object.assign({
    schema: 'rcos-eval/1',
    eval_id: id,
    capability_id: 'fixture-cap',
    adapter: { argv: ['node', '-e', 'process.exit(0)'] },
    fixtures: [],
    gates: [{ id: 'g', type: 'deterministic', argv: ['node', '-e', 'process.exit(0)'], required: true }]
  }, over);
}

test('makeRunId / isRunId: sortable, collision-resistant, strict format', () => {
  const id = ER.makeRunId(new Date('2026-09-17T21:14:12Z'));
  assert.match(id, /^20260917T211412Z-[0-9a-f]{6}$/);
  assert.ok(ER.isRunId(id));
  assert.ok(!ER.isRunId('2026-09-17T21:14:12Z-abc'));
  assert.notEqual(ER.makeRunId(new Date(0)), ER.makeRunId(new Date(0)));
});

test('validateEvalSpec refuses packages that could ship without passing anything', () => {
  const bad = [
    [minimalSpec('x', { schema: 'nope' }), /schema/],
    [minimalSpec('x', { eval_id: 'y' }), /directory name/],
    [minimalSpec('x', { adapter: { argv: [] } }), /adapter\.argv/],
    [minimalSpec('x', { gates: [] }), /gates: required non-empty/],
    [minimalSpec('x', { gates: [{ id: 'g', type: 'deterministic', argv: ['node'], required: false }] }), /at least one gate must be required/],
    [minimalSpec('x', { gates: [{ id: 'g', type: 'vibes', argv: ['node'] }] }), /type: must be one of/],
    [minimalSpec('x', { gates: [{ id: 'g', type: 'deterministic', argv: ['node'] }, { id: 'g', type: 'deterministic', argv: ['node'] }] }), /duplicate gate id/]
  ];
  for (const [spec, re] of bad) {
    const errs = ER.validateEvalSpec(spec, 'x');
    assert.ok(errs.some((e) => re.test(e)), re + ' not matched by: ' + errs.join(' | '));
  }
  assert.deepEqual(ER.validateEvalSpec(minimalSpec('x'), 'x'), []);
});

test('loadEvalPackage: missing package, missing fixture, and bad JSON are distinct refusals', () => {
  const home = makeHome();
  assert.throws(() => ER.loadEvalPackage(home, 'nope'), /no eval package/);
  installEval(home, 'broken', minimalSpec('broken', { fixtures: ['absent.txt'] }));
  assert.throws(() => ER.loadEvalPackage(home, 'broken'), /fixture missing/);
  fs.writeFileSync(path.join(home, 'evals', 'broken', 'eval.json'), '{not json');
  assert.throws(() => ER.loadEvalPackage(home, 'broken'), /not valid JSON/);
});

// The verdict is a pure function of adapter outcome + gate statuses. No caller
// may pass one in — this is the non-negotiable from the Core 1.0 ruling.
test('deriveVerdict: adapter outcome and gate results fully determine the verdict', () => {
  const ok = { status: 'ok' };
  const g = (id, status, required = true) => ({ id, status, required });
  assert.equal(ER.deriveVerdict(ok, [g('a', 'pass'), g('b', 'pass')]).verdict, 'ship');
  assert.equal(ER.deriveVerdict(ok, [g('a', 'pass'), g('b', 'fail')]).verdict, 'fix');
  assert.equal(ER.deriveVerdict(ok, [g('a', 'pass'), g('b', 'fail', false)]).verdict, 'ship');
  assert.equal(ER.deriveVerdict(ok, [g('a', 'pass'), g('b', 'blocked')]).verdict, 'blocked');
  assert.equal(ER.deriveVerdict(ok, [g('a', 'pass'), g('b', 'error')]).verdict, 'blocked');
  assert.equal(ER.deriveVerdict({ status: 'failed', reason: 'adapter exited 1' }, [g('a', 'blocked')]).verdict, 'blocked');
  assert.equal(ER.deriveVerdict({ status: 'blocked', reason: 'prereq' }, []).verdict, 'blocked');
  assert.match(ER.deriveVerdict(ok, [g('a', 'pass'), g('b', 'fail')]).basis, /b/);
});

test('eval-run: fix and blocked verdicts come from exit codes, and exit codes mirror them', () => {
  const home = makeHome();
  installEval(home, 'pkg-fix', minimalSpec('pkg-fix', {
    gates: [{ id: 'fails', type: 'deterministic', argv: ['node', '-e', 'process.exit(3)'], required: true }]
  }));
  installEval(home, 'pkg-blocked', minimalSpec('pkg-blocked', {
    adapter: { argv: ['node', '-e', 'process.exit(4)'] }
  }));
  installEval(home, 'pkg-error', minimalSpec('pkg-error', {
    gates: [{ id: 'crashes', type: 'deterministic', argv: ['node', '-e', 'process.exit(1)'], required: true }]
  }));
  installEval(home, 'pkg-optional-fail', minimalSpec('pkg-optional-fail', {
    gates: [
      { id: 'must', type: 'deterministic', argv: ['node', '-e', 'process.exit(0)'], required: true },
      { id: 'nice', type: 'deterministic', argv: ['node', '-e', 'process.exit(3)'], required: false }
    ]
  }));

  const fix = run(home, 'eval-run', '--eval', 'pkg-fix');
  assert.equal(fix.status, 3);
  assert.match(fix.stdout, /fix — 1 of 1 required gates fail: fails/);

  const blocked = run(home, 'eval-run', '--eval', 'pkg-blocked');
  assert.equal(blocked.status, 4);
  assert.match(blocked.stdout, /blocked — adapter could not execute/);

  // A crashing gate is NOT a failed check — the evaluation could not establish
  // a result, which is blocked, not fix.
  const err = run(home, 'eval-run', '--eval', 'pkg-error');
  assert.equal(err.status, 4);
  assert.match(err.stdout, /blocked — evaluation could not establish a result: crashes \(error\)/);

  const opt = run(home, 'eval-run', '--eval', 'pkg-optional-fail');
  assert.equal(opt.status, 0);
  assert.match(opt.stdout, /ship — all 1 required gates pass/);

  // When the adapter never executed, gates are recorded as not-run, not silently dropped.
  const runId = blocked.stdout.match(/run (\S+):/)[1];
  const checks = JSON.parse(fs.readFileSync(path.join(home, 'runs', runId, 'checks.json'), 'utf8'));
  assert.equal(checks.gates[0].status, 'blocked');
  assert.match(checks.gates[0].note, /not run/);
});

test('eval-run: a run directory is immutable, sealed, and refuses to be rewritten', () => {
  const home = makeHome();
  installRealEval(home, 'reuse-ledger-invariant-v1');
  const res = run(home, 'eval-run', '--eval', 'reuse-ledger-invariant-v1');
  assert.equal(res.status, 0, res.stdout + res.stderr);
  const runId = res.stdout.match(/run (\S+):/)[1];
  const dir = path.join(home, 'runs', runId);
  for (const f of ['manifest.json', 'input.json', 'output.json', 'checks.json', 'receipt.json']) {
    assert.ok(fs.existsSync(path.join(dir, f)), f + ' written');
  }
  const receipt = JSON.parse(fs.readFileSync(path.join(dir, 'receipt.json'), 'utf8'));
  assert.equal(receipt.verdict, 'ship');
  assert.equal(receipt.schema, ER.RECEIPT_SCHEMA);
  assert.ok(receipt.artifacts.length >= 5, 'receipt seals the run');
  assert.equal(receipt.gates.filter((g) => g.status === 'pass').length, 4);

  assert.throws(() => ER.runEval(home, 'reuse-ledger-invariant-v1', { runId }), /immutable and never rewritten/);
  assert.equal(run(home, 'eval-verify', '--run', runId).status, 0);

  fs.appendFileSync(path.join(dir, 'checks.json'), '\n');
  const tampered = run(home, 'eval-verify', '--run', runId);
  assert.equal(tampered.status, 3);
  assert.match(tampered.stdout, /MISMATCH checks.json: sha256 mismatch/);

  fs.writeFileSync(path.join(dir, 'evidence', 'outputs', 'planted.txt'), 'not in the receipt\n');
  const planted = run(home, 'eval-verify', '--run', runId);
  assert.equal(planted.status, 3);
  assert.match(planted.stdout, /not listed in receipt/);
});

test('eval-run --submit: the run is the evidence, provenance is executed, reuse does NOT move', () => {
  const home = makeFixtureHome();
  installRealEval(home, 'reuse-ledger-invariant-v1');
  const res = run(home, 'eval-run', '--eval', 'reuse-ledger-invariant-v1', '--submit', '--task', 't-exec-1');
  assert.equal(res.status, 0, res.stdout + res.stderr);
  assert.match(res.stdout, /provenance executed/);
  assert.match(res.stdout, /reuse_count unchanged/);
  const runId = res.stdout.match(/run (\S+):/)[1];

  // The run reached the capability through the invocation kernel: the receipt
  // names the invocation, and that invocation is a sealed artifact of its own.
  const receipt = JSON.parse(fs.readFileSync(path.join(home, 'runs', runId, 'receipt.json'), 'utf8'));
  assert.equal(receipt.capability_id, 'reuse-ledger');
  assert.equal(receipt.invocation.status, 'completed');
  assert.ok(fs.existsSync(path.join(home, receipt.invocation.dir, 'manifest.json')), 'invocation artifact written');

  const reg = JSON.parse(fs.readFileSync(path.join(home, 'registry', 'capability-registry.json'), 'utf8'));
  const cap = reg.capabilities.find((c) => c.id === 'reuse-ledger');
  const submitted = cap.evals.find((e) => e.task_id === 't-exec-1');
  assert.equal(submitted.verdict, 'ship');
  assert.equal(submitted.run_id, runId);
  assert.equal(submitted.provenance, 'executed');
  // The probe capability the eval's own fixture registry carries is untouched:
  // an eval run records evidence about the capability it evaluated, and about
  // nothing else the sandbox happened to mention.
  const probe = reg.capabilities.find((c) => c.id === 'fixture-cap');
  assert.equal(probe.evals.find((e) => e.task_id === 't-seed-1').provenance, 'asserted');
  assert.equal(probe.evals.length, 2);
  // An eval run is evidence about a capability, not proof it was invoked: the
  // trace records the verdict with source=null and the reuse cache stays put.
  assert.equal(cap.reuse_count, 0);

  const traces = fs.readFileSync(path.join(home, 'traces', 'traces.jsonl'), 'utf8')
    .split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l));
  assert.equal(traces.length, 1);
  assert.equal(traces[0].source, null);
  assert.equal(traces[0].task_id, 't-exec-1');
});

test('eval-run --submit refuses an unknown capability before spending a run', () => {
  const home = makeFixtureHome();
  installRetargetedEval(home, 'reuse-ledger-invariant-v1', 'ghost-cap');
  const missing = run(home, 'eval-run', '--eval', 'reuse-ledger-invariant-v1', '--submit', '--task', 't-ghost');
  assert.equal(missing.status, 2);
  assert.match(missing.stderr, /unknown capability 'ghost-cap'/);
  assert.ok(!fs.existsSync(path.join(home, 'runs')) || fs.readdirSync(path.join(home, 'runs')).length === 0,
    'no run dir for a rejected submit');
  // Without --submit the package still runs — but the registry is load-bearing
  // for evaluation too: a capability that is not registered cannot be invoked,
  // so the evaluation is BLOCKED rather than quietly passing. The refusal comes
  // from the eligibility engine, which runs before the kernel: a ghost never
  // reaches execution at all.
  const ghost = run(home, 'eval-run', '--eval', 'reuse-ledger-invariant-v1');
  assert.equal(ghost.status, 4);
  assert.match(ghost.stdout, /blocked — adapter could not execute: eligibility could not be decided: no such capability 'ghost-cap' in the registry/);
});

test('provenance: manual eval-submit is asserted; audit warns while promoted caps are asserted-only', () => {
  const home = makeFixtureHome();
  const before = run(home, 'audit');
  assert.match(before.stdout, /1\/1 promoted capabilities rest entirely on asserted evals/);

  assert.equal(run(home, 'eval-submit', '--id', 'fixture-cap', '--task', 't-manual',
    '--verdict', 'ship', '--run', '20260917T000000Z-cccccc').status, 0);
  const reg = JSON.parse(fs.readFileSync(path.join(home, 'registry', 'capability-registry.json'), 'utf8'));
  const manual = reg.capabilities[0].evals.find((e) => e.task_id === 't-manual');
  assert.equal(manual.provenance, 'asserted');

  const mid = run(home, 'audit');
  assert.match(mid.stdout, /1\/1 promoted capabilities rest entirely on asserted evals/);

  // Only an EXECUTED eval clears the warning, and only for the capability it
  // actually evaluated: the ratio counts promoted capabilities, so evaluating a
  // candidate leaves it exactly where it was.
  installEval(home, 'pkg-exec-fixture', minimalSpec('pkg-exec-fixture'));
  assert.equal(run(home, 'eval-run', '--eval', 'pkg-exec-fixture', '--submit', '--task', 't-exec-9').status, 0);
  const after = run(home, 'audit');
  assert.ok(!/rest entirely on asserted evals/.test(after.stdout), 'warning clears once an executed eval exists');

  installRealEval(home, 'reuse-ledger-invariant-v1');
  assert.equal(run(home, 'eval-run', '--eval', 'reuse-ledger-invariant-v1', '--submit', '--task', 't-exec-10').status, 0);
  const reg2 = JSON.parse(fs.readFileSync(path.join(home, 'registry', 'capability-registry.json'), 'utf8'));
  const candidate = reg2.capabilities.find((c) => c.id === 'reuse-ledger');
  assert.equal(candidate.evals.find((e) => e.task_id === 't-exec-10').provenance, 'executed');
  assert.equal(reg2.capabilities.find((c) => c.id === 'fixture-cap').evals.filter((e) => e.provenance === 'executed').length, 1);

  // Provenance is a closed vocabulary — a made-up value fails validation.
  const bad = JSON.parse(fs.readFileSync(path.join(home, 'registry', 'capability-registry.json'), 'utf8'));
  bad.capabilities[0].evals[0].provenance = 'probably';
  assert.throws(() => R.saveRegistry(home, bad), /provenance/);
});

test('evals / runs: listing surfaces packages, invalid packages, and run history', () => {
  const home = makeHome();
  installRealEval(home, 'reuse-ledger-invariant-v1');
  installEval(home, 'broken', minimalSpec('broken', { gates: [] }));
  const evals = run(home, 'evals');
  assert.equal(evals.status, 0);
  assert.match(evals.stdout, /reuse-ledger-invariant-v1\treuse-ledger\t4 gates\t1 fixtures/);
  assert.match(evals.stdout, /INVALID\tbroken/);

  assert.match(run(home, 'runs').stdout, /no runs yet/);
  assert.equal(run(home, 'eval-run', '--eval', 'reuse-ledger-invariant-v1').status, 0);
  const runs = run(home, 'runs');
  assert.match(runs.stdout, /\tship\treuse-ledger-invariant-v1\treuse-ledger\t/);
  const asJson = JSON.parse(run(home, 'runs', '--json').stdout);
  assert.equal(asJson.length, 1);
  assert.equal(asJson[0].verdict, 'ship');
});
