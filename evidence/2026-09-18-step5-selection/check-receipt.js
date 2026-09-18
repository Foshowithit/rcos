#!/usr/bin/env node
// Read-only verifier for the claims RECEIPT.json makes that sync-receipt.js does
// NOT own.
//
// sync-receipt.js recomputes the derived fields and writes them. That closes the
// transcription gap but it leaves a different one open: the receipt also asserts
// things that are not derived from the two records of record — that a named commit
// exists and contains exactly the named paths, that the pinned blob shas are the
// bytes that commit actually contains, that the dogfood invocations on disk really
// carry the cited selection and decision ids, that the sweep's funnel numbers are
// the sweep's numbers. Nothing in the sync loop would notice if any of those were
// wrong, because nothing in the sync loop reads them.
//
// So this file reads them. It writes nothing, mutates nothing, and mints no
// artifacts: every check is a comparison between the receipt, git, and bytes on
// disk. Run it after sync-receipt.js; a receipt that passes both is consistent
// with its records AND with the world.
//
// Two classes of claim are checked differently:
//   HARD  — must match exactly. A mismatch is a FAIL and exits 1.
//   LIVE  — a value that was true when the receipt was written and that the
//           autonomous study loop may legitimately have moved since (the registry
//           and trace shas). A mismatch prints MOVED with the commits that moved
//           it, so drift is visible and attributed instead of silent. It does not
//           fail the run, because a receipt is a statement about a moment and the
//           study loop is allowed to write after that moment.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const HOME = path.resolve(__dirname, '..', '..');
const RECEIPT_PATH = path.join(__dirname, 'RECEIPT.json');
const receipt = JSON.parse(fs.readFileSync(RECEIPT_PATH, 'utf8'));

const sha256 = (buf) => crypto.createHash('sha256').update(buf).digest('hex');
const sha256File = (p) => sha256(fs.readFileSync(p));
const countLines = (buf) => (buf.toString('utf8').match(/\n/g) || []).length;
const countNonEmpty = (buf) => buf.toString('utf8').split('\n').filter((l) => l.trim().length > 0).length;

const git = (...args) => execFileSync('git', args, { cwd: HOME, maxBuffer: 256 * 1024 * 1024 });
const gitText = (...args) => git(...args).toString('utf8');
const gitBlob = (rev, p) => git('show', rev + ':' + p);
const gitBlobSha = (rev, p) => sha256(gitBlob(rev, p));

// ids carry their own creation second: sel_20260918T041756Z-75466d
const idSecond = (id) => {
  const m = /^[a-z]+_(\d{8}T\d{6}Z)-/.exec(String(id));
  return m ? m[1] : null;
};

const results = [];
const record = (kind, id, claim, ok, detail) => results.push({ kind, id, claim, ok, detail });

const check = (id, claim, fn) => {
  let ok = false;
  let detail = '';
  try {
    const r = fn();
    ok = r === true || (r && r.ok === true);
    if (r && typeof r === 'object' && r.detail) detail = r.detail;
    else if (typeof r === 'string') detail = r;
  } catch (e) {
    detail = 'threw: ' + e.message;
  }
  record('HARD', id, claim, ok, detail);
};

const live = (id, claim, fn) => {
  let ok = false;
  let detail = '';
  try {
    const r = fn();
    ok = r === true || (r && r.ok === true);
    if (r && typeof r === 'object' && r.detail) detail = r.detail;
    else if (typeof r === 'string') detail = r;
  } catch (e) {
    detail = 'threw: ' + e.message;
  }
  record('LIVE', id, claim, ok, detail);
};

const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const show = (v) => JSON.stringify(v);

// ---------------------------------------------------------------- git identity

const COMMIT = receipt.artifacts.commit;
const SHORT = receipt.commit;
const BASE = receipt.artifacts.base_commit;

check('G1', 'the named commit exists, and the short sha is its prefix', () => {
  const type = gitText('cat-file', '-t', COMMIT).trim();
  if (type !== 'commit') return { ok: false, detail: 'git cat-file -t ' + COMMIT + ' = ' + type };
  if (!COMMIT.startsWith(SHORT)) return { ok: false, detail: SHORT + ' is not a prefix of ' + COMMIT };
  return { ok: true, detail: COMMIT.slice(0, 12) + ' (' + gitText('show', '-s', '--format=%s', COMMIT).trim() + ')' };
});

check('G2', 'the base commit is an ancestor of the step commit', () => {
  try {
    git('merge-base', '--is-ancestor', BASE, COMMIT);
  } catch (e) {
    return { ok: false, detail: BASE + ' is not an ancestor of ' + COMMIT };
  }
  return { ok: true, detail: BASE + ' -> ' + SHORT };
});

