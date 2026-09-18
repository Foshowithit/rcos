#!/usr/bin/env node
'use strict';
// Deterministic gates for evals/qr-camo-embed-grounding-v1.
//
// One gate id per argv tail. Every gate judges the adapter's observation
// ($RCOS_INVOCATION_DIR/output.json) against the evidence the run itself left
// behind — the invocation's evidence copies, the run's input.json and fixture
// copies, and the pinned bytes committed in this package and the capability —
// never against a narrative. Where a gate needs pixels it re-measures them
// through the pinned helper scripts beside this file (measure_blend.py,
// stress_ladder.py, decode_controls.py), spawned through the interpreter the
// cases actually recorded: $RCOS_QR_PYTHON, else evidence/qr-venv/bin/python
// under RCOS_HOME. The helpers replicate the frozen script's own canvas and
// ladder code rather than trusting it.
//
// Exit codes: 0 = gate PASSED, 3 = gate FAILED, 4 = blocked (the gate could
// not judge — missing kernel env, unreadable observation, unknown gate id, or
// a helper that could not run). A blocked gate is never a pass: the eval
// runner records it and the receipt cannot ship on a blocked run.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const id = process.argv[2];
const invocationDir = process.env.RCOS_INVOCATION_DIR || null;
const runDir = process.env.RCOS_RUN_DIR || null;
const home = process.env.RCOS_HOME || null;
const workDir = process.env.RCOS_WORK_DIR || null;
const evalDir = process.env.RCOS_EVAL_DIR || null;
const invWork = invocationDir ? path.join(invocationDir, 'work') : null;

// ---------- pins (captured from executed runs before this package existed) ----------
const SCRIPT_REL = 'capabilities/qr-camo-embed/adapter/make_header_v2.py';
const SCRIPT_SHA = '8dc1960468b002dde416d8f27fa5f07fb97febcd015198674fc3f92c4550bdeb';
const ADAPTER_SHA = 'bb9e0ce1806d1890a104ef7315621f079f620fd21e3d3ea8affe553efdcb90b5';
const CONTRACT_SHA = 'b7296d29c2a0034bce1ff614221c8b54eb5f44b4a8f1de0c1aeb0ead18317bc9';
const MEASURE_SHA = 'aaf605a51d0a806b9156151ba76293aa2692191a5f67dc776cd65407c9462449';
const LADDER_SHA = '4f1f468939c95b0743debab689d1a655c8597a69d5c923eb30d0cde3736a4f8e';
const DECODE_SHA = 'b03f094485d21d0d1db7bd48df60f42fd86cb83d6e6c264be9a1a91822e9a584';
const PREFIX_SHA = '110a747215f68395a363eaa6e1ecdd4f85bf2db34c7bd557473c0a087c3b27cc';

const FIXTURES = {
  'bearing-camo-src.png': { sha256: 'ec7f944766a3eda36d087657bf3647dd483d98782de68a09df392aaa6386300d', bytes: 2574318 },
  'dark-camo-src.png': { sha256: 'd48a416011b5c76ab768b393d1256bc57e9f0249be5c8d4aede4ddccc24b6d97', bytes: 3177670 },
  'pale-camo-src.png': { sha256: '14b0c0672dc8912210bf4d6dcb6b29c456934e7fbc7acf0682db7f67cfccdf68', bytes: 354418 },
  'oracle-ship-header.png': { sha256: '24de696df0bad3f0bab972eabbb715440fca8a666cbf403a61ae8e88214b8b6d', bytes: 868866 },
  'oracle-pale-header.png': { sha256: 'f8824bc41ca52808beacd341696e4cc94178752fe625d6e31b6bc754acfcc623', bytes: 428910 },
  'muse-eval6-ship.log': { sha256: 'd8f3e7c791ae99b5fa2e0d514ff6af0a2163c0777dd36ff45abb0bd0e01d5f6f', bytes: 387 },
  'muse-eval5-fail.log': { sha256: '5f99e44383c39a25aee20274bbb2af472ee7edd7d4dd7cf90ccaad760f19b019', bytes: 622 },
  'prefix-orientation-make_header_v2.py': { sha256: PREFIX_SHA, bytes: 5554 },
};

const ORACLE_SHIP_SHA = FIXTURES['oracle-ship-header.png'].sha256;
const ORACLE_PALE_SHA = FIXTURES['oracle-pale-header.png'].sha256;
const VARIANT_OUT_SHA = '7c5e75dd3fe63034739485f39d052ee5eced10ae7974b37de39197b99357e23f';

const DEPS_PINS = { cv2: '4.13.0', qrcode: '8.2', zxingcpp: '3.1.1', numpy: '2.4.6', pillow: '10.4.0' };
const PYTHON_PIN = '3.14.7';
const PROBE_SNIPPET =
  "import json,sys,cv2,numpy,PIL;" +
  "from importlib.metadata import version as _v;" +
  "print(json.dumps({'cv2':cv2.__version__,'qrcode':_v('qrcode')," +
  "'zxingcpp':_v('zxing-cpp'),'numpy':numpy.__version__," +
  "'pillow':PIL.__version__,'python':sys.version.split()[0]}))";

// The script's stdout is deterministic given (cover, url): these are the exact
// streams the executed runs produced, pinned line for line.
const ALL_PASS_LINE = 'ALL SCANS PASS (stress ladder at minimal visible contrast)';
const SHIP_STDOUT = [
  'QR version 3, 37x37 modules',
  'placed at (1065,60), smoothness score 25.5',
  'adaptive contrast: dark_gain top 0.8 (v1 used 0.52 flat)',
  ALL_PASS_LINE,
].join('\n') + '\n';
const PALE_STDOUT = [
  'QR version 3, 37x37 modules',
  'placed at (905,20), smoothness score 32.2',
  'adaptive contrast: dark_gain top 0.68 (v1 used 0.52 flat)',
  ALL_PASS_LINE,
].join('\n') + '\n';
const VARIANT_STDOUT = SHIP_STDOUT; // same cover, same 37x37 payload box, same placement
const DARK_STDOUT = [
  'QR version 3, 37x37 modules',
  'placed at (1065,20), smoothness score 40.9',
  'adaptive contrast: dark_gain top 0.8 (v1 used 0.52 flat)',
  ALL_PASS_LINE,
].join('\n') + '\n';
const OVERFLOW_STDOUT = 'QR version 5, 45x45 modules\n';
const OVERFLOW_STDERR = 'payload too long: QR 495px does not fit the 1500x500 placement window\n';
const REFUSAL_LINE = 'no contrast level survived the stress ladder — payload or cover unusable';

