#!/usr/bin/env node
'use strict';
// Adapter for hunyuan3d-mlx-local (image -> textured 3D asset, Mac-local, $0).
//
// The capability is three frozen scripts beside this file, executed as one
// chain per case in the case's own scratch directory:
//
//   prep_reference.py <src> <dst>
//       background removal + recenter to a 518x518 reference; writes
//       ref_518_full.png then ref_518.png. Exits 1 on an unreadable source
//       (e.g. PIL UnidentifiedImageError on a 0-byte PNG) and on any other
//       uncaught error; both look the same to this adapter.
//   run_shape.py <ref.png> <out_dir>
//       seeded (42) MLX shape generation; writes out_dir/shape.glb and
//       out_dir/white_mesh_remesh.obj. Exits 2 on wrong arity, 1 on any
//       uncaught error (its own torch-free assert included).
//   run_texture.py <mesh.glb> <ref.png> <out_dir>
//       MLX PBR texture synthesis; writes out_dir/{textured.obj,textured.glb,
//       material.mtl,paint_pbr.png}. Same exit semantics as run_shape.py.
//
// The scripts are not modified, re-implemented, or patched here. Each stage's
// argv uses cwd-relative paths (the case scratch dir is the cwd), so the
// scripts' own stdout path lines are constant across invocations. The adapter
// never judges the output: every value in the observation is an argv, one of
// the scripts' own output streams, a header fact of a file a stage read or
// wrote, or an environment identity measured at run time. It cannot turn a
// failed stage into a passing record: the first nonzero (or signaled) stage
// stops the chain and the remaining stages are simply not run — their absence
// from the stages array is the receipt that they did not run.
//
// Exit-code semantics of the ADAPTER (not the scripts): 0 = ran and wrote the
// observation; 4 = could not run (missing kernel env, malformed input,
// duplicate case names, unreadable source file, no usable interpreter, or a
// failing dependency probe). Per-stage chain outcomes: exit 0 = the stage
// succeeded; exit 1 = refused (the scripts' documented refusal/traceback code
// — the streams decide what kind); exit 2 = errored (arity misuse); any other
// exit or a signal other than the adapter's own timeout = errored; SIGTERM =
// this adapter's timeout fired (timed_out).
//
// Interpreter resolution, in order: $RCOS_HUNYUAN_PYTHON if set, else
// ~/venvs/hunyuan3d-mlx/bin/python under the current user's home. A one-shot
// dependency probe (python, mlx, numpy, trimesh, rembg, pillow via
// importlib.metadata) runs before any case; a missing or broken interpreter
// is cannotRun (exit 4), never a fabricated case record. The interpreter, the
// upstream hunyuan3d-2.1-mlx checkout ($RCOS_HUNYUAN_REPO, else
// ~/tools/hunyuan3d-2.1-mlx) and the HF weights snapshot are ENVIRONMENT, not
// committed capability bytes; the adapter MEASURES their identity at run time
// (git head + working-tree diff hash, snapshot directory scan — all nullable)
// and the gates pin the expected values.
//
// Kernel interface (lib/invocation.js): the input document is at $RCOS_INPUT,
// the result goes to $RCOS_OUTPUT, supporting files go under
// $RCOS_EVIDENCE_DIR, and the process cwd is the invocation work dir
// ($RCOS_INVOCATION_WORK_DIR). Exit 4 = could not run; exit 0 = ran and wrote
// a result.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

// Observed wall-clock envelope (Mac, pinned env): prep ~15s, shape ~478-493s,
// texture ~404s. Timeouts are several times the envelope; SIGTERM from one of
// these is recorded as timed_out, never retried.
const STAGE_TIMEOUT_MS = { prep: 300000, shape: 1500000, texture: 1500000 };
const SRC_NAME = 'ref_source.png';
const PROBE_SNIPPET =
  "import json,sys;" +
  "from importlib.metadata import version as _v;" +
  "print(json.dumps({'python':sys.version.split()[0],'mlx':_v('mlx')," +
  "'numpy':_v('numpy'),'trimesh':_v('trimesh'),'rembg':_v('rembg')," +
  "'pillow':_v('pillow')}))";
// The observation's stdout/stderr strings are capped by the contract; if a
// stream ever exceeds the cap the tail is kept (the measurement lines live at
// the end) and the full raw bytes go to evidence untruncated.
const STREAM_CAP = 20000;

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

const SCRIPTS = ['prep_reference.py', 'run_shape.py', 'run_texture.py']
  .map((name) => {
    const abs = path.join(__dirname, name);
    return { name, abs, sha256: sha256(fs.readFileSync(abs)) };
  });