check('G3', 'artifacts.step5_paths is exactly the file list of the step commit', () => {
  const actual = gitText('diff-tree', '--no-commit-id', '--name-only', '-r', COMMIT)
    .split('\n').filter((l) => l.trim().length > 0).sort();
  const claimed = [...receipt.artifacts.step5_paths].sort();
  if (!eq(actual, claimed)) {
    return { ok: false, detail: 'commit touched ' + show(actual) + ', receipt claims ' + show(claimed) };
  }
  const leaked = actual.filter((p) => /^(registry|traces)\//.test(p));
  if (leaked.length) return { ok: false, detail: 'the step commit touches registry/ or traces/: ' + show(leaked) };
  return { ok: true, detail: actual.length + ' paths, none under registry/ or traces/' };
});

check('G4', 'deltas.step5_only_diffstat is the commit\u2019s own numstat over those paths', () => {
  const numstat = gitText('diff', '--numstat', BASE, COMMIT, '--', ...receipt.artifacts.step5_paths)
    .split('\n').filter((l) => l.trim().length > 0);
  let ins = 0;
  let del = 0;
  for (const line of numstat) {
    const [a, d] = line.split('\t');
    ins += Number(a);
    del += Number(d);
  }
  const recomputed = numstat.length + ' files changed, ' + ins + ' insertions(+), ' + del + ' deletions(-)';
  if (recomputed !== receipt.deltas.step5_only_diffstat) {
    return { ok: false, detail: 'recomputed "' + recomputed + '", receipt claims "' + receipt.deltas.step5_only_diffstat + '"' };
  }
  return { ok: true, detail: recomputed };
});

check('G5', 'pushed and merged are false because this repo has no remote at all', () => {
  const remotes = gitText('remote', '-v').trim();
  if (remotes.length !== 0) return { ok: false, detail: 'repo now has a remote: ' + remotes.split('\n')[0] };
  if (receipt.pushed !== false || receipt.merged !== false) {
    return { ok: false, detail: 'receipt claims pushed=' + receipt.pushed + ' merged=' + receipt.merged };
  }
  return { ok: true, detail: 'no remote configured; pushed=false merged=false' };
});

// ------------------------------------------------------------------ blob pins

// The source files are pinned to what the COMMIT contains, not to the working
// tree — a receipt that pins working-tree bytes would go quietly wrong the moment
// anyone edits a file after committing.
check('B1', 'every pinned source file matches the bytes inside the step commit', () => {
  const pinned = [...receipt.deltas.new_files, ...receipt.deltas.modified_files]
    .filter((e) => !/^evidence\//.test(e.path));
  const bad = [];
  for (const e of pinned) {
    const blob = gitBlob(COMMIT, e.path);
    const sha = sha256(blob);
    if (sha !== e.sha256) bad.push(e.path + ': sha ' + sha + ' != pinned ' + e.sha256);
    if (e.lines !== undefined && countLines(blob) !== e.lines) {
      bad.push(e.path + ': ' + countLines(blob) + ' lines != pinned ' + e.lines);
    }
  }
  const covered = pinned.map((e) => e.path).sort();
  if (!eq(covered, [...receipt.artifacts.step5_paths].sort())) {
    bad.push('pins cover ' + show(covered) + ' but step5_paths is ' + show(receipt.artifacts.step5_paths));
  }
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: pinned.length + ' files, sha + line count each, all from ' + SHORT };
});

// The evidence files, unlike the source files, are pinned to DISK — at the time
// the receipt was written they were not committed yet, and the commit that adds
// them is the one that makes the two agree. Checked against disk so the check
// works both before and after that commit.
check('B2', 'every pinned evidence file matches the bytes on disk', () => {
  const bad = [];
  for (const [name, sha] of Object.entries(receipt.artifacts.evidence_files)) {
    if (sha === 'this file') continue;
    const p = path.join(__dirname, name);
    if (!fs.existsSync(p)) { bad.push(name + ': missing'); continue; }
    const actual = sha256File(p);
    if (actual !== sha) bad.push(name + ': sha ' + actual + ' != pinned ' + sha);
  }
  for (const e of receipt.deltas.new_files.filter((x) => /^evidence\//.test(x.path))) {
    const p = path.join(HOME, e.path);
    if (!fs.existsSync(p)) { bad.push(e.path + ': missing'); continue; }
    const buf = fs.readFileSync(p);
    if (sha256(buf) !== e.sha256) bad.push(e.path + ': sha mismatch');
    if (e.bytes !== undefined && buf.length !== e.bytes) bad.push(e.path + ': ' + buf.length + ' bytes != pinned ' + e.bytes);
  }
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: Object.keys(receipt.artifacts.evidence_files).length + ' files incl. this receipt\u2019s own pin list' };
});

check('B3', 'the step-start registry/traces values are re-derivable from the step commit', () => {
  const bad = [];
  const rStart = gitBlobSha(COMMIT, 'registry/capability-registry.json');
  const tStart = gitBlobSha(COMMIT, 'traces/traces.jsonl');
  const tLines = countNonEmpty(gitBlob(COMMIT, 'traces/traces.jsonl'));
  const rBase = gitBlobSha(BASE, 'registry/capability-registry.json');
  if (receipt.registry.sha256_at_step5_start_re_derived_from_git !== rStart) {
    bad.push('registry at step start: git says ' + rStart + ', receipt says ' + receipt.registry.sha256_at_step5_start_re_derived_from_git);
  }
  if (receipt.registry.sha256_at_step5_start !== rStart) bad.push('registry sha256_at_step5_start disagrees with git');
  if (receipt.traces.sha256_at_step5_start_re_derived_from_git !== tStart) {
    bad.push('traces at step start: git says ' + tStart + ', receipt says ' + receipt.traces.sha256_at_step5_start_re_derived_from_git);
  }
  if (receipt.traces.sha256_at_step5_start !== tStart) bad.push('traces sha256_at_step5_start disagrees with git');
  if (receipt.traces.lines_at_step5_start !== tLines) bad.push('traces lines at step start: git says ' + tLines + ', receipt says ' + receipt.traces.lines_at_step5_start);
  if (receipt.registry.sha256_at_the_step4_commit !== rBase) {
    bad.push('registry at the step-4 commit: git says ' + rBase + ', receipt says ' + receipt.registry.sha256_at_the_step4_commit);
  }
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: 'registry ' + rStart.slice(0, 12) + ' / traces ' + tStart.slice(0, 12) + ' @ ' + SHORT + '; step-4 registry ' + rBase.slice(0, 12) };
});