// ---------- small helpers ----------
function sha256(buf) { return crypto.createHash('sha256').update(buf).digest('hex'); }
function hashFile(p) { return sha256(fs.readFileSync(p)); }
function realOr(p) { try { return fs.realpathSync(p); } catch (e) { return p; } }
function homePath(rel) {
  if (!home || typeof rel !== 'string' || rel === '') return null;
  return path.isAbsolute(rel) ? rel : path.join(home, rel.replace(/^[/\\]+/, ''));
}
function runCopyOf(name) { return workDir ? path.join(workDir, name) : null; }
function fixturePath(name) {
  return evalDir ? path.join(evalDir, 'fixtures', name) : path.join(__dirname, '..', 'fixtures', name);
}
function helperPath(name) { return path.join(__dirname, name); }
function deepEq(a, b) {
  if (a === b) return true;
  if (typeof a !== typeof b) return false;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => deepEq(x, b[i]));
  if (a && b && typeof a === 'object') {
    const ka = Object.keys(a); const kb = Object.keys(b);
    return ka.length === kb.length && ka.every((k) => deepEq(a[k], b[k]));
  }
  return false;
}
const ok = (detail) => ({ ok: true, detail });
const no = (detail) => ({ ok: false, detail });
function done(problems, passDetail) { return problems.length === 0 ? ok(passDetail) : no(problems.join(' | ')); }

// ---------- observation + evidence preflight ----------
if (!invocationDir) { console.error('blocked: RCOS_INVOCATION_DIR is not set'); process.exit(4); }
const outputJson = path.join(invocationDir, 'output.json');
if (!fs.existsSync(outputJson)) { console.error('blocked: the invocation has no output.json at ' + outputJson); process.exit(4); }
let O = null;
try { O = JSON.parse(fs.readFileSync(outputJson, 'utf8')); } catch (e) {
  console.error('blocked: output.json is not valid JSON: ' + e.message); process.exit(4);
}

// A case's source was read from the run's work dir; if the recorded absolute
// path has moved (copied invocation), the run's own fixture copy stands in —
// but whichever path answers, its bytes must hash to what the case recorded.
function srcOf(c) {
  const p = c && c.source && typeof c.source.path === 'string' ? c.source.path : null;
  if (!p) return null;
  if (fs.existsSync(p)) return p;
  const w = runCopyOf(path.basename(p));
  return w && fs.existsSync(w) ? w : p;
}

function caseEvidenceProblems(c) {
  const problems = [];
  const base = path.join('evidence', 'case-' + c.name);
  const readIf = (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null);
  if (readIf(path.join(invocationDir, base + '.stdout.txt')) !== c.stdout) problems.push(c.name + ': recorded stdout does not match the evidence copy');
  if (readIf(path.join(invocationDir, base + '.stderr.txt')) !== c.stderr) problems.push(c.name + ': recorded stderr does not match the evidence copy');
  const argvPath = path.join(invocationDir, base + '.argv.json');
  if (!fs.existsSync(argvPath)) problems.push(c.name + ': no argv.json in the invocation evidence');
  else {
    let a = null;
    try { a = JSON.parse(fs.readFileSync(argvPath, 'utf8')); } catch (e) { problems.push(c.name + ': argv.json is not valid JSON'); }
    if (a) {
      if (!deepEq(a.argv, c.argv)) problems.push(c.name + ': argv.json disagrees with the recorded argv');
      if (a.exit_status !== c.exit_status) problems.push(c.name + ': argv.json exit_status disagrees with the record');
      if ((a.signal || null) !== (c.signal || null)) problems.push(c.name + ': argv.json signal disagrees with the record');
      if (a.duration_ms !== c.duration_ms) problems.push(c.name + ': argv.json duration disagrees with the record');
      if (!invWork || realOr(String(a.cwd)) !== realOr(path.join(invWork, 'case-' + c.name))) problems.push(c.name + ': argv.json cwd is not the case scratch dir');
      if (realOr(String(a.interpreter)) !== realOr(String(c.interpreter_path))) problems.push(c.name + ': argv.json interpreter is not the one the case recorded');
      if (Array.isArray(c.argv) && c.argv[1] !== c.url) problems.push(c.name + ': the recorded URL is not the one on the command line');
    }
  }
  for (const f of (Array.isArray(c.out_files) ? c.out_files : [])) {
    if (!f || !f.png) continue;
    const copy = path.join(invocationDir, base + '.' + String(f.path).split('/').pop());
    if (!fs.existsSync(copy)) { problems.push(c.name + ': no evidence copy of ' + f.path); continue; }
    if (hashFile(copy) !== f.sha256) problems.push(c.name + ': the evidence copy of ' + f.path + ' is not the bytes recorded');
  }
  const src = srcOf(c);
  if (!src || !fs.existsSync(src)) problems.push(c.name + ': the source the case read is gone');
  else if (hashFile(src) !== c.source.sha256) problems.push(c.name + ': the source on disk is not the bytes the case recorded');
  return problems;
}

const EVIDENCE = [];
if (O.schema !== 'qr-camo-embed-observation/1') {
  EVIDENCE.push("the observation schema is " + JSON.stringify(O.schema) + ", not 'qr-camo-embed-observation/1'");
} else {
  if (!O.frozen || typeof O.frozen !== 'object' || !O.frozen.script || !O.frozen.interpreter) EVIDENCE.push('the observation records no frozen script/interpreter identity');
  if (!fs.existsSync(path.join(invocationDir, 'evidence', 'frozen.sha256'))) EVIDENCE.push('the run wrote no frozen.sha256 into the invocation evidence');
  if (!fs.existsSync(path.join(invocationDir, 'evidence', 'deps.json'))) EVIDENCE.push('the run wrote no deps.json into the invocation evidence');
  if (runDir && !fs.existsSync(path.join(runDir, 'input.json'))) EVIDENCE.push('the run dir has no input.json');
  for (const c of (Array.isArray(O.cases) ? O.cases : [])) {
    if (!c || typeof c.name !== 'string') { EVIDENCE.push('the observation carries a caseless record'); continue; }
    EVIDENCE.push(...caseEvidenceProblems(c));
  }
}

