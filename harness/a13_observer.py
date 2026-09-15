#!/usr/bin/env python3
"""A13 isolation observer: harness-owned counters, external tripwire,
per-leg sampling, launch records, process journal (harness side).

Counter-ownership doctrine (auditor's words, the property he is
buying): "the code being isolated is not the sole authority for
the evidence that proves its own isolation." All counters below
are harness-owned monotonic state: the isolated legs never write
them (they only trigger observations the harness records), the
runner bumps them at its single provider-invocation site and at
cell completion, and every receipt value derived from them is a
recomputation over recorded samples (shared identity, zero
deltas), never prose and never a boolean standing in for a count.

Proof stack (auditor): STATIC (reachable-callable scan, dynamic
escape rejection, no executable-capability parameters,
subprocess/exec family rejection) . RUNTIME authoritative
(harness-owned provider monotonic counter, harness-owned
ORDER-cell counter, external tripwire, per-leg before/after
samples) . IDENTITY (same captured response sha and same cell
identity across ON/OFF/PASS) . FROZEN EXPECTATION (enclosing
provider-call total == 1, sourced from prereg/lock, not the
receipt) . q recomputes everything; absence == FAIL; assertion
without measurement == FAIL; any observer disagreement == FAIL.

Claim wording (auditor): a clean grade on those equalities is
read as "during A13 causal execution, zero unprecommitted
process execution was permitted" -- that is the CONCLUSION of a
passing recomputation over the journal, the budget, the sealed
launch records, the tripwire record and the jail boundary -- not
a free-standing prose assertion and never general hostile-code
containment (sys.addaudithook hooks belong to the current
interpreter and Python warns they are not a security sandbox;
the unbypassable descendant control is the jail boundary
itself: --network none, read-only, cap-drop ALL).

Stdlib only. No audit-event-raising calls inside the hook body
(plain comparisons, tuple/frozenset membership, list append,
integer arithmetic, attribute reads); raising vetoes the audited
operation, which is the deny mechanism.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

from dockersandbox import DockerSandbox

OBSERVER_SCHEMA = "a13-observer-v1"

# In-region container-launch roles (auditor Ruling 1): the OFF
# counterfactual leg is exactly two authorized launches in this
# order -- snapshot_verify FIRST (the /task byte-binding proof on
# the fresh DockerSandbox.run() path), engine_exec SECOND. Both
# roles are recorded and separately identity-bound; extra,
# missing, reordered, or role-substituted launches FAIL. The
# snapshot verifier stays INSIDE the isolation region (it is part
# of the real fresh-run path required before OFF execution) and is
# frozen as its own infrastructure role -- never folded into the
# engine-execution budget.
SNAPSHOT_VERIFY_ROLE = "snapshot-verify"
ENGINE_ROLE = "engine"
# Closed role set for jail launches (q enforces membership).
JAIL_LAUNCH_ROLES = (SNAPSHOT_VERIFY_ROLE, ENGINE_ROLE)

# ---- harness-owned monotonic state (plain data; provider- and
# capability-incapable by construction: ints, strings, lists of
# recorded observations -- never handles, never callables) ----
_PROVIDER_CALLS = 0
_ORDER_CELLS = 0
_REGION_DEPTH = 0
_TRIP_RECORDS = []
_PROCESS_LOG = []
_JOURNAL_OPEN = True
_JOURNAL_START = 0
_JOURNAL_STOP_MONO = None
_JOURNAL_CLOSED_MONO = None
_REGION_EXIT_MONO = None
_REGION_EXIT_WALL = None
_CURRENT_LEG = None
_REGION_ENTRY_INDEX = 0
_REGION_ENTRY_WALL = None
_REGION_ENTRY_MONO = None
_HOOK_INSTALLED = False
_ENGINE_JAIL_BUILDER = None

# Monotonic sequence for trip/process records (len() of the owning
# list -- no clock, no randomness, fully deterministic order).
# Denied provider-adjacent imports (fresh imports only; everything
# the frozen path needs is imported before arming -- proven green
# under an armed hook by the H35 suite, so any trip here is a real
# deviation, fail-closed direction).
_DENY_IMPORTS = ("openai", "anthropic", "litellm", "requests",
                 "httpx", "urllib3", "aiohttp", "boto3", "botocore",
                 "groq", "together", "fireworks", "replicate",
                 "cohere", "mistralai", "websocket", "websockets",
                 "sseclient", "socket", "ssl")
# Shell executables: a shell Popen has no legitimate use on the
# frozen leg path (engines/checkers/git/docker run direct argv).
_SHELL_BASENAMES = ("sh", "bash", "dash", "zsh", "fish")
# AF_UNIX value without importing socket inside the hook path
# (the module never imports socket at all; the smoke asserts this
# constant equals socket.AF_UNIX).
_AF_UNIX = 1


class TripwireError(RuntimeError):
    """A provider-relevant event was attempted inside the isolated
    region. Carries the audit event name; raised from inside the
    audit hook, which vetoes the operation."""


def _record_trip(event, detail):
    _TRIP_RECORDS.append((len(_TRIP_RECORDS), event, detail))
    return len(_TRIP_RECORDS)


def _hook(event, args):
    # External tripwire: observes beneath the client layer. Inactive
    # outside regions (depth 0). Denies network egress, shell/system/
    # exec escapes, dynamic code is NOT denied here (CPython raises
    # exec/compile events constantly for lazy imports -- census:
    # 48 imports + 32 execs from plain hashlib/json/decimal use --
    # so runtime exec-denial would false-trip; direct exec/eval/
    # compile identifiers are banned transitively by the static
    # layer instead). Popen is allowed and RECORDED (jail, checker
    # and frozen-read launches are the experiment; budgets grade
    # counts at runtime); shell-shaped Popen is denied.
    if _REGION_DEPTH <= 0:
        return
    if event == "socket.getaddrinfo":
        _record_trip(event, "dns")
        raise TripwireError(event)
    if event == "socket.connect":
        try:
            _family = args[0].family
        except (AttributeError, IndexError):
            _family = None
        if _family != _AF_UNIX:
            _record_trip(event, "non-unix-egress")
            raise TripwireError(event)
        return
    if event == "os.system":
        _record_trip(event, "shell")
        raise TripwireError(event)
    if event == "os.exec" or event.startswith("os.exec") or \
            event.startswith("os.spawn") or event in ("os.fork",
                                                      "os.forkpty"):
        _record_trip(event, "process-replacement")
        raise TripwireError(event)
    if event == "subprocess.Popen":
        try:
            _exe = args[0]
            _argv = list(args[1]) if isinstance(args[1], list) else []
            _cwd = args[2] if len(args) > 2 else None
        except (IndexError, TypeError):
            _exe, _argv, _cwd = None, [], None
        _base = _exe.rsplit("/", 1)[-1] if isinstance(_exe, str) \
            else ""
        if _base in _SHELL_BASENAMES:
            _record_trip(event, "shell")
            raise TripwireError(event)
        if _JOURNAL_OPEN:
            _PROCESS_LOG.append((len(_PROCESS_LOG), _CURRENT_LEG, _exe,
                                 _argv, _cwd))
        return
    if event == "import":
        _mod = args[0] if args else ""
        _base = _mod.split(".")[0] if isinstance(_mod, str) else ""
        if _base in _DENY_IMPORTS:
            _record_trip(event, _base)
            raise TripwireError(event)
        return


def install_hook():
    """Install the persistent harness audit hook (idempotent; hooks
    cannot be removed once added, so removal is never attempted --
    the hook is inert at depth 0 and regions nest by counter)."""
    global _HOOK_INSTALLED
    if not _HOOK_INSTALLED:
        sys.addaudithook(_hook)
        _HOOK_INSTALLED = True


def _warm_interpreter():
    # Pre-warm lazy C accelerators BEFORE arming (their first use
    # raises import/exec noise that must not trip the region):
    # every module the frozen leg path touches is imported at
    # harness load; only these accelerators load lazily.
    hashlib.sha256(b"a13-warm").hexdigest()
    __import__("decimal").Decimal("1.1")
    json.dumps({"a13": "warm"})


def region_enter():
    """Enter the isolated region (nestable): install the hook,
    snapshot counters, stamp entry times. Returns the entry depth.
    """
    global _REGION_DEPTH, _REGION_ENTRY_INDEX, _REGION_ENTRY_WALL
    global _REGION_ENTRY_MONO, _CURRENT_LEG, _JOURNAL_OPEN
    global _JOURNAL_START
    _warm_interpreter()
    install_hook()
    if _REGION_DEPTH == 0:
        _REGION_ENTRY_INDEX = len(_TRIP_RECORDS)
        _REGION_ENTRY_WALL = time.time()
        _REGION_ENTRY_MONO = time.monotonic()
        _CURRENT_LEG = None
        _JOURNAL_OPEN = True
        _JOURNAL_START = len(_PROCESS_LOG)
    _REGION_DEPTH += 1
    return _REGION_DEPTH


def region_exit():
    """Leave the isolated region (try/finally paired with enter).
    Stamps the exit times used by the seal chain."""
    global _REGION_DEPTH, _CURRENT_LEG
    global _REGION_EXIT_MONO, _REGION_EXIT_WALL
    if _REGION_DEPTH > 0:
        _REGION_DEPTH -= 1
    if _REGION_DEPTH == 0:
        _CURRENT_LEG = None
        _REGION_EXIT_MONO = time.monotonic()
        _REGION_EXIT_WALL = time.time()
    return _REGION_DEPTH


def region_exit_times():
    """Monotonic/wall exit stamp (set when the outermost region
    closes); None before the first close."""
    global _REGION_EXIT_MONO, _REGION_EXIT_WALL
    return _REGION_EXIT_MONO, _REGION_EXIT_WALL


def region_active():
    return _REGION_DEPTH > 0


def mark_leg(leg):
    """Tag subsequent hook-observed launches with a leg name (or
    None outside legs) for journal attribution."""
    global _CURRENT_LEG
    _CURRENT_LEG = leg


def note_provider_call():
    """Record one issued provider call (called by the runner at its
    single provider-invocation site). Returns the new total."""
    global _PROVIDER_CALLS
    _PROVIDER_CALLS += 1
    return _PROVIDER_CALLS


def note_cell_completed():
    """Record one completed ORDER cell (called by the runner when a
    cell completes and chains). Returns the new total."""
    global _ORDER_CELLS
    _ORDER_CELLS += 1
    return _ORDER_CELLS


def sample():
    """Harness-observed (provider_total, order_total) snapshot."""
    return (_PROVIDER_CALLS, _ORDER_CELLS)


def trip_slice():
    """(count, first_event_or_None) of tripwire records since the
    outermost region entry. On any completed receipt this is
    (0, None): a trip raises, so no receipt is ever written after
    one -- the record states the tripwire was armed and silent."""
    own = _TRIP_RECORDS[_REGION_ENTRY_INDEX:]
    if not own:
        return 0, None
    return len(own), own[0][1]


def process_log():
    """Hook-observed launch records [(seq, leg, executable, argv,
    cwd)] since process start (leg-tagged at mark time)."""
    return [list(e) for e in _PROCESS_LOG]


def region_process_log():
    """Hook-observed launches since the outermost region entry
    (the region's own process evidence slice)."""
    return [list(e) for e in _PROCESS_LOG[_JOURNAL_START:]]


def close_journal():
    """Stop journal intake ahead of sealing (the tripwire stays
    armed through region close -- separate mechanism, separate
    lifetime). After this, hook-observed launches are no longer
    recorded; sealing then hashes a fixed observation set. Returns
    (stop_monotonic, exit_moment_note)."""
    global _JOURNAL_OPEN, _JOURNAL_STOP_MONO, _JOURNAL_CLOSED_MONO
    _JOURNAL_OPEN = False
    _JOURNAL_STOP_MONO = time.monotonic()
    _JOURNAL_CLOSED_MONO = _JOURNAL_STOP_MONO
    return _JOURNAL_STOP_MONO, _JOURNAL_CLOSED_MONO


def jail_backend_name():
    """Honest label for the bound jail backend (pinning aid for
    launch records): docker-cli default or the test-double name."""
    if _ENGINE_JAIL_BUILDER is None:
        return "docker-cli (DockerSandbox, pinned image)"
    name = getattr(_ENGINE_JAIL_BUILDER, "__name__",
                   type(_ENGINE_JAIL_BUILDER).__name__)
    return f"{name} (test double)"


def set_engine_jail_builder(builder):
    """Bind the harness-owned jail builder for the A13 legs (or
    None for the production default). Harness setup only -- never
    called from inside the isolated region."""
    global _ENGINE_JAIL_BUILDER
    _ENGINE_JAIL_BUILDER = builder


def build_engine_jail(work, visible):
    """Build the OFF-leg engine jail through the harness-owned
    builder (fixed accessor name: non-injectable route)."""
    return (_ENGINE_JAIL_BUILDER or DockerSandbox)(work, visible)


def collect_docker_events(since_wall, until_wall=None, limit=1000):
    """Best-effort daemon-side container lifecycle history (host
    side, unprivileged): create/start/die/destroy/exec/oom/kill
    with 64-hex actor ids, images, exit codes and daemon
    timestamps. Honest about limits: no pids/tgids (those need a
    privileged tracer -- recorded absent, never invented), daemon
    clock (wall), bounded lines with explicit truncation.
    Returns {"mechanism", "observed", "reason", "window",
    "events", "truncated", "unparsable"}. Never raises on daemon
    trouble (records it)."""
    until_wall = float(until_wall) if until_wall is not None \
        else time.time()
    base = {"mechanism": "docker-events --since/--until (daemon "
                         "history, host side, unprivileged)",
            "observed": False, "reason": None,
            "window": {"since": since_wall, "until": until_wall},
            "events": [], "truncated": False, "unparsable": 0}
    try:
        p = subprocess.run(
            ["docker", "events", "--since", str(int(since_wall)),
             "--until", str(int(until_wall) + 1),
             "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=60)
    except (OSError, ValueError) as e:
        base["reason"] = f"daemon query failed: {type(e).__name__}"
        return base
    if p.returncode != 0:
        base["reason"] = "daemon query refused rc=%s: %s" % (
            p.returncode, (p.stderr or "")[:120])
        return base
    kept = []
    for line in (p.stdout or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            kept.append(json.loads(line))
        except ValueError:
            base["unparsable"] += 1
    if len(kept) > limit:
        base["truncated"] = True
        kept = kept[:limit]
    base["events"] = kept
    base["observed"] = True
    return base


def cgroup_quiescent(container_id):
    """Verify cgroup quiescence for a docker container id (systemd
    driver layout, unprivileged reads): path absent means removed
    (quiescent by removal); present requires an empty cgroup.procs.
    Returns (quiescent_bool_or_None, detail). None only when the
    layout is unreadable (honest absence, never asserted)."""
    if not isinstance(container_id, str) or len(container_id) != 64:
        return None, "no 64-hex container id to check"
    path = cgroup_path_for(container_id)
    try:
        if not os.path.exists(path):
            return True, "cgroup removed (quiescent by removal)"
        with open(os.path.join(path, "cgroup.procs")) as f:
            members = [ln.strip() for ln in f if ln.strip()]
    except OSError as e:
        return None, f"cgroup unreadable: {type(e).__name__}"
    if not members:
        return True, "cgroup empty"
    return False, f"cgroup has live tasks: {members[:4]}"


def cgroup_path_for(container_id):
    """The systemd-driver cgroup path CLAIM for a container id (a
    deterministic derivation, not a measurement: quiescence reads
    through cgroup_quiescent confirm or deny it)."""
    return "/sys/fs/cgroup/system.slice/docker-%s.scope" % container_id


def docker_entry_pid(container_id):
    """Runtime-reported entry pid for a container id (auditor
    Ruling 1 per-role identity: every launch binds the runtime's
    own entry-pid report plus the binding that produced it).

    Best-effort host-side read (`docker inspect State.Pid` over
    the daemon socket -- no new capability: the harness already
    shells docker for events). Returns (pid_or_None, source).
    pid is None with an honest source note when the container is
    already gone (--rm removes it at exit, so a post-exit inspect
    cannot report): missing, never invented. The independent
    probe fails an unbound entry pid rather than inferring one."""
    if not isinstance(container_id, str) or len(container_id) != 64:
        return None, "no 64-hex container id to inspect"
    try:
        p = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Pid}}", container_id],
            capture_output=True, text=True, timeout=60)
    except (OSError, ValueError) as e:
        return None, (f"docker inspect unavailable "
                      f"({type(e).__name__})")
    if p.returncode != 0:
        return None, ("docker inspect refused (container gone: "
                      "unprivileged post-exit read unavailable)")
    try:
        pid = int((p.stdout or "").strip())
    except ValueError:
        return None, "docker inspect unparseable pid"
    if pid <= 0:
        return None, ("docker inspect reports non-running "
                      "container (pid 0)")
    return pid, "docker inspect State.Pid (PID 1 in the jail)"


def _sha_hex(data):
    import hashlib as _hl
    return _hl.sha256(data).hexdigest()


def canonical_json(obj):
    return json.dumps(obj, sort_keys=True, indent=1) + "\n"


def seal_journal(entries, launch_records, observer_record,
                 daemon_events, quiescence, jail_launches=None):
    """Seal the harness-side process journal (canonical bytes +
    sha). Entries are host/daemon-observed launches (argv-level);
    kernel pid/tgid pairs are NOT fabricated when unavailable --
    the journal states its own coverage honestly and the frozen
    budget grades counts, not identities, from it. jail_launches
    (the per-leg role-tagged container-launch evidence) is sealed
    alongside the launch records so the budget the probe grades
    is the sealed bytes, never a post-seal rewrite. Returns
    (journal_dict_with_sha, journal_bytes)."""
    journal = {
        "journal_schema": "a13-process-journal-v1",
        "observer": observer_record,
        "launch_records": launch_records,
        "jail_launches": jail_launches,
        "host_process_log": entries,
        "daemon_container_events": daemon_events,
        "quiescence": quiescence,
    }
    body = canonical_json(journal).encode()
    journal["journal_sha256"] = _sha_hex(body)
    return journal, canonical_json(journal).encode()