live('B4', 'the step-end registry/traces values are the ones on disk now', () => {
  const rNow = sha256File(path.join(HOME, 'registry/capability-registry.json'));
  const tNow = sha256File(path.join(HOME, 'traces/traces.jsonl'));
  const tLinesNow = countNonEmpty(fs.readFileSync(path.join(HOME, 'traces/traces.jsonl')));
  const moved = [];
  if (rNow !== receipt.registry.sha256_at_step5_end) moved.push('registry ' + receipt.registry.sha256_at_step5_end.slice(0, 12) + ' -> ' + rNow.slice(0, 12));
  if (tNow !== receipt.traces.sha256_at_step5_end) moved.push('traces ' + receipt.traces.sha256_at_step5_end.slice(0, 12) + ' -> ' + tNow.slice(0, 12));
  if (tLinesNow !== receipt.traces.lines) moved.push('trace lines ' + receipt.traces.lines + ' -> ' + tLinesNow);
  if (moved.length) {
    const since = gitText('log', '--format=%h %s', COMMIT + '..HEAD', '--', 'registry/', 'traces/')
      .split('\n').filter((l) => l.trim().length > 0);
    return { ok: false, detail: moved.join(', ') + ' | moved by: ' + (since.length ? since.join(' ; ') : '(uncommitted)') };
  }
  return { ok: true, detail: 'registry ' + rNow.slice(0, 12) + ', traces ' + tNow.slice(0, 12) + ', ' + tLinesNow + ' lines' };
});

check('B5', 'the spec the receipt quotes is the file on disk', () => {
  const p = '/Users/adam26/.zcode/workspace/default/partsnap-rcos/GPT-REPLY-7-20260917.md';
  if (!fs.existsSync(p)) return { ok: false, detail: 'missing: ' + p };
  const actual = sha256File(p);
  if (actual !== receipt.artifacts.spec_source.sha256) {
    return { ok: false, detail: 'disk ' + actual + ' != pinned ' + receipt.artifacts.spec_source.sha256 };
  }
  return { ok: true, detail: actual.slice(0, 12) + ' (outside the repo, as noted)' };
});

// ------------------------------------------------------- dogfood artifact linkage

for (const inv of receipt.dogfood_invocations) {
  const id = inv.invocation_id;
  check('C-' + id, id + ': the manifest on disk carries the cited selection, decision and status', () => {
    const mp = path.join(HOME, 'invocations', id, 'manifest.json');
    if (!fs.existsSync(mp)) return { ok: false, detail: 'no manifest at invocations/' + id + '/manifest.json' };
    const m = JSON.parse(fs.readFileSync(mp, 'utf8'));
    const bad = [];
    if (m.invocation_id !== id) bad.push('invocation_id mismatch');
    if (m.capability_id !== inv.capability_id) bad.push('capability_id ' + m.capability_id + ' != ' + inv.capability_id);
    if (m.mode !== inv.mode) bad.push('mode ' + m.mode + ' != ' + inv.mode);
    if (m.status !== inv.status) bad.push('status ' + m.status + ' != ' + inv.status);
    if (m.selection_id !== inv.selection_id) bad.push('selection_id ' + m.selection_id + ' != ' + inv.selection_id);
    if (!m.selection || m.selection.selected_capability_id !== inv.selection_winner) {
      bad.push('manifest selection winner is not ' + inv.selection_winner);
    }
    if (m.eligibility_decision_id !== inv.execute_decision_id) {
      bad.push('eligibility_decision_id ' + m.eligibility_decision_id + ' != ' + inv.execute_decision_id);
    }
    if (!m.eligibility || m.eligibility.scope !== 'execute') bad.push('manifest eligibility scope is not execute');
    if (m.eligibility && m.eligibility.purpose !== inv.execute_decision_purpose) {
      bad.push('manifest eligibility purpose ' + m.eligibility.purpose + ' != ' + inv.execute_decision_purpose);
    }
    if (bad.length) return { ok: false, detail: bad.join(' | ') };
    return { ok: true, detail: m.status + ' via ' + m.selection_id + ' + ' + m.eligibility_decision_id };
  });

  check('C-' + id + '-sel', id + ': the selection artifact on disk really chose that winner from that ballot', () => {
    const sp = path.join(HOME, 'selections', inv.selection_id, 'selection.json');
    if (!fs.existsSync(sp)) return { ok: false, detail: 'no selection.json for ' + inv.selection_id };
    const buf = fs.readFileSync(sp);
    const d = JSON.parse(buf.toString('utf8'));
    const bad = [];
    if (d.selection_id !== inv.selection_id) bad.push('selection_id mismatch');
    if (d.status !== 'selected') bad.push('status is ' + d.status + ', not selected');
    if (d.selected_capability_id !== inv.selection_winner) bad.push('selected ' + d.selected_capability_id + ' != ' + inv.selection_winner);
    const candidates = (d.candidates || []).map((c) => c.capability_id).sort();
    const competing = inv.competing_decisions.map((s) => s.replace(/\s*\(compete\)$/, '')).sort();
    const competingCaps = competing.map((cid) => {
      const dp = path.join(HOME, 'eligibility', cid, 'decision.json');
      return fs.existsSync(dp) ? JSON.parse(fs.readFileSync(dp, 'utf8')).capability_id : 'MISSING:' + cid;
    }).sort();
    if (!eq(candidates, competingCaps)) bad.push('ballot ' + show(candidates) + ' != cited ' + show(competingCaps));
    // the manifest's selection_sha256 is the sha of these bytes (lib/invocation.js:475)
    const mp = path.join(HOME, 'invocations', id, 'manifest.json');
    if (fs.existsSync(mp)) {
      const m = JSON.parse(fs.readFileSync(mp, 'utf8'));
      if (m.selection_sha256 !== sha256(buf)) bad.push('manifest selection_sha256 does not hash these bytes');
    }
    if (bad.length) return { ok: false, detail: bad.join(' | ') };
    return { ok: true, detail: d.status + ' ' + d.selected_capability_id + ' from a ' + candidates.length + '-capability ballot, bytes pinned by the manifest' };
  });

  check('C-' + id + '-elig', id + ': the execute decision is a real, fresh, scope=execute decision for the winner', () => {
    const dp = path.join(HOME, 'eligibility', inv.execute_decision_id, 'decision.json');
    if (!fs.existsSync(dp)) return { ok: false, detail: 'no decision.json for ' + inv.execute_decision_id };
    const d = JSON.parse(fs.readFileSync(dp, 'utf8'));
    const bad = [];
    if (d.scope !== 'execute') bad.push('scope is ' + d.scope + ', not execute');
    if (d.capability_id !== inv.capability_id) bad.push('decision is for ' + d.capability_id + ', not ' + inv.capability_id);
    const competingIds = inv.competing_decisions.map((s) => s.replace(/\s*\(compete\)$/, ''));
    if (competingIds.includes(inv.execute_decision_id)) bad.push('the execute decision is one of the ballot decisions');
    const execSecond = idSecond(inv.execute_decision_id);
    const selSecond = idSecond(inv.selection_id);
    if (!execSecond || !selSecond) bad.push('could not parse a creation second from the ids');
    else if (execSecond <= selSecond) bad.push('execute decision ' + execSecond + ' is not after the selection ' + selSecond);
    // every cited ballot decision must be a real scope=compete decision for a
    // capability that is actually on the ballot — read from the selection, so the
    // ballot is the one the core recorded, not the one the receipt describes
    const sp = path.join(HOME, 'selections', inv.selection_id, 'selection.json');
    const ballot = fs.existsSync(sp)
      ? new Set((JSON.parse(fs.readFileSync(sp, 'utf8')).candidates || []).map((c) => c.capability_id))
      : null;
    if (!ballot) bad.push('cannot read the ballot to check the competing decisions against it');
    for (const cid of competingIds) {
      const cp = path.join(HOME, 'eligibility', cid, 'decision.json');
      if (!fs.existsSync(cp)) { bad.push('cited ballot decision ' + cid + ' has no artifact'); continue; }
      const cd = JSON.parse(fs.readFileSync(cp, 'utf8'));
      if (cd.scope !== 'compete') bad.push(cid + ' is scope ' + cd.scope + ', not compete');
      if (ballot && !ballot.has(cd.capability_id)) bad.push(cid + ' is for ' + cd.capability_id + ', which is not on the ballot');
    }
    if (bad.length) return { ok: false, detail: bad.join(' | ') };
    return { ok: true, detail: 'scope=execute for ' + d.capability_id + ', ' + selSecond + ' -> ' + execSecond + ', not on the ballot; all ' + competingIds.length + ' cited ballot decisions are scope=compete for ballot capabilities' };
  });
}