function caseOf(name) {
  const c = (Array.isArray(O.cases) ? O.cases : []).find((x) => x && x.name === name);
  if (!c) throw new Error('the observation has no case ' + name);
  return c;
}

// The work copy of a produced file, verified against the record's own hash.
function producedPath(c, name) {
  const rel = 'case-' + c.name + '/' + name;
  const f = (Array.isArray(c.out_files) ? c.out_files : []).find((x) => x && x.path === rel);
  if (!f) throw new Error('case ' + c.name + ' recorded no output ' + name);
  const p = path.join(invWork, rel);
  if (!fs.existsSync(p)) throw new Error('the work copy of ' + rel + ' is gone');
  if (hashFile(p) !== f.sha256) throw new Error('the work copy of ' + rel + ' is not the bytes the case recorded');
  return p;
}

// Placement coordinates from a case's own stdout; the script lays 11 px per
// module (its MODULE constant), so the quiet-zone box is modules*11.
function placementOf(c) {
  const pm = /placed at \((\d+),(\d+)\)/.exec(c.stdout || '');
  const qm = /(\d+)x(\d+) modules/.exec(c.stdout || '');
  if (!pm || !qm) throw new Error('case ' + c.name + ': stdout carries no placement line');
  return { x: parseInt(pm[1], 10), y: parseInt(pm[2], 10), qs: parseInt(qm[1], 10) * 11 };
}

// The interpreter the measuring gates re-measure through — the same resolution
// order the adapter documents. Missing here is a FAIL for identity gates (the
// environment can no longer back the record) and a block for spawn gates.
function interpBin() {
  if (process.env.RCOS_QR_PYTHON) return process.env.RCOS_QR_PYTHON;
  const p = homePath('evidence/qr-venv/bin/python');
  return p && fs.existsSync(p) ? p : null;
}
function pyBin() {
  const p = interpBin();
  if (!p) throw new Error('no interpreter for the measuring gates: set RCOS_QR_PYTHON or provide evidence/qr-venv/bin/python under RCOS_HOME');
  return p;
}
function runPy(args, timeoutMs, cwd) {
  const res = spawnSync(pyBin(), args, { encoding: 'utf8', timeout: timeoutMs || 120000, cwd: cwd || undefined });
  if (res.error && res.error.code !== 'ETIMEDOUT') throw new Error('could not start ' + pyBin() + ': ' + res.error.message);
  return res;
}
function runLadder(pngPath, url) {
  const res = runPy([helperPath('stress_ladder.py'), pngPath, url], 150000);
  if (res.status !== 0) throw new Error('stress_ladder.py exited ' + res.status + ': ' + String(res.stderr || '').slice(0, 300));
  return JSON.parse(res.stdout);
}

// ---------- gates ----------
const checks = {};

checks.ship_frame_reproduced = async () => {
  const problems = [];
  const c = caseOf('ship_bearing_frame');
  if (c.outcome !== 'embedded' || c.exit_status !== 0 || c.signal !== null) problems.push('the ship case did not embed cleanly (outcome ' + c.outcome + ', exit ' + c.exit_status + ', signal ' + c.signal + ')');
  if (c.stderr !== '') problems.push('the ship case wrote to stderr: ' + JSON.stringify(c.stderr.slice(0, 200)));
  if (c.stdout !== SHIP_STDOUT) problems.push('the ship case stdout is not the pinned 4 lines: ' + JSON.stringify(c.stdout));
  if (!c.source || c.source.sha256 !== FIXTURES['bearing-camo-src.png'].sha256) problems.push('the ship case did not read the pinned bearing cover');
  const paths = (Array.isArray(c.out_files) ? c.out_files : []).map((f) => f.path);
  if (!deepEq(paths, ['case-ship_bearing_frame/camo-qr-header.png'])) problems.push('the ship case left ' + JSON.stringify(paths) + ' behind, not exactly one camo-qr-header.png');
  try {
    const out = producedPath(c, 'camo-qr-header.png');
    const got = hashFile(out);
    if (got !== ORACLE_SHIP_SHA) problems.push('the ship case wrote ' + got.slice(0, 12) + '…, not the oracle bytes eval-6 shipped (' + ORACLE_SHIP_SHA.slice(0, 12) + '…)');
    const oracle = fixturePath('oracle-ship-header.png');
    if (!fs.existsSync(oracle)) problems.push('the package has no oracle fixture to compare against');
    else if (hashFile(oracle) !== got) problems.push("the package's oracle fixture is not the bytes the ship case wrote");
    const f = (c.out_files || []).find((x) => x.path === 'case-ship_bearing_frame/camo-qr-header.png');
    if (f && f.png && (f.png.width !== 1500 || f.png.height !== 500)) problems.push('the output is ' + f.png.width + 'x' + f.png.height + ', not 1500x500');
  } catch (e) { problems.push(e.message); }
  return done(problems, 'the ship case embedded exit 0 with the pinned placement/gain/ALL-SCANS stdout, read the pinned bearing cover, wrote exactly camo-qr-header.png (1500x500), and its bytes are the oracle fixture eval-6 shipped (' + ORACLE_SHIP_SHA.slice(0, 12) + '…)');
};

