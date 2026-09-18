#!/usr/bin/env node
'use strict';
// Falsifiability selftest for evals/qr-camo-embed-grounding-v1/gates/check.js.
//
// The checker's danger is not that it can fail — it is that it can PASS
// something false. So this rig does not re-run the gates on happy paths and
// count green. It clones the latest SHIPPED run (run dir + invocation dir +
// eval package) into throwaway APFS sandboxes, applies exactly one mutation
// per sandbox, and asserts the specific gate that exists to catch that
// mutation refuses (exit 3), while an honest relocation of the same run stays
// fully green (control 0). A mutation the pin web cannot see would be a
// false-green class; any control here failing means the checker is weaker
// than its gates claim and the eval must not ship.
//
// Controls:
//   C0  honest relocation (output.json + argv.json re-pointed at the clone)
//       —— all 14 gates still exit 0 (no false RED from moving a run)
//   C1  package oracle fixture swapped ........................ ship_frame_reproduced 3
//   C2  observation stdout tampered ........................... preflight "contradicts its own evidence" 3
//   C3  produced header bytes flipped in the work dir ......... ship_frame_reproduced 3
//   C4  recorded URL tampered (argv disagrees) ................ preflight 3
//   C5  sealed muse receipt replaced .......................... muse_receipts_sealed 3
//   C6  pre-fix orientation fixture swapped for the fixed script orientation_fix_bites 3
//   C7  run-work cover swapped for different bytes ............ preflight 3
//   C8  self-consistent URL forgery (observation AND argv.json) artifact_identity_pinned 3
//       (payload_overflow_bites alone still passes here — the recorded-run
//        judge cannot re-run the adapter; the request-vs-observation leg of
//        the identity gate is what kills it)
//   C9  live interpreter downgraded (RCOS_QR_PYTHON=/usr/bin/python3)
//       ........................................................ interpreter_declared 3 (FAIL, not blocked)
//   C9b interpreter unreachable (empty RCOS_HOME) .............. interpreter_declared 3
//   C10 measuring helper tampered .............................. frozen_source_pinned 3
//   C11 unknown gate id ........................................ exit 4 (blocked), never a pass
//
// Exit: 0 = every control behaved; 1 = a control exposed a weakness (printed).

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const HOME = process.env.RCOS_HOME_SELFTEST || path.resolve(__dirname, '..', '..', '..');
const RUN_ID = process.env.SELFTEST_RUN_ID || '20260918T204426Z-ff1c90';
const INV_ID = process.env.SELFTEST_INV_ID || 'inv_20260918T204426Z-208c54';
const BASE_RUN = path.join(HOME, 'runs', RUN_ID);
const BASE_INV = path.join(HOME, 'invocations', INV_ID);
const BASE_EVAL = path.join(HOME, 'evals', 'qr-camo-embed-grounding-v1');
const GATES = [
  'ship_frame_reproduced', 'pale_cover_reproduced', 'stress_ladder_holds',
  'variant_url_decodes', 'payload_overflow_bites', 'dark_cover_halo_lifts',
  'pale_cover_signature', 'muse_receipts_sealed', 'cv2_weaker_than_zxing',
  'orientation_fix_bites', 'determinism_repeat', 'interpreter_declared',
  'frozen_source_pinned', 'artifact_identity_pinned',
];

function clone(src, dst) {
  const r = spawnSync('cp', ['-Rc', src, dst], { encoding: 'utf8' });
  if (r.status !== 0) fs.cpSync(src, dst, { recursive: true });
}
function readJson(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }
function writeJson(p, obj) { fs.writeFileSync(p, JSON.stringify(obj, null, 2) + '\n'); }

// Clone run + invocation + package, then re-point the observation's absolute
// records at the clone. This is the honest shape of a relocated run: the
// observation describes the SAME execution, the bytes just live elsewhere.
function makeSandbox(root, name) {
  const sbx = path.join(root, name);
  fs.mkdirSync(sbx);
  clone(BASE_RUN, path.join(sbx, 'run'));
  clone(BASE_INV, path.join(sbx, 'inv'));
  clone(BASE_EVAL, path.join(sbx, 'eval'));
  const inv = path.join(sbx, 'inv');
  const runWork = path.join(sbx, 'run', 'work');
  const out = readJson(path.join(inv, 'output.json'));
  for (const c of out.cases) {
    c.source.path = path.join(runWork, path.basename(c.source.path));
    const argvPath = path.join(inv, 'evidence', 'case-' + c.name + '.argv.json');
    const a = readJson(argvPath);
    a.cwd = path.join(inv, 'work', 'case-' + c.name);
    writeJson(argvPath, a);
  }
  writeJson(path.join(inv, 'output.json'), out);
  return { sbx, inv, run: path.join(sbx, 'run'), eval: path.join(sbx, 'eval'), work: runWork };
}