for (const run of receipt.dogfood_runs) {
  const invId = (run.steps || []).map((s) => /inv_\d{8}T\d{6}Z-[0-9a-f]+/.exec(s)).filter(Boolean)[0];
  if (!invId) continue;
  const inv = receipt.dogfood_invocations.find((x) => x.invocation_id === invId);
  if (!inv || !inv.eval_run) continue;
  check('C-' + invId + '-eval', invId + ': the cited eval receipt exists and says ' + inv.eval_verdict, () => {
    const p = path.join(HOME, inv.eval_run);
    if (!fs.existsSync(p)) return { ok: false, detail: 'missing: ' + inv.eval_run };
    const r = JSON.parse(fs.readFileSync(p, 'utf8'));
    const bad = [];
    if (r.verdict !== inv.eval_verdict) bad.push('verdict ' + r.verdict + ' != ' + inv.eval_verdict);
    const gates = r.gates || [];
    const failed = gates.filter((g) => g.status !== 'pass').map((g) => g.id);
    if (inv.eval_gate_failed && !failed.includes(inv.eval_gate_failed)) {
      bad.push('the cited failing gate "' + inv.eval_gate_failed + '" is not among the failed gates ' + show(failed));
    }
    const okCount = gates.length - failed.length;
    if (inv.eval_gates_ok && !inv.eval_gates_ok.startsWith(String(okCount) + ' of ' + gates.length)) {
      bad.push('receipt says "' + inv.eval_gates_ok + '" but the run has ' + okCount + ' of ' + gates.length + ' passing');
    }
    if (bad.length) return { ok: false, detail: bad.join(' | ') };
    return { ok: true, detail: 'verdict ' + r.verdict + ', failed: ' + show(failed) + ', ' + okCount + ' of ' + gates.length + ' gates ok' };
  });
}

// ----------------------------------------------------------- sweep-derived claims

const sweep = JSON.parse(fs.readFileSync(path.join(__dirname, 'sweep.out.json'), 'utf8'));
const out = JSON.parse(fs.readFileSync(path.join(__dirname, 'shipbar.out.json'), 'utf8'));