checks.pale_cover_reproduced = async () => {
  const problems = [];
  const c = caseOf('pale_cover');
  if (c.outcome !== 'embedded' || c.exit_status !== 0 || c.signal !== null) problems.push('the pale case did not embed cleanly (outcome ' + c.outcome + ', exit ' + c.exit_status + ', signal ' + c.signal + ')');
  if (c.stderr !== '') problems.push('the pale case wrote to stderr: ' + JSON.stringify(c.stderr.slice(0, 200)));
  if (c.stdout !== PALE_STDOUT) problems.push('the pale case stdout is not the pinned 4 lines: ' + JSON.stringify(c.stdout));
  if (!c.source || c.source.sha256 !== FIXTURES['pale-camo-src.png'].sha256) problems.push('the pale case did not read the pinned pale cover');
  const paths = (Array.isArray(c.out_files) ? c.out_files : []).map((f) => f.path);
  if (!deepEq(paths, ['case-pale_cover/camo-qr-header.png'])) problems.push('the pale case left ' + JSON.stringify(paths) + ' behind, not exactly one camo-qr-header.png');
  try {
    const out = producedPath(c, 'camo-qr-header.png');
    const got = hashFile(out);
    if (got !== ORACLE_PALE_SHA) problems.push('the pale case wrote ' + got.slice(0, 12) + '…, not the pinned pale oracle bytes (' + ORACLE_PALE_SHA.slice(0, 12) + '…)');
    const oracle = fixturePath('oracle-pale-header.png');
    if (!fs.existsSync(oracle)) problems.push('the package has no pale oracle fixture to compare against');
    else if (hashFile(oracle) !== got) problems.push("the package's pale oracle fixture is not the bytes the pale case wrote");
  } catch (e) { problems.push(e.message); }
  return done(problems, 'the pale case embedded exit 0 with the pinned (905,20)/score 32.2/gain-0.68 stdout, read the pinned pale cover, and its bytes reproduce the pale oracle fixture byte for byte (' + ORACLE_PALE_SHA.slice(0, 12) + '…)');
};

checks.stress_ladder_holds = async () => {
  const problems = [];
  const c = caseOf('ship_bearing_frame');
  try {
    const out = producedPath(c, 'camo-qr-header.png');
    const r = runLadder(out, c.url);
    if (r.url !== 'https://archon.diy') problems.push('the ladder decoded ' + JSON.stringify(r.url) + ', not the case URL');
    if (r.all_pass !== true) problems.push('the stress ladder did not pass every leg: ' + JSON.stringify(r.legs));
  } catch (e) { problems.push(e.message); }
  return done(problems, "the pinned ladder helper (zxing-only, on decoded arrays, mirroring the script's own stress_pass) decodes the ship output as https://archon.diy and every leg passes — disk, PNG round-trip, half-size, jpeg q78, jpeg q85");
};

checks.variant_url_decodes = async () => {
  const problems = [];
  const c = caseOf('variant_short_url');
  if (c.outcome !== 'embedded' || c.exit_status !== 0) problems.push('the variant case did not embed cleanly (outcome ' + c.outcome + ', exit ' + c.exit_status + ')');
  if (c.stdout !== VARIANT_STDOUT) problems.push('the variant case stdout is not the pinned 4 lines: ' + JSON.stringify(c.stdout));
  try {
    const out = producedPath(c, 'camo-qr-header.png');
    const got = hashFile(out);
    if (got !== VARIANT_OUT_SHA) problems.push('the variant case wrote ' + got.slice(0, 12) + '…, not the bytes the prove run pinned (' + VARIANT_OUT_SHA.slice(0, 12) + '…)');
    if (got === ORACLE_SHIP_SHA) problems.push('the variant bytes equal the ship oracle — the URL did not reach the payload');
    const r = runLadder(out, c.url);
    if (r.url !== 'https://archon.diy/rcos') problems.push('the ladder decoded ' + JSON.stringify(r.url) + ', not the variant URL');
    if (r.all_pass !== true) problems.push('the stress ladder did not pass every leg on the variant: ' + JSON.stringify(r.legs));
  } catch (e) { problems.push(e.message); }
  return done(problems, 'the variant case reproduced its pinned bytes (different from the ship oracle — the URL is in the payload), kept the pinned placement, and decodes as https://archon.diy/rcos with every ladder leg passing');
};

checks.payload_overflow_bites = async () => {
  const problems = [];
  const c = caseOf('overflow_hog_url');
  if (c.exit_status !== 1 || c.outcome !== 'refused') problems.push('the overflow case did not exit 1/refused (exit ' + c.exit_status + ', outcome ' + c.outcome + ')');
  if (c.signal !== null) problems.push('the overflow case died on a signal: ' + c.signal);
  if (c.stdout !== OVERFLOW_STDOUT) problems.push('the overflow stdout is ' + JSON.stringify(c.stdout) + ', not the pinned version line alone');
  if (c.stderr !== OVERFLOW_STDERR) problems.push('the overflow stderr is ' + JSON.stringify(c.stderr) + ', not the exact payload-too-long refusal');
  if ((Array.isArray(c.out_files) ? c.out_files.length : -1) !== 0) problems.push('the refusal left ' + JSON.stringify((c.out_files || []).map((f) => f.path)) + ' behind');
  return done(problems, 'the 45x45 payload refuses with exit 1, the exact "payload too long" stderr line, the version line as its only stdout, and no file left behind — the documented refusal path is real');
};

