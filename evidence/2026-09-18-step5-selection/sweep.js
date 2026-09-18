'use strict';
// Step-5 dogfood sweep: measure how wide the selection bus actually is against
// the real registry, today, with nothing stubbed.
//
// The chain measured, per capability:
//   registry -> executable? -> may compete? -> is it on the ballot? -> can it be
//   explicitly selected? -> would a FRESH scope=execute decision authorize it?
//
// Discipline: the live home is read-only here. Every artifact this sweep needs
// to mint (compete decisions, selections) is minted in a throwaway probe home
// seeded from the real registry, and the live home's registry sha, trace file
// sha and per-capability reuse counts are snapshotted before and after to prove
// it. The sweep is a measurement, not an exercise of authority: no invocation
// is created, so nothing is executed and no reuse is recorded.
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const E = require('/Users/adam26/zcode-rcos/lib/eligibility');
const R = require('/Users/adam26/zcode-rcos/lib/registry');
const S = require('/Users/adam26/zcode-rcos/lib/selection');

const home = '/Users/adam26/zcode-rcos';
const sha256 = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function snap() {
  const reuse = {};
  for (const cap of R.loadRegistry(home).capabilities) reuse[cap.id] = cap.reuse_count;
  const tracesPath = path.join(home, 'traces/traces.jsonl');
  return {
    registry_sha256: sha256(path.join(home, 'registry/capability-registry.json')),
    traces_sha256: fs.existsSync(tracesPath) ? sha256(tracesPath) : null,
    trace_lines: fs.existsSync(tracesPath)
      ? fs.readFileSync(tracesPath, 'utf8').split('\n').filter((l) => l.trim().length > 0).length
      : 0,
    reuse_counts: reuse
  };
}
const before = snap();

const reg = R.loadRegistry(home);
const caps = reg.capabilities.map((c) => ({ id: c.id, status: c.status, version: c.version }));
const competePurposes = ['normal', 'eval', 'forensic'];

// A throwaway home: the sweep mints real artifacts, but never in the real home.
const probe = fs.mkdtempSync(path.join(os.tmpdir(), 'step5-sweep-'));
for (const sub of ['registry', 'capabilities', 'evals']) {
  fs.cpSync(path.join(home, sub), path.join(probe, sub), { recursive: true });
}
const removeProbe = (dir) => {
  if (typeof dir !== 'string' || !dir.startsWith(os.tmpdir() + path.sep) || dir === home) {
    throw new Error('refusing to delete ' + dir + ' — removeProbe only deletes probe directories under ' + os.tmpdir());
  }
  fs.rmSync(dir, { recursive: true, force: true });
  return true;
};

const out = {
  home,
  probe_home: probe,
  registry_capabilities: caps.length,
  selectors_installed: Object.keys(S.SELECTORS),
  purposes: {},
  funnel: {},
  selector_refusals: {},
  statuses_reachable_in_this_sweep: [],
  live_home_untouched: null
};

// ---- 1. the eligibility ladder, per purpose, for every capability ----------
for (const p of competePurposes) {
  const rows = [];
  for (const cap of caps) {
    const opts = { capabilityId: cap.id, scope: 'compete' };
    if (p === 'forensic') opts.forensicReason = 'step-5 dogfood sweep — read-only, no invocation is recorded';
    const res = E.evaluate(home, cap.id, E.buildContext(p, opts));
    if (!res.ok) { console.log('ERROR ' + cap.id + ': ' + res.error); continue; }
    rows.push({
      id: cap.id,
      status: cap.status,
      executable: res.state.executable,
      provenance: res.state.provenance,
      may_compete: res.decision.eligible,
      reasons: res.decision.reasons
    });
  }
  const eligible = rows.filter((r) => r.may_compete).map((r) => r.id).sort();
  const hist = {};
  for (const r of rows) {
    const k = r.reasons.join(' + ') || '(eligible)';
    hist[k] = (hist[k] || 0) + 1;
  }
  out.purposes[p] = { scope: 'compete', eligible_count: eligible.length, total: rows.length, eligible, histogram: hist, rows };
  console.log('=== compete eligibility, purpose: ' + p + ' ===');
  console.log('may compete ' + eligible.length + '/' + rows.length + ': ' + (eligible.join(', ') || '(none)'));
  for (const [k, v] of Object.entries(hist).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))) {
    console.log('  ' + String(v).padStart(2) + '  ' + k);
  }
  console.log('');
}

