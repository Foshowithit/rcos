#!/usr/bin/env node
'use strict';

// Gates for preview-server-verify (rcos-eval/2). Each gate reads the
// CAPABILITY's recorded observation — $RCOS_INVOCATION_DIR/output.json, the
// bytes the invocation kernel froze and hashed — re-reads the raw checker text
// it was parsed from, and recomputes the hashes from the fixtures on disk.
// Never the capability's live state, never the registry. Exit 0 = pass,
// 3 = fail, 4 = no observation to judge.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const net = require('node:net');

const id = process.argv[2];
const invocationDir = process.env.RCOS_INVOCATION_DIR;
if (!invocationDir) {
  console.error('blocked: RCOS_INVOCATION_DIR is not set — this gate judges an invocation, not a work dir');
  process.exit(4);
}
const outputPath = path.join(invocationDir, 'output.json');
if (!fs.existsSync(outputPath)) {
  console.error('blocked: ' + outputPath + ' not found — the capability produced no observation');
  process.exit(4);
}
const O = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
const probe = (name) => O.probes.find((p) => p.name === name);
const work = process.env.RCOS_WORK_DIR;
const runDir = process.env.RCOS_RUN_DIR;
const home = process.env.RCOS_HOME;

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const hashFile = (p) => sha256(fs.readFileSync(p));

// An observation is only worth judging if the bytes it rests on agree with it.
// A claim its own evidence contradicts is a FAIL, not "blocked": there IS
// evidence, and it disagrees. Exit 4 stays for evidence that is absent.
function evidenceProblems() {
  const problems = [];
  for (const p of O.probes) {
    const ev = path.join(invocationDir, 'evidence', 'probe-' + p.name + '.stdout.txt');
    if (!fs.existsSync(ev)) problems.push('evidence/probe-' + p.name + '.stdout.txt missing');
    else if (fs.readFileSync(ev, 'utf8') !== p.stdout) {
      problems.push('evidence/probe-' + p.name + '.stdout.txt is not the text recorded in the observation');
    }
  }
  const checker = home ? path.join(home, O.checker.path) : null;
  if (!checker || !fs.existsSync(checker)) {
    problems.push('the checker the observation names cannot be re-read: ' + (checker || O.checker.path));
  } else if (hashFile(checker) !== O.checker.sha256) {
    problems.push('the checker on disk is no longer the checker that ran');
  }
  const inputPath = runDir ? path.join(runDir, 'input.json') : null;
  if (!inputPath || !fs.existsSync(inputPath)) problems.push('run input.json missing — the frozen fixture hashes are unavailable');
  return problems;
}
const EVIDENCE = evidenceProblems();

// The fixture hashes the RUNNER recorded before anything executed.
function frozenFixture(name) {
  const inputPath = path.join(runDir, 'input.json');
  const frozen = JSON.parse(fs.readFileSync(inputPath, 'utf8')).fixtures;
  return frozen.find((f) => f.name === name) || null;
}

function livePortOpen(port) {
  // Synchronous-enough probe: net.connect emits 'error' for a refused port and
  // 'connect' if something is listening. Returns a promise the caller awaits.
  return new Promise((resolve) => {
    const s = net.connect({ host: '127.0.0.1', port });
    const done = (open) => { s.destroy(); resolve(open); };
    s.setTimeout(1500);
    s.on('connect', () => done(true));
    s.on('error', () => done(false));
    s.on('timeout', () => done(true));
  });
}

