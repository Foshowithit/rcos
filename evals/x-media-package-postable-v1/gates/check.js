#!/usr/bin/env node
'use strict';

// Gates for x-media-package-postable-v1 (rcos-eval/2). Each gate reads the
// CAPABILITY's recorded observation — $RCOS_INVOCATION_DIR/output.json, the bytes
// the invocation kernel froze and hashed — re-reads the raw checker text it was
// parsed from (the run's own evidence copies), re-derives fixture hashes from the
// run's frozen record, and re-extracts the poster with the checker's own ffmpeg
// arguments. Never the capability's live state, never the registry, never this
// eval's own fixtures copy.
//
// The historical logs this eval reproduces were committed with absolute poster
// paths (/Users/adam26/zcode-rcos/evidence/...); a reproduction writes its own
// poster into its own scratch dir, so the poster line is matched by SHAPE and the
// poster FILE is judged by what it resolves to (realpath), not by the string.
//
// Exit 0 = pass, 3 = fail, 4 = no observation to judge.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const os = require('node:os');
const { spawnSync } = require('node:child_process');

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
const pkg = (name) => (Array.isArray(O.packages) ? O.packages.find((p) => p.name === name) : undefined);
const work = process.env.RCOS_WORK_DIR;
const runDir = process.env.RCOS_RUN_DIR;
const home = process.env.RCOS_HOME;

// The kernel runs the adapter with cwd = the INVOCATION's own work dir, and the
// adapter records every run-local artifact (poster.path, copies[].path, run_dir)
// relative to that dir — not relative to the runner's RCOS_WORK_DIR, which holds
// the frozen fixtures the run read FROM. The two roots are different directories,
// so recorded work-relative paths are judged against this one.
const invWork = path.join(invocationDir, 'work');

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const hashFile = (p) => sha256(fs.readFileSync(p));
const realOr = (p) => {
  try {
    return fs.realpathSync(p);
  } catch (e) {
    return p;
  }
};

// A recorded path is judged as the file it resolves to, never as a string: on
// macOS /tmp and /private/tmp (and any symlinked work root) must judge identically,
// which is why recorded paths are accepted in invocation-work-relative or absolute
// spelling and compared through realpath against the run's own artifacts.
function under(base, p) {
  if (typeof p !== 'string' || p === '') return null;
  return path.isAbsolute(p) ? p : path.resolve(base, p);
}

// The checker prints its lines with fixed spacing (two spaces before `duration`);
// the committed historical logs are the source of these exact strings. Matching the
// escaped literal as a full line means a changed number, spacing or suffix fails.
function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function exactLine(stdout, s) {
  return new RegExp('^' + escapeRe(s) + '$', 'm').test(stdout);
}
const POSTER_LINE = /^poster frame -> .*x-poster\.jpg \(run muse eyes gate on this\)$/m;

const CHECKER_PIN = '641ce9064b696425ee07efc5fb0d16a80d8f9086bc11cd3e9520c641d2ba8191';
const CHECKER_PATH = 'capabilities/x-media-package/adapter/xcheck.py';

// The frozen input artifacts, by the sha256 of the bytes that live in this eval's
// fixtures/ dir and that were committed in evidence/ long before this eval existed
// (chalk-capture-recipe/eval-2, dell-gpu-dispatch/eval-2, face-in-scene-shot/eval-2,
// x-media-package/{eval-1,eval-2,eval-3,attack}). Authored controls:
// portrait-crop-chalk.mp4, duration-141s.mp4, cap-280/281/empty.txt,
// alt-empty/1000/1001.txt.
const FIXTURES = {
  'chalk-eval2.mp4': 'c43aae245a1dc031c76a826e2053195a0bc61b998559d5d3a02c4a76a83e39bd',
  'rcos-dispatch-eval-2-out.mp4': 'a73ae94906f44192414348503fe2452abecd9c9ce2e239db5c80a279ad1d1dfd',
  'shot-face-v2-r3.mp4': '596896b57a00f07ec6bb6324a16ff3706d81e6400f047b198af647314b296c84',
  'portrait-crop-chalk.mp4': '475ca8c1dd8127633cd320cdb35737716e3f080bb1956e366ce42884cd57d5ac',
  'duration-141s.mp4': 'c242f703c4c24b2209a10d8fe4ed7ba04ca99d0d620bb2fe0824c7a1f3f07481',
  'cap-eval1.txt': 'afc36fd95d66e072a52c9185320f8647f2c6dd08c9215172fa1e078bb7f8cfe2',
  'alt-eval1.txt': '20e822f258b703ede87cc832d3df945b0790a11d27189530360a5cc8fe44c3de',
  'cap-eval2.txt': '7d417d923d317054ab842000ec12cc014a0558cf02198997c34ffb5c3253f9e8',
  'alt-eval2.txt': '3f59a8cc356e60ea744cd48c29812fd008cf77051d45a46f48a70ddd0ba35cfe',
  'cap-eval3.txt': 'eb0c807b5f1ce8b92580c70abd8844dee4a0a34d220e308d47132231db6abfc0',
  'alt-eval3.txt': 'bd831332240b37c4bc080b3268257620e6913783aa34d2f423e412dee46ce149',
  'cap-attack321.txt': 'dcac91876e30961963a62bb98b22726c7aeef677f8b35d4f0cc4236ddca2e9c9',
  'cap-280.txt': 'deb992ecaaf9e772cfbec1e74c9f9bef7c262c46a67dfea16c15d213be944434',
  'cap-281.txt': 'ba561e2f2c776bda5315ab23c34ae46444df8986c966aaa839553e09b20ebf7c',
  'cap-empty.txt': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  'alt-empty.txt': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  'alt-1000.txt': '058c39df21df5cba37b7907387c81cc908a6dcc1cca74dfeb33d0a43aea98336',
  'alt-1001.txt': '0dbf8ae9985870472dd530ac3b42ea4423369c5685f01c8d7da723c44b6ef591'
};