check('S1', 'the_funnel rungs are the sweep\u2019s own funnel numbers', () => {
  const keys = ['rung_1_in_the_registry', 'rung_2_executable', 'rung_3_may_compete_at_purpose_eval',
    'rung_4_on_the_ballot', 'rung_5_explicitly_selectable', 'rung_6_execute_eligible_at_purpose_eval',
    'rung_6_execute_eligible_at_purpose_normal', 'where_the_funnel_narrows'];
  const bad = [];
  for (const k of keys) {
    if (!eq(receipt.the_funnel[k], sweep.funnel[k])) {
      bad.push(k + ': receipt ' + show(receipt.the_funnel[k]) + ' != sweep ' + show(sweep.funnel[k]));
    }
  }
  if (receipt.the_funnel.rung_1_in_the_registry !== sweep.registry_capabilities) bad.push('rung 1 != sweep.registry_capabilities');
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: keys.length + ' keys agree; rung 1 = ' + sweep.registry_capabilities };
});

check('S2', 'the_funnel.statuses_reachable_in_this_sweep is the sweep\u2019s own list', () => {
  if (!eq(receipt.the_funnel.statuses_reachable_in_this_sweep, sweep.statuses_reachable_in_this_sweep)) {
    return { ok: false, detail: 'receipt ' + show(receipt.the_funnel.statuses_reachable_in_this_sweep) + ' != sweep ' + show(sweep.statuses_reachable_in_this_sweep) };
  }
  return { ok: true, detail: show(sweep.statuses_reachable_in_this_sweep) };
});

check('S3', 'reuse_counts before/after are the harness\u2019s snapshots and nothing moved', () => {
  const bad = [];
  if (!eq(receipt.reuse_counts.before, out.before.reuse_counts)) bad.push('before: receipt differs from shipbar.out.json before.reuse_counts');
  if (!eq(receipt.reuse_counts.after, out.after.reuse_counts)) bad.push('after: receipt differs from shipbar.out.json after.reuse_counts');
  if (!eq(receipt.reuse_counts.before, receipt.reuse_counts.after)) bad.push('the receipt\u2019s own before != after');
  const moved = Object.keys(receipt.reuse_counts.before).filter((k) => receipt.reuse_counts.before[k] !== receipt.reuse_counts.after[k]);
  if (moved.length) bad.push('moved: ' + show(moved));
  if (!eq(receipt.reuse_counts.moved, [])) bad.push('moved is not []');
  if (!eq(sweep.live_home_untouched.reuse_counts_moved, [])) bad.push('the sweep reports reuse counts moved: ' + show(sweep.live_home_untouched.reuse_counts_moved));
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: Object.keys(receipt.reuse_counts.before).length + ' capabilities, identical before and after in both the harness and the sweep' };
});

check('S4', 'the fresh-execute rows in the receipt are the sweep\u2019s execute_sweep rows', () => {
  const rows = (sweep.execute_sweep && sweep.execute_sweep.rows) || [];
  const claimed = receipt.sweep.fresh_execute_decisions_minted_in_the_probe || [];
  if (rows.length === 0) return { ok: false, detail: 'the sweep recorded no execute rows' };
  const norm = (r) => ({
    decision_id: r.execute_decision_id || r.decision_id,
    capability: r.id || r.capability || r.capability_id,
    purpose: r.purpose,
    may_execute: r.may_execute,
    is_one_of_the_candidate_decisions: r.fresh === undefined ? r.is_one_of_the_candidate_decisions : !r.fresh,
  });
  const byId = (a, b) => String(a.decision_id).localeCompare(String(b.decision_id));
  const a = rows.map(norm).sort(byId);
  const b = claimed.map(norm).sort(byId);
  if (!eq(a, b)) {
    return { ok: false, detail: 'receipt lists ' + b.length + ' rows, the sweep has ' + a.length + ', and they differ: receipt ' + show(b) + ' vs sweep ' + show(a) };
  }
  const notFresh = a.filter((r) => r.is_one_of_the_candidate_decisions);
  if (notFresh.length) return { ok: false, detail: 'a row is one of the candidate decisions: ' + show(notFresh) };
  const normal = a.filter((r) => r.purpose === 'normal');
  if (normal.some((r) => r.may_execute)) return { ok: false, detail: 'a purpose=normal row may_execute' };
  if (sweep.execute_sweep.every_execute_decision_is_a_new_artifact !== true) {
    return { ok: false, detail: 'the sweep itself does not claim every execute decision is a new artifact' };
  }
  return { ok: true, detail: a.length + ' rows, none on the ballot; ' + normal.length + ' at purpose=normal, all may_execute=false' };
});

check('S5', 'the three reachable refusals in the receipt are the sweep\u2019s refusals', () => {
  if (!eq(receipt.sweep.the_three_reachable_selector_refusals, sweep.selector_refusals)) {
    const claimed = Object.keys(receipt.sweep.the_three_reachable_selector_refusals || {}).sort();
    const actual = Object.keys(sweep.selector_refusals || {}).sort();
    return { ok: false, detail: 'receipt keys ' + show(claimed) + ' vs sweep keys ' + show(actual) };
  }
  return { ok: true, detail: show(Object.keys(sweep.selector_refusals)) };
});

check('S6', 'the sweep\u2019s own untouched-home finding is in the receipt verbatim', () => {
  if (!eq(receipt.sweep.live_home_untouched, sweep.live_home_untouched)) {
    return { ok: false, detail: 'the receipt\u2019s copy of live_home_untouched differs from the sweep\u2019s' };
  }
  const lhu = sweep.live_home_untouched;
  const ok = lhu.registry_sha256.identical === true && lhu.traces_sha256.identical === true;
  if (!ok) return { ok: false, detail: 'the sweep itself reports the live home was touched' };
  return { ok: true, detail: 'registry and traces byte-identical across the sweep; 0 selections and 0 invocations in the live home from it' };
});

