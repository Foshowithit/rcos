'use strict';
// The invocation kernel: one way for RCOS to execute a registered capability.
//
// Invariant this file exists to hold:
//   If a registry entry claims to be a reusable capability, RCOS itself must
//   know how to invoke that capability from its declared adapter and validate
//   the result against its contract.
//
// What it deliberately is NOT: a router, a selector, a planner, or a judge.
// The caller names the capability. The kernel resolves the declaration, checks
// the input contract, runs the entrypoint once, checks the output contract and
// writes a write-once invocation artifact. It never decides whether the result
// was *good* — that belongs to the eval runner. An invocation succeeding does
// not prove the capability is good.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const R = require('./registry');
const A = require('./adapter');

const INVOCATION_SCHEMA = 'rcos-invocation/1';
// normal  = production reuse. promoted only.
// eval    = the eval runner exercising a capability that is not yet promoted.
// forensic= an explicit, recorded override to run something RCOS would
//           otherwise refuse (retired, or an unpromoted candidate).
const MODES = ['normal', 'eval', 'forensic'];
const INVOCATION_STATUSES = ['completed', 'rejected', 'failed', 'blocked'];
const ADAPTER_EXIT_BLOCKED = 4;
const DEFAULT_TIMEOUT_SECONDS = 60;
const MAX_BUFFER = 16 * 1024 * 1024;
const INVOCATION_ID_RE = /^inv_\d{8}T\d{6}Z-[0-9a-f]{6}$/;

function sha256(buf) { return crypto.createHash('sha256').update(buf).digest('hex'); }

function makeInvocationId(now = new Date()) {
  const iso = now.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
  return 'inv_' + iso + '-' + crypto.randomBytes(3).toString('hex');
}

function isInvocationId(id) { return INVOCATION_ID_RE.test(String(id)); }

function invocationsDir(homeDir) { return path.join(homeDir, 'invocations'); }
function invocationDir(homeDir, id) { return path.join(invocationsDir(homeDir), id); }

// Which registry statuses a mode may invoke. Kept here, next to the modes, so
// "normal reuse runs promoted things only" is one readable rule.
function eligibility(status, mode) {
  if (mode === 'normal' && status !== 'promoted') {
    return { ok: false, reason: 'status \'' + status + '\' is not eligible for normal invocation (only promoted capabilities are); use --mode eval (development) or --mode forensic --forensic <reason> (explicit override)' };
  }
  if (mode === 'eval' && status !== 'promoted' && status !== 'candidate') {
    return { ok: false, reason: 'status \'' + status + '\' is not eligible for eval invocation (promoted|candidate); retired capabilities need an explicit forensic override' };
  }
  return { ok: true, reason: null };
}

function listFilesRecursive(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.isFile()) out.push(p);
    }
  };
  walk(dir);
  return out;
}

function fileEntry(root, p) {
  const buf = fs.readFileSync(p);
  return { path: path.relative(root, p).split(path.sep).join('/'), sha256: sha256(buf), bytes: buf.length };
}

// Self-integrity: the manifest hashes itself so a hand-edited manifest is
// detectable without trusting the file's own contents.
function manifestIntegrity(manifest) {
  const { integrity, ...rest } = manifest;
  return sha256(JSON.stringify(rest, null, 2) + '\n');
}