const USAGE = {
  'prep_reference.py': 'prep_reference.py <src> <dst> — rembg + recenter to 518x518; writes <dst>_full.png then <dst>',
  'run_shape.py': 'run_shape.py <ref.png> <out_dir> — seeded MLX shape gen; writes out_dir/shape.glb + white_mesh_remesh.obj',
  'run_texture.py': 'run_texture.py <mesh.glb> <ref.png> <out_dir> — MLX PBR texture; writes out_dir/{textured.obj,textured.glb,material.mtl,paint_pbr.png}',
};

function resolveInterpreter() {
  const candidates = [];
  if (process.env.RCOS_HUNYUAN_PYTHON) candidates.push(process.env.RCOS_HUNYUAN_PYTHON);
  candidates.push(path.join(os.homedir(), 'venvs', 'hunyuan3d-mlx', 'bin', 'python'));
  for (const p of candidates) {
    try {
      fs.accessSync(p, fs.constants.X_OK);
      return p;
    } catch (e) {
      // try the next candidate
    }
  }
  cannotRun('no usable interpreter: set RCOS_HUNYUAN_PYTHON or provide ~/venvs/hunyuan3d-mlx/bin/python');
}

const PYTHON = resolveInterpreter();

// The interpreter's dependency versions are measured, not asserted; mlx has no
// __version__ attribute, so everything resolves through importlib.metadata.
function probeInterpreter(pythonAbs) {
  const res = spawnSync(pythonAbs, ['-c', PROBE_SNIPPET], { encoding: 'utf8', timeout: 60000 });
  const err = res.error;
  if (err && err.code !== 'ETIMEDOUT') {
    cannotRun('could not start interpreter ' + pythonAbs + ': ' + err.message);
  }
  if (res.status !== 0) {
    cannotRun('dependency probe failed for ' + pythonAbs +
      ' (exit ' + String(res.status) + '): ' + (res.stderr || '').trim().slice(0, 500));
  }
  let deps;
  try {
    deps = JSON.parse((res.stdout || '').trim().split('\n').pop());
  } catch (e) {
    cannotRun('dependency probe produced unparseable output: ' + (res.stdout || '').slice(0, 200));
  }
  for (const k of ['python', 'mlx', 'numpy', 'trimesh', 'rembg', 'pillow']) {
    if (typeof deps[k] !== 'string' || !deps[k]) cannotRun('dependency probe missing ' + k);
  }
  return deps;
}

const DEPS = probeInterpreter(PYTHON);

// Recorded paths are invocation-relative wherever they can be, so a copied
// invocation's record still reads correctly in the copy.
function workRel(p) {
  const rel = path.relative(WORK, p);
  return rel && !rel.startsWith('..') && !path.isAbsolute(rel) ? rel.split(path.sep).join('/') : p;
}

// Scripts and (when they live under the home) the interpreter/upstream repo
// are recorded relative to RCOS_HOME or the user's home, so the record
// survives a copied home. No absolute user path is embedded in these lines.
function homeRel(p) {
  for (const base of [HOME, os.homedir()]) {
    const rel = path.relative(base, p);
    if (rel && !rel.startsWith('..') && !path.isAbsolute(rel)) return rel.split(path.sep).join('/');
  }
  return p;
}

// Header only: the scripts' own bytes decide what the images contain, and the
// gates re-read the pixels. This asks the file, not PIL.
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

// GLB container header + the asset block of the embedded JSON chunk. Header
// facts only: the gates decide what the asset must be.
function glbHeader(buf) {
  if (buf.length < 20) return null;
  if (buf.readUInt32LE(0) !== 0x46546c67) return null; // 'glTF' little-endian
  if (buf.toString('latin1', 8, 12) !== 'JSON') return null;
  const version = buf.readUInt32LE(4);
  const jsonBytes = buf.readUInt32LE(12);
  let assetVersion = null;
  let generator = null;
  try {
    const json = JSON.parse(buf.toString('utf8', 20, 20 + jsonBytes));
    if (json.asset && typeof json.asset.version === 'string') assetVersion = json.asset.version;
    if (json.asset && typeof json.asset.generator === 'string') {
      generator = json.asset.generator.slice(0, 200);
    }
  } catch (e) {
    // keep the container facts, drop the JSON-derived ones
  }
  return { version, json_bytes: jsonBytes, asset_version: assetVersion, generator };
}

function fileEntry(abs) {
  const buf = fs.readFileSync(abs);
  const isGlb = abs.endsWith('.glb');
  return {
    path: workRel(abs),
    sha256: sha256(buf),
    bytes: buf.length,
    png: pngHeader(buf),
    glb: isGlb ? glbHeader(buf) : null,
  };
}