check('S7', 'test_output is item 17\u2019s suite, not a remembered one', () => {
  const i17 = out.items['17_step1_to_4_still_green'];
  const bad = [];
  if (receipt.test_output.tests !== i17.suite.tests) bad.push('tests');
  if (receipt.test_output.pass !== i17.suite.pass) bad.push('pass');
  if (receipt.test_output.fail !== i17.suite.fail) bad.push('fail');
  if (receipt.test_output.skipped !== i17.suite.skipped) bad.push('skipped');
  if (receipt.test_output.exit !== i17.suite.exit) bad.push('exit');
  if (!eq(receipt.test_output.files, i17.test_files)) bad.push('files');
  if (!eq(receipt.test_output.counters_as_printed, i17.suite_counters_as_printed)) bad.push('counters_as_printed');
  if (bad.length) return { ok: false, detail: 'disagrees with item 17 on: ' + show(bad) };
  return { ok: true, detail: receipt.test_output.tests + ' tests / ' + receipt.test_output.pass + ' pass / ' + receipt.test_output.fail + ' fail across ' + receipt.test_output.files.length + ' files' };
});

// -------------------------------------------------------------- harness and bus

check('H1', 'the harness of record passed all 18 items and said so', () => {
  if (out.all_pass !== true) return { ok: false, detail: 'shipbar.out.json all_pass is not true' };
  const items = Object.entries(out.items);
  if (items.length !== 18) return { ok: false, detail: items.length + ' items, expected 18' };
  const notPass = items.filter(([, v]) => v.verdict !== 'PASS');
  if (notPass.length) return { ok: false, detail: 'not PASS: ' + show(notPass.map(([k]) => k)) };
  return { ok: true, detail: '18/18 PASS at ' + out.checked_at };
});

check('H2', 'every receipt ship_bar line is the harness\u2019s verdict for that item number', () => {
  if (receipt.ship_bar.length !== 18) return { ok: false, detail: receipt.ship_bar.length + ' ship_bar entries, expected 18' };
  const bad = [];
  for (const entry of receipt.ship_bar) {
    const key = Object.keys(out.items).find((k) => k.startsWith(entry.id + '_'));
    if (!key) { bad.push('item ' + entry.id + ': no harness item'); continue; }
    if (out.items[key].verdict !== entry.status) bad.push('item ' + entry.id + ': receipt ' + entry.status + ', harness ' + out.items[key].verdict);
  }
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: '18/18 statuses agree with the harness' };
});

check('H3', 'every refusal shape the receipt names appears in the harness record', () => {
  const haystack = JSON.stringify(out);
  const bad = [];
  for (const key of Object.keys(receipt.refusal_shapes.measured)) {
    if (!haystack.includes(key)) bad.push('"' + key + '" is not mentioned anywhere in shipbar.out.json');
  }
  if (receipt.must_fail_closed.all_six_pinned !== true) bad.push('must_fail_closed.all_six_pinned is not true');
  const statuses = new Set(Object.values(receipt.refusal_shapes.measured));
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: Object.keys(receipt.refusal_shapes.measured).length + ' shapes, observed statuses ' + show([...statuses]) };
});

check('T1', 'the five statuses in the receipt are the five statuses the module exports', () => {
  const sel = require(path.join(HOME, 'lib/selection.js'));
  const bad = [];
  if (!eq(receipt.statuses.canonical_order, sel.SELECTION_STATUSES)) bad.push('canonical_order != SELECTION_STATUSES');
  if (!eq(receipt.statuses.selector_may_return, sel.SELECTOR_RESULT_STATUSES)) bad.push('selector_may_return != SELECTOR_RESULT_STATUSES');
  const coreOnly = sel.SELECTION_STATUSES.filter((s) => !sel.SELECTOR_RESULT_STATUSES.includes(s));
  if (!eq(receipt.statuses.core_only, coreOnly)) bad.push('core_only != the difference');
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: show(sel.SELECTION_STATUSES) + ', selector may return ' + show(sel.SELECTOR_RESULT_STATUSES) };
});

// ------------------------------------------------- the live home's inventory

// This step ran live, so it left artifacts in the real home: eligibility
// decisions, selections, invocations and one eval run. The receipt now claims to
// account for every one of them by tier. These checks re-derive the inventory
// from disk and from git rather than reading it back, because the failure this
// guards against is not "the receipt is wrong about a number" — it is "the
// receipt quietly stops mentioning the artifacts nobody cited".
//
// The M2/M3 checks are written so they cannot pass on an empty inventory: a
// vacuous "every id landed in a tier" over zero ids is exactly the kind of check
// that reads as evidence while proving nothing, so the counts are asserted
// non-zero first.

const MINTED = receipt.live_artifacts_this_step_minted;
const trackedPaths = new Set(gitText('ls-files', '--', 'eligibility', 'selections', 'invocations', 'runs')
  .split('\n').filter((l) => l.trim().length > 0));
const isTracked = (p) => { for (const t of trackedPaths) if (t.startsWith(p + '/')) return true; return false; };
const dirsOnDisk = (prefix) => fs.readdirSync(path.join(HOME, prefix), { withFileTypes: true })
  .filter((e) => e.isDirectory()).map((e) => prefix + '/' + e.name);
const inNoCommit = (prefix) => dirsOnDisk(prefix).filter((p) => !isTracked(p)).sort();
const readJsonAt = (p) => JSON.parse(fs.readFileSync(path.join(HOME, p), 'utf8'));

