'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { KINDS, VERDICTS, validateRegistry, shipCount } = require('./validate');
const { deriveReuseCounts } = require('./traces');

const RETIREMENT_POLICY_VERSION = 'rcos-retire/1';

function todayStr(d = new Date()) { return d.toISOString().slice(0, 10); }

function loadRegistry(homeDir) {
  const p = path.join(homeDir, 'registry', 'capability-registry.json');
  const reg = JSON.parse(fs.readFileSync(p, 'utf8'));
  const errors = validateRegistry(reg);
  if (errors.length > 0) throw new Error('invalid registry at ' + p + ':\n- ' + errors.join('\n- '));
  return reg;
}

function saveRegistry(homeDir, reg) {
  const errors = validateRegistry(reg);
  if (errors.length > 0) throw new Error('refusing to save invalid registry:\n- ' + errors.join('\n- '));
  fs.writeFileSync(path.join(homeDir, 'registry', 'capability-registry.json'), JSON.stringify(reg, null, 2) + '\n');
}

function findCapability(reg, id) {
  const cap = reg.capabilities.find((c) => c.id === id);
  if (!cap) throw new Error('unknown capability \'' + id + '\'');
  return cap;
}

function queryCapabilities(reg, opts = {}) {
  return reg.capabilities.filter((c) =>
    (!opts.status || c.status === opts.status) && (!opts.kind || c.kind === opts.kind));
}

function proposeCapability(reg, spec) {
  if (!spec || !spec.id || !spec.name || !spec.kind) throw new Error('propose requires id, name, kind');
  if (reg.capabilities.some((c) => c.id === spec.id)) throw new Error('capability \'' + spec.id + '\' already exists');
  if (!KINDS.includes(spec.kind)) throw new Error('kind must be one of ' + KINDS.join('|'));
  const cap = {
    id: spec.id, name: spec.name, kind: spec.kind, version: spec.version || '0.1.0',
    status: 'candidate', admitted_after: [], evals: [], reuse_count: 0, last_eval: null
  };
  if (spec.lineage !== undefined) cap.lineage = spec.lineage;
  reg.capabilities.push(cap);
  return cap;
}

function submitEval(reg, id, ev) {
  const cap = findCapability(reg, id);
  if (!ev || !ev.task_id || !ev.run_id) throw new Error('eval-submit requires task_id and run_id');
  if (!VERDICTS.includes(ev.verdict)) throw new Error('verdict must be one of ' + VERDICTS.join('|'));
  cap.evals.push({ task_id: ev.task_id, verdict: ev.verdict, run_id: ev.run_id });
  cap.last_eval = ev.date || todayStr();
  return cap;
}

function promoteCapability(reg, id, date = todayStr()) {
  const cap = findCapability(reg, id);
  if (cap.status !== 'candidate') throw new Error('cannot promote \'' + id + '\': status is ' + cap.status + ', must be candidate');
  const ships = cap.evals.filter((e) => e.verdict === 'ship');
  if (ships.length < 2) throw new Error('cannot promote \'' + id + '\': x2-ship gate needs 2 shipped evals, has ' + ships.length);
  const tasks = [...new Set(ships.map((e) => e.task_id))];
  if (tasks.length < 2) {
    throw new Error('cannot promote \'' + id + '\': x2-ship gate needs 2 DISTINCT task ids — same-task repeats do not count ' +
      '(the point is transfer, not memorization); both ships are on \'' + tasks[0] + '\'');
  }
  const runless = ships.filter((e) => typeof e.run_id !== 'string' || e.run_id.trim().length === 0);
  if (runless.length > 0) {
    throw new Error('cannot promote \'' + id + '\': no run id, no admission — ship eval(s) missing run_id: ' +
      runless.map((e) => e.task_id).join(', '));
  }
  cap.status = 'promoted';
  cap.admitted_after = tasks;
  armRetirement(cap, date);
  return cap;
}