function clipStream(s) {
  return s.length <= STREAM_CAP ? s : s.slice(s.length - STREAM_CAP);
}

// One chain stage. argv is built with cwd-relative paths so the scripts' own
// stdout path lines are constant across invocations.
function stageArgv(stage, caseDir) {
  const abs = SCRIPTS.find((s) => s.name === stage.script).abs;
  if (stage.stage === 'prep') return [abs, SRC_NAME, 'ref_518.png'];
  if (stage.stage === 'shape') return [abs, 'ref_518.png', 'out_shape'];
  return [abs, 'out_shape/shape.glb', 'ref_518.png', 'out_tex'];
}

const CHAIN = [
  { stage: 'prep', script: 'prep_reference.py' },
  { stage: 'shape', script: 'run_shape.py' },
  { stage: 'texture', script: 'run_texture.py' },
];

function outcomeOf(exitStatus, signal) {
  if (signal === 'SIGTERM') return 'timed_out';
  if (exitStatus === 0) return 'embedded';
  if (exitStatus === 1) return 'refused';
  return 'errored';
}

// The stage's own copy of its streams, argv and produced bytes, so a later
// reader never has to trust this record or the work dir's survival. The
// .stdout.txt/.stderr.txt copies are byte-identical to the observation
// strings (the gates re-hash them); .raw-* copies keep the untruncated bytes.
function writeStageEvidence(c, rec) {
  const base = 'case-' + c.name + '.' + rec.stage;
  fs.writeFileSync(path.join(EVIDENCE, base + '.stdout.txt'), rec.stdout);
  fs.writeFileSync(path.join(EVIDENCE, base + '.stderr.txt'), rec.stderr);
  fs.writeFileSync(path.join(EVIDENCE, base + '.argv.json'),
    JSON.stringify({ argv: rec.argv, interpreter: PYTHON, cwd: path.join(WORK, 'case-' + c.name),
      exit_status: rec.exit_status, signal: rec.signal, duration_ms: rec.duration_ms }, null, 2) + '\n');
  return base;
}

function runCase(c) {
  const started = Date.now();
  const caseDir = path.join(WORK, 'case-' + c.name);
  fs.mkdirSync(caseDir, { recursive: true });
  // prep reads SRC_NAME relative to its cwd: the source is copied under THAT
  // name, whatever the case's source path is called.
  fs.copyFileSync(c.source, path.join(caseDir, SRC_NAME));

  const stages = [];
  let chainOutcome = null;
  for (const stage of CHAIN) {
    const argv = stageArgv(stage, caseDir);
    const t0 = Date.now();
    const res = spawnSync(PYTHON, argv, {
      cwd: caseDir,
      encoding: 'utf8',
      timeout: STAGE_TIMEOUT_MS[stage.stage],
      maxBuffer: 64 * 1024 * 1024,
    });
    if (res.error && res.error.code !== 'ETIMEDOUT') {
      cannotRun('could not start interpreter: ' + res.error.message);
    }
    const rec = {
      stage: stage.stage,
      argv,
      exit_status: typeof res.status === 'number' ? res.status : null,
      signal: res.signal || null,
      duration_ms: Date.now() - t0,
      stdout: clipStream(res.stdout || ''),
      stderr: clipStream(res.stderr || ''),
    };
    const evidenceBase = writeStageEvidence(c, rec);
    if (rec.stdout.length < (res.stdout || '').length) {
      fs.writeFileSync(path.join(EVIDENCE, evidenceBase + '.raw-stdout.txt'), res.stdout || '');
    }
    if (rec.stderr.length < (res.stderr || '').length) {
      fs.writeFileSync(path.join(EVIDENCE, evidenceBase + '.raw-stderr.txt'), res.stderr || '');
    }
    stages.push(rec);
    if (rec.exit_status !== 0 || rec.signal) {
      chainOutcome = outcomeOf(rec.exit_status, rec.signal);
      break;
    }
  }
  if (!chainOutcome) chainOutcome = 'embedded';

  // Everything the chain left in its scratch dir except the source this
  // adapter placed: on success the prep intermediates + shape + texture
  // artifacts; on refusal only what the failing stage managed to write.
  const outFiles = [];
  (function walk(dir) {
    for (const e of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const abs = path.join(dir, e.name);
      if (e.isDirectory()) {
        walk(abs);
      } else if (e.isFile() && e.name !== SRC_NAME) {
        outFiles.push(fileEntry(abs));
      }
    }
  })(caseDir);
  if (outFiles.length > 16) cannotRun('case ' + c.name + ': produced ' + outFiles.length + ' files, contract allows 16');
  for (const f of outFiles) {
    // evidence copy keyed by the work-relative path so subdirectories survive
    const copyName = 'case-' + c.name + '.' + f.path.split('/').join('__');
    fs.copyFileSync(path.join(WORK, f.path), path.join(EVIDENCE, copyName));
  }

  return {
    name: c.name,
    operation: c.operation,
    source: fileEntry(c.source),
    stages,
    outcome: chainOutcome,
    duration_ms: Date.now() - started,
    out_files: outFiles,
  };
}