const checks = {
  // A loopback server answers 200 with the pinned bytes and says so.
  serves() {
    const p = probe('pin_ok');
    if (!p) return { ok: false, detail: 'probe pin_ok missing' };
    const ok = p.exit_status === 0 && p.outcome === 'passed' &&
      p.observed.http_status === 200 && p.observed.served_bytes > 0 && p.observed.pass_marker === true;
    return {
      ok,
      detail: 'exit ' + p.exit_status + ' (' + p.outcome + '), http ' + p.observed.http_status +
        ', ' + p.observed.served_bytes + ' bytes, marker ' + p.observed.pass_marker
    };
  },

  // The pin is recomputed from the fixture on disk, by this gate, and compared
  // against both the declared pin and the hash the checker printed. The stale
  // probe's pin is required to disagree with the fresh one, or that probe is a
  // check that cannot fail.
  bytes_match_pin_recomputed() {
    const p = probe('pin_ok');
    const st = probe('stale_pin');
    if (!p || !st) return { ok: false, detail: 'probe pin_ok or stale_pin missing' };
    const fresh = frozenFixture('docroot/index.html');
    const stale = frozenFixture('docroot/stale.html');
    if (!fresh || !stale) return { ok: false, detail: 'frozen fixture hashes missing from run input.json' };

    const workFresh = hashFile(path.join(work, 'docroot', 'index.html'));
    const workStale = hashFile(path.join(work, 'docroot', 'stale.html'));
    const evInput = path.join(runDir, 'evidence', 'inputs', 'docroot', 'index.html');
    const evFresh = fs.existsSync(evInput) ? hashFile(evInput) : null;

    const problems = [];
    if (workFresh !== fresh.sha256) problems.push('work copy of the fixture is not the frozen fixture (tampered after freeze)');
    if (evFresh !== null && evFresh !== fresh.sha256) problems.push('evidence copy of the fixture is not the frozen fixture');
    if (p.expect_sha256 !== fresh.sha256) problems.push('declared pin is not the sha256 of the fresh fixture');
    if (st.expect_sha256 !== stale.sha256) problems.push('stale pin is not the sha256 of the superseded fixture');
    if (st.expect_sha256 === p.expect_sha256) problems.push('the stale probe pins the same bytes as the fresh probe — it proves nothing');
    if (p.observed.served_sha256_prefix !== p.expect_sha256.slice(0, 16)) {
      problems.push('bytes served do not match the pin (served ' + p.observed.served_sha256_prefix + ' vs pin ' + p.expect_sha256.slice(0, 16) + ')');
    }
    if (p.observed.disk_sha256_prefix !== p.observed.served_sha256_prefix) {
      problems.push('served bytes differ from the docroot on disk (transport mangling)');
    }
    if (fresh.bytes !== fs.statSync(path.join(work, 'docroot', 'index.html')).size) {
      problems.push('frozen byte count does not match the file on disk');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'pin ' + p.expect_sha256.slice(0, 16) + ' == recomputed fixture hash; served == docroot-disk; stale pin ' +
          st.expect_sha256.slice(0, 16) + ' differs'
    };
  },

  // The 09-17 split-brain case: the server answers 200 with bytes that match
  // the docroot on disk, and they are STILL wrong. Only the authoring-time pin
  // catches it — which is the difference between this gate and a 200 check.
  stale_pin_caught() {
    const p = probe('stale_pin');
    if (!p) return { ok: false, detail: 'probe stale_pin missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (!/STALE_OR_WRONG_BYTES/.test(p.stdout)) problems.push('the checker did not name STALE_OR_WRONG_BYTES');
    if (p.observed.http_status !== 200) problems.push('http ' + p.observed.http_status + ' (want 200: the catch must come from the pin, not the transport)');
    if (p.observed.served_sha256_prefix !== p.observed.disk_sha256_prefix) {
      problems.push('served and docroot-disk disagreed, so this run does not exercise the stale-server case');
    }
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on a stale pin');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'exit 3 + STALE_OR_WRONG_BYTES while served == docroot-disk (' + p.observed.served_sha256_prefix + '): the pin, not the transport, caught it'
    };
  },

  // A path that is not there is a caught failure, not a pass and not a block.
  missing_path_caught() {
    const p = probe('missing_path');
    if (!p) return { ok: false, detail: 'probe missing_path missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (p.observed.http_status !== 404) problems.push('http ' + p.observed.http_status + ' (want 404)');
    if (p.expect_sha256 !== null) problems.push('this probe carries a pin, so the catch is not attributable to the missing path');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on a missing path');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'exit 3 + STATUS 404 with no pin declared'
    };
  },

  // Teardown is checked twice: the checker's own line for each port it served
  // from, and a fresh connection from this gate to the last port it bound.
  async port_released() {
    const bound = O.probes.filter((p) => p.observed.bound_port !== null);
    if (bound.length < 2) return { ok: false, detail: 'fewer than 2 probes ever bound a port — nothing to check' };
    const problems = [];
    for (const p of bound) {
      if (p.observed.teardown_port !== p.observed.bound_port) {
        problems.push(p.name + ': no teardown line for port ' + p.observed.bound_port);
      }
    }
    const last = bound[bound.length - 1];
    const stillOpen = await livePortOpen(last.observed.bound_port);
    if (stillOpen) problems.push('port ' + last.observed.bound_port + ' still accepts connections from this gate');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : bound.length + ' ports torn down (last ' + last.observed.bound_port + '); an independent connect from this gate is refused'
    };
  }
};

if (!id || !checks[id]) {
  console.error('unknown gate id: ' + id + ' (known: ' + Object.keys(checks).join(', ') + ')');
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