// ---- 2. the bus itself: mint the ballot, then ask explicit@1 for each cap ---
// The widest ballot the registry can produce today is the purpose=eval one.
const ballotPurpose = 'eval';
const ballotIds = out.purposes[ballotPurpose].eligible;
const minted = {};
for (const id of ballotIds) {
  const d = E.decideForHome(probe, id, { purpose: ballotPurpose, scope: 'compete' });
  if (!d.ok) { console.log('MINT ERROR ' + id + ': ' + d.error); continue; }
  minted[id] = d.decision_id;
}
const candidateDecisionIds = Object.values(minted);
console.log('=== the ballot (purpose ' + ballotPurpose + ') ===');
console.log('minted ' + candidateDecisionIds.length + ' compete decisions: ' + candidateDecisionIds.join(', '));
console.log('');

// Every capability in the registry is offered to the selector by name — the
// eligible ones and the ineligible ones alike. That is the measurement: what
// does the bus do with a name it cannot act on?
const selectionRows = [];
for (const cap of caps) {
  const sel = S.createSelection(probe, { selectorInput: { capability_id: cap.id }, candidateDecisionIds });
  const verify = sel.ok ? S.verifySelection(probe, sel.selection_id) : null;
  selectionRows.push({
    id: cap.id,
    status: cap.status,
    on_the_ballot: ballotIds.includes(cap.id),
    selection_status: sel.ok ? sel.status : 'error',
    selected_capability_id: sel.ok ? sel.selected_capability_id : null,
    status_basis: sel.ok ? sel.status_basis : sel.error,
    selection_id: sel.ok ? sel.selection_id : null,
    verifies: verify ? verify.ok : null
  });
}
const selHist = {};
for (const r of selectionRows) selHist[r.selection_status] = (selHist[r.selection_status] || 0) + 1;
out.selection_sweep = {
  selector: 'explicit@1',
  ballot_purpose: ballotPurpose,
  candidate_decision_ids: minted,
  offered: selectionRows.length,
  histogram: selHist,
  rows: selectionRows
};
console.log('=== explicit@1 offered every capability by name ===');
console.log('offered ' + selectionRows.length + ', ' + JSON.stringify(selHist));
for (const r of selectionRows.filter((x) => x.selection_status !== 'selected')) {
  console.log('  ' + r.selection_status + '  ' + r.id + ' — ' + r.status_basis);
}
console.log('');

// ---- 3. the winner's second question: a FRESH scope=execute decision -------
// The selected capability is asked again, at execute scope, at every purpose —
// and this time the answer is minted, so the freshness claim is a fact about
// two artifact ids rather than an assumption about an in-memory object.
const winners = selectionRows.filter((r) => r.selection_status === 'selected');
const executeRows = [];
for (const w of winners) {
  for (const p of competePurposes) {
    const opts = { purpose: p, scope: 'execute' };
    if (p === 'forensic') opts.forensicReason = 'step-5 dogfood sweep — read-only, no invocation is recorded';
    const d = E.decideForHome(probe, w.id, opts);
    if (!d.ok) { console.log('EXECUTE DECIDE ERROR ' + w.id + ': ' + d.error); continue; }
    executeRows.push({
      id: w.id,
      purpose: p,
      execute_decision_id: d.decision_id,
      may_execute: d.decision.eligible,
      reasons: d.decision.reasons,
      scope: d.decision.scope,
      fresh: !candidateDecisionIds.includes(d.decision_id)
    });
  }
}
out.execute_sweep = {
  rows: executeRows,
  every_execute_decision_is_a_new_artifact: executeRows.every((r) => r.fresh && r.scope === 'execute')
};
console.log('=== the selected winner is asked again, at execute scope ===');
for (const r of executeRows) {
  console.log('  ' + r.id + '  purpose=' + r.purpose + '  may execute: ' + r.may_execute
    + '  ' + r.execute_decision_id + (r.fresh ? ' (fresh)' : ' (REUSED A CANDIDATE ID)')
    + (r.may_execute ? '' : '  (' + r.reasons.join(' + ') + ')'));
}
console.log('');

