#!/usr/bin/env node
'use strict';
// Adapter for receipt-figure-render.
//
// The capability is two frozen scripts that already sit beside this file:
//
//   receipt_figures.py <registry.json> <out-dir>
//       renders fig-verdicts.png + fig-per-capability.png from the registry and
//       writes a values.json sidecar of the numbers it drew
//   check_figures.py   <registry.json> <values.json>
//       recomputes the same numbers straight from the registry through a second
//       code path and diffs them against the sidecar
//
// Neither script is modified, re-implemented, or patched here. This adapter
// chooses their arguments, runs them, and records what they did — including the
// bytes they left behind. It cannot turn a bad render into a good record: every
// value in the observation is either an argv, one of the script's own output
// streams, or a hash of a file the script wrote.
//
// Why per-case scratch directories: the renderer writes its figures into the
// out-dir it is given, so each case gets its own <work>/case-<name>/out. A case
// that names a values file produced by an earlier case reads that file through
// the same path the case declared; nothing is inferred from order.
//
// Kernel interface (lib/invocation.js): the input document is at $RCOS_INPUT,
// the result goes to $RCOS_OUTPUT, supporting files go under $RCOS_EVIDENCE_DIR.
// Exit 4 = could not run; exit 0 = ran and wrote a result.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const CASE_TIMEOUT_MS = 60000;
const FIGURE_NAMES = ['fig-verdicts.png', 'fig-per-capability.png'];
const SIDECAR_NAME = 'values.json';

function cannotRun(msg) {
  console.error(msg);
  process.exit(4);
}

function sha256(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

const HOME = process.env.RCOS_HOME || path.join(os.homedir(), 'zcode-rcos');
// The invocation kernel exports RCOS_INVOCATION_WORK_DIR (lib/invocation.js);
// RCOS_WORK_DIR belongs to the eval runner's gate children, which do not spawn
// this file. The kernel also sets the process cwd to the invocation work dir.
const WORK = process.env.RCOS_INVOCATION_WORK_DIR || process.env.RCOS_WORK_DIR;
const EVIDENCE = process.env.RCOS_EVIDENCE_DIR;
const INPUT = process.env.RCOS_INPUT;
const OUTPUT = process.env.RCOS_OUTPUT;
if (!WORK || !EVIDENCE || !INPUT || !OUTPUT) {
  cannotRun('missing kernel env (RCOS_INVOCATION_WORK_DIR/RCOS_EVIDENCE_DIR/RCOS_INPUT/RCOS_OUTPUT)');
}

const RENDERER = path.join(__dirname, 'receipt_figures.py');
const CHECKER = path.join(__dirname, 'check_figures.py');
const RENDERER_SHA = sha256(fs.readFileSync(RENDERER));
const CHECKER_SHA = sha256(fs.readFileSync(CHECKER));

// Recorded paths are invocation-relative wherever they can be, so a copied
// invocation's record still reads correctly in the copy.
function workRel(p) {
  const rel = path.relative(WORK, p);
  return rel && !rel.startsWith('..') && !path.isAbsolute(rel) ? rel.split(path.sep).join('/') : p;
}

// The frozen scripts are recorded relative to RCOS_HOME, the same way a
// capability's other files are named, so the record survives a copied home.
function homeRel(p) {
  const rel = path.relative(HOME, p);
  return rel && !rel.startsWith('..') && !path.isAbsolute(rel) ? rel.split(path.sep).join('/') : p;
}

function fileEntry(p) {
  const buf = fs.readFileSync(p);
  return { path: workRel(p), sha256: sha256(buf), bytes: buf.length };
}

// Header only: the renderer's own bytes decide the size and colour format of
// each figure, and the gate re-reads the pixels. This asks the file, not PIL.
function pngHeader(buf) {
  const sig = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (buf.length < 33) return null;
  for (let i = 0; i < sig.length; i++) if (buf[i] !== sig[i]) return null;
  if (buf.toString('latin1', 12, 16) !== 'IHDR') return null;
  return {
    width: buf.readUInt32BE(16),
    height: buf.readUInt32BE(20),
    bit_depth: buf[24],
    color_type: buf[25],
  };
}

function listFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .sort();
}

// The adapter's own count of a registry's evals, walked here so the gate can
// compare two independent counts (this one and the renderer's sidecar).
function registryFacts(p) {
  const buf = fs.readFileSync(p);
  const facts = {
    path: workRel(p),
    sha256: sha256(buf),
    bytes: buf.length,
    parsed: false,
    n_capabilities: null,
    n_evals: null,
  };
  try {
    const reg = JSON.parse(buf.toString('utf8'));
    if (Array.isArray(reg.capabilities)) {
      facts.parsed = true;
      facts.n_capabilities = reg.capabilities.length;
      facts.n_evals = reg.capabilities.reduce((n, c) => n + (Array.isArray(c.evals) ? c.evals.length : 0), 0);
    }
  } catch (e) {
    // Left unparsed on purpose: whether the scripts can read it is their call,
    // and this record must not pre-empt their answer.
  }
  return facts;
}

function outcomeOf(operation, exitStatus, signal) {
  if (signal === 'SIGTERM') return 'timed_out';
  if (operation === 'render') return exitStatus === 0 ? 'rendered' : 'errored';
  if (exitStatus === 0) return 'accepted';
  return exitStatus === 3 ? 'caught' : 'errored';
}