checks.dark_cover_halo_lifts = async () => {
  const problems = [];
  try {
    const ship = caseOf('ship_bearing_frame');
    const dark = caseOf('dark_cover');
    const shipOut = producedPath(ship, 'camo-qr-header.png');
    const darkOut = producedPath(dark, 'camo-qr-header.png');
    const sp = placementOf(ship);
    const dp = placementOf(dark);
    const mShip = JSON.parse(runPy([helperPath('measure_blend.py'), String(srcOf(ship)), shipOut, String(sp.x), String(sp.y), String(sp.qs)]).stdout);
    const mDark = JSON.parse(runPy([helperPath('measure_blend.py'), String(srcOf(dark)), darkOut, String(dp.x), String(dp.y), String(dp.qs)]).stdout);
    if (!(mShip.ring44_delta < 0)) problems.push('the ship embedding should darken its ring (measured ' + mShip.ring44_delta + ')');
    if (!(mDark.ring44_delta > 0)) problems.push('the dark cover embedding should lift its ring (measured ' + mDark.ring44_delta + ')');
    const lift = Math.round((mDark.ring44_delta - mShip.ring44_delta) * 100) / 100;
    if (!(lift >= 50)) problems.push('the dark-vs-ship ring contrast split is ' + lift + ', below the 50-unit pin (prove run measured 78.18)');
    if (!(mDark.ring44_out >= 70 && mDark.ring44_out <= 110)) problems.push('the dark embedding ring luma ' + mDark.ring44_out + ' is outside [70,110] (prove run measured 90.09) — too dark to scan or too washed to hide');
    if (!(mDark.ring44_canvas < mShip.ring44_canvas)) problems.push('the dark canvas ring (' + mDark.ring44_canvas + ') should sit below the ship canvas ring (' + mShip.ring44_canvas + ') — this is the halo, measured');
  } catch (e) { problems.push(e.message); }
  return done(problems, 'measured on the real pixels: the ship embedding darkens its ring while the dark-cover embedding lifts it, the contrast split clears the 50-unit pin (prove run 78.18), the dark ring lands inside the scannable band, and the dark canvas sits far below the ship canvas');
};

checks.pale_cover_signature = async () => {
  const problems = [];
  try {
    const c = caseOf('pale_cover');
    const out = producedPath(c, 'camo-qr-header.png');
    const p = placementOf(c);
    const r = runLadder(out, c.url);
    if (r.url !== 'https://archon.diy' || r.all_pass !== true) problems.push('the pale output does not survive the stress ladder as its URL: ' + JSON.stringify(r));
    const m = JSON.parse(runPy([helperPath('measure_blend.py'), String(srcOf(c)), out, String(p.x), String(p.y), String(p.qs)]).stdout);
    if (!(m.ring44_delta >= 5)) problems.push('the pale embedding ring lift is ' + m.ring44_delta + ', below the 5-unit pin (prove run measured 15.77) — a pale cover must push the ring UP, not down');
    if (!(m.ring44_out >= 95 && m.ring44_out <= 125)) problems.push('the pale embedding ring luma ' + m.ring44_out + ' is outside [95,125] (prove run measured 108.8)');
    if (!(Math.abs(m.box_delta) <= 10)) problems.push('the pale box delta ' + m.box_delta + ' exceeds 10 (prove run measured 2.51) — the patch would read as a sticker');
  } catch (e) { problems.push(e.message); }
  return done(problems, 'the pale cover output survives the full stress ladder and its geometry holds the measured signature: ring lifted (+15.77 at prove), ring luma near the pale canvas, box delta 2.51 — the muse SHIP verdict is sealed history this gate does not re-derive');
};

checks.muse_receipts_sealed = async () => {
  const problems = [];
  const pairs = [
    ['muse-eval6-ship.log', 'evidence/qr-camo-embed/eval-6/muse-gate.log', 'VERDICT: SHIP — camouflaged but still findable as a QR.'],
    ['muse-eval5-fail.log', 'evidence/qr-camo-embed/eval-5/muse-gate.log', 'VERDICT: FAIL — flat box / sticker look, not camouflaged into artwork.'],
  ];
  for (const [name, homeRel, verdict] of pairs) {
    const pin = FIXTURES[name];
    const f = fixturePath(name);
    if (!fs.existsSync(f)) { problems.push('the package has no copy of ' + name); continue; }
    if (hashFile(f) !== pin.sha256) { problems.push(name + ' is not the pinned bytes'); continue; }
    if (!fs.readFileSync(f, 'utf8').includes(verdict)) problems.push(name + ' does not carry the pinned VERDICT line');
    const h = homePath(homeRel);
    if (!h || !fs.existsSync(h)) problems.push('the home has no muse-gate original at ' + homeRel);
    else if (hashFile(h) !== pin.sha256) problems.push('the muse-gate original at ' + homeRel + ' is not the bytes this package seals');
  }
  return done(problems, 'the sealed muse receipts — eval-6 SHIP and eval-5 FAIL — are the pinned bytes in the package AND in evidence/qr-camo-embed/ under RCOS_HOME, verdict lines intact; the historical taste ruling stands, unedited and unrerun');
};

checks.cv2_weaker_than_zxing = async () => {
  const problems = [];
  try {
    const c = caseOf('ship_bearing_frame');
    const out = producedPath(c, 'camo-qr-header.png');
    const p = placementOf(c);
    const res = runPy([helperPath('decode_controls.py'), out, String(srcOf(c)), String(p.x), String(p.y), String(p.qs), c.url], 150000);
    if (res.status !== 0) problems.push('decode_controls.py exited ' + res.status + ': ' + String(res.stderr || '').slice(0, 300));
    else {
      const legs = JSON.parse(res.stdout).legs;
      if (!legs || !legs['0.10'] || !legs['0.15'] || !legs['0.20']) problems.push('decode_controls returned no 0.10/0.15/0.20 legs: ' + JSON.stringify(legs));
      else {
        if (legs['0.10'].zxing !== c.url || legs['0.10'].cv2 !== c.url) problems.push('at fade 0.10 both decoders should still read the URL (zxing ' + JSON.stringify(legs['0.10'].zxing) + ', cv2 ' + JSON.stringify(legs['0.10'].cv2) + ')');
        if (legs['0.15'].zxing !== c.url) problems.push('at fade 0.15 zxing should still decode (got ' + JSON.stringify(legs['0.15'].zxing) + ')');
        if (legs['0.15'].cv2 !== null) problems.push('at fade 0.15 cv2 should already miss (got ' + JSON.stringify(legs['0.15'].cv2) + ') — this separation is why cv2 is never the oracle');
        if (legs['0.20'].zxing !== null) problems.push('at fade 0.20 zxing should miss too (got ' + JSON.stringify(legs['0.20'].zxing) + ')');
      }
    }
  } catch (e) { problems.push(e.message); }
  return done(problems, 'on identical re-serialized pixels the separation reproduces: both decoders hold at fade 0.10, at 0.15 zxing still reads while cv2 already misses, at 0.20 both miss — cv2 is strictly weaker here and stays out of the oracle seat');
};