// Environment identity, measured at run time. Every field is nullable: the
// gates pin what the environment must be, this only records what it is.
function measureUpstream() {
  const repo = process.env.RCOS_HUNYUAN_REPO || path.join(os.homedir(), 'tools', 'hunyuan3d-2.1-mlx');
  const out = {
    repo: homeRel(repo),
    repo_head: null,
    patch_sha256: null,
    weights: { repo_id: 'dgrauet/hunyuan3d-2.1-mlx', snapshot: null },
  };
  try {
    const head = spawnSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8', timeout: 15000 });
    if (head.status === 0) out.repo_head = head.stdout.trim() || null;
    const diff = spawnSync('git', ['-C', repo, 'diff'], {
      encoding: 'utf8', timeout: 15000, maxBuffer: 64 * 1024 * 1024,
    });
    if (diff.status === 0) out.patch_sha256 = sha256(Buffer.from(diff.stdout, 'utf8'));
  } catch (e) {
    // stays null; the gates decide whether that is acceptable
  }
  try {
    const hub = process.env.HF_HOME
      ? path.join(process.env.HF_HOME, 'hub')
      : path.join(os.homedir(), '.cache', 'huggingface', 'hub');
    const snaps = path.join(hub, 'models--dgrauet--hunyuan3d-2.1-mlx', 'snapshots');
    const entries = fs.readdirSync(snaps, { withFileTypes: true })
      .filter((e) => e.isDirectory() && !e.name.startsWith('.'))
      .map((e) => e.name);
    if (entries.length === 1) out.weights.snapshot = entries[0];
  } catch (e) {
    // stays null; the gates decide whether that is acceptable
  }
  return out;
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
  let st;
  try {
    st = fs.statSync(c.source);
  } catch (e) {
    cannotRun('case ' + c.name + ': source does not exist: ' + c.source);
  }
  if (!st.isFile()) cannotRun('case ' + c.name + ': source is not a regular file: ' + c.source);
}

const UPSTREAM = measureUpstream();

fs.writeFileSync(path.join(EVIDENCE, 'frozen.sha256'),
  SCRIPTS.map((s) => s.sha256 + '  ' + s.name).join('\n') + '\n' + 'interpreter: ' + PYTHON + '\n');
fs.writeFileSync(path.join(EVIDENCE, 'deps.json'), JSON.stringify(DEPS, null, 2) + '\n');
fs.writeFileSync(path.join(EVIDENCE, 'upstream.json'), JSON.stringify(UPSTREAM, null, 2) + '\n');

const cases = input.cases.map(runCase);

const observation = {
  schema: 'hunyuan3d-mlx-local-observation/1',
  frozen: {
    scripts: SCRIPTS.map((s) => ({
      name: s.name,
      path: 'capabilities/hunyuan3d-mlx-local/adapter/' + s.name,
      sha256: s.sha256,
      usage: USAGE[s.name],
    })),
    interpreter: {
      path: PYTHON === path.join(os.homedir(), 'venvs', 'hunyuan3d-mlx', 'bin', 'python')
        ? '~/venvs/hunyuan3d-mlx/bin/python'
        : PYTHON,
      version: DEPS.python,
      deps: {
        mlx: DEPS.mlx,
        numpy: DEPS.numpy,
        trimesh: DEPS.trimesh,
        rembg: DEPS.rembg,
        pillow: DEPS.pillow,
      },
    },
    upstream: UPSTREAM,
  },
  cases,
};

fs.writeFileSync(OUTPUT, JSON.stringify(observation, null, 2) + '\n');

for (const c of cases) {
  console.log(c.name + ' [' + c.operation + '] outcome=' + c.outcome +
    ' stages=' + c.stages.map((s) => s.stage + ':' + String(s.exit_status)).join(',') +
    ' out_files=' + c.out_files.length + ' ' + (c.duration_ms / 1000).toFixed(1) + 's');
}
console.log('observed ' + cases.length + ' cases (scripts ' +
  SCRIPTS.map((s) => s.sha256.slice(0, 8)).join('/') + ', interpreter ' +
  DEPS.python + '/mlx ' + DEPS.mlx + ', head ' + (UPSTREAM.repo_head || 'unmeasured').slice(0, 8) + ')');
process.exit(0);