function invokeCapability(homeDir, capabilityId, opts = {}) {
  const mode = opts.mode || 'normal';
  if (!MODES.includes(mode)) return { ok: false, error: 'unknown mode \'' + mode + '\' (one of ' + MODES.join('|') + ')' };
  const now = opts.now || new Date();
  const reg = R.loadRegistry(homeDir);
  // Deliberately not R.findCapability: an id the registry does not hold is a
  // refusal the kernel reports, not an exception the caller has to catch.
  const cap = reg.capabilities.find((c) => c.id === capabilityId);
  if (!cap) return { ok: false, error: 'no such capability \'' + capabilityId + '\' in the registry' };

  let id = opts.invocationId || makeInvocationId(now);
  if (opts.invocationId && !isInvocationId(id)) throw new Error('bad invocation id: ' + id);
  const dir = invocationDir(homeDir, id);
  // The container may not exist yet; the id directory itself is created
  // non-recursively so EEXIST stays the write-once signal.
  fs.mkdirSync(invocationsDir(homeDir), { recursive: true });
  for (let attempt = 0; ; attempt += 1) {
    try { fs.mkdirSync(dir); break; } catch (e) {
      if (e.code !== 'EEXIST') throw e;
      if (opts.invocationId) throw new Error('invocation ' + id + ' already exists — invocations are write-once and never rewritten');
      if (attempt >= 5) throw e;
      id = makeInvocationId(now);
    }
  }
  const workDir = path.join(dir, 'work');
  const evidenceDir = path.join(dir, 'evidence');
  fs.mkdirSync(workDir);
  fs.mkdirSync(evidenceDir);

  const startedAt = new Date();
  const inputDoc = opts.input === undefined ? null : opts.input;
  fs.writeFileSync(path.join(dir, 'input.json'), JSON.stringify(inputDoc, null, 2) + '\n');

  const decl = cap.adapter;
  const declErrors = decl === undefined
    ? ['capability declares no adapter — RCOS has no declared way to invoke it']
    : A.validateAdapterDeclaration(decl);
  const contractRes = declErrors.length === 0 ? A.loadContract(homeDir, decl) : { ok: false, contract: null, errors: [], path: null };
  const entrypoint = declErrors.length === 0 ? A.resolveEntrypoint(homeDir, decl) : null;

  let status;
  let basis;
  let spawnRes = null;
  let inputCheck = { status: 'not-checked', errors: [] };
  let outputCheck = { status: 'not-checked', errors: [] };
  let outputFile = null;

  const finish = () => {
    const completedAt = new Date();
    fs.writeFileSync(path.join(dir, 'stdout.txt'), spawnRes && spawnRes.stdout ? spawnRes.stdout : '');
    fs.writeFileSync(path.join(dir, 'stderr.txt'), spawnRes && spawnRes.stderr ? spawnRes.stderr : '');
    const manifest = {
      schema: INVOCATION_SCHEMA,
      invocation_id: id,
      capability_id: cap.id,
      capability_version: cap.version,
      registry_status: cap.status,
      mode,
      status,
      status_basis: basis,
      started_at: startedAt.toISOString(),
      completed_at: completedAt.toISOString(),
      duration_ms: completedAt.getTime() - startedAt.getTime(),
      input: fileEntry(dir, path.join(dir, 'input.json')),
      output: outputFile && fs.existsSync(outputFile) ? fileEntry(dir, outputFile) : null,
      stdout: fileEntry(dir, path.join(dir, 'stdout.txt')),
      stderr: fileEntry(dir, path.join(dir, 'stderr.txt')),
      evidence: listFilesRecursive(evidenceDir).map((p) => fileEntry(dir, p)),
      adapter: {
        type: declErrors.length === 0 ? decl.type : null,
        entrypoint: declErrors.length === 0 ? decl.entrypoint : null,
        timeout_seconds: declErrors.length === 0 ? (decl.timeout_seconds === undefined ? DEFAULT_TIMEOUT_SECONDS : decl.timeout_seconds) : null,
        exit_code: spawnRes ? spawnRes.status : null,
        signal: spawnRes ? spawnRes.signal : null,
        error: spawnRes && spawnRes.error ? String(spawnRes.error.code || spawnRes.error.message) : null
      },
      contract: {
        path: contractRes.path === null || contractRes.path === undefined ? null : path.relative(homeDir, contractRes.path),
        declaration_errors: declErrors,
        contract_errors: contractRes.errors,
        input: inputCheck,
        output: outputCheck
      },
      rcos_home: homeDir,
      created_at: completedAt.toISOString()
    };
    if (mode === 'forensic') manifest.forensic_reason = opts.forensicReason || null;
    manifest.integrity = { algo: 'sha256', value: manifestIntegrity(manifest) };
    const manifestPath = path.join(dir, 'manifest.json');
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
    return {
      ok: true,
      status,
      basis,
      invocation_id: id,
      capability_id: cap.id,
      dir,
      manifest,
      manifest_path: manifestPath,
      manifest_sha256: sha256(fs.readFileSync(manifestPath)),
      output_sha256: manifest.output ? manifest.output.sha256 : null
    };
  };

  // 1. Eligibility. A capability RCOS would refuse to reuse must not be
  //    runnable by accident.
  const elig = eligibility(cap.status, mode);
  if (!elig.ok) { status = 'blocked'; basis = elig.reason; return finish(); }

  // 2. Adapter declaration.
  if (declErrors.length > 0) { status = 'blocked'; basis = 'adapter declaration is not usable: ' + declErrors.join('; '); return finish(); }

  // 3. Contract declaration (a contract that cannot be enforced blocks; it does
  //    not silently downgrade to "no contract").
  if (!contractRes.ok) { status = 'blocked'; basis = 'declared contract is not usable: ' + contractRes.errors.join('; '); return finish(); }

  // 4. Entrypoint.
  if (!fs.existsSync(entrypoint)) {
    status = 'blocked';
    basis = 'adapter entrypoint is missing: ' + decl.entrypoint;
    return finish();
  }
  if (!fs.statSync(entrypoint).isFile()) { status = 'blocked'; basis = 'adapter entrypoint is not a file: ' + decl.entrypoint; return finish(); }
  try { fs.accessSync(entrypoint, fs.constants.X_OK); } catch (e) {
    status = 'blocked';
    basis = 'adapter entrypoint is not executable: ' + decl.entrypoint;
    return finish();
  }

  // 5. Input contract — before any execution.
  if (contractRes.contract && contractRes.contract.input) {
    const errs = A.validateValue(inputDoc, contractRes.contract.input, 'input');
    if (errs.length > 0) {
      inputCheck = { status: 'fail', errors: errs };
      status = 'rejected';
      basis = 'input did not satisfy the declared input contract: ' + errs.join('; ');
      return finish();
    }
    inputCheck = { status: 'pass', errors: [] };
  }

  // 6. Execute the declared adapter once.
  outputFile = path.join(dir, 'output.json');
  const timeoutSeconds = decl.timeout_seconds === undefined ? DEFAULT_TIMEOUT_SECONDS : decl.timeout_seconds;
  const childEnv = Object.assign({}, process.env, {
    RCOS_HOME: homeDir,
    RCOS_BIN: path.join(__dirname, '..', 'bin', 'rcos'),
    RCOS_INVOCATION_ID: id,
    RCOS_INVOCATION_DIR: dir,
    RCOS_INVOCATION_WORK_DIR: workDir,
    RCOS_INPUT: path.join(dir, 'input.json'),
    RCOS_OUTPUT: outputFile,
    RCOS_EVIDENCE_DIR: evidenceDir,
    RCOS_CAPABILITY_ID: cap.id,
    RCOS_CAPABILITY_VERSION: cap.version,
    RCOS_CAPABILITY_DIR: path.join(homeDir, 'capabilities', cap.id),
    RCOS_ADAPTER_TYPE: decl.type,
    RCOS_MODE: mode
  });
  spawnRes = spawnSync(entrypoint, [], {
    cwd: workDir,
    env: childEnv,
    encoding: 'utf8',
    timeout: timeoutSeconds * 1000,
    maxBuffer: MAX_BUFFER
  });

  if (spawnRes.error) {
    const code = String(spawnRes.error.code || spawnRes.error.message);
    status = 'blocked';
    basis = 'adapter could not be started (' + code + ')';
    return finish();
  }
  if (spawnRes.signal) {
    status = 'failed';
    basis = 'adapter was killed by ' + spawnRes.signal + (spawnRes.signal === 'SIGTERM' && spawnRes.status === null ? ' (timeout after ' + timeoutSeconds + 's)' : '');
    return finish();
  }
  if (spawnRes.status === ADAPTER_EXIT_BLOCKED) {
    status = 'blocked';
    basis = 'adapter reported it could not run (exit ' + ADAPTER_EXIT_BLOCKED + ')';
    return finish();
  }
  if (spawnRes.status !== 0) {
    status = 'failed';
    basis = 'adapter exited ' + spawnRes.status;
    return finish();
  }

  // 7. Output contract. Exit 0 with malformed output is a failure, never a
  //    completion.
  if (!fs.existsSync(outputFile)) {
    status = 'failed';
    basis = 'adapter exited 0 but wrote no output at $RCOS_OUTPUT';
    return finish();
  }
  let outputDoc;
  try {
    outputDoc = JSON.parse(fs.readFileSync(outputFile, 'utf8'));
  } catch (e) {
    outputCheck = { status: 'fail', errors: ['output.json is not valid JSON: ' + e.message] };
    status = 'failed';
    basis = 'adapter exited 0 but its output is not valid JSON: ' + e.message;
    return finish();
  }
  if (contractRes.contract && contractRes.contract.output) {
    const errs = A.validateValue(outputDoc, contractRes.contract.output, 'output');
    if (errs.length > 0) {
      outputCheck = { status: 'fail', errors: errs };
      status = 'failed';
      basis = 'adapter exited 0 but its output violates the declared output contract: ' + errs.join('; ');
      return finish();
    }
    outputCheck = { status: 'pass', errors: [] };
  } else {
    outputCheck = { status: 'not-declared', errors: [] };
  }

  status = 'completed';
  basis = 'adapter exited 0 and its output satisfied the declared contract';
  return finish();
}