checks.orientation_fix_bites = async () => {
  const problems = [];
  let scratch = null;
  try {
    const prefix = fixturePath('prefix-orientation-make_header_v2.py');
    if (!fs.existsSync(prefix) || hashFile(prefix) !== PREFIX_SHA) throw new Error('the prefix-orientation fixture is not the pinned pre-fix script');
    const ship = caseOf('ship_bearing_frame');
    scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-camo-orient-'));
    fs.copyFileSync(String(srcOf(ship)), path.join(scratch, 'camo-src.png'));
    const res = runPy([prefix, 'https://archon.diy'], 200000, scratch);
    if (res.status !== 1) problems.push('the pre-fix script exited ' + res.status + ' on the landscape cover, not the documented refusal 1');
    if (String(res.stderr || '') !== REFUSAL_LINE + '\n') problems.push('the pre-fix stderr is ' + JSON.stringify(res.stderr) + ', not the exact stress-ladder refusal');
    const so = String(res.stdout || '');
    if (!so.includes('QR version 3, 37x37 modules')) problems.push('the pre-fix stdout never sized the payload');
    if (!so.includes('placed at (1045,20)')) problems.push('the pre-fix stdout does not carry its pinned landscape placement (1045,20): ' + JSON.stringify(so));
    if (so.includes(ALL_PASS_LINE)) problems.push('the pre-fix script claimed ALL SCANS PASS — it refused at eval-4/eval-5');
    const left = fs.readdirSync(scratch).filter((n) => n !== 'camo-src.png' && n !== 'prefix.py');
    if (left.length !== 0) problems.push('the pre-fix refusal left files behind: ' + JSON.stringify(left));
  } catch (e) { problems.push(e.message); } finally {
    if (scratch) { try { fs.rmSync(scratch, { recursive: true, force: true }); } catch (e) { /* scratch only */ } }
  }
  return done(problems, 'the script as eval-4/eval-5 ran it (pinned prefix fixture) refuses the same landscape cover the fixed script ships on: pinned (1045,20) placement line, exact refusal stderr, no output file — the orientation fix is a demonstrated behavior change, not prose');
};

checks.determinism_repeat = async () => {
  const problems = [];
  const ship = caseOf('ship_bearing_frame');
  const rep = caseOf('ship_bearing_frame_repeat');
  if (rep.stdout !== ship.stdout) problems.push('the repeat case stdout differs from the ship case: ' + JSON.stringify(rep.stdout));
  if (rep.exit_status !== ship.exit_status || rep.outcome !== ship.outcome) problems.push('the repeat case exited differently from the ship case');
  try {
    const a = hashFile(producedPath(ship, 'camo-qr-header.png'));
    const b = hashFile(producedPath(rep, 'camo-qr-header.png'));
    if (a !== b) problems.push('the repeat case wrote different bytes from the ship case');
    if (a !== ORACLE_SHIP_SHA) problems.push('both ship cases differ from the oracle bytes');
  } catch (e) { problems.push(e.message); }
  return done(problems, 'the repeat case reproduces the ship case exactly — same stdout, same exit, byte-identical output equal to the oracle — determinism as observed, on committed covers, with no randomness in the script');
};

checks.interpreter_declared = async () => {
  const problems = [];
  const interp = (O.frozen && O.frozen.interpreter) || {};
  for (const k of Object.keys(DEPS_PINS)) {
    if (!interp.deps || interp.deps[k] !== DEPS_PINS[k]) problems.push('the observation records ' + k + ' ' + JSON.stringify(interp.deps ? interp.deps[k] : undefined) + ', not the pinned ' + DEPS_PINS[k]);
  }
  if (interp.version !== PYTHON_PIN) problems.push('the observation records python ' + JSON.stringify(interp.version) + ', not the pinned ' + PYTHON_PIN);
  const depsPath = path.join(invocationDir, 'evidence', 'deps.json');
  if (!fs.existsSync(depsPath)) problems.push('the invocation evidence has no deps.json');
  else {
    let d = null;
    try { d = JSON.parse(fs.readFileSync(depsPath, 'utf8')); } catch (e) { problems.push('deps.json is not valid JSON'); }
    if (d) {
      for (const k of Object.keys(DEPS_PINS)) if (d[k] !== DEPS_PINS[k]) problems.push('deps.json records ' + k + ' ' + JSON.stringify(d[k]) + ', not the pinned ' + DEPS_PINS[k]);
      if (d.python !== PYTHON_PIN) problems.push('deps.json records python ' + JSON.stringify(d.python) + ', not the pinned ' + PYTHON_PIN);
    }
  }
  const resolved = interpBin();
  if (!resolved) problems.push('no interpreter is reachable now ($RCOS_QR_PYTHON unset, no evidence/qr-venv under RCOS_HOME) — the recorded environment cannot be re-verified');
  else {
    const recordedPath = homePath(String(interp.path || ''));
    if (!recordedPath || realOr(recordedPath) !== realOr(resolved)) problems.push('the recorded interpreter path ' + JSON.stringify(interp.path) + ' does not resolve to the live interpreter ' + resolved);
    const seen = new Set();
    for (const c of (Array.isArray(O.cases) ? O.cases : [])) {
      const r = realOr(String(c.interpreter_path));
      seen.add(r);
      if (r !== realOr(resolved)) problems.push(c.name + ' ran ' + c.interpreter_path + ', not the resolved interpreter');
    }
    if (seen.size !== 1) problems.push('the cases ran ' + seen.size + ' distinct interpreters');
    const probe = spawnSync(resolved, ['-c', PROBE_SNIPPET], { encoding: 'utf8', timeout: 60000 });
    if (probe.error || probe.status !== 0) problems.push('the live dependency probe failed: ' + String(probe.stderr || (probe.error && probe.error.message) || '').slice(0, 300));
    else {
      let live = null;
      try { live = JSON.parse(String(probe.stdout || '').trim().split('\n').pop()); } catch (e) { problems.push('the live probe printed unparseable output'); }
      if (live) {
        for (const k of Object.keys(DEPS_PINS)) if (live[k] !== DEPS_PINS[k]) problems.push('the LIVE interpreter reports ' + k + ' ' + JSON.stringify(live[k]) + ', not the pinned ' + DEPS_PINS[k]);
        if (live.python !== PYTHON_PIN) problems.push('the LIVE interpreter is python ' + JSON.stringify(live.python) + ', not the pinned ' + PYTHON_PIN);
      }
    }
  }
  return done(problems, 'the interpreter is declared and re-proven: observation, deps.json and a live probe through the exact interpreter the cases ran all report the pinned versions (cv2 4.13.0, qrcode 8.2, zxingcpp 3.1.1, numpy 2.4.6, pillow 10.4.0, python 3.14.7), one interpreter across all six cases');
};

