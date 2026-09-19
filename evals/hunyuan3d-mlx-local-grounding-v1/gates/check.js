#!/usr/bin/env node
/**
 * Gates for eval hunyuan3d-mlx-local-grounding-v1 (rcos-eval/2).
 *
 * Exit contract: 0 = pass, 3 = fail, 4 = blocked. A blocked gate is never a
 * pass. All gates are required.
 *
 * Pin provenance: the 8 chain artifacts are byte-identical between the
 * committed eval-2 oracle (evidence/hunyuan3d-mlx-local/eval-2, run 2026-09-17)
 * and an independent probe execution (2026-09-18, run1) that predated this
 * package — full-chain byte determinism across a day gap, dual-proven. Stdout
 * pins follow the declared policy: the frozen scripts' own print() lines are
 * pinned exactly in STDOUT (their emission point is provable from the frozen
 * bytes); library internals (Hierarchical Volume Decoding, Loading, step and
 * decoded lines, tqdm) are matched as lines in EITHER stream because the probe
 * logs merged both. Volatile quantities (peak-RSS gigabytes, "ready in X s",
 * tqdm progress, [TIMING] seconds) are regex-pinned — counts and geometry are
 * properties of the seeded run; seconds and gigabytes are properties of the
 * day. The environment (interpreter, upstream repo, weights snapshot) is
 * environment, not committed bytes; the environment gates re-measure it live
 * and demand it still matches what the run recorded, so a changed environment
 * fails here instead of being silently excused.
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const RUN = process.env.RCOS_RUN_DIR;
const WORK = process.env.RCOS_WORK_DIR;
const EVALDIR = process.env.RCOS_EVAL_DIR;
const HOME = process.env.RCOS_HOME;
if (!RUN || !WORK || !EVALDIR || !HOME) {
  console.error('missing kernel env: RCOS_RUN_DIR/RCOS_WORK_DIR/RCOS_EVAL_DIR/RCOS_HOME');
  process.exit(4);
}
// On a real /2 run the adapter executes inside the invocation kernel: its case
// work lives in <invocation>/work, its evidence copies in <invocation>/evidence
// and its observation at <invocation>/output.json ($RCOS_INVOCATION_DIR is set
// for gate children). The eval run dir holds only the frozen fixtures, the
// input layer and the runner's own records. The RUN/evidence fallback exists
// for out-of-kernel validation layouts only.
const INVOKE = process.env.RCOS_INVOCATION_DIR || null;
const CASES_ROOT = INVOKE ? path.join(INVOKE, 'work') : WORK;
const EVIDENCE = INVOKE ? path.join(INVOKE, 'evidence') : path.join(RUN, 'evidence');
const ADAPTER_DIR = path.join(HOME, 'capabilities', 'hunyuan3d-mlx-local', 'adapter');

const CAP = 'capabilities/hunyuan3d-mlx-local';
const E2E = 'bearing_product_e2e';
const REPEAT = 'bearing_product_e2e_repeat';
const EMPTY = 'empty_source_refused';

// ---------------------------------------------------------------------------
// pins — captured from executed bytes before this package existed
// ---------------------------------------------------------------------------
const PINS = {
  scripts: {
    'prep_reference.py': '248a925110f717e7006c3d581c90acd955cedef3437e1ad2a34e834f030a7ce0',
    'run_shape.py': 'b103eb76a0ad021d37a56db99f235aa26c3d3ea2c49a968685deae9de72d320e',
    'run_texture.py': '83152585cec0538b9b76439747066b968d8a32123c72155ce1de14c146bb318b',
  },
  adapter_sha: 'c136e640a2ef733d09ac89c12291a606f9d8de62ad2a3eea331a79ac3f9aa2c9',
  contract_sha: '95aa26b21782c527b24d4df24a5de0b77e2f15633cf6c88a5772f11b0b6d7ae8',
  helper_sha: '9fe1dd5e0f3ee74b5a0b6ec7f53079e925140be4520a58c1f0aae6148c6f4d61',
  fixtures: {
    'bearing-ref.png': { sha256: '94f1e7347fc9156cd82587df5b321e90ed745ca20b9c6b7325384bd436b766cf', bytes: 1524333 },
    'empty-source.png': { sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', bytes: 0 },
    'pipeline_mlx-PR8.patch': { sha256: '784a2344d4b8e5e3f28fb88e9a5ac751b271976e36a7b3d80902052e3c9b37bf', bytes: 2357 },
  },
  // case-relative artifact paths; identical for both e2e cases
  artifacts: {
    'ref_518_full.png': { sha256: '0c8afb96584c61d8dfc8451f42122c9ad9bc6d9f71cbbb4b6a7d8306eaa82144', bytes: 1439507 },
    'ref_518.png': { sha256: 'ae1b04aa652f3e832aa440d5263e07ecfca287302e6334c039c0ff529ca210c8', bytes: 211299 },
    'out_shape/shape.glb': { sha256: 'f2fb09c68beaa2eb9831d3aae1daaf22b5d674ff3adf964a4506e8321c45d13d', bytes: 10312244 },
    'out_shape/white_mesh_remesh.obj': { sha256: '8281e26b613e4b14553f6189dfa026c18424238bd3bca505af63fd50d763d275', bytes: 1457537 },
    'out_tex/material.mtl': { sha256: 'cfd4f7af57dda806ca62a969663ec0a92565e6a2a50fad4b4b4836eefaebf2e9', bytes: 196 },
    'out_tex/paint_pbr.png': { sha256: '958c266c1693a0164a41bcf20d91909d722ba9865c046dfc7dc8f005d5a38dd1', bytes: 5762579 },
    'out_tex/textured.glb': { sha256: 'c3f7e95fda71960da64d79d3fd85f26cbefa51321944038ac02ba31654718b91', bytes: 9795304 },
    'out_tex/textured.obj': { sha256: '726033af6ccb02ab6d1012ab6344f60c6f48028e6afd8389287b96dc27f272eb', bytes: 2986016 },
  },
  upstream: {
    repo: 'tools/hunyuan3d-2.1-mlx',
    head: '5fe21945b790fbb7fb28c510e89babd7b9feabe6',
    patch: '784a2344d4b8e5e3f28fb88e9a5ac751b271976e36a7b3d80902052e3c9b37bf',
    weights_repo: 'dgrauet/hunyuan3d-2.1-mlx',
    snapshot: '5b1cf9ae1114c0b046d9385fd4f5ac6570df5287',
  },
  deps: { python: '3.12.13', mlx: '0.32.2', numpy: '2.5.3', trimesh: '5.1.0', rembg: '2.0.84', pillow: '12.3.0' },
  interp_suffix: 'venvs/hunyuan3d-mlx/bin/python',
};

const SHAPE_MESH = {
  verts: 286384, faces: 572904, watertight: true,
  extents: [1.978850245475769, 1.9875415563583374, 0.37871360778808594],
  bounds: [[-0.9946253299713135, -0.9971956014633179, -0.19342494010925293],
           [0.9842249155044556, 0.9903459548950195, 0.185288667678833]],
  glb: { version: 2, json_bytes: 760, asset_version: '2.0',
         generator: 'https://github.com/mikedh/trimesh', meshes: 1, images: 0 },
};
const TEXTURED_MESH = {
  verts: 25633, faces: 40000, watertight: false,
  extents: [1.9790595769882202, 1.9873679876327515, 0.37901973724365234],
  glb: { version: 2, json_bytes: 1396, asset_version: '2.0',
         generator: 'https://github.com/mikedh/trimesh', meshes: 1, images: 2 },
};
const PNG_FACTS = {
  'out_tex/paint_pbr.png': { width: 4096, height: 4096, bit_depth: 8, color_type: 2 },
  'ref_518.png': { width: 518, height: 518, bit_depth: 8, color_type: 2 },
};

// prep stdout is fully deterministic — pinned byte-exact (103 bytes)
const PREP_STDOUT_EXACT =
  'rembg       -> ref_518_full.png (1600, 1600)\n' +
  'opaque frac : 0.4300\n' +
  'recentered  -> ref_518.png (518x518)\n';

// shape stage: the frozen script's own print() lines (stdout-certain). The
// padding after the label is regex'd; content is exact.
const SHAPE_STDOUT_RE = [
  /^\[Stage 1\] image\s+: ref_518\.png$/,
  /^\[Stage 1\] output\s+: out_shape\/shape\.glb$/,
  /^\[Stage 1\] weights\s+: dgrauet\/hunyuan3d-2\.1-mlx \(fp16 default\)$/,
  /^\[Stage 1\] extents\s+: \[1\.97885025 1\.98754156 0\.37871361\]$/,
  /^\[Stage 1\] bounds\s+: \[\[-0\.9946253299713135, -0\.9971956014633179, -0\.19342494010925293\], \[0\.9842249155044556, 0\.9903459548950195, 0\.185288667678833\]\]$/,
  /^\[Stage 1\] watertight\s+: True$/,
  /^\[Stage 1\] peak RSS at start: \d+\.\d+ GB$/,
  /^\[Stage 1\] generated in \d+\.\d+s \(286384 verts, 572904 faces\)$/,
  /^\[Stage 1\] saved\s+: out_shape\/shape\.glb \(9\.8 MB\)$/,
  /^\[Stage 1\] pipeline ready in \d+\.\d+s \(peak RSS \d+\.\d+ GB\)$/,
  /^\[Stage 1\] peak RSS\s+: \d+\.\d+ GB$/,
  /^\[TIMING\] shape load \d+\.\d+s \+ infer \d+\.\d+s = \d+\.\d+s total$/,
];
const SHAPE_EITHER_LINES = [
  'Hierarchical Volume Decoding [r65]: 274625 points',
  'Hierarchical Volume Decoding [r129]: 373485 points (of 2146689 total)',
  'Hierarchical Volume Decoding [r257]: 1488269 points (of 16974593 total)',
];
const SHAPE_EITHER_RE = [/Fetching 5 files:[\s\S]*?5\/5/];

const TEXTURE_STDOUT_RE = [
  /^\[Stage 2\] mesh\s+: out_shape\/shape\.glb$/,
  /^\[Stage 2\] reference\s+: ref_518\.png$/,
  /^\[Stage 2\] output\s+: out_tex\/textured\.obj \(\+ \.glb\)$/,
  /^\[Stage 2\] cfg: max_selected_view_num=6 resolution=512 texture_size=4096 render_size=2048 mlx_diffusion=True mlx_superres=True$/,
  /^\[Stage 2\] pipeline ready in \d+\.\d+s \(peak RSS \d+\.\d+ GB\)$/,
  /^\[Stage 2\] texture synthesized in \d+\.\d+s$/,
  /^\[Stage 2\] peak RSS\s+: \d+\.\d+ GB$/,
  /^\[TIMING\] texture load \d+\.\d+s \+ synth \d+\.\d+s = \d+\.\d+s total$/,
];
const TEXTURE_EITHER_LINES = [
  'Loading VAE...',
  'Loading DINOv2...',
  'Loading UNet...',
  '  Loaded 1054/1061 main UNet weights (remaining keys load into text embeds + DINO proj below)',
  'Loading dual-stream reference UNet...',
  '  Loaded 686/686 dual UNet weights',
  'All components loaded.',
  'MLX diffusion model loaded.',
  '  Encoding conditions...',
  '  Extracting DINO features...',
  '  Extracting reference features...',
  '  Denoising (15 steps, 6 views, CFG=3.0)...',
  '    step 0/15: t=999, range=9.3',
  '    step 5/15: t=666, range=11.5',
  '    step 10/15: t=332, range=18.8',
  '    step 14/15: t=66, range=21.8',
  '  Decoding...',
  '    decoded 6/12',
  '    decoded 12/12',
];
const TEXTURE_EITHER_RE = [
  /Fetching 5 files:[\s\S]*?5\/5/,
  /MLX super-resolution loaded \([^)]*snapshots\/5b1cf9ae1114c0b046d9385fd4f5ac6570df5287\/realesrgan_x4plus\.safetensors\)\./,
];

const REFUSAL_RE = [/PIL\.UnidentifiedImageError: cannot identify image file/, /ref_source\.png/];

const BUDGETS = {
  prep_ms: 120000, shape_ms: 900000, texture_ms: 800000,
  case_ms: 2000000, empty_ms: 120000, peak_rss_gb: 10,
};

const PROBE_SNIPPET =
  'import json,sys;from importlib.metadata import version as _v;' +
  'print(json.dumps({"python":sys.version.split()[0],"mlx":_v("mlx"),"numpy":_v("numpy"),' +
  '"trimesh":_v("trimesh"),"rembg":_v("rembg"),"pillow":_v("pillow")}))';

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------
let fails = 0;
let gid = process.argv[2] || '(none)';
function ok(msg) { console.log('[gate] ' + gid + ': ok ' + msg); }
function no(msg) { fails += 1; console.log('[gate] ' + gid + ': no ' + msg); }

function sha256(s) { return crypto.createHash('sha256').update(s).digest('hex'); }
function hashFile(p) { return sha256(fs.readFileSync(p)); }
function readJson(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }
function deepEq(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

function stageOf(c, name) {
  const s = c.stages.find((s) => s.stage === name);
  // a missing stage (chain died early) must FAIL the gate, never crash it
  if (!s) no((c.name || '?') + ': stage record missing: ' + name);
  return s || { stage: name, argv: null, exit_status: null, signal: null, duration_ms: 0, stdout: '', stderr: '' };
}

// out_files[].path is WORK-relative as the frozen adapter emits it
// ('case-<name>/<rel>'); the pin keys are case-relative. The adapter's case
// dirs live under CASES_ROOT (<invocation>/work on a real run).
function caseRel(c, rel) { return 'case-' + c.name + '/' + rel; }

function producedArtifact(c, rel) {
  const pin = PINS.artifacts[rel];
  if (!pin) { no('no pin for artifact ' + rel); return null; }
  const rec = c.out_files.find((f) => f.path === caseRel(c, rel));
  if (!rec) { no('artifact missing from out_files: ' + rel); return null; }
  if (rec.sha256 !== pin.sha256 || rec.bytes !== pin.bytes) {
    no('out_files record mismatch for ' + rel + ': recorded ' + rec.sha256 + '/' + rec.bytes +
       ', pinned ' + pin.sha256 + '/' + pin.bytes);
    return null;
  }
  const abs = path.join(CASES_ROOT, caseRel(c, rel));
  let live;
  try { live = hashFile(abs); } catch (e) { no('artifact unreadable at ' + abs); return null; }
  if (live !== pin.sha256) { no('work copy hash mismatch for ' + rel); return null; }
  const st = fs.statSync(abs);
  if (st.size !== pin.bytes) { no('work copy size mismatch for ' + rel); return null; }
  return rec;
}

function requireStdoutRe(c, stageName, regexes) {
  const s = stageOf(c, stageName);
  // the pinned REs are ^...$ line-anchored; test per line, not the whole blob
  const lines = String(s.stdout).split('\n');
  for (const re of regexes) {
    if (!lines.some((line) => re.test(line))) { no(stageName + ' stdout missing /' + re.source + '/'); }
  }
}

function requireEitherLines(c, stageName, lines) {
  const s = stageOf(c, stageName);
  const hay = (s.stdout + '\n' + s.stderr).split('\n');
  for (const line of lines) {
    if (!hay.includes(line)) {
      no(stageName + ' neither-stream line missing: ' + JSON.stringify(line.slice(0, 72)));
    }
  }
}

function requireEitherRe(c, stageName, regexes) {
  const s = stageOf(c, stageName);
  for (const re of regexes) {
    if (!re.test(s.stdout) && !re.test(s.stderr)) {
      no(stageName + ' neither-stream regex missing: ' + re.source.slice(0, 60));
    }
  }
}

function peakRssValues(rec) {
  const out = [];
  const hay = rec.stdout + '\n' + rec.stderr;
  // matches all three script forms: "peak RSS at start: 0.05 GB",
  // "peak RSS   : 7.15 GB" and "(peak RSS 7.15 GB)"
  const re = /peak RSS(?: at start)?\s*:?\s*(\d+(?:\.\d+)?) GB/g;
  let m;
  while ((m = re.exec(hay)) !== null) out.push(parseFloat(m[1]));
  return out;
}

function pyBin() {
  const candidates = [];
  if (process.env.RCOS_HUNYUAN_PYTHON) candidates.push(process.env.RCOS_HUNYUAN_PYTHON);
  candidates.push(path.join(os.homedir(), 'venvs', 'hunyuan3d-mlx', 'bin', 'python'));
  for (const p of candidates) {
    try { fs.accessSync(p, fs.constants.X_OK); return p; } catch (e) { /* next */ }
  }
  return null;
}