// Container facts from the committed logs and from this box's dry run of the two
// authored videos. The checker prints them from ffprobe and len(); they are
// metadata, exact by construction, not measurements of a rendering.
const CHALK = { w: 960, h: 540, aspect: 1.778, duration: 3.0, size: 0.1, caption: 150, alt: 112 };
const DISPATCH = { w: 1280, h: 720, aspect: 1.778, duration: 4.0, size: 0.0, caption: 99, alt: 99 };
const SLATE = { w: 1080, h: 1080, aspect: 1.0, duration: 2.0, size: 0.4, caption: 148, alt: 117 };
const PORTRAIT = { w: 180, h: 540, aspect: 0.333, duration: 3.0, size: 0.0, caption: 150, alt: 112 };
const DUR141 = { w: 180, h: 320, aspect: 0.562, duration: 141.0, size: 0.0, caption: 150, alt: 112 };

const CHALK_VIDEO_LINE = 'video 960x540 aspect 1.778  duration 3.0s  size 0.1MB';
const DISPATCH_VIDEO_LINE = 'video 1280x720 aspect 1.778  duration 4.0s  size 0.0MB';
const SLATE_VIDEO_LINE = 'video 1080x1080 aspect 1.000  duration 2.0s  size 0.4MB';
const PORTRAIT_VIDEO_LINE = 'video 180x540 aspect 0.333  duration 3.0s  size 0.0MB';
const DUR141_VIDEO_LINE = 'video 180x320 aspect 0.562  duration 141.0s  size 0.0MB';

// Every package whose video is probeable records a poster — including the ones the
// checker rejects (the poster is written before the pass/fail decision, as the
// historical attack log shows). Only control_not_a_video (exit 4) has none.
const POSTER_PACKAGES = [
  'chalk_package',
  'dispatch_package',
  'slate_package',
  'attack_long_caption',
  'control_caption_280',
  'control_caption_281',
  'control_caption_empty',
  'control_alt_empty',
  'control_alt_1000',
  'control_alt_1001',
  'control_aspect_portrait',
  'control_duration_141s'
];

// The posters committed in the historical corpus, sha256 of the files on disk in
// evidence/{chalk-capture-recipe,dell-gpu-dispatch,face-in-scene-shot}/eval-2/.
// Re-extracting from the frozen videos with the checker's own arguments reproduces
// these bytes exactly (measured 2026-09-18), so a receipt that carries them carries
// the artifact the muse poster gates shipped.
const HISTORICAL_POSTERS = {
  chalk_package: '7b73e1ca6f40d98184be71165337b050e64b841f92f1abf57e1655e0e32f290c',
  dispatch_package: 'f7aff2b025279283d271b6a7b70ce411e78587301412b9e19af3c3af6d7b8051',
  slate_package: '18830a2c25d0cfcbdfa04bce1eb9eef5c8a58edee689dff86cc58f2d16ab9452'
};

function checkerCandidates(p) {
  if (!p) return [];
  if (path.isAbsolute(p)) return home ? [p, path.join(home, p.replace(/^[/\\]+/, ''))] : [p];
  return home ? [path.join(home, p), p] : [p];
}
function resolveChecker(p) {
  for (const c of checkerCandidates(p)) {
    try {
      if (fs.statSync(c).isFile()) return c;
    } catch (e) {
      /* keep looking */
    }
  }
  return null;
}