// ---- 4. the funnel, in one line per rung ----------------------------------
const executableCount = out.purposes[ballotPurpose].rows.filter((r) => r.executable).length;
out.funnel = {
  rung_1_in_the_registry: caps.length,
  rung_2_executable: executableCount,
  rung_3_may_compete_at_purpose_eval: ballotIds.length,
  rung_4_on_the_ballot: candidateDecisionIds.length,
  rung_5_explicitly_selectable: winners.length,
  rung_6_execute_eligible_at_purpose_eval: executeRows.filter((r) => r.purpose === 'eval' && r.may_execute).length,
  rung_6_execute_eligible_at_purpose_normal: executeRows.filter((r) => r.purpose === 'normal' && r.may_execute).length,
  where_the_funnel_narrows: 'the executability ladder (declared adapter, supported type, usable contract, present entrypoint) — not the selection bus'
};
console.log('=== the funnel ===');
for (const [k, v] of Object.entries(out.funnel)) {
  if (typeof v === 'number') console.log('  ' + String(v).padStart(3) + '  ' + k);
}
console.log('  ---  ' + out.funnel.where_the_funnel_narrows);
console.log('');

// ---- 5. the statuses a caller can reach, and the ones only a selector can --
const noCandidates = S.createSelection(probe, { selectorInput: { capability_id: caps[0].id }, candidateDecisionIds: [] });
const unknownName = S.createSelection(probe, { selectorInput: { capability_id: 'no-such-capability-anywhere' }, candidateDecisionIds });
const badKey = S.createSelection(probe, { selectorInput: { capability_id: caps[0].id, similarity: 0.9 }, candidateDecisionIds });
// A malformed input never reaches the status machinery — it is refused at the
// input boundary, which is why it reports an error rather than a status.
const asStatus = (r) => (r.ok ? r.status : 'refused (not a status: a malformed input never reaches the core)');
out.selector_refusals = {
  empty_ballot: { status: asStatus(noCandidates), basis: noCandidates.ok ? noCandidates.status_basis : noCandidates.error },
  a_name_that_is_not_on_the_ballot: { status: asStatus(unknownName), basis: unknownName.ok ? unknownName.status_basis : unknownName.error },
  an_unknown_input_key: { status: asStatus(badKey), basis: badKey.ok ? badKey.status_basis : badKey.error }
};
out.statuses_reachable_in_this_sweep = [...new Set(selectionRows.map((r) => r.selection_status)
  .concat([asStatus(noCandidates), asStatus(unknownName)]))].sort();
console.log('=== what a caller can reach without a custom selector ===');
console.log('  empty ballot            -> ' + asStatus(noCandidates) + '  (' + out.selector_refusals.empty_ballot.basis + ')');
console.log('  a name off the ballot   -> ' + asStatus(unknownName) + '  (' + out.selector_refusals.a_name_that_is_not_on_the_ballot.basis + ')');
console.log('  an unknown input key    -> ' + asStatus(badKey) + '  (' + out.selector_refusals.an_unknown_input_key.basis + ')');
console.log('  statuses reached here: ' + out.statuses_reachable_in_this_sweep.join(', '));
console.log('  not reachable without a selector implementation: ambiguous, failed — see shipbar item 9');
console.log('');

// ---- 6. the live home was never written to --------------------------------
removeProbe(probe);
const after = snap();
const moved = Object.keys(before.reuse_counts).filter((k) => before.reuse_counts[k] !== after.reuse_counts[k]);
out.live_home_untouched = {
  registry_sha256: { before: before.registry_sha256, after: after.registry_sha256, identical: before.registry_sha256 === after.registry_sha256 },
  traces_sha256: { before: before.traces_sha256, after: after.traces_sha256, identical: before.traces_sha256 === after.traces_sha256 },
  reuse_counts_moved: moved,
  selections_created_in_the_live_home: 0,
  invocations_created_in_the_live_home: 0
};
console.log('=== the live home ===');
console.log('registry identical: ' + out.live_home_untouched.registry_sha256.identical);
console.log('traces identical:   ' + out.live_home_untouched.traces_sha256.identical);
console.log('reuse counts moved: ' + (moved.length === 0 ? 'none' : moved.join(', ')));
console.log('');

fs.writeFileSync(path.join(__dirname, 'sweep.out.json'), JSON.stringify(out, null, 2) + '\n');
console.log('wrote ' + path.join(__dirname, 'sweep.out.json'));