function runHelper(glbAbs) {
  const bin = pyBin();
  if (!bin) { no('no interpreter for measurement helper'); return null; }
  const helper = path.join(EVALDIR, 'gates', 'measure_mesh.py');
  const r = spawnSync(bin, [helper, glbAbs], { cwd: WORK, timeout: 240000, encoding: 'utf8' });
  if (r.error || r.status !== 0) {
    no('measurement helper failed: ' + (r.stderr || String(r.error)).split('\n')[0]);
    return null;
  }
  const lines = r.stdout.split('\n').filter((l) => l.trim() !== '');
  return JSON.parse(lines[lines.length - 1]);
}

function floatEq(a, b) {
  if (Array.isArray(a)) return a.length === b.length && a.every((x, i) => floatEq(x, b[i]));
  return Math.abs(a - b) <= 1e-9;
}

function observationPath() {
  const candidates = [];
  if (process.env.RCOS_INVOCATION_DIR) candidates.push(path.join(process.env.RCOS_INVOCATION_DIR, 'output.json'));
  candidates.push(path.join(RUN, 'output.json'));
  candidates.push(path.join(EVIDENCE, 'outputs', 'output.json'));
  for (const p of candidates) { try { fs.accessSync(p); return p; } catch (e) { /* next */ } }
  return null;
}