checks.frozen_source_pinned = async () => {
  const problems = [];
  const script = homePath(SCRIPT_REL);
  if (!script || !fs.existsSync(script)) problems.push('the frozen script is not on disk at ' + SCRIPT_REL);
  else if (hashFile(script) !== SCRIPT_SHA) problems.push('the script on disk does not hash to the revision the run executed');
  const f = (O.frozen && O.frozen.script) || {};
  if (f.sha256 !== SCRIPT_SHA) problems.push('the observation recorded script sha ' + JSON.stringify(f.sha256) + ', not the pinned revision');
  if (f.usage !== 'make_header_v2.py [url] — reads ./camo-src.png, writes ./camo-qr-header.png, cwd-relative') problems.push('the recorded script usage is ' + JSON.stringify(f.usage));
  if (!deepEq(f.documented_exit_codes, [0, 1])) problems.push('the recorded documented_exit_codes are ' + JSON.stringify(f.documented_exit_codes) + ', not [0, 1]');
  if (script && typeof f.path === 'string') {
    const recorded = homePath(f.path);
    if (!recorded || realOr(recorded) !== realOr(script)) problems.push('the recorded script path (' + f.path + ') is not ' + SCRIPT_REL);
  }
  // evidence/frozen.sha256: line 1 pins the script, line 2 the interpreter.
  const frozenFile = path.join(invocationDir, 'evidence', 'frozen.sha256');
  if (!fs.existsSync(frozenFile)) problems.push('the run wrote no frozen.sha256');
  else {
    const lines = fs.readFileSync(frozenFile, 'utf8').split('\n').filter((l) => l !== '');
    if (lines.length !== 2) problems.push('frozen.sha256 carries ' + lines.length + ' lines, not script + interpreter');
    const m1 = /^([0-9a-f]{64}) {2}(.*)$/.exec(lines[0] || '');
    if (!m1) problems.push('frozen.sha256 line 1 is not a sha256sum line');
    else {
      if (m1[1] !== SCRIPT_SHA) problems.push('frozen.sha256 line 1 carries sha ' + m1[1].slice(0, 12) + '…, not the pinned script revision');
      if (script && realOr(m1[2]) !== realOr(script)) problems.push('frozen.sha256 line 1 names ' + m1[2] + ', not the frozen script');
    }
    const m2 = /^interpreter: (.*)$/.exec(lines[1] || '');
    if (!m2) problems.push('frozen.sha256 line 2 is not an interpreter line');
    else if (interpBin() && realOr(m2[1]) !== realOr(interpBin())) problems.push('frozen.sha256 names interpreter ' + m2[1] + ', not the one reachable now');
  }
  // The rest of the executed surface, re-hashed on disk: adapter, contract,
  // and the three helpers this checker itself spawns.
  const onDisk = [
    ['capabilities/qr-camo-embed/adapter/run.js', ADAPTER_SHA, 'the adapter'],
    ['capabilities/qr-camo-embed/contract.json', CONTRACT_SHA, 'the contract'],
  ];
  for (const [rel, want, label] of onDisk) {
    const p = homePath(rel);
    if (!p || !fs.existsSync(p)) problems.push(label + ' is not on disk at ' + rel);
    else if (hashFile(p) !== want) problems.push(label + ' on disk does not hash to the pinned revision');
  }
  for (const [name, want] of [['measure_blend.py', MEASURE_SHA], ['stress_ladder.py', LADDER_SHA], ['decode_controls.py', DECODE_SHA]]) {
    const p = helperPath(name);
    if (!fs.existsSync(p)) problems.push('the helper ' + name + ' is missing beside this checker');
    else if (hashFile(p) !== want) problems.push('the helper ' + name + ' is not the pinned revision');
  }
  // Every executed case ran the frozen script with the case URL.
  let executed = 0;
  for (const c of (Array.isArray(O.cases) ? O.cases : [])) {
    if (!Array.isArray(c.argv) || c.argv.length !== 2) { problems.push(c.name + ': argv is ' + JSON.stringify(c.argv)); continue; }
    if (script && realOr(c.argv[0]) !== realOr(script)) problems.push(c.name + ': ran ' + c.argv[0] + ', not the frozen script');
    if (c.argv[1] !== c.url) problems.push(c.name + ': argv[1] is ' + JSON.stringify(c.argv[1]) + ', not the case URL');
    executed += 1;
  }
  if (executed !== 6) problems.push('the run executed ' + executed + ' cases, not the 6 the package declares');
  return done(problems, 'the frozen script, adapter, contract and all three measuring helpers are the pinned revisions on disk, evidence/frozen.sha256 carries the script + interpreter identity the run wrote, and all ' + executed + ' cases ran that exact script with their own URL (check.js pins everything except itself — its identity rides the commit and the trace receipt)');
};