function runGate(sbx, gateId, envOverrides) {
  const env = Object.assign({}, process.env, {
    RCOS_INVOCATION_DIR: sbx.inv,
    RCOS_RUN_DIR: sbx.run,
    RCOS_WORK_DIR: sbx.work,
    RCOS_EVAL_DIR: sbx.eval,
    RCOS_HOME: HOME,
  });
  delete env.RCOS_QR_PYTHON;
  Object.assign(env, envOverrides || {});
  const r = spawnSync(process.execPath, [path.join(sbx.eval, 'gates', 'check.js'), gateId], { encoding: 'utf8', timeout: 240000, env });
  return { code: r.status, out: String(r.stdout || ''), err: String(r.stderr || '') };
}

const failures = [];
function expect(label, cond, detail) {
  if (cond) console.log('  ok   ' + label);
  else { console.log('  WEAK ' + label + ' — ' + detail); failures.push(label + ': ' + detail); }
}
function caseIn(sbx, name) {
  const out = readJson(path.join(sbx.inv, 'output.json'));
  return out.cases.find((c) => c.name === name);
}
function saveObservation(sbx, c) {
  const out = readJson(path.join(sbx.inv, 'output.json'));
  const i = out.cases.findIndex((x) => x.name === c.name);
  out.cases[i] = c;
  writeJson(path.join(sbx.inv, 'output.json'), out);
}

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-camo-selftest-'));
let cleanup = true;
try {
  // C0 — honest relocation stays green across all 14 gates.
  console.log('C0  honest relocation');
  const c0 = makeSandbox(root, 'c0');
  for (const g of GATES) {
    const r = runGate(c0, g);
    expect('C0 ' + g + ' exit 0', r.code === 0 && r.out.startsWith('PASS '), 'exit ' + r.code + ' ' + (r.out || r.err).trim().slice(0, 220));
  }

  // C1 — the oracle fixture in the package is swapped for other bytes.
  console.log('C1  oracle fixture swap');
  const c1 = makeSandbox(root, 'c1');
  fs.copyFileSync(path.join(c1.eval, 'fixtures', 'oracle-pale-header.png'), path.join(c1.eval, 'fixtures', 'oracle-ship-header.png'));
  const r1 = runGate(c1, 'ship_frame_reproduced');
  expect('C1 ship_frame_reproduced refuses', r1.code === 3, 'exit ' + r1.code + ' ' + (r1.out || r1.err).trim().slice(0, 220));

  // C2 — the observation's stdout is edited (score line rewritten).
  console.log('C2  observation stdout tamper');
  const c2 = makeSandbox(root, 'c2');
  const s2 = caseIn(c2, 'ship_bearing_frame');
  s2.stdout = s2.stdout.replace('smoothness score 25.5', 'smoothness score 20.1');
  saveObservation(c2, s2);
  const r2 = runGate(c2, 'ship_frame_reproduced');
  expect('C2 preflight contradiction', r2.code === 3 && /contradicts its own evidence/.test(r2.out), 'exit ' + r2.code + ' ' + (r2.out || r2.err).trim().slice(0, 220));

  // C3 — the produced header in the invocation work dir is flipped.
  console.log('C3  produced header byte flip');
  const c3 = makeSandbox(root, 'c3');
  fs.appendFileSync(path.join(c3.inv, 'work', 'case-ship_bearing_frame', 'camo-qr-header.png'), 'x');
  const r3 = runGate(c3, 'ship_frame_reproduced');
  expect('C3 ship_frame_reproduced refuses', r3.code === 3, 'exit ' + r3.code + ' ' + (r3.out || r3.err).trim().slice(0, 220));

  // C4 — the recorded URL is rewritten; the command line in argv.json disagrees.
  console.log('C4  recorded URL tamper');
  const c4 = makeSandbox(root, 'c4');
  const s4 = caseIn(c4, 'ship_bearing_frame');
  s4.url = 'https://archon.example';
  saveObservation(c4, s4);
  const r4 = runGate(c4, 'cv2_weaker_than_zxing');
  expect('C4 preflight contradiction', r4.code === 3 && /contradicts its own evidence/.test(r4.out), 'exit ' + r4.code + ' ' + (r4.out || r4.err).trim().slice(0, 220));

  // C5 — the sealed muse receipt is replaced with the other receipt's bytes.
  console.log('C5  muse receipt swap');
  const c5 = makeSandbox(root, 'c5');
  fs.copyFileSync(path.join(c5.eval, 'fixtures', 'muse-eval5-fail.log'), path.join(c5.eval, 'fixtures', 'muse-eval6-ship.log'));
  const r5 = runGate(c5, 'muse_receipts_sealed');
  expect('C5 muse_receipts_sealed refuses', r5.code === 3, 'exit ' + r5.code + ' ' + (r5.out || r5.err).trim().slice(0, 220));

  // C6 — the pre-fix script fixture is swapped for the FIXED script.
  console.log('C6  prefix fixture swap');
  const c6 = makeSandbox(root, 'c6');
  fs.copyFileSync(path.join(HOME, 'capabilities', 'qr-camo-embed', 'adapter', 'make_header_v2.py'),
    path.join(c6.eval, 'fixtures', 'prefix-orientation-make_header_v2.py'));
  const r6 = runGate(c6, 'orientation_fix_bites');
  expect('C6 orientation_fix_bites refuses', r6.code === 3, 'exit ' + r6.code + ' ' + (r6.out || r6.err).trim().slice(0, 220));

  // C7 — the run-work cover is swapped for different bytes (post-relocation,
  // so srcOf resolves inside the sandbox and must catch it).
  console.log('C7  run-work cover swap');
  const c7 = makeSandbox(root, 'c7');
  fs.copyFileSync(path.join(c7.work, 'dark-camo-src.png'), path.join(c7.work, 'bearing-camo-src.png'));
  const r7 = runGate(c7, 'stress_ladder_holds');
  expect('C7 preflight contradiction', r7.code === 3 && /contradicts its own evidence/.test(r7.out), 'exit ' + r7.code + ' ' + (r7.out || r7.err).trim().slice(0, 220));

  // C8 — a SELF-CONSISTENT forgery: observation AND argv.json both shortened.
  // The recorded-run judge cannot re-run the adapter, so the overflow gate
  // still passes — the request-vs-observation leg of the identity gate is
  // what refuses to let this ship.
  console.log('C8  self-consistent URL forgery');
  const c8 = makeSandbox(root, 'c8');
  const s8 = caseIn(c8, 'overflow_hog_url');
  s8.url = 'https://x.dev';
  s8.argv[1] = 'https://x.dev';
  saveObservation(c8, s8);
  const a8p = path.join(c8.inv, 'evidence', 'case-overflow_hog_url.argv.json');
  const a8 = readJson(a8p);
  a8.argv[1] = 'https://x.dev';
  writeJson(a8p, a8);
  const r8a = runGate(c8, 'payload_overflow_bites');
  expect('C8 overflow gate isolated (still passes)', r8a.code === 0, 'exit ' + r8a.code + ' ' + (r8a.out || r8a.err).trim().slice(0, 220));
  const r8b = runGate(c8, 'artifact_identity_pinned');
  expect('C8 artifact_identity_pinned refuses', r8b.code === 3 && /the request asked for/.test(r8b.out), 'exit ' + r8b.code + ' ' + (r8b.out || r8b.err).trim().slice(0, 220));

  // C9 — a live interpreter that is NOT the recorded environment: the gate
  // must FAIL (the record is no longer backed), not block.
  console.log('C9  interpreter downgrade');
  const c9 = makeSandbox(root, 'c9');
  const r9 = runGate(c9, 'interpreter_declared', { RCOS_QR_PYTHON: '/usr/bin/python3' });
  expect('C9 interpreter_declared FAILs (not blocked)', r9.code === 3, 'exit ' + r9.code + ' ' + (r9.out || r9.err).trim().slice(0, 220));

  // C9b — no interpreter reachable at all: identity gates must still FAIL.
  console.log('C9b interpreter unreachable');
  const c9b = makeSandbox(root, 'c9b');
  const emptyHome = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-camo-empty-home-'));
  const r9b = runGate(c9b, 'interpreter_declared', { RCOS_HOME: emptyHome });
  expect('C9b interpreter_declared FAILs', r9b.code === 3, 'exit ' + r9b.code + ' ' + (r9b.out || r9b.err).trim().slice(0, 220));
  fs.rmSync(emptyHome, { recursive: true, force: true });

  // C10 — a measuring helper beside the checker is tampered.
  console.log('C10 helper tamper');
  const c10 = makeSandbox(root, 'c10');
  fs.appendFileSync(path.join(c10.eval, 'gates', 'decode_controls.py'), '\n# tampered\n');
  const r10 = runGate(c10, 'frozen_source_pinned');
  expect('C10 frozen_source_pinned refuses', r10.code === 3, 'exit ' + r10.code + ' ' + (r10.out || r10.err).trim().slice(0, 220));

  // C11 — an unknown gate id blocks; it never passes.
  console.log('C11 unknown gate id');
  const c11 = makeSandbox(root, 'c11');
  const r11 = runGate(c11, 'no_such_gate');
  expect('C11 exit 4 blocked', r11.code === 4, 'exit ' + r11.code + ' ' + (r11.out || r11.err).trim().slice(0, 220));
} catch (e) {
  failures.push('harness error: ' + e.message);
  console.error('harness error: ' + e.stack);
  cleanup = false;
} finally {
  if (cleanup && failures.length === 0) fs.rmSync(root, { recursive: true, force: true });
  else console.log('sandboxes left at ' + root + ' for inspection');
}

if (failures.length > 0) {
  console.log('\nSELFTEST WEAK — ' + failures.length + ' control(s) did not behave:');
  for (const f of failures) console.log('  ' + f);
  process.exit(1);
}
console.log('\nSELFTEST CLEAN — every mutation was caught by the gate built for it; honest relocation stays green.');