// ---------------------------------------------------------------------------
// preflight: evidence structural integrity (any problem = FAIL, not blocked)
// ---------------------------------------------------------------------------
function caseEvidenceProblems(obs) {
  const problems = [];
  for (const c of obs.cases) {
    const caseDir = path.join(CASES_ROOT, 'case-' + c.name);
    // source copy in work matches the recorded identity
    try {
      const srcAbs = path.join(caseDir, 'ref_source.png');
      if (hashFile(srcAbs) !== c.source.sha256) problems.push(c.name + ': source copy hash mismatch');
      if (fs.statSync(srcAbs).size !== c.source.bytes) problems.push(c.name + ': source copy size mismatch');
    } catch (e) { problems.push(c.name + ': source copy unreadable: ' + e.message); }
    // stage evidence: stream copies byte-equal the observation, argv cross-checks
    for (const s of c.stages) {
      const base = 'case-' + c.name + '.' + s.stage;
      try {
        if (fs.readFileSync(path.join(EVIDENCE, base + '.stdout.txt'), 'utf8') !== s.stdout) {
          problems.push(c.name + '/' + s.stage + ': stdout evidence copy differs from observation');
        }
        if (fs.readFileSync(path.join(EVIDENCE, base + '.stderr.txt'), 'utf8') !== s.stderr) {
          problems.push(c.name + '/' + s.stage + ': stderr evidence copy differs from observation');
        }
        const argv = readJson(path.join(EVIDENCE, base + '.argv.json'));
        if (!deepEq(argv.argv, s.argv)) problems.push(c.name + '/' + s.stage + ': argv evidence mismatch');
        if (argv.cwd !== caseDir) problems.push(c.name + '/' + s.stage + ': argv cwd mismatch: ' + argv.cwd);
        if (!String(argv.interpreter || '').endsWith(PINS.interp_suffix)) {
          problems.push(c.name + '/' + s.stage + ': argv interpreter not the pinned venv');
        }
      } catch (e) { problems.push(c.name + '/' + s.stage + ': evidence unreadable: ' + e.message); }
    }
    // out_files: work copy AND evidence copy must both exist and agree
    for (const f of (c.out_files || [])) {
      try {
        const workAbs = path.join(CASES_ROOT, f.path);
        if (hashFile(workAbs) !== f.sha256) problems.push(c.name + ': work copy mismatch ' + f.path);
        const evName = 'case-' + c.name + '.' + f.path.replace(/\//g, '__');
        const evAbs = path.join(EVIDENCE, evName);
        if (hashFile(evAbs) !== f.sha256) problems.push(c.name + ': evidence copy mismatch ' + evName);
      } catch (e) { problems.push(c.name + ': artifact unreadable ' + f.path + ': ' + e.message); }
    }
  }
  return problems;
}

// ---------------------------------------------------------------------------
// gates
// ---------------------------------------------------------------------------
const GATES = {

  prep_reference_reproduced(c) {
    const prep = stageOf(c, 'prep');
    if (!prep) return no('prep stage missing');
    if (prep.exit_status !== 0 || prep.signal !== null) return no('prep did not exit 0');
    if (prep.stdout !== PREP_STDOUT_EXACT) {
      return no('prep stdout not byte-exact (got ' + prep.stdout.length + ' bytes, pinned ' + PREP_STDOUT_EXACT.length + ')');
    }
    if (!producedArtifact(c, 'ref_518_full.png')) return;
    if (!producedArtifact(c, 'ref_518.png')) return;
    const rec = c.out_files.find((f) => f.path === caseRel(c, 'ref_518.png'));
    if (!rec.png || rec.png.width !== 518 || rec.png.height !== 518) no('ref_518.png png fact wrong');
    ok('prep stdout byte-exact, both prep artifacts reproduce');
  },

  shape_reproduced(c) {
    const before = fails;
    const s = stageOf(c, 'shape');
    if (!s) return no('shape stage missing');
    if (s.exit_status !== 0 || s.signal !== null) return no('shape did not exit 0');
    requireStdoutRe(c, 'shape', SHAPE_STDOUT_RE);
    requireEitherLines(c, 'shape', SHAPE_EITHER_LINES);
    requireEitherRe(c, 'shape', SHAPE_EITHER_RE);
    producedArtifact(c, 'out_shape/shape.glb');
    producedArtifact(c, 'out_shape/white_mesh_remesh.obj');
    if (fails === before) ok('shape stdout pins + both shape artifacts reproduce');
  },

  shape_topology_measured(c) {
    const h = runHelper(path.join(CASES_ROOT, 'case-' + c.name, 'out_shape', 'shape.glb'));
    if (!h) return;
    if (h.verts !== SHAPE_MESH.verts) no('shape verts ' + h.verts + ' != ' + SHAPE_MESH.verts);
    if (h.faces !== SHAPE_MESH.faces) no('shape faces ' + h.faces + ' != ' + SHAPE_MESH.faces);
    if (h.watertight !== SHAPE_MESH.watertight) no('shape watertight ' + h.watertight);
    if (!floatEq(h.extents, SHAPE_MESH.extents)) no('shape extents ' + JSON.stringify(h.extents));
    if (!floatEq(h.bounds, SHAPE_MESH.bounds)) no('shape bounds ' + JSON.stringify(h.bounds));
    if (!deepEq(h.glb, SHAPE_MESH.glb)) no('shape glb facts ' + JSON.stringify(h.glb));
    // cross-check the helper against the script's own stdout counts
    const s = stageOf(c, 'shape');
    const m = /generated in \d+\.\d+s \((\d+) verts, (\d+) faces\)/.exec(s.stdout + '\n' + s.stderr);
    if (!m) no('shape stdout has no generated counts line');
    else if (Number(m[1]) !== h.verts || Number(m[2]) !== h.faces) {
      no('stdout counts (' + m[1] + ',' + m[2] + ') != helper (' + h.verts + ',' + h.faces + ')');
    } else ok('helper topology matches script stdout counts');
    ok('shape.glb helper measurement matches pins (286384v/572904f watertight)');
  },

  texture_artifacts_reproduced(c) {
    const before = fails;
    const s = stageOf(c, 'texture');
    if (!s) return no('texture stage missing');
    if (s.exit_status !== 0 || s.signal !== null) return no('texture did not exit 0');
    requireStdoutRe(c, 'texture', TEXTURE_STDOUT_RE);
    requireEitherLines(c, 'texture', TEXTURE_EITHER_LINES);
    requireEitherRe(c, 'texture', TEXTURE_EITHER_RE);
    producedArtifact(c, 'out_tex/material.mtl');
    producedArtifact(c, 'out_tex/paint_pbr.png');
    producedArtifact(c, 'out_tex/textured.glb');
    producedArtifact(c, 'out_tex/textured.obj');
    if (fails === before) ok('texture stdout pins + all four texture artifacts reproduce');
  },

  texture_measurements(c) {
    const h = runHelper(path.join(CASES_ROOT, 'case-' + c.name, 'out_tex', 'textured.glb'));
    if (!h) return;
    if (h.verts !== TEXTURED_MESH.verts) no('textured verts ' + h.verts + ' != ' + TEXTURED_MESH.verts);
    if (h.faces !== TEXTURED_MESH.faces) no('textured faces ' + h.faces + ' != ' + TEXTURED_MESH.faces);
    if (h.watertight !== TEXTURED_MESH.watertight) no('textured watertight ' + h.watertight);
    if (!floatEq(h.extents, TEXTURED_MESH.extents)) no('textured extents ' + JSON.stringify(h.extents));
    if (!deepEq(h.glb, TEXTURED_MESH.glb)) no('textured glb facts ' + JSON.stringify(h.glb));
    const rec = c.out_files.find((f) => f.path === caseRel(c, 'out_tex/textured.glb'));
    if (rec && rec.glb && h.glb) {
      if (rec.glb.version !== h.glb.version || rec.glb.json_bytes !== h.glb.json_bytes) {
        no('adapter glb record disagrees with helper');
      }
    }
    for (const rel of Object.keys(PNG_FACTS)) {
      const r = c.out_files.find((f) => f.path === caseRel(c, rel));
      const want = PNG_FACTS[rel];
      if (!r || !r.png) { no('no png fact recorded for ' + rel); continue; }
      if (!deepEq(r.png, want)) no('png fact for ' + rel + ': ' + JSON.stringify(r.png) + ' != ' + JSON.stringify(want));
    }
    ok('textured.glb helper measurement + png facts match pins (25633v/40000f, 2 images)');
  },

  e2e_repeat_consistent(obs) {
    const c1 = obs.cases.find((x) => x.name === E2E);
    const c2 = obs.cases.find((x) => x.name === REPEAT);
    if (!c1 || !c2) return no('missing e2e or repeat case');
    if (c1.outcome !== 'embedded' || c2.outcome !== 'embedded') return no('an e2e case did not embed');
    for (const rel of Object.keys(PINS.artifacts)) {
      const r1 = c1.out_files.find((f) => f.path === caseRel(c1, rel));
      const r2 = c2.out_files.find((f) => f.path === caseRel(c2, rel));
      if (!r1 || !r2) { no('repeat missing artifact ' + rel); continue; }
      if (r1.sha256 !== r2.sha256) no('repeat artifact differs: ' + rel);
    }
    if (stageOf(c1, 'prep').stdout !== stageOf(c2, 'prep').stdout) no('repeat prep stdout differs');
    const s1 = stageOf(c1, 'shape'); const s2 = stageOf(c2, 'shape');
    for (const line of SHAPE_EITHER_LINES) {
      const hay1 = s1.stdout + '\n' + s1.stderr; const hay2 = s2.stdout + '\n' + s2.stderr;
      if (hay1.includes(line) !== hay2.includes(line)) no('repeat shape line differs: ' + line.slice(0, 50));
    }
    const t1 = stageOf(c1, 'texture'); const t2 = stageOf(c2, 'texture');
    for (const line of TEXTURE_EITHER_LINES) {
      const hay1 = t1.stdout + '\n' + t1.stderr; const hay2 = t2.stdout + '\n' + t2.stderr;
      if (hay1.includes(line) !== hay2.includes(line)) no('repeat texture line differs: ' + line.slice(0, 50));
    }
    if (s1.argv.join(' ') !== s2.argv.join(' ')) no('repeat shape argv differs');
    if (t1.argv.join(' ') !== t2.argv.join(' ')) no('repeat texture argv differs');
    ok('repeat case: all 8 artifacts byte-identical + deterministic stdout lines identical');
  },

  empty_source_refused(obs) {
    const c = obs.cases.find((x) => x.name === EMPTY);
    if (!c) return no('refusal case missing');
    const before = fails;
    if (c.outcome !== 'refused') return no('outcome ' + c.outcome + ' != refused');
    if (c.source.sha256 !== PINS.fixtures['empty-source.png'].sha256 || c.source.bytes !== 0) {
      no('refusal source identity wrong');
    }
    if (c.source.png !== null) no('refusal source png fact not null');
    if (c.stages.length !== 1) no('refusal ran ' + c.stages.length + ' stages');
    const prep = c.stages[0];
    if (!prep || prep.stage !== 'prep') no('refusal first stage not prep');
    if (prep.exit_status !== 1) no('refusal exit ' + prep.exit_status + ' != 1');
    if (prep.stdout !== '') no('refusal stdout not empty');
    for (const re of REFUSAL_RE) {
      if (!re.test(prep.stderr)) no('refusal stderr missing /' + re.source + '/');
    }
    if ((c.out_files || []).length !== 0) no('refusal produced out_files');
    if (c.duration_ms >= BUDGETS.empty_ms) no('refusal took ' + c.duration_ms + 'ms');
    if (fails === before) ok('0-byte source refused: prep exit 1, empty stdout, UnidentifiedImageError, nothing downstream ran');
  },

  torch_free_asserted() {
    for (const name of ['run_shape.py', 'run_texture.py']) {
      const bytes = fs.readFileSync(path.join(ADAPTER_DIR, name), 'utf8');
      if (!bytes.includes('assert "torch" not in sys.modules')) no(name + ': torch-free assert line missing');
      if (/^\s*import torch\b/m.test(bytes)) no(name + ': contains a bare torch import');
    }
    const obs = GATES.__obs;
    for (const cn of [E2E]) {
      const c = obs.cases.find((x) => x.name === cn);
      if (!c) { no(cn + ': case record missing'); continue; }
      const shape = stageOf(c, 'shape');
      const tex = stageOf(c, 'texture');
      if (shape.exit_status !== 0 || tex.exit_status !== 0) {
        no(cn + ': e2e stages did not exit 0 (case ' + c.outcome + ')');
      }
    }
    const deps = readJson(path.join(EVIDENCE, 'deps.json'));
    if (!deepEq(deps, PINS.deps)) no('deps.json ' + JSON.stringify(deps) + ' != pins');
    ok('torch-free: assert lines in frozen bytes, stages exited 0, deps carry no torch');
  },

  source_identity_pinned() {
    const patchBytes = fs.readFileSync(path.join(EVALDIR, 'fixtures', 'pipeline_mlx-PR8.patch'));
    if (sha256(patchBytes) !== PINS.upstream.patch) no('fixture patch hash != pin');
    // the pin is home-relative (run.js homeRel tries RCOS_HOME then ~)
    let repo = path.join(HOME, PINS.upstream.repo);
    if (!fs.existsSync(path.join(repo, '.git'))) repo = path.join(os.homedir(), PINS.upstream.repo);
    const g1 = spawnSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8', timeout: 30000 });
    if (g1.error || g1.status !== 0) return no('git rev-parse failed: ' + (g1.stderr || g1.error));
    if (g1.stdout.trim() !== PINS.upstream.head) no('repo head ' + g1.stdout.trim() + ' != pin');
    const g2 = spawnSync('git', ['-C', repo, 'diff'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 30000 });
    if (g2.error || g2.status !== 0) return no('git diff failed: ' + (g2.stderr || g2.error));
    const livePatch = g2.stdout;
    if (sha256(livePatch) !== PINS.upstream.patch) no('live git diff hash != pin');
    if (livePatch !== patchBytes.toString('utf8')) no('live git diff bytes != fixture patch bytes');
    const hubRoot = process.env.HF_HOME
      ? path.join(process.env.HF_HOME, 'hub')
      : path.join(os.homedir(), '.cache', 'huggingface', 'hub');
    const snapDir = path.join(hubRoot, 'models--dgrauet--hunyuan3d-2.1-mlx', 'snapshots');
    const snaps = fs.readdirSync(snapDir).filter((d) => !d.startsWith('.'));
    if (snaps.length !== 1 || snaps[0] !== PINS.upstream.snapshot) {
      no('weights snapshot scan: ' + JSON.stringify(snaps) + ' != [' + PINS.upstream.snapshot + ']');
    }
    ok('upstream identity re-derived live: head, patch (byte-equal to fixture), snapshot');
  },

  interpreter_declared() {
    const bin = pyBin();
    if (!bin) return no('no pinned interpreter on this machine');
    const r = spawnSync(bin, ['-c', PROBE_SNIPPET], { encoding: 'utf8', timeout: 60000 });
    if (r.error || r.status !== 0) return no('interpreter probe failed: ' + (r.stderr || r.error));
    let live;
    try { live = JSON.parse(r.stdout.split('\n').filter((l) => l.trim())[0]); } catch (e) {
      return no('probe output unparseable: ' + r.stdout.slice(0, 80));
    }
    if (!deepEq(live, PINS.deps)) no('live interpreter ' + JSON.stringify(live) + ' != pins');
    ok('live interpreter probe matches declared pins (python ' + PINS.deps.python + ', mlx ' + PINS.deps.mlx + ')');
  },

  frozen_source_pinned() {
    for (const [name, pin] of Object.entries(PINS.scripts)) {
      const abs = path.join(ADAPTER_DIR, name);
      let live;
      try { live = hashFile(abs); } catch (e) { no('frozen script unreadable: ' + name); continue; }
      if (live !== pin) no('frozen script hash drift: ' + name);
    }
    if (hashFile(path.join(ADAPTER_DIR, 'run.js')) !== PINS.adapter_sha) no('adapter run.js hash drift');
    if (hashFile(path.join(HOME, CAP, 'contract.json')) !== PINS.contract_sha) no('contract.json hash drift');
    if (hashFile(path.join(EVALDIR, 'gates', 'measure_mesh.py')) !== PINS.helper_sha) no('helper hash drift');
    const frozen = fs.readFileSync(path.join(EVIDENCE, 'frozen.sha256'), 'utf8');
    for (const [name, pin] of Object.entries(PINS.scripts)) {
      if (!frozen.includes(pin + '  ' + name)) no('frozen.sha256 missing pin line for ' + name);
    }
    ok('frozen sources on disk, in observation, and in evidence all match pins');
  },

  budgets_within_declared(obs) {
    for (const cn of [E2E, REPEAT]) {
      const c = obs.cases.find((x) => x.name === cn);
      const b = { prep: BUDGETS.prep_ms, shape: BUDGETS.shape_ms, texture: BUDGETS.texture_ms };
      for (const s of c.stages) {
        if (s.duration_ms >= b[s.stage]) no(cn + '/' + s.stage + ' over budget: ' + s.duration_ms + 'ms');
        if (s.signal !== null) no(cn + '/' + s.stage + ' was signalled: ' + s.signal);
        for (const v of peakRssValues(s)) {
          if (v > BUDGETS.peak_rss_gb) no(cn + '/' + s.stage + ' peak RSS ' + v + ' GB > ' + BUDGETS.peak_rss_gb);
        }
      }
      if (c.duration_ms >= BUDGETS.case_ms) no(cn + ' over case budget: ' + c.duration_ms + 'ms');
    }
    ok('all stages within declared budgets, peak RSS <= ' + BUDGETS.peak_rss_gb + ' GB, no signals');
  },

  artifact_identity_pinned(obs) {
    const input = readJson(path.join(RUN, 'input.json'));
    if (input.eval_sha256 !== hashFile(path.join(EVALDIR, 'eval.json'))) no('input.json eval_sha256 != eval.json bytes');
    if (!deepEq(input.fixtures, Object.entries(PINS.fixtures).map(([name, v]) => ({ name, sha256: v.sha256, bytes: v.bytes })))) {
      no('input.json fixtures != pins');
    }
    const ciPath = path.join(RUN, 'capability-input.json');
    const ci = input.capability_input || {};
    if (ci.path !== 'capability-input.json' || ci.sha256 !== hashFile(ciPath)) no('capability-input.json freeze mismatch');
    const capIn = readJson(ciPath);
    if (capIn.cases.length !== 3) no('capability_input cases != 3');
    if (capIn.cases[0].operation !== 'e2e' || !String(capIn.cases[0].source).endsWith('/bearing-ref.png')) no('case0 identity wrong');
    if (capIn.cases[1].operation !== 'e2e' || !String(capIn.cases[1].source).endsWith('/bearing-ref.png')) no('case1 identity wrong');
    if (!String(capIn.cases[2].source).endsWith('/empty-source.png')) no('case2 identity wrong');
    for (const [name, v] of Object.entries(PINS.fixtures)) {
      if (hashFile(path.join(EVALDIR, 'fixtures', name)) !== v.sha256) no('eval fixture drift: ' + name);
      if (hashFile(path.join(WORK, name)) !== v.sha256) no('work fixture drift: ' + name);
      if (hashFile(path.join(RUN, 'evidence', 'inputs', name)) !== v.sha256) no('evidence fixture drift: ' + name);
    }
    for (const cn of [E2E, REPEAT]) {
      const c = obs.cases.find((x) => x.name === cn);
      if ((c.out_files || []).length !== 8) no(cn + ' out_files length ' + (c.out_files || []).length + ' != 8');
      for (const [rel, pin] of Object.entries(PINS.artifacts)) {
        const r = c.out_files.find((f) => f.path === caseRel(c, rel));
        if (!r || r.sha256 !== pin.sha256 || r.bytes !== pin.bytes) no(cn + ' artifact pin mismatch: ' + rel);
      }
    }
    ok('freeze layer verified: eval bytes, fixtures triple-located, 8/8 artifacts pinned per e2e case');
  },

  oracle_eval2_lineage() {
    const oracle = path.join(HOME, 'evidence', 'hunyuan3d-mlx-local', 'eval-2');
    for (const [rel, pin] of Object.entries(PINS.artifacts)) {
      let live;
      try { live = hashFile(path.join(oracle, rel)); } catch (e) {
        no('eval-2 oracle unreadable: ' + rel + ' (lineage not verifiable here)');
        continue;
      }
      if (live !== pin.sha256) no('eval-2 oracle drift: ' + rel);
    }
    ok('all 8 pins byte-match the committed eval-2 oracle (2026-09-17) and were re-proven by the 2026-09-18 probe before this package existed');
  },
};

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
try {
  if (process.argv[2] === '--list') {
    console.log(Object.keys(GATES).join('\n'));
    process.exit(0);
  }
  gid = process.argv[2];
  if (!gid || !Object.prototype.hasOwnProperty.call(GATES, gid)) {
    console.error('unknown gate id: ' + gid);
    process.exit(4);
  }
  const obsPath = observationPath();
  if (!obsPath) { console.error('observation not found'); process.exit(4); }
  const obs = readJson(obsPath);
  if (obs.schema !== 'hunyuan3d-mlx-local-observation/1') {
    console.error('unexpected observation schema: ' + obs.schema);
    process.exit(4);
  }
  GATES.__obs = obs;
  const problems = caseEvidenceProblems(obs);
  if (problems.length > 0) {
    for (const p of problems) console.log('[gate] evidence-problem: ' + p);
    process.exit(3);
  }
  const g = GATES[gid];
  // gate bodies receive either the e2e case or the whole observation
  const OBS_GATES = ['e2e_repeat_consistent', 'empty_source_refused',
                     'torch_free_asserted', 'budgets_within_declared',
                     'artifact_identity_pinned'];
  const e2eCase = obs.cases.find((x) => x.name === E2E);
  if (!e2eCase) { console.error('e2e case missing from observation'); process.exit(4); }
  if (OBS_GATES.includes(gid)) g(obs); else g(e2eCase);
  process.exit(fails > 0 ? 3 : 0);
} catch (e) {
  console.error('gate crashed: ' + (e && e.stack ? e.stack.split('\n').slice(0, 4).join(' | ') : e));
  process.exit(4);
}