// Re-hashes every artifact the manifest lists and flags files present but
// unlisted. Same discipline as eval-verify: an invocation artifact that has
// been edited is detectable.
function verifyInvocation(homeDir, id) {
  const dir = invocationDir(homeDir, id);
  if (!fs.existsSync(dir)) return { ok: false, problems: ['invocation not found: ' + id], checked: 0 };
  const manifestPath = path.join(dir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) return { ok: false, problems: ['manifest.json missing'], checked: 0 };
  let manifest;
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  } catch (e) {
    return { ok: false, problems: ['manifest.json is not valid JSON: ' + e.message], checked: 0 };
  }
  const problems = [];
  if (!manifest.integrity || manifest.integrity.algo !== 'sha256') problems.push('manifest.integrity missing or not sha256');
  else if (manifest.integrity.value !== manifestIntegrity(manifest)) problems.push('manifest integrity mismatch — the manifest was edited after it was written');

  const listed = [];
  for (const key of ['input', 'output', 'stdout', 'stderr']) {
    if (manifest[key]) listed.push(manifest[key]);
  }
  for (const e of manifest.evidence || []) listed.push(e);
  for (const e of listed) {
    const p = path.join(dir, e.path);
    if (!fs.existsSync(p)) { problems.push('listed artifact is missing: ' + e.path); continue; }
    const buf = fs.readFileSync(p);
    if (sha256(buf) !== e.sha256) problems.push('artifact changed since the invocation was written: ' + e.path);
    if (buf.length !== e.bytes) problems.push('artifact size changed since the invocation was written: ' + e.path);
  }
  const listedPaths = new Set(listed.map((e) => e.path));
  for (const p of listFilesRecursive(dir)) {
    const rel = path.relative(dir, p).split(path.sep).join('/');
    if (rel === 'manifest.json' || rel.startsWith('work/')) continue;
    if (!listedPaths.has(rel)) problems.push('artifact present but not listed in the manifest: ' + rel);
  }
  return { ok: problems.length === 0, problems, checked: listed.length, manifest };
}

function readManifest(homeDir, id) {
  const p = path.join(invocationDir(homeDir, id), 'manifest.json');
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function listInvocations(homeDir) {
  const dir = invocationsDir(homeDir);
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && isInvocationId(e.name))
    .map((e) => e.name)
    .sort()
    .map((id) => {
      const m = readManifest(homeDir, id);
      return {
        invocation_id: id,
        capability_id: m ? m.capability_id : null,
        capability_version: m ? m.capability_version : null,
        status: m ? m.status : null,
        mode: m ? m.mode : null,
        started_at: m ? m.started_at : null,
        completed_at: m ? m.completed_at : null,
        dir: invocationDir(homeDir, id)
      };
    });
}

module.exports = {
  INVOCATION_SCHEMA,
  MODES,
  INVOCATION_STATUSES,
  DEFAULT_TIMEOUT_SECONDS,
  makeInvocationId,
  isInvocationId,
  invocationsDir,
  invocationDir,
  eligibility,
  invokeCapability,
  verifyInvocation,
  readManifest,
  listInvocations,
  sha256
};