// Retirement is armed AT ADMISSION, never later: promotion without retirement
// is hoarding — the registry must shrink as well as grow. Thresholds stay null
// until pilot data calibrates them (the upstream spec says settle from pilot
// data; inventing numbers here would be a check that cannot fail).
function armRetirement(cap, date = todayStr()) {
  if (cap.retirement) return cap;
  cap.retirement = {
    armed_at: date,
    policy_version: RETIREMENT_POLICY_VERSION,
    decay: { window: 5, threshold: null },
    neglect: { n: 20, threshold: null }
  };
  return cap;
}

function retireCapability(reg, id, reason) {
  const cap = findCapability(reg, id);
  if (!reason || reason.trim().length === 0) throw new Error('cannot retire \'' + id + '\': a reason is required');
  cap.status = 'retired';
  cap.retire_reason = reason.trim();
  return cap;
}

// reuse_count is a CACHE of the trace log, not independent truth. There is no
// manual increment path: reuseDeltas() is read-only, syncDerivedReuse() is the
// single writer, and the only way to move the number is to append a trace.
function reuseDeltas(reg, traces) {
  const counts = deriveReuseCounts(traces);
  const deltas = [];
  for (const c of reg.capabilities) {
    const derived = counts[c.id] || 0;
    if (c.reuse_count !== derived) deltas.push({ id: c.id, stored: c.reuse_count, derived });
  }
  return deltas;
}

function syncDerivedReuse(reg, traces) {
  const deltas = reuseDeltas(reg, traces);
  for (const d of deltas) findCapability(reg, d.id).reuse_count = d.derived;
  return deltas;
}

function auditRegistry(reg, now = new Date(), traces = null) {
  const errors = validateRegistry(reg);
  const warnings = [];
  for (const c of reg.capabilities) {
    if (c.status === 'promoted' && shipCount(c) < 2) {
      errors.push('\'' + c.id + '\': promoted without x2-ship gate (' + shipCount(c) + ' ships)');
    }
    if (c.status === 'promoted') {
      const tasks = [...new Set(c.evals.filter((e) => e.verdict === 'ship').map((e) => e.task_id))];
      if (tasks.length < 2) {
        errors.push('\'' + c.id + '\': promoted without 2 distinct ship task ids (' + tasks.length + ') — same-task repeats do not count');
      }
      const runless = c.evals.filter((e) => e.verdict === 'ship' && (typeof e.run_id !== 'string' || e.run_id.trim().length === 0));
      if (runless.length > 0) {
        errors.push('\'' + c.id + '\': no run id, no admission — ship eval(s) missing run_id: ' + runless.map((e) => e.task_id).join(', '));
      }
      if (!c.retirement) errors.push('\'' + c.id + '\': promoted without retirement armed (arm at admission, never later)');
    }
    if (c.status === 'candidate' && c.evals.length === 0) {
      warnings.push('\'' + c.id + '\': candidate with zero evals');
    } else {
      const tail = c.evals.slice(-2);
      if (tail.length === 2 && tail.every((e) => e.verdict !== 'ship')) {
        const armed = c.status === 'promoted' && c.retirement ? ' (retirement armed ' + c.retirement.armed_at + ', policy ' + c.retirement.policy_version + ')' : '';
        warnings.push('\'' + c.id + '\': decaying — last 2 evals not shipped' + armed);
      }
    }
    if (c.status === 'promoted' && c.last_eval) {
      const ageDays = (now - Date.parse(c.last_eval + 'T00:00:00Z')) / 86400000;
      if (ageDays > 90) warnings.push('\'' + c.id + '\': stale — last eval ' + c.last_eval);
    }
  }
  if (traces !== null) {
    for (const d of reuseDeltas(reg, traces)) {
      warnings.push('\'' + d.id + '\': reuse cache stale — stored ' + d.stored + ', trace-derived ' + d.derived + ' (run `rcos sync`)');
    }
  }
  return { ok: errors.length === 0, errors, warnings };
}

module.exports = {
  todayStr, loadRegistry, saveRegistry, findCapability, queryCapabilities,
  proposeCapability, submitEval, promoteCapability, retireCapability, armRetirement,
  reuseDeltas, syncDerivedReuse, auditRegistry, RETIREMENT_POLICY_VERSION
};
