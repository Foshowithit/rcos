'use strict';
// Gates for agents-md-compactor-v1 (rcos-eval/2). Each gate reads the
// CAPABILITY's recorded observation — $RCOS_INVOCATION_DIR/output.json, the
// bytes the invocation kernel froze and hashed — and decides whether the
// tool's OWN stated policy held. Exit 0 = pass, 3 = fail, 4 = cannot decide.
//
// Policy under test (from the tool's docstring):
//   P1  each changelog entry is replaced by its bold headline (or its first
//       ~220 chars when it has none) — an entry that HAS a headline keeps it
//   P2  only the region from '## Changelog' onward is touched; '#' headings are
//       preserved verbatim; the '- \u26a0 *' policy line is never digested
//   P3  compaction is idempotent
//   P4  cuts land on clause/word boundaries and never build a malformed entry
//   P5  a dated backup is written before the file is rewritten
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const gateId = process.argv[2];
const POLICY_RE = /^- \u26a0 \*/;
const DIGEST_MAX = 220;
const HEADLINE_MAX = 300;

// The tool under test is frozen: these bytes, and only these. Checked three
// independent ways below — this literal, the eval's own fixture copy, and the
// evidence the kernel recorded. The old form hashed one file against itself
// and could not fail.
const PINNED_TOOL_SHA256 = '0955ad78cd4808dae85c5b74818839c2f1e1f5f4f4dfccdd0fa5a7cce85cc1e9';

const invocationDir = process.env.RCOS_INVOCATION_DIR;
if (!invocationDir) {
  console.log('blocked: RCOS_INVOCATION_DIR is not set — this gate judges an invocation, not a work dir');
  process.exit(4);
}
const obsPath = path.join(invocationDir, 'output.json');
if (!fs.existsSync(obsPath)) {
  console.log('blocked: ' + obsPath + ' not found — the capability produced no observation');
  process.exit(4);
}
const ledger = JSON.parse(fs.readFileSync(obsPath, 'utf8'));

function split(text) {
  const lines = text.split('\n');
  const ci = lines.findIndex((l) => l.startsWith('## Changelog'));
  return ci < 0 ? null : { head: lines.slice(0, ci), body: lines.slice(ci) };
}
const isEntry = (l) => l.startsWith('- ') && !POLICY_RE.test(l);
const entriesOf = (lines) => lines.filter(isEntry);
const stripEllipsis = (l) => (l.endsWith(' \u2026') ? l.slice(0, -2) : l);
const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

const before = split(ledger.pass1.input);
const after = split(ledger.pass1.output);
if (!before || !after) { console.log('blocked: fixture has no ## Changelog region'); process.exit(4); }
const srcs = entriesOf(before.body);
const digs = entriesOf(after.body);

// P1 — an entry that carries a headline keeps it; no digest invents text.
function semanticSurvival() {
  const problems = [];
  if (srcs.length !== digs.length) {
    problems.push('entry count changed: ' + srcs.length + ' in, ' + digs.length + ' out');
  }
  for (let i = 0; i < Math.min(srcs.length, digs.length); i++) {
    const src = srcs[i], dig = digs[i];
    const body = stripEllipsis(dig);
    if (!src.startsWith(body)) {
      problems.push('entry ' + i + ': digest is not a reduction of its source — ' + JSON.stringify(dig.slice(0, 80)));
      continue;
    }
    if (/\*\*.+?\*\*/.test(src) && !/\*\*.+?\*\*/.test(dig)) {
      problems.push('entry ' + i + ': source carries a bold headline and the digest dropped it — ' + JSON.stringify(dig.slice(0, 80)));
    }
    const bare = dig.replace(/^- (?:20\d\d-)?\d\d-\d\d\s*/, '').replace(/ \u2026$/, '');
    if (bare.length < 40) problems.push('entry ' + i + ': digest keeps only ' + bare.length + ' characters of content');
  }
  return problems.length === 0
    ? { ok: true, detail: srcs.length + ' entries digested, every digest a reduction of its source, every headline kept' }
    : { ok: false, detail: problems.length + ' violation(s): ' + problems.join(' | ') };
}

// P2 — head region untouched, headings verbatim, policy line untouched, order kept.
function rangeAndOrder() {
  const problems = [];
  const headIn = before.head.join('\n'), headOut = after.head.join('\n');
  if (headIn !== headOut) problems.push('the region before ## Changelog was rewritten');
  const headingsIn = before.body.filter((l) => l.startsWith('#'));
  const headingsOut = after.body.filter((l) => l.startsWith('#'));
  if (headingsIn.join('\n') !== headingsOut.join('\n')) {
    problems.push('headings inside the changelog changed: ' + JSON.stringify(headingsIn.join('|')) + ' -> ' + JSON.stringify(headingsOut.join('|')));
  }
  const polIn = before.body.filter((l) => POLICY_RE.test(l));
  const polOut = after.body.filter((l) => POLICY_RE.test(l));
  if (polIn.length !== polOut.length || polIn.join('\n') !== polOut.join('\n')) {
    problems.push('the - \u26a0 * policy line was not preserved verbatim');
  }
  if (polIn.length === 0) problems.push('fixture has no policy line to preserve (the check would be vacuous)');
  for (let i = 0; i < Math.min(srcs.length, digs.length); i++) {
    const d = srcs[i].match(/^- (?:20\d\d-)?\d\d-\d\d/);
    if (d && !digs[i].startsWith(d[0])) problems.push('entry ' + i + ': date prefix lost or reordered');
  }
  return problems.length === 0
    ? { ok: true, detail: 'head region byte-identical, ' + headingsIn.length + ' heading(s) and ' + polIn.length + ' policy line(s) verbatim, order preserved' }
    : { ok: false, detail: problems.join(' | ') };
}

