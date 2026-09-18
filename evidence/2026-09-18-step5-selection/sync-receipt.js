#!/usr/bin/env node
// Recompute every derived field of RECEIPT.json from the two records of record
// (shipbar.out.json, sweep.out.json), from git, and from the bytes on disk.
//
// Why this exists: the receipt was first written by hand against an earlier run
// of both records. Re-running the harness produced fresh ids, fresh shas and a
// fresh (higher) trace line count, and one hand-transcribed field disagreed with
// the artifact it claimed to summarise. A receipt that is copied by hand is a
// receipt that can silently disagree with its own evidence, so nothing here is
// typed twice: every value below is read from a record or from disk.
//
// Idempotent. Prints every path it changed and every path it re-derived and found
// already correct, so a second run reporting zero changes is itself the check
// that the receipt and the records agree.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const DIR = __dirname;
const HOME = process.env.RCOS_HOME || '/Users/adam26/zcode-rcos';
const receiptPath = path.join(DIR, 'RECEIPT.json');

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const sha256 = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const bytes = (p) => fs.statSync(p).size;
const lines = (p) => fs.readFileSync(p, 'utf8').split('\n').length;

const receipt = readJson(receiptPath);
const out = readJson(path.join(DIR, 'shipbar.out.json'));
const sweep = readJson(path.join(DIR, 'sweep.out.json'));
const sel = require(path.join(HOME, 'lib/selection.js'));

// Captured before anything is set: the prose below quotes the step-start values
// as history, and `set` mutates in place, so reading them afterwards would read
// the freshly written value and quietly turn "then vs now" into "now vs now".
const REGISTRY_SHA_AT_STEP5_START = receipt.registry.sha256_at_step5_start;
const TRACES_SHA_AT_STEP5_START = receipt.traces.sha256_at_step5_start;

// The step-start values are not remembered, they are re-derived from this step's
// own commit: whatever the tree held at 6c34ee2 is what the step began with, and
// it is still in git after the study loop moves the live files on. Same trick
// shipbar-verify.js uses for REGISTRY_SHA_AT_STEP5_START. The recorded values are
// then asserted against the derived ones, so a receipt that quotes a step-start
// sha the commit does not contain fails here instead of being believed.
const STEP5_COMMIT = receipt.artifacts.commit;
const STEP5_BASE = receipt.artifacts.base_commit;
const gitBlob = (rev, p) => execFileSync('git', ['show', rev + ':' + p], { cwd: HOME, maxBuffer: 64 * 1024 * 1024 });
const gitBlobSha = (rev, p) => crypto.createHash('sha256').update(gitBlob(rev, p)).digest('hex');
const countTraceLines = (buf) => buf.toString('utf8').split('\n').filter((l) => l.trim().length > 0).length;

const START = {
  registry_sha256: gitBlobSha(STEP5_COMMIT, 'registry/capability-registry.json'),
  traces_sha256: gitBlobSha(STEP5_COMMIT, 'traces/traces.jsonl'),
  trace_lines: countTraceLines(gitBlob(STEP5_COMMIT, 'traces/traces.jsonl')),
  registry_sha256_at_the_base_commit: gitBlobSha(STEP5_BASE, 'registry/capability-registry.json')
};
if (START.registry_sha256 !== REGISTRY_SHA_AT_STEP5_START) {
  throw new Error('the receipt\'s recorded step-start registry sha is not what commit ' + STEP5_COMMIT + ' contains: '
    + REGISTRY_SHA_AT_STEP5_START + ' vs ' + START.registry_sha256);
}
if (START.traces_sha256 !== TRACES_SHA_AT_STEP5_START) {
  throw new Error('the receipt\'s recorded step-start traces sha is not what commit ' + STEP5_COMMIT + ' contains: '
    + TRACES_SHA_AT_STEP5_START + ' vs ' + START.traces_sha256);
}

const git = (args) => execFileSync('git', args, { cwd: HOME, encoding: 'utf8' });

