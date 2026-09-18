#!/usr/bin/env node
'use strict';

// Gates for audio-offline-verify (rcos-eval/2). Each gate reads the
// CAPABILITY's recorded observation — $RCOS_INVOCATION_DIR/output.json, the
// bytes the invocation kernel froze and hashed — re-reads the raw checker text
// it was parsed from, and recomputes the fixture hashes from the run's own
// frozen record. Never the capability's live state, never the registry.
// Exit 0 = pass, 3 = fail, 4 = no observation to judge.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

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
const near = (a, b, tol) => typeof a === 'number' && Math.abs(a - b) <= tol;
const realOr = (p) => { try { return fs.realpathSync(p); } catch (e) { return p; } };

// The observation names its checker. A receipt has to stay judgeable when it is
// read from a root other than the one it was written on, and a symlinked root
// makes the same file nameable two ways (node resolves the adapter's own
// directory, so /tmp/x/... can arrive as /private/tmp/x/...). Both notations are
// therefore tried before a gate declares the checker unreadable — the claim
// being tested is which FILE it names, not which string.
function checkerCandidates(p) {
  if (!p) return [];
  if (path.isAbsolute(p)) {
    return home ? [p, path.join(home, p.replace(/^[/\\]+/, ''))] : [p];
  }
  return home ? [path.join(home, p), p] : [p];
}
function resolveChecker(p) {
  for (const c of checkerCandidates(p)) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

// The revision this eval was authored against, and the fixture bytes it was
// authored on. Both are constants HERE, in the eval package — not read from the
// capability, not read from the registry. If av_check.py or a fixture changes,
// these gates fail and the receipt is quarantined as being about a revision
// that no longer exists; re-pinning is then a deliberate authoring act.
const CHECKER_PIN = '29eb2d8f6f48677ad15d6123d23ae5fedeef68b04aa21b7ea0e5f88a6a8b7b6e';
const CHECKER_PATH = 'capabilities/audio-offline-verify/adapter/av_check.py';
const FIXTURES = {
  'chalk-eval2.mp4': 'c43aae245a1dc031c76a826e2053195a0bc61b998559d5d3a02c4a76a83e39bd',
  'chalk-eval1.mp4': '905b54ff4e88ebbe26d49b5e83869fd04f9bf7cca72ff8083d01beab653c7b2e',
  'shot-face-v2-r3.mp4': '596896b57a00f07ec6bb6324a16ff3706d81e6400f047b198af647314b296c84',
  'rcos-dispatch-eval-2-out.mp4': 'a73ae94906f44192414348503fe2452abecd9c9ce2e239db5c80a279ad1d1dfd'
};
// container facts from the committed historical logs; metadata, so exact
const FACE = { duration: 2.0, w: 1080, h: 1080, audio: 'aac', rate: '48000', ch: '2' };
const CHALK1 = { duration: 4.0, w: 960, h: 540, audio: 'aac', rate: '44100', ch: '1', rms: -35.104884 };
const CHALK2 = { duration: 3.0, w: 960, h: 540, audio: 'aac', rate: '44100', ch: '1', rms: -35.113250 };
const DISPATCH = { duration: 4.0, w: 1280, h: 720 };
const RMS_TOLERANCE_DB = 0.5;

// An observation is only worth judging if the bytes it rests on agree with it.
// A claim its own evidence contradicts is a FAIL, not "blocked": there IS
// evidence, and it disagrees. Exit 4 stays for evidence that is absent.
function evidenceProblems() {
  const problems = [];
  for (const p of O.probes) {
    const base = 'evidence/probe-' + p.name;
    const stdoutPath = path.join(invocationDir, base + '.stdout.txt');
    const stderrPath = path.join(invocationDir, base + '.stderr.txt');
    const argvPath = path.join(invocationDir, base + '.argv.json');
    if (!fs.existsSync(stdoutPath)) problems.push(base + '.stdout.txt missing');
    else if (fs.readFileSync(stdoutPath, 'utf8') !== p.stdout) {
      problems.push(base + '.stdout.txt is not the text recorded in the observation');
    }
    if (!fs.existsSync(stderrPath)) problems.push(base + '.stderr.txt missing');
    else if (fs.readFileSync(stderrPath, 'utf8') !== p.stderr) {
      problems.push(base + '.stderr.txt is not the text recorded in the observation');
    }
    if (!fs.existsSync(argvPath)) problems.push(base + '.argv.json missing');
    else if (JSON.stringify(JSON.parse(fs.readFileSync(argvPath, 'utf8'))) !== JSON.stringify(p.argv)) {
      problems.push(base + '.argv.json is not the argv recorded in the observation');
    }
  }
  const checker = resolveChecker(O.checker.path);
  if (!checker) {
    problems.push('the checker the observation names cannot be re-read: ' + (O.checker.path || '(none named)')
      + ' (tried ' + checkerCandidates(O.checker.path).join(', ') + ')');
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

// Container facts are exact; the RMS reading is a measurement of the same bytes
// by whatever ffmpeg is on the box, so it is pinned with a tolerance and the
// historical value is what it is compared against.
function containerProblems(p, want, label) {
  const o = p.observed;
  const problems = [];
  if (o.container_duration_s !== want.duration) problems.push(label + ' duration ' + o.container_duration_s + ' (want ' + want.duration + ')');
  if (want.w !== undefined && o.video_width !== want.w) problems.push(label + ' width ' + o.video_width + ' (want ' + want.w + ')');
  if (want.h !== undefined && o.video_height !== want.h) problems.push(label + ' height ' + o.video_height + ' (want ' + want.h + ')');
  if (want.audio !== undefined && o.audio_codec !== want.audio) problems.push(label + ' audio codec ' + o.audio_codec + ' (want ' + want.audio + ')');
  if (want.rate !== undefined && o.audio_sample_rate !== want.rate) problems.push(label + ' sample rate ' + o.audio_sample_rate + ' (want ' + want.rate + ')');
  if (want.ch !== undefined && o.audio_channels !== want.ch) problems.push(label + ' channels ' + o.audio_channels + ' (want ' + want.ch + ')');
  return problems;
}

const checks = {
  // Both voiced artifacts pass with must-sound ON: exit 0, the checker's own
  // pass marker, a real RMS reading above the floor, and the container facts
  // the historical logs recorded.
  voiced_passes() {
    const problems = [];
    for (const [name, want] of [['chalk2_voiced', CHALK2], ['chalk1_voiced', CHALK1]]) {
      const p = probe(name);
      if (!p) { problems.push('probe ' + name + ' missing'); continue; }
      if (p.exit_status !== 0) problems.push(name + ': exit ' + p.exit_status + ' (want 0)');
      if (p.outcome !== 'passed') problems.push(name + ': outcome ' + p.outcome);
      if (p.observed.pass_marker !== true) problems.push(name + ': the checker did not print AV_CHECK_PASS');
      if (p.observed.fail_lines.length > 0) problems.push(name + ': fail lines ' + JSON.stringify(p.observed.fail_lines));
      if (!p.argv.includes('--audio-must-sound')) problems.push(name + ': must-sound was not passed, so the pass is not the evaluated claim');
      if (typeof p.observed.rms_dbfs !== 'number') problems.push(name + ': RMS not a number (' + p.observed.rms_token + ') — a must-sound pass needs a reading');
      else if (!near(p.observed.rms_dbfs, want.rms, RMS_TOLERANCE_DB)) {
        problems.push(name + ': RMS ' + p.observed.rms_dbfs + ' vs historical ' + want.rms + ' (tolerance ' + RMS_TOLERANCE_DB + ' dB)');
      } else if (p.observed.rms_dbfs < -60) problems.push(name + ': RMS ' + p.observed.rms_dbfs + ' is below the -60 floor yet passed');
      problems.push(...containerProblems(p, want, name));
    }
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'chalk-eval2 ' + CHALK2.rms + ' dBFS / chalk-eval1 ' + CHALK1.rms + ' dBFS, both must-sound, both AV_CHECK_PASS'
    };
  },

  // The duration leg alone can fail: the SAME bytes that pass in their authoring
  // envelope exit 3 when the envelope excludes them, and the only fail line is
  // DURATION with the declared numbers in it. A gate no file can trip would be
  // decoration; this is the file tripping it.
  envelope_gate_bites() {
    const p = probe('chalk2_wrong_envelope');
    const paired = probe('chalk2_voiced');
    if (!p || !paired) return { ok: false, detail: 'probe chalk2_wrong_envelope or chalk2_voiced missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS outside the envelope');
    if (p.observed.fail_lines.length !== 1) problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines) + ' (want exactly one)');
    else if (!/^DURATION 3\.000 outside \[3\.5, 4\.5\]$/.test(p.observed.fail_lines[0])) {
      problems.push('fail line is not the authored envelope rejection: ' + JSON.stringify(p.observed.fail_lines[0]));
    }
    if (p.observed.container_duration_s !== CHALK2.duration) problems.push('the file under test is not the 3.000s chalk mux');
    if (paired.exit_status !== 0) problems.push('the same file did not pass in its authoring envelope, so the catch is not attributable to the envelope');
    if (p.file !== paired.file) problems.push('the two probes did not read the same file');
    if (p.observed.container_duration_s !== paired.observed.container_duration_s) problems.push('the two probes did not see the same duration');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'exit 3 on ' + p.observed.fail_lines[0] + '; the identical bytes exit 0 inside the envelope'
    };
  },

  // RMS is REPORTED, not asserted, when must-sound is off: a silent-by-design
  // mux passes, and the receipt still carries the measurement that says so.
  silence_reported_not_asserted() {
    const p = probe('face_silent_report');
    if (!p) return { ok: false, detail: 'probe face_silent_report missing' };
    const problems = [];
    if (p.exit_status !== 0) problems.push('exit ' + p.exit_status + ' (want 0: report-only is a pass)');
    if (p.observed.pass_marker !== true) problems.push('the checker did not print AV_CHECK_PASS');
    if (p.observed.fail_lines.length > 0) problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines));
    if (p.argv.includes('--audio-must-sound')) problems.push('must-sound was passed, so this probe does not exercise report-only');
    if (p.observed.rms_token !== '-inf') problems.push('rms token ' + JSON.stringify(p.observed.rms_token) + ' (want the string -inf)');
    if (p.observed.rms_dbfs !== null) problems.push('rms_dbfs ' + p.observed.rms_dbfs + ' (want null: -inf is not a number)');
    if (!/^audio RMS -inf dBFS$/m.test(p.stdout)) problems.push('the checker did not report the RMS it measured');
    problems.push(...containerProblems(p, FACE, 'face'));
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'exit 0 on a silent file with RMS -inf reported and not asserted (must-sound absent from argv)'
    };
  },

  // The 09-17 mute attack: the bytes that just passed report-only exit 3 when
  // sound is ASSERTED, with the historical floor message, in the same run that
  // records the -inf reading. Same file, same checker: only the assertion moved.
  mute_caught() {
    const p = probe('face_silent_must_sound');
    const paired = probe('face_silent_report');
    if (!p || !paired) return { ok: false, detail: 'probe face_silent_must_sound or face_silent_report missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on a silent track with must-sound on');
    if (!p.argv.includes('--audio-must-sound')) problems.push('must-sound was not passed');
    if (p.observed.fail_lines.length !== 1) problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines) + ' (want exactly one)');
    else {
      const f = p.observed.fail_lines[0];
      if (!/^MUST_SOUND but RMS (None|-inf) dBFS below -60 floor \(silent track\)$/.test(f)) {
        problems.push('fail line is not the floor rejection: ' + JSON.stringify(f));
      }
    }
    if (p.observed.rms_token !== '-inf') problems.push('rms token ' + JSON.stringify(p.observed.rms_token) + ' (the run must record the reading it rejected)');
    if (paired.exit_status !== 0) problems.push('the report-only twin did not pass, so this is not the same-file assertion flip');
    if (p.file !== paired.file) problems.push('the two probes did not read the same file');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'exit 3 with "' + p.observed.fail_lines[0] + '" while the identical bytes exit 0 report-only: the assertion, not the file, caught it'
    };
  },

  // Absence is a claim too. Declaring it (--expect-audio none) passes; claiming
  // sound from a file with no audio stream is an honest FAIL that the missing
  // stream causes — not the expectation, and not a missing measurement.
  absence_asserted_not_assumed() {
    const p = probe('dispatch_absent_expect_none');
    const q = probe('dispatch_absent_must_sound');
    if (!p || !q) return { ok: false, detail: 'probe dispatch_absent_expect_none or dispatch_absent_must_sound missing' };
    const problems = [];
    if (p.exit_status !== 0) problems.push('expect-none: exit ' + p.exit_status + ' (want 0)');
    if (p.observed.pass_marker !== true) problems.push('expect-none: the checker did not print AV_CHECK_PASS');
    if (p.observed.fail_lines.length > 0) problems.push('expect-none: fail lines ' + JSON.stringify(p.observed.fail_lines));
    const op = p.argv.indexOf('--expect-audio');
    if (op === -1 || p.argv[op + 1] !== 'none') problems.push('expect-none: --expect-audio none was not passed');
    if (p.observed.audio_codec !== null) problems.push('expect-none: audio codec ' + p.observed.audio_codec + ' (want null: no audio stream)');
    if (/^audio RMS /m.test(p.stdout)) problems.push('expect-none: an RMS line was printed for a file with no audio stream');
    problems.push(...containerProblems(p, DISPATCH, 'dispatch'));

    if (q.exit_status !== 3) problems.push('must-sound: exit ' + q.exit_status + ' (want 3)');
    if (q.observed.pass_marker === true) problems.push('must-sound: the checker reported PASS');
    if (q.observed.fail_lines.length !== 1) problems.push('must-sound: fail lines ' + JSON.stringify(q.observed.fail_lines) + ' (want exactly one)');
    else if (q.observed.fail_lines[0] !== 'MUST_SOUND but no audio stream') {
      problems.push('must-sound: fail line is not the missing-stream rejection: ' + JSON.stringify(q.observed.fail_lines[0]));
    }
    if (q.argv.includes('--expect-audio')) problems.push('must-sound: the historical attack passed no --expect-audio, so this probe no longer reproduces it');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'declared absence passes (no audio stream, no RMS line); claimed sound from the same bytes fails "MUST_SOUND but no audio stream"'
    };
  },

  // This receipt is about ONE revision of the checker. The pin lives in this
  // package, so re-pinning after a legitimate change to av_check.py is an
  // authoring decision someone makes on purpose, not a silent carry-forward.
  // The path is judged as a resolution, not as a string: what must hold is that
  // the observation names THIS file, whether it spells it relative to RCOS_HOME
  // or absolutely.
  checker_revision_pinned() {
    const problems = [];
    if (O.checker.sha256 !== CHECKER_PIN) problems.push('checker sha256 ' + O.checker.sha256 + ' is not the revision this eval was authored against (' + CHECKER_PIN.slice(0, 16) + '…)');
    const named = resolveChecker(O.checker.path);
    const expected = home ? path.join(home, CHECKER_PATH) : null;
    if (!named || !expected || realOr(named) !== realOr(expected)) {
      problems.push('checker path ' + JSON.stringify(O.checker.path) + ' does not resolve to ' + CHECKER_PATH
        + (named ? ' — it resolves to ' + named : ''));
    }
    if (JSON.stringify(O.checker.documented_exit_codes) !== JSON.stringify([0, 3, 4])) {
      problems.push('documented exit codes ' + JSON.stringify(O.checker.documented_exit_codes) + ' (want [0,3,4])');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : 'revision ' + CHECKER_PIN.slice(0, 16) + '… at ' + CHECKER_PATH + ' (named '
          + (path.isAbsolute(O.checker.path) ? 'absolutely' : 'relative to RCOS_HOME') + '), exit codes [0,3,4]'
    };
  },

  // The bytes the probes ran on are the bytes the runner froze, and the frozen
  // hashes are the historical artifacts' hashes. This is the backward link to
  // the committed evidence corpus, and the tamper check in one gate: change a
  // fixture under the run and both sides disagree.
  artifact_identity_pinned() {
    if (!runDir) return { ok: false, detail: 'RCOS_RUN_DIR is not set' };
    const problems = [];
    for (const [name, pinned] of Object.entries(FIXTURES)) {
      const frozen = frozenFixture(name);
      if (!frozen) { problems.push('fixture ' + name + ' is not in the run input.json'); continue; }
      if (frozen.sha256 !== pinned) problems.push(name + ': frozen hash is not the historical artifact hash');
      const workCopy = path.join(work, name);
      if (!fs.existsSync(workCopy)) problems.push(name + ': no work copy');
      else if (hashFile(workCopy) !== pinned) problems.push(name + ': work copy is not the frozen fixture (changed after freeze)');
      const evCopy = path.join(runDir, 'evidence', 'inputs', name);
      if (fs.existsSync(evCopy) && hashFile(evCopy) !== pinned) problems.push(name + ': evidence copy is not the frozen fixture');
    }
    for (const p of O.probes) {
      const base = path.basename(p.file);
      if (FIXTURES[base] === undefined) { problems.push('probe ' + p.name + ' read ' + base + ', which is not one of the four pinned artifacts'); continue; }
      // Same resolution-over-string rule as the checker: when RCOS_WORK_DIR is
      // symlinked, an identical path spelled under /tmp and under /private/tmp
      // is the same directory, and the gate must judge the directory, not the string.
      if (realOr(path.resolve(path.dirname(p.file))) !== realOr(path.resolve(work))) {
        problems.push('probe ' + p.name + ' did not read from the run work dir');
      }
      if (!fs.existsSync(p.file)) { problems.push('probe ' + p.name + ': the file it read is gone'); continue; }
      if (hashFile(p.file) !== FIXTURES[base]) problems.push('probe ' + p.name + ' read bytes that are not the historical artifact');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ')
        : Object.keys(FIXTURES).length + ' fixtures pinned to their historical sha256 in work/, evidence/inputs/ and the probe argv ' +
          '(' + O.probes.length + ' probes)'
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