// P3 — running the tool on its own output changes nothing.
function idempotence() {
  if (ledger.pass2.output === ledger.pass1.output) {
    return { ok: true, detail: 'second pass over the digested file is byte-identical (' + ledger.pass1.output.length + ' bytes)' };
  }
  const a = ledger.pass1.output.split('\n'), b = ledger.pass2.output.split('\n');
  const first = a.findIndex((l, i) => l !== b[i]);
  return {
    ok: false,
    detail: 'second pass is not a no-op: ' + a.length + ' -> ' + b.length + ' lines, first difference at line ' + first +
      ' ' + JSON.stringify((a[first] || '').slice(0, 70)) + ' -> ' + JSON.stringify((b[first] || '').slice(0, 70))
  };
}

// P4 — a shortened digest is marked as shortened, bounded, and well-formed.
function digestConstruction() {
  const problems = [];
  for (let i = 0; i < Math.min(srcs.length, digs.length); i++) {
    const src = srcs[i], dig = digs[i];
    const shortened = dig.length < src.length;
    if (shortened && !dig.endsWith(' \u2026')) problems.push('entry ' + i + ': shortened but not marked with a trailing ellipsis');
    const hasHeadline = /\*\*.+?\*\*/.test(src);
    const limit = hasHeadline ? HEADLINE_MAX : DIGEST_MAX + 2;
    if (dig.length > limit) problems.push('entry ' + i + ': digest is ' + dig.length + ' chars, over the ' + limit + ' limit');
    const bolds = (dig.match(/\*\*/g) || []).length;
    if (bolds % 2) problems.push('entry ' + i + ': unbalanced bold marker left in the digest');
    if ((dig.match(/`/g) || []).length % 2) problems.push('entry ' + i + ': unbalanced inline-code marker left in the digest');
    if (/^- (?:20\d\d-)?\d\d-\d\d\s*\u2026?$/.test(dig)) problems.push('entry ' + i + ': digest reduced to a bare date');
  }
  return problems.length === 0
    ? { ok: true, detail: srcs.length + ' digests bounded, ellipsis-marked when shortened, no dangling markers' }
    : { ok: false, detail: problems.join(' | ') };
}

// P5 — the backup exists and holds the pre-run bytes; without a backup the file
// is not touched at all.
function backupBeforeWrite() {
  const problems = [];
  for (const pass of ['pass1', 'pass2']) {
    const p = ledger[pass];
    if (!p.backup) { problems.push(pass + ': no backup written'); continue; }
    if (p.backup.sha256 !== p.input_sha256) problems.push(pass + ': backup does not match the pre-run bytes');
  }
  const na = ledger.noarchive;
  if (na.output !== na.input) problems.push('noarchive: the file was rewritten even though no backup could be written');
  return problems.length === 0
    ? { ok: true, detail: 'backups match pre-run bytes for both passes; without an archive dir the file was left untouched (exit ' + na.exit + ')' }
    : { ok: false, detail: problems.join(' | ') };
}

// Provenance of the thing under test, pinned three ways: the literal hash of
// the frozen tool, the eval's own frozen fixture (which the capability never
// executes), and the evidence the kernel recorded for the bytes that ran.
function frozenTool() {
  const problems = [];
  const ran = ledger.tool.sha256;
  if (ran !== PINNED_TOOL_SHA256) {
    problems.push('the tool that ran (' + String(ran).slice(0, 12) + ') is not the pinned tool (' + PINNED_TOOL_SHA256.slice(0, 12) + ')');
  }
  if (ledger.tool.source !== 'capability') {
    problems.push('the run was pointed at a tool by its input (source=' + ledger.tool.source + ') instead of the capability\'s own copy');
  }
  const runDir = process.env.RCOS_RUN_DIR;
  const runInput = path.join(runDir || '', 'input.json');
  if (!runDir || !fs.existsSync(runInput)) {
    problems.push('the eval\'s frozen inputs (RCOS_RUN_DIR/input.json) are not readable');
  } else {
    const fx = (JSON.parse(fs.readFileSync(runInput, 'utf8')).fixtures || []).find((f) => f.name === 'compact_agents_md.py');
    if (!fx) problems.push('this package no longer freezes compact_agents_md.py as its pin');
    else if (fx.sha256 !== PINNED_TOOL_SHA256) {
      problems.push('the eval\'s frozen pin (' + fx.sha256.slice(0, 12) + ') is not the pinned tool (' + PINNED_TOOL_SHA256.slice(0, 12) + ')');
    }
  }
  const evTool = path.join(invocationDir, 'evidence', 'executed-tool.py');
  if (!fs.existsSync(evTool)) problems.push('evidence/executed-tool.py missing');
  else if (sha256(fs.readFileSync(evTool)) !== ran) problems.push('evidence/executed-tool.py is not the tool the observation says ran');
  return problems.length === 0
    ? { ok: true, detail: 'tool under test is the pinned tool ' + PINNED_TOOL_SHA256.slice(0, 12) + ' (' + ledger.tool.bytes + ' bytes), executed from the capability\'s own copy, matching the eval\'s frozen pin and the recorded evidence' }
    : { ok: false, detail: problems.join(' | ') };
}

const GATES = {
  'semantic-survival': semanticSurvival,
  'range-and-order': rangeAndOrder,
  'idempotence': idempotence,
  'digest-construction': digestConstruction,
  'backup-before-write': backupBeforeWrite,
  'frozen-tool': frozenTool
};

if (!GATES[gateId]) { console.log('blocked: unknown gate ' + gateId); process.exit(4); }
const res = GATES[gateId]();
console.log((res.ok ? 'PASS ' : 'FAIL ') + gateId + ': ' + res.detail);
process.exit(res.ok ? 0 : 3);