const changed = [];
const unchanged = [];
const set = (jsonPath, value) => {
  const keys = jsonPath.split('.');
  const leaf = keys.pop();
  const parent = keys.reduce((o, k) => o[k], receipt);
  const had = Object.prototype.hasOwnProperty.call(parent, leaf);
  const was = had ? JSON.stringify(parent[leaf]) : undefined;
  const now = JSON.stringify(value);
  parent[leaf] = value;
  (had && was === now ? unchanged : changed).push(jsonPath + (had ? '' : '  (added)'));
};
// For fields that were renamed. Leaving the old one in place would put two
// different inventories side by side and let a reader quote the stale one.
const del = (jsonPath) => {
  const keys = jsonPath.split('.');
  const leaf = keys.pop();
  const parent = keys.reduce((o, k) => o[k], receipt);
  if (Object.prototype.hasOwnProperty.call(parent, leaf)) {
    delete parent[leaf];
    changed.push(jsonPath + '  (removed)');
  }
};

const i15 = out.items['15_selection_moves_no_reuse_and_no_trace'];
const i17 = out.items['17_step1_to_4_still_green'];
const i18 = out.items['18_registry_unchanged'];
if (!i15 || !i17 || !i18) throw new Error('shipbar.out.json is missing items 15/17/18');
if (i18.verdict !== 'PASS' || i15.verdict !== 'PASS' || i17.verdict !== 'PASS') {
  throw new Error('refusing to sync a receipt from a red harness: ' + [i15.verdict, i17.verdict, i18.verdict].join('/'));
}
if (out.all_pass !== true) throw new Error('refusing to sync: shipbar.out.json all_pass is not true');
if (sweep.live_home_untouched.registry_sha256.identical !== true
  || sweep.live_home_untouched.traces_sha256.identical !== true) {
  throw new Error('refusing to sync: the sweep reports the live home was touched');
}