// The observation must not contradict the evidence the run itself wrote into the
// invocation dir: the checker-visible stdout/stderr/argv are re-read from disk and
// compared to what output.json says they were, the named checker must hash to the
// recorded revision, and the run must carry a frozen input record.
function evidenceProblems() {
  const problems = [];
  if (!Array.isArray(O.packages)) return ['the observation contains no packages array'];
  for (const p of O.packages) {
    const base = 'evidence/probe-' + p.name;
    const textLegs = [
      ['.stdout.txt', p.stdout, 'stdout'],
      ['.stderr.txt', p.stderr, 'stderr']
    ];
    for (const [suffix, recorded, label] of textLegs) {
      const f = path.join(invocationDir, base + suffix);
      if (!fs.existsSync(f)) {
        problems.push(base + suffix + ' is missing — the recorded ' + label + ' has no bytes behind it');
        continue;
      }
      if (fs.readFileSync(f, 'utf8') !== recorded) {
        problems.push(base + suffix + ' does not match the ' + label + ' recorded in the observation');
      }
    }
    const argvFile = path.join(invocationDir, base + '.argv.json');
    if (!fs.existsSync(argvFile)) {
      problems.push(base + '.argv.json is missing — the recorded argv has no bytes behind it');
    } else {
      const onDisk = JSON.parse(fs.readFileSync(argvFile, 'utf8'));
      if (JSON.stringify(onDisk) !== JSON.stringify(p.argv)) {
        problems.push(base + '.argv.json does not match the argv recorded in the observation');
      }
    }
  }
  const c = O.checker;
  const checkerFile = resolveChecker(c && c.path);
  if (!checkerFile) {
    problems.push('the checker named in the observation (' + ((c && c.path) || 'nothing') + ') is not on disk');
  } else if (sha256(fs.readFileSync(checkerFile)) !== (c && c.sha256)) {
    problems.push('the checker on disk does not hash to the revision the observation recorded');
  }
  if (runDir && !fs.existsSync(path.join(runDir, 'input.json'))) {
    problems.push('the run has no input.json — the frozen fixture record is gone');
  }
  return problems;
}
const EVIDENCE = evidenceProblems();

function frozenFixture(name) {
  if (!runDir) return null;
  const f = path.join(runDir, 'input.json');
  if (!fs.existsSync(f)) return null;
  const input = JSON.parse(fs.readFileSync(f, 'utf8'));
  const list = Array.isArray(input.fixtures) ? input.fixtures : [];
  return list.find((x) => (typeof x === 'string' ? x === name : x && x.name === name)) || null;
}

// The observed numbers must equal the pins; a run whose stdout is unchanged but
// whose parsed fields were edited (or the reverse) is not a reproduction.
function factsProblems(p, want, label) {
  const o = p.observed;
  const problems = [];
  const eq = (k, got, wanted) => {
    if (got !== wanted) problems.push(label + ': ' + k + ' ' + JSON.stringify(got) + ' (want ' + JSON.stringify(wanted) + ')');
  };
  if (want.w !== undefined) eq('width', o.video_width, want.w);
  if (want.h !== undefined) eq('height', o.video_height, want.h);
  if (want.aspect !== undefined) eq('aspect', o.aspect, want.aspect);
  if (want.duration !== undefined) eq('duration', o.container_duration_s, want.duration);
  if (want.size !== undefined) eq('size_mb', o.size_mb, want.size);
  if (want.caption !== undefined) eq('caption_chars', o.caption_chars, want.caption);
  if (want.alt !== undefined) eq('alt_chars', o.alt_chars, want.alt);
  return problems;
}

// The seek the checker derives from a container duration: str(min(1.0, dur/3)) in
// python, mirrored here. The shortest round-trip decimal for the double 2/3 is
// 0.6666666666666666 in both runtimes — the 2.0s slate package exercises that path.
function seekArg(durationS) {
  const s = Math.min(1.0, durationS / 3);
  return s >= 1 ? '1.0' : String(s);
}

function extractFrame(videoAbs, seek, out) {
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', seek, '-i', videoAbs, '-frames:v', '1', '-q:v', '3', out], { encoding: 'utf8' });
  if (r.error) throw new Error('ffmpeg could not be run: ' + r.error.message);
  return r;
}