function runCase(c) {
  const started = Date.now();
  const caseDir = path.join(WORK, 'case-' + c.name);
  fs.mkdirSync(caseDir, { recursive: true });
  const outDir = path.join(caseDir, 'out');

  const argv = c.operation === 'render'
    ? [RENDERER, c.registry, outDir]
    : [CHECKER, c.registry, c.values];

  const res = spawnSync('python3', argv, { cwd: WORK, encoding: 'utf8', timeout: CASE_TIMEOUT_MS });
  if (res.error) cannotRun('could not start python3: ' + res.error.message);
  const duration_ms = Date.now() - started;
  const stdout = res.stdout || '';
  const stderr = res.stderr || '';
  const exit_status = typeof res.status === 'number' ? res.status : null;
  const signal = res.signal || null;

  const out_files = c.operation === 'render' ? listFiles(outDir) : [];

  const figures = [];
  const produced = [];
  if (c.operation === 'render') {
    for (const name of FIGURE_NAMES) {
      const p = path.join(outDir, name);
      if (!fs.existsSync(p)) continue;
      const buf = fs.readFileSync(p);
      produced.push({ evidenceName: name, source: p });
      figures.push({ name, path: workRel(p), sha256: sha256(buf), bytes: buf.length, png: pngHeader(buf) });
    }
  }

  let sidecar = null;
  const sidecarPath = path.join(outDir, SIDECAR_NAME);
  if (c.operation === 'render' && fs.existsSync(sidecarPath)) {
    const buf = fs.readFileSync(sidecarPath);
    let values = null;
    try {
      values = JSON.parse(buf.toString('utf8'));
    } catch (e) {
      values = null;
    }
    produced.push({ evidenceName: SIDECAR_NAME, source: sidecarPath });
    sidecar = { path: workRel(sidecarPath), sha256: sha256(buf), bytes: buf.length, values };
  }

  // The run's own copy of every stream and every produced byte, so a later
  // reader never has to trust this record or the work dir's survival.
  fs.writeFileSync(path.join(EVIDENCE, 'case-' + c.name + '.stdout.txt'), stdout);
  fs.writeFileSync(path.join(EVIDENCE, 'case-' + c.name + '.stderr.txt'), stderr);
  fs.writeFileSync(path.join(EVIDENCE, 'case-' + c.name + '.argv.json'),
    JSON.stringify({ argv, cwd: WORK, exit_status, signal, duration_ms }, null, 2) + '\n');
  for (const p of produced) {
    fs.copyFileSync(p.source, path.join(EVIDENCE, 'case-' + c.name + '.' + p.evidenceName));
  }

  return {
    name: c.name,
    operation: c.operation,
    registry: registryFacts(c.registry),
    input_values: c.operation === 'check' ? fileEntry(c.values) : null,
    argv,
    exit_status,
    signal,
    outcome: outcomeOf(c.operation, exit_status, signal),
    duration_ms,
    stdout,
    stderr,
    fail_lines: [...stdout.matchAll(/^FAIL (.*)$/gm)].map((m) => m[1]),
    out_files,
    figures,
    sidecar,
  };
}

let input;
try {
  input = JSON.parse(fs.readFileSync(INPUT, 'utf8'));
} catch (e) {
  cannotRun('could not read $RCOS_INPUT as JSON: ' + e.message);
}

// Cross-field rules the contract's schema subset cannot express. Reported as
// exit 4: this is a request the capability cannot carry out, not a finding.
const seen = new Set();
for (const c of input.cases) {
  if (seen.has(c.name)) cannotRun('duplicate case name: ' + c.name);
  seen.add(c.name);
  if (c.operation === 'check' && typeof c.values !== 'string') {
    cannotRun('case ' + c.name + ': operation=check requires values');
  }
  if (c.operation === 'render' && c.values !== undefined) {
    cannotRun('case ' + c.name + ': operation=render must not name values');
  }
  if (!fs.existsSync(c.registry)) cannotRun('case ' + c.name + ': registry does not exist: ' + c.registry);
  if (typeof c.values === 'string' && !fs.existsSync(c.values)) {
    cannotRun('case ' + c.name + ': values does not exist: ' + c.values);
  }
}

fs.writeFileSync(path.join(EVIDENCE, 'frozen.sha256'),
  RENDERER_SHA + '  ' + RENDERER + '\n' + CHECKER_SHA + '  ' + CHECKER + '\n');

const cases = input.cases.map(runCase);

const observation = {
  schema: 'receipt-figure-render-observation/1',
  frozen: {
    renderer: {
      path: homeRel(RENDERER),
      sha256: RENDERER_SHA,
      usage: 'receipt_figures.py <registry.json> <out-dir>',
      documented_exit_codes: null,
    },
    checker: {
      path: homeRel(CHECKER),
      sha256: CHECKER_SHA,
      usage: 'check_figures.py <registry.json> <values.json>',
      documented_exit_codes: [0, 3],
    },
  },
  cases,
};

fs.writeFileSync(OUTPUT, JSON.stringify(observation, null, 2) + '\n');

for (const c of cases) {
  console.log(c.name + ' [' + c.operation + '] exit=' + String(c.exit_status) +
    ' outcome=' + c.outcome + ' figures=' + c.figures.length +
    ' sidecar=' + (c.sidecar ? 'yes' : 'no') +
    (c.fail_lines.length ? ' fail_lines=' + c.fail_lines.length : ''));
}
console.log('observed ' + cases.length + ' cases (renderer ' + RENDERER_SHA.slice(0, 12) +
  ', checker ' + CHECKER_SHA.slice(0, 12) + ')');
process.exit(0);