const diskInventory = () => {
  const elig = inNoCommit('eligibility').map((p) => readJsonAt(p + '/decision.json').decision_id);
  const sel = inNoCommit('selections').map((p) => readJsonAt(p + '/selection.json').selection_id);
  const inv = inNoCommit('invocations').map((p) => readJsonAt(p + '/manifest.json').invocation_id);
  const runs = inNoCommit('runs').map((p) => readJsonAt(p + '/receipt.json').run_id);
  return { elig, sel, inv, runs };
};

check('M1', 'the receipt\u2019s live-artifact counts are the counts on disk, and none of them is zero', () => {
  const d = diskInventory();
  const claims = MINTED.counts;
  const bad = [];
  if (claims.eligibility_decisions !== d.elig.length) bad.push('eligibility_decisions: receipt ' + claims.eligibility_decisions + ', disk ' + d.elig.length);
  if (claims.selections !== d.sel.length) bad.push('selections: receipt ' + claims.selections + ', disk ' + d.sel.length);
  if (claims.invocations !== d.inv.length) bad.push('invocations: receipt ' + claims.invocations + ', disk ' + d.inv.length);
  if (claims.runs !== d.runs.length) bad.push('runs: receipt ' + claims.runs + ', disk ' + d.runs.length);
  const sum = claims.eligibility_decisions + claims.selections + claims.invocations + claims.runs;
  if (claims.total !== sum) bad.push('total ' + claims.total + ' != the sum of the four kinds ' + sum);
  if (d.elig.length === 0) bad.push('the eligibility inventory is empty, so every claim below it is vacuous');
  if (d.sel.length === 0) bad.push('the selection inventory is empty, so every claim below it is vacuous');
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: d.elig.length + ' eligibility + ' + d.sel.length + ' selections + ' + d.inv.length + ' invocations + ' + d.runs.length + ' runs = ' + claims.total };
});

check('M2', 'the three tiers partition the inventory exactly: no id in two tiers, none in none', () => {
  const d = diskInventory();
  const ids = d.elig.concat(d.sel, d.inv, d.runs);
  if (ids.length === 0) return { ok: false, detail: 'no ids on disk to classify — this check would pass vacuously' };
  const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
  if (dupes.length) return { ok: false, detail: 'the same id appears under two kinds: ' + show(dupes) };
  const t = MINTED.tiers;
  const sum = t.named_in_the_final_harness_run + t.cited_elsewhere_in_this_receipt + t.named_nowhere_in_this_receipt;
  if (sum !== ids.length) return { ok: false, detail: 'tier counts sum to ' + sum + ' but the inventory holds ' + ids.length };
  if (t.the_three_tiers_partition_the_inventory !== true) return { ok: false, detail: 'the receipt does not itself claim the partition' };
  // And the per-kind rows the receipt lists are the ids on disk, not a sample.
  const listedSel = MINTED.selections.map((r) => r.selection_id).sort();
  if (!eq(listedSel, d.sel.slice().sort())) return { ok: false, detail: 'the receipt lists ' + listedSel.length + ' selections, disk holds ' + d.sel.length };
  const listedInv = MINTED.invocations.map((r) => r.invocation_id).sort();
  if (!eq(listedInv, d.inv.slice().sort())) return { ok: false, detail: 'the receipt lists ' + listedInv.length + ' invocations, disk holds ' + d.inv.length };
  const listedRuns = MINTED.runs.map((r) => r.run_id).sort();
  if (!eq(listedRuns, d.runs.slice().sort())) return { ok: false, detail: 'the receipt lists ' + listedRuns.length + ' runs, disk holds ' + d.runs.length };
  return { ok: true, detail: ids.length + ' ids = ' + t.named_in_the_final_harness_run + ' harness + ' + t.cited_elsewhere_in_this_receipt + ' cited + ' + t.named_nowhere_in_this_receipt + ' uncited' };
});

check('M3', 'the harness-run tier is exactly the ids shipbar.out.json reports minting', () => {
  const t1 = new Set();
  for (const r of MINTED.selections) if (r.tier === 'named_in_the_final_harness_run') t1.add(r.selection_id);
  for (const r of MINTED.invocations) if (r.tier === 'named_in_the_final_harness_run') t1.add(r.invocation_id);
  for (const r of MINTED.runs) if (r.tier === 'named_in_the_final_harness_run') t1.add(r.run_id);
  const harnessElig = [];
  for (const b of MINTED.eligibility_decisions.batches) {
    const ids = b.named_in_the_final_harness_run_ids || [];
    if (ids.length !== b.named_in_the_final_harness_run) {
      return { ok: false, detail: 'a batch claims ' + b.named_in_the_final_harness_run + ' harness-tier decisions but names ' + ids.length };
    }
    if (ids.length > 0 && b.count !== ids.length) {
      return { ok: false, detail: 'a batch mixes tiers: ' + b.at_second + ' ' + b.scope + ' has ' + b.count + ' rows, ' + ids.length + ' in the harness tier' };
    }
    for (const id of ids) { t1.add(id); harnessElig.push(id); }
  }
  const fromHarness = new Set([out.live_dogfood.selected, out.live_dogfood.abstained, out.live_dogfood.no_candidates]
    .concat(out.live_dogfood.compete_decisions_minted || []));
  if (fromHarness.size === 0) return { ok: false, detail: 'shipbar.out.json reports minting nothing, so this check is vacuous' };
  const missing = [...fromHarness].filter((id) => !t1.has(id));
  if (missing.length) return { ok: false, detail: 'shipbar.out.json names ' + show(missing) + ' but the receipt does not put them in the harness tier' };
  if (t1.size !== fromHarness.size) return { ok: false, detail: 'the harness tier holds ' + t1.size + ' ids, shipbar.out.json names ' + fromHarness.size };
  // The named eligibility ids must be real artifacts, not plausible-looking strings.
  const d = diskInventory();
  const ghosts = harnessElig.filter((id) => d.elig.indexOf(id) === -1);
  if (ghosts.length) return { ok: false, detail: 'harness-tier eligibility ids that are not on disk: ' + show(ghosts) };
  return { ok: true, detail: t1.size + ' ids, the same set the harness reports (' + harnessElig.length + ' eligibility + ' + (t1.size - harnessElig.length) + ' other)' };
});