const checks = {
  // The three acceptance packages: exit 0, the checker's own pass marker, and the
  // exact stdout lines committed in the historical logs (the poster PATH is
  // run-local and matched by shape; every other line is the historical literal).
  platform_limits_pass() {
    const problems = [];
    if (O.schema !== 'x-media-package-observation/1') problems.push('observation schema ' + JSON.stringify(O.schema) + ' (want x-media-package-observation/1)');
    const legs = [
      ['chalk_package', CHALK, CHALK_VIDEO_LINE, 'caption 150 chars', 'alt-text 112 chars'],
      ['dispatch_package', DISPATCH, DISPATCH_VIDEO_LINE, 'caption 99 chars', 'alt-text 99 chars'],
      ['slate_package', SLATE, SLATE_VIDEO_LINE, 'caption 148 chars', 'alt-text 117 chars']
    ];
    for (const [name, want, videoLine, captionLine, altLine] of legs) {
      const p = pkg(name);
      if (!p) {
        problems.push('package ' + name + ' missing');
        continue;
      }
      if (p.exit_status !== 0) problems.push(name + ': exit ' + p.exit_status + ' (want 0)');
      if (p.outcome !== 'passed') problems.push(name + ': outcome ' + JSON.stringify(p.outcome) + ' (want passed)');
      if (p.observed.pass_marker !== true) problems.push(name + ': the checker did not print XCHECK_PASS');
      if (p.observed.fail_lines.length > 0) problems.push(name + ': fail lines ' + JSON.stringify(p.observed.fail_lines));
      if (!exactLine(p.stdout, videoLine)) problems.push(name + ': the historical video line is not reproduced verbatim: ' + JSON.stringify(videoLine));
      if (!exactLine(p.stdout, captionLine)) problems.push(name + ': line ' + JSON.stringify(captionLine) + ' is not reproduced');
      if (!exactLine(p.stdout, altLine)) problems.push(name + ': line ' + JSON.stringify(altLine) + ' is not reproduced');
      if (!POSTER_LINE.test(p.stdout)) problems.push(name + ': no poster-frame line in the checker output');
      problems.push(...factsProblems(p, want, name));
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'chalk 960x540/3.0s, dispatch 1280x720/4.0s, slate 1080x1080/2.0s all XCHECK_PASS with their historical lines reproduced verbatim, poster line present'
    };
  },

  // The historical attack: a 321-char caption on the SAME video and alt text the
  // accepted chalk package used — the catch is attributable to the caption.
  long_caption_caught() {
    const p = pkg('attack_long_caption');
    const paired = pkg('chalk_package');
    if (!p) return { ok: false, detail: 'package attack_long_caption missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (p.outcome !== 'caught') problems.push('outcome ' + JSON.stringify(p.outcome) + ' (want caught)');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on the 321-char caption');
    if (p.observed.fail_lines.length !== 1) problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines) + ' (want exactly one)');
    else if (p.observed.fail_lines[0] !== 'CAPTION 321 > 280 chars') problems.push('fail line is not the historical rejection: ' + JSON.stringify(p.observed.fail_lines[0]));
    if (!exactLine(p.stdout, 'FAIL CAPTION 321 > 280 chars')) problems.push('the historical attack line is not reproduced verbatim');
    if (!exactLine(p.stdout, 'caption 321 chars')) problems.push('the 321-char caption line is not reproduced');
    problems.push(...factsProblems(p, { w: CHALK.w, h: CHALK.h, aspect: CHALK.aspect, duration: CHALK.duration, caption: 321, alt: CHALK.alt }, 'attack'));
    if (!paired) problems.push('chalk_package missing, so the attack cannot be tied to the accepted package');
    else {
      if (!exactLine(p.stdout, CHALK_VIDEO_LINE)) problems.push('the attack did not reproduce the accepted chalk video line — a different file would explain the catch');
      if (p.observed.alt_chars !== paired.observed.alt_chars) problems.push('the attack alt text differs from the accepted package (caption is supposed to be the only change)');
      if (paired.exit_status !== 0) problems.push('the accepted chalk package did not pass in this run, so the attack has no baseline');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'the 321-char caption on the accepted chalk video is caught (exit 3) on the historical line, while the same video+caption150+alt112 passes'
    };
  },

  // The 280-char limit from both sides, plus the empty file: the boundary is where
  // the limit claims to be, not one character off in either direction.
  caption_limit_bites() {
    const inside = pkg('control_caption_280');
    const outside = pkg('control_caption_281');
    const empty = pkg('control_caption_empty');
    const problems = [];
    for (const [name, p] of [['control_caption_280', inside], ['control_caption_281', outside], ['control_caption_empty', empty]]) {
      if (!p) problems.push('package ' + name + ' missing');
    }
    if (inside) {
      if (inside.exit_status !== 0) problems.push('280 chars: exit ' + inside.exit_status + ' (want 0)');
      if (inside.outcome !== 'passed') problems.push('280 chars: outcome ' + JSON.stringify(inside.outcome) + ' (want passed)');
      if (inside.observed.fail_lines.length > 0) problems.push('280 chars: fail lines ' + JSON.stringify(inside.observed.fail_lines));
      if (inside.observed.caption_chars !== 280) problems.push('280 chars: caption_chars ' + JSON.stringify(inside.observed.caption_chars));
      if (!exactLine(inside.stdout, 'caption 280 chars')) problems.push('280 chars: the printed count line is not reproduced');
      if (!exactLine(inside.stdout, CHALK_VIDEO_LINE)) problems.push('280 chars: not the chalk video — the caption is supposed to be the only difference');
    }
    if (outside) {
      if (outside.exit_status !== 3) problems.push('281 chars: exit ' + outside.exit_status + ' (want 3)');
      if (outside.outcome !== 'caught') problems.push('281 chars: outcome ' + JSON.stringify(outside.outcome) + ' (want caught)');
      if (outside.observed.pass_marker === true) problems.push('281 chars: the checker reported PASS');
      if (outside.observed.fail_lines.length !== 1 || outside.observed.fail_lines[0] !== 'CAPTION 281 > 280 chars') problems.push('281 chars: fail lines ' + JSON.stringify(outside.observed.fail_lines));
      if (outside.observed.caption_chars !== 281) problems.push('281 chars: caption_chars ' + JSON.stringify(outside.observed.caption_chars));
      if (!exactLine(outside.stdout, 'caption 281 chars')) problems.push('281 chars: the printed count line is not reproduced');
      if (!exactLine(outside.stdout, CHALK_VIDEO_LINE)) problems.push('281 chars: not the chalk video — the caption is supposed to be the only difference');
    }
    if (empty) {
      if (empty.exit_status !== 3) problems.push('empty caption: exit ' + empty.exit_status + ' (want 3)');
      if (empty.observed.fail_lines.length !== 1 || empty.observed.fail_lines[0] !== 'CAPTION_EMPTY') problems.push('empty caption: fail lines ' + JSON.stringify(empty.observed.fail_lines));
      if (empty.observed.caption_chars !== 0) problems.push('empty caption: caption_chars ' + JSON.stringify(empty.observed.caption_chars));
      if (!exactLine(empty.stdout, 'caption 0 chars')) problems.push('empty caption: the printed count line is not reproduced');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : '280 chars passes, 281 is caught, the empty caption is caught, all three on the chalk video with only the caption differing'
    };
  },

  // Alt text: 1000 passes, 1001 is caught, empty is caught as the accessibility
  // gate — on the chalk video with the accepted caption text.
  alt_gate_bites() {
    const inside = pkg('control_alt_1000');
    const outside = pkg('control_alt_1001');
    const empty = pkg('control_alt_empty');
    const problems = [];
    for (const [name, p] of [['control_alt_1000', inside], ['control_alt_1001', outside], ['control_alt_empty', empty]]) {
      if (!p) problems.push('package ' + name + ' missing');
    }
    if (inside) {
      if (inside.exit_status !== 0) problems.push('1000 chars: exit ' + inside.exit_status + ' (want 0)');
      if (inside.outcome !== 'passed') problems.push('1000 chars: outcome ' + JSON.stringify(inside.outcome));
      if (inside.observed.fail_lines.length > 0) problems.push('1000 chars: fail lines ' + JSON.stringify(inside.observed.fail_lines));
      if (inside.observed.alt_chars !== 1000) problems.push('1000 chars: alt_chars ' + JSON.stringify(inside.observed.alt_chars));
      if (!exactLine(inside.stdout, 'alt-text 1000 chars')) problems.push('1000 chars: the printed count line is not reproduced');
      if (!exactLine(inside.stdout, CHALK_VIDEO_LINE)) problems.push('1000 chars: not the chalk video — the alt text is supposed to be the only difference');
      if (inside.observed.caption_chars !== CHALK.caption) problems.push('1000 chars: the caption changed too (want the accepted 150)');
    }
    if (outside) {
      if (outside.exit_status !== 3) problems.push('1001 chars: exit ' + outside.exit_status + ' (want 3)');
      if (outside.outcome !== 'caught') problems.push('1001 chars: outcome ' + JSON.stringify(outside.outcome));
      if (outside.observed.pass_marker === true) problems.push('1001 chars: the checker reported PASS');
      if (outside.observed.fail_lines.length !== 1 || outside.observed.fail_lines[0] !== 'ALT_TEXT 1001 > 1000 chars') problems.push('1001 chars: fail lines ' + JSON.stringify(outside.observed.fail_lines));
      if (outside.observed.alt_chars !== 1001) problems.push('1001 chars: alt_chars ' + JSON.stringify(outside.observed.alt_chars));
      if (!exactLine(outside.stdout, 'alt-text 1001 chars')) problems.push('1001 chars: the printed count line is not reproduced');
      if (!exactLine(outside.stdout, CHALK_VIDEO_LINE)) problems.push('1001 chars: not the chalk video — the alt text is supposed to be the only difference');
    }
    if (empty) {
      if (empty.exit_status !== 3) problems.push('empty alt text: exit ' + empty.exit_status + ' (want 3)');
      if (empty.observed.fail_lines.length !== 1 || empty.observed.fail_lines[0] !== 'ALT_TEXT_EMPTY (accessibility gate)') problems.push('empty alt text: fail lines ' + JSON.stringify(empty.observed.fail_lines));
      if (empty.observed.alt_chars !== 0) problems.push('empty alt text: alt_chars ' + JSON.stringify(empty.observed.alt_chars));
      if (!exactLine(empty.stdout, 'alt-text 0 chars')) problems.push('empty alt text: the printed count line is not reproduced');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : '1000 chars passes, 1001 is caught, empty alt text is caught as the accessibility gate, all on the chalk video with the accepted caption'
    };
  },

  // A portrait crop of the chalk video: same duration (3.0s), same caption text
  // (150) and alt text (112) as the accepted package — the only changed fact is the
  // pixel geometry, and the checker's only complaint is the aspect.
  aspect_gate_bites() {
    const p = pkg('control_aspect_portrait');
    if (!p) return { ok: false, detail: 'package control_aspect_portrait missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (p.outcome !== 'caught') problems.push('outcome ' + JSON.stringify(p.outcome) + ' (want caught)');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on the portrait crop');
    if (p.observed.fail_lines.length !== 1 || p.observed.fail_lines[0] !== 'ASPECT 0.333 outside [0.5, 2.0]') problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines));
    if (!exactLine(p.stdout, PORTRAIT_VIDEO_LINE)) problems.push('the portrait video line is not reproduced verbatim');
    if (!exactLine(p.stdout, 'caption 150 chars')) problems.push('the accepted caption line is not reproduced (the crop should not have changed it)');
    if (!exactLine(p.stdout, 'alt-text 112 chars')) problems.push('the accepted alt-text line is not reproduced (the crop should not have changed it)');
    problems.push(...factsProblems(p, PORTRAIT, 'portrait'));
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'the portrait crop (180x540, aspect 0.333) is caught on aspect alone, with duration, caption and alt text unchanged from the accepted chalk package'
    };
  },

  // A 141s clip: aspect 0.562 is inside [0.5, 2.0] and the caption/alt text are the
  // accepted text — duration is the only fail line.
  duration_gate_bites() {
    const p = pkg('control_duration_141s');
    if (!p) return { ok: false, detail: 'package control_duration_141s missing' };
    const problems = [];
    if (p.exit_status !== 3) problems.push('exit ' + p.exit_status + ' (want 3)');
    if (p.outcome !== 'caught') problems.push('outcome ' + JSON.stringify(p.outcome) + ' (want caught)');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on the 141s clip');
    if (p.observed.fail_lines.length !== 1 || p.observed.fail_lines[0] !== 'DURATION 141.0s > 140s organic limit') problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines));
    if (!exactLine(p.stdout, DUR141_VIDEO_LINE)) problems.push('the 141s video line is not reproduced verbatim');
    if (!exactLine(p.stdout, 'caption 150 chars')) problems.push('the accepted caption line is not reproduced (the length control should not have changed it)');
    if (!exactLine(p.stdout, 'alt-text 112 chars')) problems.push('the accepted alt-text line is not reproduced');
    problems.push(...factsProblems(p, DUR141, '141s'));
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'the 141.0s clip is caught on duration alone (aspect 0.562 is in range, caption and alt text are the accepted ones)'
    };
  },

  // The poster claim checked against the bytes it names: the file the observation
  // points at resolves to this package's own x-poster.jpg (judged through realpath,
  // so a symlinked work root is the same file), its sha256/size are the recorded
  // ones, its JPEG dimensions are the video's, the evidence copy behind the claim
  // matches, and a package the probe could not open carries no poster at all.
  poster_extracted() {
    const problems = [];
    for (const name of POSTER_PACKAGES) {
      const p = pkg(name);
      if (!p) {
        problems.push('package ' + name + ' missing');
        continue;
      }
      const o = p.observed;
      const claim = o.poster;
      if (!claim) {
        problems.push(name + ': no poster recorded although the probe reached the frame step');
        continue;
      }
      const workPoster = path.join(invWork, p.run_dir, 'x-poster.jpg');
      const named = under(invWork, claim.path);
      if (!named) problems.push(name + ': the poster claim names no path');
      else {
        if (!fs.existsSync(named)) problems.push(name + ': the poster file it names is gone: ' + claim.path);
        else {
          const bytes = fs.readFileSync(named);
          if (sha256(bytes) !== claim.sha256) problems.push(name + ': the poster bytes are not the poster the observation records');
          if (bytes.length !== claim.bytes) problems.push(name + ': poster size ' + bytes.length + ' (recorded ' + claim.bytes + ')');
        }
        if (realOr(named) !== realOr(workPoster)) problems.push(name + ': the poster claim does not resolve to this package\'s own x-poster.jpg');
      }
      if (claim.jpeg !== true) problems.push(name + ': the recorded poster bytes are not a JPEG');
      if (claim.width !== o.video_width || claim.height !== o.video_height) {
        problems.push(name + ': poster ' + claim.width + 'x' + claim.height + ' is not a frame of the ' + o.video_width + 'x' + o.video_height + ' video');
      }
      const evid = path.join(invocationDir, 'evidence', 'probe-' + name + '.poster.jpg');
      if (!fs.existsSync(evid)) problems.push(name + ': the poster evidence copy is missing');
      else if (hashFile(evid) !== claim.sha256) problems.push(name + ': the poster evidence copy is not the poster the observation records');
    }
    const notvid = pkg('control_not_a_video');
    if (!notvid) problems.push('package control_not_a_video missing');
    else {
      if (notvid.observed.poster !== null) problems.push('control_not_a_video: a poster is recorded for a file the probe could not open');
      if (notvid.observed.poster_seek_s !== null) problems.push('control_not_a_video: a poster seek is recorded for a file the probe could not open');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'all 12 probeable packages carry a poster whose file, bytes, JPEG dimensions and evidence copy match the claim; the unprobeable package carries none'
    };
  },

  // The offset claim re-derived: the seek must be the one the checker computes from
  // the container duration the run recorded, and re-extracting from the package's own
  // video copy at that seek must produce the recorded bytes — in a fresh directory
  // each time, so a failed extraction can never leave a previous file to be read as
  // a result. The three acceptance packages must additionally reproduce the poster
  // committed in the historical corpus.
  poster_offset_reproduced() {
    const problems = [];
    for (const name of POSTER_PACKAGES) {
      const p = pkg(name);
      if (!p) {
        problems.push('package ' + name + ' missing');
        continue;
      }
      const o = p.observed;
      if (!o.poster) {
        problems.push(name + ': no recorded poster, so there is nothing to re-derive');
        continue;
      }
      const expected = o.container_duration_s === null ? null : seekArg(o.container_duration_s);
      if (o.poster_seek_s !== expected) {
        problems.push(name + ': recorded seek ' + JSON.stringify(o.poster_seek_s) + ' is not the seek the checker derives from ' + o.container_duration_s + 's (want ' + JSON.stringify(expected) + ')');
      }
      const videoCopy = (Array.isArray(p.copies) ? p.copies.find((c) => c.role === 'video') : null) || null;
      const videoAbs = videoCopy ? under(invWork, videoCopy.path) : null;
      if (!videoAbs || !fs.existsSync(videoAbs)) {
        problems.push(name + ': the video copy the poster came from is not readable');
        continue;
      }
      const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'xmp-offset-'));
      try {
        const out = path.join(scratch, 'x-poster.jpg');
        const r = extractFrame(videoAbs, o.poster_seek_s, out);
        if (r.status !== 0 || !fs.existsSync(out)) {
          problems.push(name + ': re-extracting at ' + o.poster_seek_s + 's failed (ffmpeg exit ' + r.status + ') — a recorded poster must be reproducible from its own video copy');
          continue;
        }
        const fresh = sha256(fs.readFileSync(out));
        if (fresh !== o.poster.sha256) {
          problems.push(name + ': re-extracting at ' + o.poster_seek_s + 's yields ' + fresh.slice(0, 16) + '…, not the recorded ' + o.poster.sha256.slice(0, 16) + '…');
        }
      } finally {
        fs.rmSync(scratch, { recursive: true, force: true });
      }
      const hist = HISTORICAL_POSTERS[name];
      if (hist && o.poster.sha256 !== hist) {
        problems.push(name + ': the recorded poster is not the poster committed in the historical corpus (' + hist.slice(0, 16) + '…)');
      }
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'all 12 posters re-extract to their recorded bytes from their own video copies at the seek the duration implies; the three acceptance posters are the committed historical files'
    };
  },

  // The probe-failure path reports what it could not learn: exit 4, the PROBE_FAIL
  // line, no pass marker, no fail lines, and every container fact null — a file the
  // probe could not open has no dimensions, no duration and no caption to report.
  cannot_probe_reported() {
    const p = pkg('control_not_a_video');
    if (!p) return { ok: false, detail: 'package control_not_a_video missing' };
    const problems = [];
    if (p.exit_status !== 4) problems.push('exit ' + p.exit_status + ' (want 4: the probe could not read the file)');
    if (p.outcome !== 'could_not_probe') problems.push('outcome ' + JSON.stringify(p.outcome) + ' (want could_not_probe)');
    if (p.observed.pass_marker === true) problems.push('the checker reported PASS on a text file');
    if (p.observed.fail_lines.length > 0) problems.push('fail lines ' + JSON.stringify(p.observed.fail_lines) + ' (a file the probe could not open has no verdict lines)');
    if (!/^PROBE_FAIL .+/m.test(p.stdout)) problems.push('the checker output carries no PROBE_FAIL line: ' + JSON.stringify(String(p.stdout).trim().slice(0, 120)));
    for (const k of ['video_width', 'video_height', 'aspect', 'container_duration_s', 'size_mb', 'caption_chars', 'alt_chars']) {
      if (p.observed[k] !== null) problems.push(k + ' ' + JSON.stringify(p.observed[k]) + ' (want null: nothing was probed)');
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'a text file passed as a video reaches exit 4 with the PROBE_FAIL line and every container and text fact null'
    };
  },

  // The checker revision the run used is the frozen one: the recorded hash is the
  // pin, and the file it names (however it is spelled) resolves to the same bytes.
  checker_revision_pinned() {
    const problems = [];
    const c = O.checker;
    if (!c || typeof c !== 'object') return { ok: false, detail: 'the observation records no checker' };
    if (c.sha256 !== CHECKER_PIN) problems.push('recorded checker revision ' + String(c.sha256).slice(0, 16) + '… is not the pinned revision');
    const named = resolveChecker(c.path);
    if (!named) problems.push('the named checker is not on disk: ' + c.path);
    else if (sha256(fs.readFileSync(named)) !== CHECKER_PIN) problems.push('the checker on disk is not the pinned revision');
    else if (home && realOr(named) !== realOr(path.join(home, CHECKER_PATH))) problems.push('the named checker is not X-media-package\'s checker at ' + CHECKER_PATH);
    const codes = Array.isArray(c.documented_exit_codes) ? c.documented_exit_codes : [];
    if (JSON.stringify(codes) !== JSON.stringify([0, 3, 4])) problems.push('documented exit codes ' + JSON.stringify(codes) + ' (want [0,3,4])');
    return {
      ok: problems.length === 0,
      detail: problems.length ? problems.join(' | ') : 'checker hash is the pin 641ce906…, the named file resolves to capabilities/x-media-package/adapter/xcheck.py, exit codes [0,3,4]'
    };
  },

  // Every artifact the run read is the historical file: the 18 fixtures frozen in the
  // run's input.json hash to the pins, each package's three copies are those files (the
  // adapter records them relative to the invocation's own work dir — its cwd — so that
  // is the root they are judged against, through realpath, so a symlinked root and an
  // absolute spelling are the same file).
  artifact_identity_pinned() {
    if (!runDir) return { ok: false, detail: 'RCOS_RUN_DIR is not set — fixture identity is judged against the frozen run record' };
    const problems = [];
    for (const [name, pinned] of Object.entries(FIXTURES)) {
      const frozen = frozenFixture(name);
      if (!frozen) {
        problems.push('fixture ' + name + ' is not in the run input.json');
        continue;
      }
      if (frozen.sha256 !== pinned) problems.push(name + ': the frozen hash is not the historical artifact hash');
      if (work) {
        const workCopy = path.join(work, name);
        if (!fs.existsSync(workCopy)) problems.push(name + ': no work copy');
        else if (hashFile(workCopy) !== pinned) problems.push(name + ': the work copy is not the frozen fixture (changed after freeze)');
      }
      const evCopy = path.join(runDir, 'evidence', 'inputs', name);
      if (fs.existsSync(evCopy) && hashFile(evCopy) !== pinned) problems.push(name + ': the evidence copy is not the frozen fixture');
    }
    const roles = ['video', 'caption', 'alt'];
    for (const p of Array.isArray(O.packages) ? O.packages : []) {
      const copies = Array.isArray(p.copies) ? p.copies : [];
      if (copies.length !== roles.length) problems.push(p.name + ': ' + copies.length + ' copies recorded (want 3)');
      for (const role of roles) {
        const c = copies.find((x) => x.role === role);
        if (!c) {
          problems.push(p.name + ': no ' + role + ' copy recorded');
          continue;
        }
        const srcName = path.basename(String(c.source));
        if (FIXTURES[srcName] === undefined) problems.push(p.name + ': the ' + role + ' copy came from ' + srcName + ', which is not one of the pinned artifacts');
        else if (c.sha256 !== FIXTURES[srcName]) problems.push(p.name + ': the recorded ' + role + ' copy hash is not ' + srcName + '\'s historical hash');
        const onDisk = under(invWork, c.path);
        if (!onDisk || !fs.existsSync(onDisk)) problems.push(p.name + ': the ' + role + ' copy ' + c.path + ' is not in the invocation work dir');
        else if (hashFile(onDisk) !== c.sha256) problems.push(p.name + ': the bytes at ' + c.path + ' are not the copy the checker was given');
        const i = roles.indexOf(role);
        const argvPath = Array.isArray(p.argv) ? p.argv[i] : undefined;
        if (argvPath === undefined) problems.push(p.name + ': argv is missing entry ' + i + ' (' + role + ')');
        else if (realOr(argvPath) !== realOr(path.join(invWork, c.path))) problems.push(p.name + ': argv[' + i + '] does not name the run\'s ' + role + ' copy');
      }
    }
    return {
      ok: problems.length === 0,
      detail: problems.length
        ? problems.join(' | ')
        : 'all 18 fixtures are the pinned historical artifacts in the frozen record and the work dir; every package\'s three copies and its recorded argv name those files'
    };
  }
};

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