// ---------------------------------------------------------------------------
// registry + traces: the value now, and who moved it since the step started
// ---------------------------------------------------------------------------
const windowCommits = git(['log', '--format=%h\t%ad\t%s', '--date=short', '5647877..HEAD', '--', 'registry/', 'traces/'])
  .split('\n').filter((l) => l.trim()).map((l) => {
    const [sha, date, ...rest] = l.split('\t');
    const subject = rest.join('\t');
    return { sha, date, subject, by_study_loop: /^(evals\(|evals:|registry\+traces:)/.test(subject) };
  });
const preWindowCommits = git(['log', '--format=%h\t%ad\t%s', '--date=short', '-5', '5647877', '--', 'registry/', 'traces/'])
  .split('\n').filter((l) => l.trim()).map((l) => {
    const [sha, date, ...rest] = l.split('\t');
    return { sha, date, subject: rest.join('\t') };
  });

set('registry.sha256_at_step5_end', i18.registry_sha256_after_this_harness);
set('registry.sha256_at_step5_start_re_derived_from_git', START.registry_sha256);
set('registry.moved_by_this_step', i18.this_steps_own_commit_touched_registry_or_traces.length !== 0);
set('registry.moved_after_the_step5_start', i18.registry_moved_after_the_step5_start);
set('registry.moved_after_the_step5_start_by', windowCommits.map((c) => c.sha));
set('registry.divergence_from_step4_attributed_to',
  'the autonomous study loop\'s machine-written eval commits. Inside this step\'s window: '
  + windowCommits.map((c) => c.sha + ' (' + c.date + ', ' + c.subject + ')').join('; ')
  + '. Before it: ' + preWindowCommits.map((c) => c.sha).join(', ') + '.');
set('step_start_values_are_re_derived_not_remembered',
  'the step-start shas and line count above are read out of this step\'s own commit (git show ' + STEP5_COMMIT
  + ':registry/capability-registry.json, and the same for traces/traces.jsonl) and asserted against the recorded values, because the live files have moved on since and a remembered value cannot be checked.');

set('traces.sha256_at_step5_end', i18.traces_sha256_after_this_harness);
set('traces.sha256_at_step5_start_re_derived_from_git', START.traces_sha256);
set('traces.lines_at_step5_start', START.trace_lines);
set('traces.lines', out.after.trace_lines);
set('traces.moved_by_this_step', false);
set('traces.moved_after_the_step5_start', i18.traces_sha256_after_this_harness !== TRACES_SHA_AT_STEP5_START);
set('traces.moved_after_the_step5_start_by', windowCommits.map((c) => c.sha));

// ---------------------------------------------------------------------------
// the selections that exist in the live home, enumerated and verified live
// ---------------------------------------------------------------------------
const all = sel.listSelections(HOME);
const unverifiable = [];
for (const s of all) {
  const v = sel.verifySelection(HOME, s.selection_id);
  if (!v.ok) unverifiable.push({ id: s.selection_id, problems: v.problems });
}
const groups = new Map();
for (const s of all) {
  const stamp = s.selection_id.replace(/^sel_/, '').split('-')[0];
  if (!groups.has(stamp)) groups.set(stamp, []);
  groups.get(stamp).push({ id: s.selection_id, status: s.status, selected: s.selected_capability_id });
}
const thisRun = i15.live_selections_created_during_this_check;
set('selection_inventory.live_selections_created_by_this_harness_run', [
  { id: thisRun.selected.id, status: thisRun.selected.status, winner: thisRun.selected.winner },
  { id: thisRun.abstained.id, status: thisRun.abstained.status, basis: thisRun.abstained.basis },
  { id: thisRun.no_candidates.id, status: thisRun.no_candidates.status }
]);
set('selection_inventory.every_selection_in_the_live_home', {
  count: all.length,
  all_verify: unverifiable.length === 0,
  unverifiable,
  by_creation_second: [...groups.entries()].map(([at, sels]) => ({ at_utc: at, count: sels.length, selections: sels })),
  why_there_are_more_than_three: 'selections accumulate: each full harness run convenes the selector three times, and the step\'s development and dogfood legs convened it more. Every one is write-once and every one verifies, so the directory is a log of the step\'s own testing, not a mutation of anything.'
});
set('selection_inventory.note',
  'selections are appended to the live home because the live home is the only place the real registry and the real decisions live. Nothing is mutated: no registry byte, no trace line, no reuse_count. A selection that was later re-run or re-thought is a new artifact with a new id; none is ever rewritten.');
del('selection_inventory.live_selections_created_by_this_harness');

// ---------------------------------------------------------------------------
// the sweep, read straight out of its own record
// ---------------------------------------------------------------------------
set('sweep.fresh_execute_decisions_minted_in_the_probe', sweep.execute_sweep.rows.map((r) => ({
  decision_id: r.execute_decision_id,
  capability: r.id,
  purpose: r.purpose,
  may_execute: r.may_execute,
  is_one_of_the_candidate_decisions: !r.fresh,
  reasons: r.reasons
})));
set('sweep.freshness_definition',
  'fresh means: this execute decision is not one of the two scope=compete candidate decisions that were on the ballot. A MAY_COMPETE decision must never be handed to the kernel, so the winner gets a decision minted after the selection, and the sweep asserts every one of the six is a new artifact (execute_sweep.every_execute_decision_is_a_new_artifact: '
  + sweep.execute_sweep.every_execute_decision_is_a_new_artifact + ').');
set('sweep.live_home_untouched', sweep.live_home_untouched);
set('sweep.the_three_reachable_selector_refusals', sweep.selector_refusals);
set('the_funnel.statuses_reachable_in_this_sweep', sweep.statuses_reachable_in_this_sweep);

// ---------------------------------------------------------------------------
// the suite, from the harness's own re-run of it
// ---------------------------------------------------------------------------
set('test_output', {
  command: 'npm test',
  files: i17.test_files,
  tests: i17.suite.tests,
  pass: i17.suite.pass,
  fail: i17.suite.fail,
  skipped: i17.suite.skipped,
  exit: i17.suite.exit,
  counters_as_printed: i17.suite_counters_as_printed,
  note: 'node --test prints its counters as ℹ tests / ℹ pass / ℹ fail, not as TAP # tests / # pass; a reader grepping for the TAP form will find nothing. Re-run inside item 17, so these counters are from the same pass that produced all_pass: true.'
});

// ---------------------------------------------------------------------------
// evidence file shas, and the two ship-bar items that quote the records
// ---------------------------------------------------------------------------
const EVIDENCE = ['shipbar-verify.js', 'shipbar.out.json', 'sweep.js', 'sweep.out.json', 'check-receipt.js', 'sync-receipt.js'];
const EVIDENCE_WHAT = {
  'check-receipt.js': 'verifies the receipt claims that this sync loop does not own — that the named commit exists and contains exactly the named paths, that the pinned blobs are that commit\'s bytes, that the dogfood invocations on disk carry the cited selection and decision ids, that the sweep\'s funnel and refusals are the sweep\'s own numbers. Read-only; writes nothing. A receipt that passes both this and the sync loop is consistent with its records AND with the world.',
  'sync-receipt.js': 'recomputes this receipt\'s derived fields from the two records of record, from git and from the bytes on disk; asserts the step-start values against this step\'s own commit and refuses to write a receipt from a red harness. Its sha is pinned here for the same reason every other harness file\'s is: the receipt is only as trustworthy as the program that produced it.'
};
const evidenceShas = {};
const evidenceRows = [];
for (const f of EVIDENCE) {
  const p = path.join(DIR, f);
  const sha = sha256(p);
  evidenceShas[f] = sha;
  const row = { path: 'evidence/2026-09-18-step5-selection/' + f, bytes: bytes(p), sha256: sha };
  const prior = (receipt.deltas.new_files || []).find((r) => r.path === row.path);
  if (prior && prior.lines !== undefined) row.lines = lines(p);
  const what = (prior && prior.what) || EVIDENCE_WHAT[f];
  if (what) row.what = what;
  evidenceRows.push(row);
}
set('artifacts.evidence_files', Object.assign({}, evidenceShas, { 'RECEIPT.json': 'this file' }));
const evidencePath = /^evidence\/2026-09-18-step5-selection\//;
const nonEvidence = (receipt.deltas.new_files || []).filter((r) => !evidencePath.test(r.path));
set('deltas.new_files', nonEvidence.concat(evidenceRows));

const bar = receipt.ship_bar.map((b) => Object.assign({}, b));
const at = (id) => bar.find((b) => b.id === id);

// The harness carries its own copies of the two step-start shas. If they ever
// drift from what git says the commits contain, one of the two is lying, and the
// receipt is not the place to find that out later.
if (i18.registry_sha256_at_step5_start !== START.registry_sha256) {
  throw new Error('the harness\'s step-5-start registry sha disagrees with git: ' + i18.registry_sha256_at_step5_start + ' vs ' + START.registry_sha256);
}
if (i18.registry_sha256_at_the_step4_commit !== START.registry_sha256_at_the_base_commit) {
  throw new Error('the harness\'s step-4 registry sha disagrees with git: ' + i18.registry_sha256_at_the_step4_commit + ' vs ' + START.registry_sha256_at_the_base_commit);
}
at(15).evidence = 'The trace-and-reuse identifiers present in the selection module: an empty list. What the selection module does write is exactly one file: '
  + 'selections/<selection_id>/selection.json, written once and never rewritten. Across the harness, which convened the selector live three times '
  + '(one selected reuse-ledger, one abstained, one no_candidates): registry sha identical before and after ('
  + i18.registry_sha256_before_this_harness.slice(0, 8) + '...), traces sha identical (' + i18.traces_sha256_before_this_harness.slice(0, 8)
  + '...), trace lines ' + out.before.trace_lines + ' before and ' + out.after.trace_lines + ' after, reuse_counts_moved: []. '
  + 'Selection is not reuse: selected is not invoked, and invoked is not successfully reused. The traces file has moved since the step-5 start ('
  + START.trace_lines + ' lines then, ' + out.after.trace_lines + ' now) but not inside this harness and not by this step\'s commit — see item 18.';
at(18).evidence = 'The registry and the traces are byte-identical before and after this harness (' + i18.registry_sha256_before_this_harness.slice(0, 8)
  + '... and ' + i18.traces_sha256_before_this_harness.slice(0, 8) + '...), nothing under registry/ or traces/ is left uncommitted, and this step\'s own commit '
  + i18.this_steps_own_commit + ' touched neither file — its paths are ' + i18.this_steps_own_commit_paths.join(', ') + '. '
  + 'The step-start values this is measured against are re-derived from that same commit rather than remembered, and the harness\'s own copies of them are asserted to agree with git. '
  + 'The registry does differ from the value at the step-4 commit (' + i18.registry_sha256_at_the_step4_commit.slice(0, 8) + '...) and from the value at this step\'s start, and the divergence is attributed rather than dropped: '
  + 'every commit in the window that touched registry/ or traces/ is a study-loop commit ('
  + windowCommits.map((c) => c.sha + ' ' + c.date).join(', ') + '), machine-written on the loop\'s own schedule. '
  + 'Read that way, "the registry remains unchanged" is a claim about this step, and it holds at both levels: the step\'s commit touches neither data file, and the harness moves neither byte.';
set('ship_bar', bar);

// ---------------------------------------------------------------------------
// the two prose blocks whose wording depended on the pre-re-run facts
// ---------------------------------------------------------------------------
set('activity_during_the_step5_window', {
  why_this_block_exists: 'the registry and traces differ from the step-4 commit and from the step-5 start, which would otherwise look like this step touched them',
  data_commits_inside_the_window: windowCommits,
  every_window_commit_is_a_study_loop_commit: windowCommits.every((c) => c.by_study_loop),
  data_commits_before_the_window: preWindowCommits,
  this_steps_own_commit: i18.this_steps_own_commit,
  this_steps_own_commit_paths: i18.this_steps_own_commit_paths,
  this_steps_own_commit_touched_registry_or_traces: i18.this_steps_own_commit_touched_registry_or_traces,
  effect_on_this_step: 'the registry sha recorded at this step\'s start (' + REGISTRY_SHA_AT_STEP5_START.slice(0, 8)
    + '...) already included the study-loop commits that preceded the window, and the window\'s own commits landed after it, so the step-start snapshot is not the live value today. '
    + 'The step\'s claim is therefore stated at two levels, and both are measured: at the step level, commit ' + i18.this_steps_own_commit
    + ' touches neither data file and the selection module contains no trace or reuse writer; at the window level, both files are byte-identical before and after the harness. '
    + 'The step-start sha is kept as a record of when the step began, not as a gate — a gate on it would have gone red for a reason that has nothing to do with the selection bus.',
  unrelated_working_tree_change_left_alone: 'capabilities/hunyuan3d-mlx-local/README.md is modified in the working tree by another lane and was deliberately never staged'
});

// ---------------------------------------------------------------------------
// what this step's live work left behind in the real home
// ---------------------------------------------------------------------------
// This step ran live. The dogfood legs, every development run of this harness and
// the exploratory probes all wrote real eligibility decisions, real selections,
// real invocations and one real eval run into HOME. The receipt cites the handful
// it uses as evidence and said nothing about the rest — which is fine right up
// until someone lists the home and finds them, and then "the receipt accounts for
// what this step did" is false in a way no check would have caught.
//
// So they are enumerated here. Nothing in this block is typed from memory: the
// inventory is read from disk, "not in any commit" is asked of git per path, and
// the tier of each id is computed from shipbar.out.json and from the receipt's
// own text as it stood before this block was written. The receipt text is
// snapshotted first precisely because this block goes on to contain every id —
// reading it afterwards would put every id in tier 2 and empty the tier that
// exists to disclose things.
//
// Three tiers, all derived, none hand-assigned:
//   named_in_the_final_harness_run  — ids shipbar.out.json itself reports
//   cited_elsewhere_in_this_receipt — ids this receipt already names as evidence
//   named_nowhere_in_this_receipt   — the remainder: harness development runs,
//                                     dogfood attempts that were superseded, and
//                                     the exploratory probes
// The third tier is the one this block exists for. The first two are listed so
// that the tiers can be checked to partition the inventory exactly, rather than
// trusted to.

// The snapshot excludes this block itself. That is not a shortcut: the block
// lists every id, so on a second run the receipt would be quoting the block it is
// about to overwrite, every id would land in the cited tier, and the tier that
// exists to disclose things would empty itself. The excluded field is the only
// one that has to be excluded for the classification to be idempotent, and a
// second run reporting zero changes is the check that it is.
const receiptTextBeforeThisBlock = JSON.stringify(Object.assign({}, receipt, { live_artifacts_this_step_minted: undefined }));
const trackedPaths = new Set(git(['ls-files', '--', 'eligibility', 'selections', 'invocations', 'runs'])
  .split('\n').filter((l) => l.trim().length > 0));
const isTracked = (p) => { for (const t of trackedPaths) if (t.startsWith(p + '/')) return true; return false; };
const untrackedDirs = (prefix) => fs.readdirSync(path.join(HOME, prefix), { withFileTypes: true })
  .filter((e) => e.isDirectory()).map((e) => prefix + '/' + e.name).filter((p) => !isTracked(p)).sort();
const inNoCommit = (p) => !isTracked(p);

const finalRunIds = new Set([
  out.live_dogfood.selected, out.live_dogfood.abstained, out.live_dogfood.no_candidates
].concat(out.live_dogfood.compete_decisions_minted || []));
const tierOf = (id) => (finalRunIds.has(id) ? 'named_in_the_final_harness_run'
  : (receiptTextBeforeThisBlock.indexOf(id) !== -1 ? 'cited_elsewhere_in_this_receipt' : 'named_nowhere_in_this_receipt'));
const atSecond = (id) => (String(id).match(/(\d{8}T\d{6}Z)-/) || [])[1] || null;

const eligInventory = untrackedDirs('eligibility').map((p) => {
  const j = readJson(path.join(HOME, p, 'decision.json'));
  return {
    decision_id: j.decision_id,
    scope: j.scope,
    purpose: j.caller_context && j.caller_context.purpose,
    capability_id: j.capability_id,
    eligible: j.eligible,
    reasons: j.reasons
  };
});
const batchKey = (r) => [atSecond(r.decision_id), r.scope, r.purpose].join(' | ');
const eligBatches = {};
for (const r of eligInventory) (eligBatches[batchKey(r)] = eligBatches[batchKey(r)] || []).push(r);
const eligByBatch = Object.keys(eligBatches).sort().map((k) => {
  const rs = eligBatches[k];
  const tier = (t) => rs.filter((r) => tierOf(r.decision_id) === t);
  const inHarness = tier('named_in_the_final_harness_run');
  return {
    at_second: atSecond(rs[0].decision_id),
    scope: rs[0].scope,
    purpose: rs[0].purpose,
    count: rs.length,
    eligible: rs.filter((r) => r.eligible).map((r) => r.capability_id).sort(),
    ineligible: rs.filter((r) => !r.eligible).length,
    named_in_the_final_harness_run: inHarness.length,
    cited_elsewhere_in_this_receipt: tier('cited_elsewhere_in_this_receipt').length,
    named_nowhere_in_this_receipt: tier('named_nowhere_in_this_receipt').length,
    // Named, not merely counted: a tally cannot be checked against another
    // record, and the harness's own report of what it minted is the only
    // independent statement about these two decisions.
    named_in_the_final_harness_run_ids: inHarness.map((r) => r.decision_id).sort()
  };
});

const selInventory = untrackedDirs('selections').map((p) => {
  const j = readJson(path.join(HOME, p, 'selection.json'));
  return {
    selection_id: j.selection_id,
    at_second: atSecond(j.selection_id),
    status: j.status,
    selected_capability_id: j.selected_capability_id,
    candidates_on_the_ballot: j.candidates.length,
    selector: j.selector.id + '@' + j.selector.version,
    tier: tierOf(j.selection_id)
  };
});

const invInventory = untrackedDirs('invocations').map((p) => {
  const j = readJson(path.join(HOME, p, 'manifest.json'));
  return {
    invocation_id: j.invocation_id,
    at_second: atSecond(j.invocation_id),
    status: j.status,
    capability_id: j.capability_id,
    mode: j.mode,
    selection_id: j.selection_id,
    authorizing_decision_id: j.eligibility_decision_id,
    authorizing_decision_scope: j.eligibility && j.eligibility.scope,
    status_basis: (j.status_basis || '').slice(0, 160),
    tier: tierOf(j.invocation_id)
  };
});

const runInventory = untrackedDirs('runs').map((p) => {
  const r = readJson(path.join(HOME, p, 'receipt.json'));
  return {
    run_id: r.run_id,
    at_second: atSecond(r.run_id),
    capability_id: r.capability_id,
    verdict: r.verdict,
    tier: tierOf(r.run_id)
  };
});

const countByTier = (rows, idOf) => {
  const c = { named_in_the_final_harness_run: 0, cited_elsewhere_in_this_receipt: 0, named_nowhere_in_this_receipt: 0 };
  for (const r of rows) c[tierOf(idOf(r))] += 1;
  return c;
};
const allIds = eligInventory.map((r) => r.decision_id)
  .concat(selInventory.map((r) => r.selection_id))
  .concat(invInventory.map((r) => r.invocation_id))
  .concat(runInventory.map((r) => r.run_id));
const tierTally = { named_in_the_final_harness_run: 0, cited_elsewhere_in_this_receipt: 0, named_nowhere_in_this_receipt: 0 };
for (const id of allIds) tierTally[tierOf(id)] += 1;
// The newest artifact's own timestamp, read out of the ids, not the clock at the
// moment of the sync. A wall-clock stamp here would be the one field in the block
// that differs on every run, and it would mean the wrong thing anyway: what a
// reader needs to know is how far the inventory is complete, which is the newest
// thing in it, not when somebody last re-ran the sync.
const newestSecond = allIds.map(atSecond).filter(Boolean).sort().pop();

set('live_artifacts_this_step_minted', {
  why_this_block_exists: 'this step ran live against the real home, and running live means minting. The receipt cites the artifacts it uses as evidence; this block accounts for every one of them, including the ones it does not cite, because an auditor who lists the home will find them and should not have to guess where they came from.',
  derived_from: 'git ls-files per path for "in no commit", each artifact\'s own bytes for its ids and fields, shipbar.out.json for the final harness run\'s ids, and this receipt\'s own text (snapshotted before this block was written) for the cited tier',
  in_no_commit: true,
  staged_by_this_step: false,
  staged_by_this_step_note: 'commit ' + i18.this_steps_own_commit + ' adds exactly ' + i18.this_steps_own_commit_paths.length
    + ' paths and none of them is an artifact directory: ' + i18.this_steps_own_commit_paths.join(', ')
    + '. The artifacts stay untracked in the working tree, and the evidence commit that follows adds only evidence/.',
  why_not_deleted: 'eligibility decisions and selections are write-once and never rewritten — un-minting them by deleting the directories would be rewriting history by another name. The dogfood invocations among them are cited by this receipt as its evidence. They are disclosed rather than removed, and disclosed rather than left for a reader to find.',
  counted_at: newestSecond,
  counted_at_means: 'the timestamp of the newest artifact in the inventory, read out of the artifact ids themselves. It is the moment this inventory is complete through, not the moment this file was last written — a wall-clock stamp would differ on every sync run and would answer a question nobody is asking.',
  counts: {
    eligibility_decisions: eligInventory.length,
    selections: selInventory.length,
    invocations: invInventory.length,
    runs: runInventory.length,
    total: allIds.length
  },
  counts_already_in_the_repo_before_this_step: {
    eligibility_decisions: fs.readdirSync(path.join(HOME, 'eligibility'), { withFileTypes: true }).filter((e) => e.isDirectory()).length - eligInventory.length,
    selections: 0,
    note: 'step 4\'s 13 decisions are committed; selections did not exist before this step, so every selection on disk is this step\'s'
  },
  tiers: {
    named_in_the_final_harness_run: tierTally.named_in_the_final_harness_run,
    cited_elsewhere_in_this_receipt: tierTally.cited_elsewhere_in_this_receipt,
    named_nowhere_in_this_receipt: tierTally.named_nowhere_in_this_receipt,
    the_three_tiers_partition_the_inventory: tierTally.named_in_the_final_harness_run
      + tierTally.cited_elsewhere_in_this_receipt + tierTally.named_nowhere_in_this_receipt === allIds.length,
    what_each_tier_means: {
      named_in_the_final_harness_run: 'minted by the run of shipbar-verify.js that produced shipbar.out.json — the live mints in item 15',
      cited_elsewhere_in_this_receipt: 'minted earlier in the step and named elsewhere in this receipt as evidence: the two dogfood legs and the eval run',
      named_nowhere_in_this_receipt: 'minted by this step and named nowhere else in this receipt — the development runs of the harness, the superseded dogfood attempts, and the exploratory probes'
    }
  },
  eligibility_decisions: {
    untracked_now: eligInventory.length,
    batches: eligByBatch,
    reading_the_batches: 'each batch is one moment of one scope at one purpose; the 22-capability batches are the two full-ladder probes that asked every registry capability at purpose eval, the 2-capability batches are the harness\'s own live mints and the dogfood legs, and the single-row execute batches are the kernel\'s fresh authorizations and one deliberate negative probe at purpose normal that returned 0 eligible'
  },
  selections: selInventory,
  invocations: invInventory,
  runs: runInventory
});

set('verification_harness.why_not_just_accept_it',
  'five of the eighteen items are negative claims (no recomputation, no authority, no reuse movement, no semantic routing, no registry movement). A negative claim that is only asserted is a check that cannot fail. '
  + 'Each is therefore measured against a control that would move if the claim were false: the same capability asked twice with different contexts, a registry and trace hash taken before and after the whole harness, '
  + 'a 24-word vocabulary scan run over comment-stripped source, and this step\'s own commit read path by path. '
  + '"Unchanged registry" is deliberately read as "unchanged by this step" and not "equal to the step-start sha": an autonomous study loop commits machine-written registry and trace updates on its own schedule, '
  + 'so a frozen-equality gate would fail for a reason that is not evidence about the selection bus, and bumping the constant until it passed would be worse. '
  + 'What is gated is what this step owns — the harness window is byte-identical for both files, nothing under them is uncommitted, and commit ' + i18.this_steps_own_commit + ' touches neither — '
  + 'and what is not gated is still recorded: every window commit that did move the data is listed by sha, date and subject.');

set('verification_harness.harness_files', [
  'evidence/2026-09-18-step5-selection/shipbar-verify.js',
  'evidence/2026-09-18-step5-selection/sweep.js',
  'evidence/2026-09-18-step5-selection/sync-receipt.js'
]);
set('verification_harness.reproduce', [
  'cd ' + HOME,
  'node evidence/2026-09-18-step5-selection/shipbar-verify.js   # writes shipbar.out.json; all_pass must be true',
  'node evidence/2026-09-18-step5-selection/sweep.js            # writes sweep.out.json; live_home_untouched.identical must be true',
  'node evidence/2026-09-18-step5-selection/sync-receipt.js     # rewrites RECEIPT.json; a second run must report 0 changed',
  'npm test                                                     # ' + i17.suite.pass + ' pass, ' + i17.suite.fail + ' fail'
]);

// ---------------------------------------------------------------------------
fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n');
console.log('sync-receipt: ' + changed.length + ' changed, ' + unchanged.length + ' already correct');
for (const p of changed) console.log('  changed   ' + p);
for (const p of unchanged) console.log('  unchanged ' + p);
console.log('record of record: shipbar checked_at ' + out.checked_at + ', sweep registry '
  + sweep.live_home_untouched.registry_sha256.before.slice(0, 8) + '..., selections in the live home ' + all.length);
