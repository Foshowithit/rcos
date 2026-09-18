#!/usr/bin/env node
'use strict';
// Adapter for the preview-server-verify capability.
//
// Domain work: run the frozen checker that already exists beside this file
// (adapter/serve_verify.py — the artifact this entry's historical run_ids name)
// once per probe, and record what it said VERBATIM. The wrapper forms no
// opinion about whether the bytes were right: that is the gates' job, and the
// checker's own exit code is the thing they read.
//
// It never modifies, re-implements or patches the checker. Its sha256 goes into
// the observation so the new receipt names the exact artifact identity it
// exercised, which is what lets a human line this receipt up against the
// historical asserted runs for the same script.
//
// Kernel interface (lib/invocation.js): the input document is at $RCOS_INPUT,
// the result goes to $RCOS_OUTPUT, supporting files go under $RCOS_EVIDENCE_DIR.
// Exit 4 = could not run; exit 0 = ran and wrote a result.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const inputPath = process.env.RCOS_INPUT;
const outputPath = process.env.RCOS_OUTPUT;
const evidenceDir = process.env.RCOS_EVIDENCE_DIR;
const home = process.env.RCOS_HOME;
const work = process.cwd();

function cannotRun(msg) { console.error(msg); process.exit(4); }

if (!inputPath || !outputPath || !evidenceDir) {
  cannotRun('adapter needs RCOS_INPUT, RCOS_OUTPUT and RCOS_EVIDENCE_DIR in the environment');
}

const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
if (typeof input.docroot !== 'string' || !Array.isArray(input.probes) || input.probes.length === 0) {
  cannotRun('input needs docroot and a non-empty probes array');
}
const docroot = path.resolve(input.docroot);
if (!fs.existsSync(docroot) || !fs.statSync(docroot).isDirectory()) {
  cannotRun('docroot is not a directory: ' + docroot);
}

const checker = path.join(__dirname, 'serve_verify.py');
if (!fs.existsSync(checker)) cannotRun('checker is missing beside the adapter: ' + checker);

const checkerSha = crypto.createHash('sha256').update(fs.readFileSync(checker)).digest('hex');
const checkerPath = home && checker.startsWith(home)
  ? path.relative(home, checker).split(path.sep).join('/')
  : checker;

// Per-probe wall clock. The kernel enforces the adapter's declared
// timeout_seconds around the whole invocation; this is the inner bound so one
// wedged server cannot swallow the budget of the probes behind it.
const PROBE_TIMEOUT_MS = 25000;

// The checker prints fixed, one-line-per-fact output. The parsed block is a
// convenience for the gates; the raw text is recorded beside it so a gate can
// check the parse against the bytes it came from.
function parseObserved(stdout) {
  const num = (re) => { const m = stdout.match(re); return m ? Number(m[1]) : null; };
  const hex = (re) => { const m = stdout.match(re); return m ? m[1] : null; };
  return {
    bound_port: num(/GET http:\/\/127\.0\.0\.1:(\d+)\//),
    http_status: num(/GET \S+ -> HTTP (\d{3})/),
    served_bytes: num(/-> HTTP \d{3} \((\d+) bytes\)/),
    served_sha256_prefix: hex(/^sha256 served ([0-9a-f]{16})/m),
    disk_sha256_prefix: hex(/docroot-disk ([0-9a-f]{16})/m),
    expect_sha256_prefix: hex(/^sha256 expect ([0-9a-f]{16})/m),
    teardown_port: num(/^teardown: port (\d+) refuses \(closed\)/m),
    pass_marker: /^SERVE_VERIFY_PASS$/m.test(stdout)
  };
}

function outcomeOf(exitStatus, signal) {
  if (signal) return signal === 'SIGTERM' ? 'timed_out' : 'errored';
  if (exitStatus === 0) return 'passed';
  if (exitStatus === 3) return 'caught';
  if (exitStatus === 4) return 'could_not_start';
  return 'errored';
}

const probes = [];
const spawnErrors = [];
for (const p of input.probes) {
  const argv = [checker, docroot, p.relpath];
  if (p.expect_sha256 !== undefined && p.expect_sha256 !== null) {
    argv.push('--expect-sha256', p.expect_sha256);
  }
  const startedAt = Date.now();
  const r = spawnSync('python3', argv, {
    cwd: work,
    encoding: 'utf8',
    timeout: PROBE_TIMEOUT_MS
  });
  spawnErrors.push(r.error ? p.name + ': ' + r.error.message : null);
  const stdout = r.stdout || '';
  const stderr = r.stderr || '';
  const exitStatus = typeof r.status === 'number' ? r.status : null;
  probes.push({
    name: p.name,
    relpath: p.relpath,
    expect_sha256: p.expect_sha256 === undefined ? null : p.expect_sha256,
    exit_status: exitStatus,
    signal: r.signal || null,
    outcome: outcomeOf(exitStatus, r.signal),
    duration_ms: Date.now() - startedAt,
    observed: parseObserved(stdout),
    stdout,
    stderr
  });
}

const observation = {
  schema: 'preview-server-verify-observation/1',
  docroot,
  checker: {
    path: checkerPath,
    sha256: checkerSha,
    // Read from the checker's own docstring, not from a run: the documented
    // contract is the claim, and the probes above are what actually happened.
    documented_exit_codes: [0, 3, 4]
  },
  probes
};
fs.writeFileSync(outputPath, JSON.stringify(observation, null, 2) + '\n');

// Evidence: the raw text each verdict will be computed from. The kernel hashes
// and lists these; it does not judge them.
fs.mkdirSync(evidenceDir, { recursive: true });
for (const p of probes) {
  fs.writeFileSync(path.join(evidenceDir, 'probe-' + p.name + '.stdout.txt'), p.stdout);
  fs.writeFileSync(path.join(evidenceDir, 'probe-' + p.name + '.stderr.txt'), p.stderr);
}
fs.writeFileSync(path.join(evidenceDir, 'checker.sha256'), checkerSha + '  ' + checkerPath + '\n');

// Exit 4 is reserved for "this capability could not run at all" — the
// interpreter is missing, or the checker was killed before it could report.
// A probe that exited 1 was able to run and failed, and that is a result the
// gates must see, not a block.
const anyExecuted = probes.some((p) => p.exit_status !== null);
if (!anyExecuted) {
  const detail = spawnErrors.filter(Boolean).join(' | ');
  console.error('no probe produced an exit status' + (detail ? ' — ' + detail : ''));
  process.exit(4);
}

console.log('checker sha256 ' + checkerSha.slice(0, 16) + '  ' + checkerPath);
for (const p of probes) {
  console.log('  ' + p.name + ': exit ' + p.exit_status + ' (' + p.outcome + '), http ' + p.observed.http_status +
    ', port ' + p.observed.bound_port + ', ' + p.duration_ms + 'ms');
}
process.exit(0);