checks.artifact_identity_pinned = async () => {
  const problems = [];
  if (!runDir) return no('the run dir is not visible to this gate');
  const inputPath = path.join(runDir, 'input.json');
  if (!fs.existsSync(inputPath)) return no('the run has no input.json');
  const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  if (!evalDir) problems.push('RCOS_EVAL_DIR is not set — the package this run belongs to cannot be identified');
  if (input.eval_id !== 'qr-camo-embed-grounding-v1') problems.push('the run is an execution of ' + JSON.stringify(input.eval_id) + ', not this package');
  if (input.capability_id !== 'qr-camo-embed') problems.push('the run executed ' + JSON.stringify(input.capability_id));
  if (evalDir) {
    const spec = path.join(evalDir, 'eval.json');
    if (!fs.existsSync(spec)) problems.push("the package's eval.json is not on disk at " + spec);
    else if (hashFile(spec) !== input.eval_sha256) problems.push('the package on disk is not the revision this run executed');
  }
  // Every declared fixture: the same bytes in the eval package, in the run's
  // work dir, in the run's evidence copy, and under the sha input.json recorded.
  const recorded = new Map();
  for (const x of (Array.isArray(input.fixtures) ? input.fixtures : [])) {
    if (typeof x === 'string') recorded.set(x, null);
    else if (x && typeof x.name === 'string') recorded.set(x.name, x);
  }
  const names = Object.keys(FIXTURES);
  if (recorded.size !== names.length) problems.push('input.json records ' + recorded.size + ' fixtures, not the ' + names.length + ' the package pins');
  for (const name of names) {
    const pin = FIXTURES[name];
    if (!recorded.has(name)) { problems.push('input.json does not record fixture ' + name); continue; }
    const rec = recorded.get(name);
    if (rec && (rec.sha256 !== pin.sha256 || rec.bytes !== pin.bytes)) {
      problems.push('input.json records ' + name + ' as ' + String(rec.sha256).slice(0, 12) + '…/' + rec.bytes + ', not the pinned ' + pin.sha256.slice(0, 12) + '…/' + pin.bytes);
    }
    const copies = [];
    const w = runCopyOf(name); if (w) copies.push(['the run work dir', w, fs.existsSync(w)]);
    const e = path.join(runDir, 'evidence', 'inputs', name); copies.push(['the run evidence copy', e, fs.existsSync(e)]);
    const p = evalDir ? path.join(evalDir, 'fixtures', name) : null; if (p) copies.push(['the package', p, fs.existsSync(p)]);
    for (const [label, file, exists] of copies) {
      if (!exists) { problems.push(label + ' has no copy of ' + name); continue; }
      const buf = fs.readFileSync(file);
      if (buf.length !== pin.bytes) problems.push(label + "'s copy of " + name + ' is ' + buf.length + ' bytes, not ' + pin.bytes);
      if (sha256(buf) !== pin.sha256) problems.push(label + "'s copy of " + name + ' is not the pinned bytes');
    }
  }
  // The run's own request, pinned by hash, with every case reading the run's
  // own fixture copy.
  const ci = input.capability_input;
  if (!ci || typeof ci.path !== 'string' || typeof ci.sha256 !== 'string') problems.push('input.json records no capability input');
  else {
    const ciPath = path.isAbsolute(ci.path) ? ci.path : path.join(runDir, ci.path);
    if (!fs.existsSync(ciPath)) problems.push("the run's capability input is gone: " + ciPath);
    else if (hashFile(ciPath) !== ci.sha256) problems.push("the run's capability input is not the bytes the run consumed");
    else {
      const req = JSON.parse(fs.readFileSync(ciPath, 'utf8'));
      const cases = Array.isArray(req.cases) ? req.cases : [];
      const got = cases.map((x) => (x && x.name) || '?');
      const want = Array.isArray(O.cases) ? O.cases.map((x) => x.name) : [];
      if (!deepEq(got, want)) problems.push('the request names ' + JSON.stringify(got) + ', the observation ' + JSON.stringify(want));
      if (got.length !== 6) problems.push('the run requested ' + got.length + ' cases, not the 6 the package declares');
      for (const x of cases) {
        if (!x || typeof x.source !== 'string') { problems.push('a requested case names no source'); continue; }
        if (x.operation !== 'embed') problems.push('a requested case has operation ' + JSON.stringify(x.operation));
        const base = path.basename(x.source);
        if (!FIXTURES[base]) { problems.push('a requested case reads ' + x.source + ', which is not a pinned fixture'); continue; }
        if (typeof x.url !== 'string' || !/^https?:\/\//.test(x.url)) problems.push('a requested case carries no URL');
        // Relocation-invariant cross-check: the request is frozen input bytes,
        // so absolute paths cannot be compared against a relocated observation —
        // but the URL the case ran and the cover's basename can.
        const oc = (Array.isArray(O.cases) ? O.cases : []).find((y) => y && y.name === x.name);
        if (!oc) problems.push('the observation has no case named ' + JSON.stringify(x.name));
        else {
          if (oc.url !== x.url) problems.push(x.name + ': the observation ran URL ' + JSON.stringify(oc.url) + ', the request asked for ' + JSON.stringify(x.url));
          if (!oc.source || path.basename(String(oc.source.path)) !== base) problems.push(x.name + ': the observation read a different cover than the request named');
        }
      }
    }
  }
  // The observation's cases are the pinned set, once each, in the declared order.
  if (!Array.isArray(O.cases) || O.cases.length !== 6) problems.push('the observation carries ' + (Array.isArray(O.cases) ? O.cases.length : 0) + ' cases, not 6');
  else {
    const seen = O.cases.map((c) => c.name);
    if (new Set(seen).size !== seen.length) problems.push('the observation names the same case twice');
  }
  return done(problems, 'the run is an execution of this exact package revision, all ' + names.length + ' pinned fixtures agree byte for byte across the package, the run work dir and the run evidence copy, and the run\'s request is pinned by hash with every case reading the run\'s own fixture copy');
};

// ---------- dispatcher ----------
if (!checks[id]) {
  console.error('blocked: unknown gate id ' + JSON.stringify(id));
  process.exit(4);
}
if (EVIDENCE.length > 0) {
  console.log('FAIL ' + id + ': the observation contradicts its own evidence: ' + EVIDENCE.join(' | '));
  process.exit(3);
}
Promise.resolve()
  .then(() => checks[id]())
  .then((res) => {
    console.log((res.ok ? 'PASS ' : 'FAIL ') + id + ': ' + res.detail);
    process.exit(res.ok ? 0 : 3);
  })
  .catch((e) => {
    console.error('blocked: gate ' + id + ' could not complete: ' + e.message);
    process.exit(4);
  });