check('M4', 'every uncited id really is uncited — it appears nowhere in this receipt but the block that discloses it', () => {
  const withoutBlock = JSON.stringify(Object.assign({}, receipt, { live_artifacts_this_step_minted: undefined }));
  const uncited = [];
  for (const r of MINTED.selections) if (r.tier === 'named_nowhere_in_this_receipt') uncited.push(r.selection_id);
  for (const r of MINTED.invocations) if (r.tier === 'named_nowhere_in_this_receipt') uncited.push(r.invocation_id);
  for (const r of MINTED.runs) if (r.tier === 'named_nowhere_in_this_receipt') uncited.push(r.run_id);
  if (uncited.length === 0) return { ok: false, detail: 'nothing is uncited, so this check would pass vacuously' };
  const leaked = uncited.filter((id) => withoutBlock.indexOf(id) !== -1);
  if (leaked.length) return { ok: false, detail: 'called uncited but named elsewhere in the receipt: ' + show(leaked) };
  // The eligibility side is listed in batches, so the same test runs over the
  // disk inventory directly: an eligibility decision is uncited exactly when it
  // is neither named in the receipt's own text nor in the harness's own report
  // of what it minted. Recomputed from disk, not from the batch's tally.
  const d = diskInventory();
  const harnessSet = new Set(out.live_dogfood.compete_decisions_minted || []);
  const recomputedUncited = d.elig.filter((id) => withoutBlock.indexOf(id) === -1 && !harnessSet.has(id));
  const claimedUncited = MINTED.tiers.named_nowhere_in_this_receipt - uncited.length;
  if (claimedUncited <= 0) return { ok: false, detail: 'the batches claim no uncited eligibility decisions, so this half of the check would pass vacuously' };
  if (claimedUncited !== recomputedUncited.length) {
    return { ok: false, detail: 'the batches claim ' + claimedUncited + ' uncited eligibility decisions, disk plus the receipt\'s own text recompute to ' + recomputedUncited.length };
  }
  return { ok: true, detail: uncited.length + ' uncited selections/invocations/runs named nowhere else, plus ' + claimedUncited + ' uncited eligibility decisions' };
});

check('M5', 'none of these artifacts is in any commit, and this step\u2019s commit added none of them', () => {
  const bad = [];
  if (MINTED.staged_by_this_step !== false) bad.push('staged_by_this_step is not false');
  if (MINTED.in_no_commit !== true) bad.push('in_no_commit is not true');
  const commitPaths = gitText('diff-tree', '--no-commit-id', '--name-only', '-r', COMMIT)
    .split('\n').filter((l) => l.trim().length > 0);
  const artifactPaths = commitPaths.filter((p) => /^(eligibility|selections|invocations|runs)\//.test(p));
  if (artifactPaths.length) bad.push('commit ' + SHORT + ' adds artifact paths: ' + show(artifactPaths));
  const d = diskInventory();
  const stillTracked = [].concat(d.elig, d.sel, d.inv, d.runs).filter((id) => {
    for (const t of trackedPaths) if (t.indexOf(id) !== -1) return true;
    return false;
  });
  if (stillTracked.length) bad.push('in a commit after all: ' + show(stillTracked));
  if (bad.length) return { ok: false, detail: bad.join(' | ') };
  return { ok: true, detail: 'commit ' + SHORT + ' touches ' + commitPaths.length + ' paths, all source or docs; ' + MINTED.counts.total + ' artifacts untracked' };
});

// ----------------------------------------------------------------------- report

const hard = results.filter((r) => r.kind === 'HARD');
const lives = results.filter((r) => r.kind === 'LIVE');
const failed = hard.filter((r) => !r.ok);
const movedLive = lives.filter((r) => !r.ok);

const width = Math.max(...results.map((r) => r.id.length));
for (const r of results) {
  const tag = r.kind === 'LIVE' ? (r.ok ? 'LIVE-OK ' : 'MOVED   ') : (r.ok ? 'PASS    ' : 'FAIL    ');
  console.log(tag + ' ' + r.id.padEnd(width) + '  ' + r.claim);
  if (r.detail) console.log('         ' + ' '.repeat(width) + '  ' + r.detail);
}

console.log('');
console.log('receipt: ' + RECEIPT_PATH);
console.log('claims checked: ' + results.length + ' (' + hard.length + ' hard, ' + lives.length + ' live)');
console.log('hard: ' + (hard.length - failed.length) + '/' + hard.length + ' PASS' + (failed.length ? ', ' + failed.length + ' FAIL' : ''));
console.log('live: ' + (lives.length - movedLive.length) + '/' + lives.length + ' unmoved' + (movedLive.length ? ', ' + movedLive.length + ' moved since the receipt was written (attributed above)' : ''));
console.log(failed.length === 0
  ? 'RESULT: the receipt agrees with git and with the bytes on disk.'
  : 'RESULT: ' + failed.length + ' claim(s) the receipt makes are not true of git or of the bytes on disk.');

process.exit(failed.length === 0 ? 0 : 1);
