"""D3 provider-boundary reuse: run the REAL D2 gate+mock and COUNT it.

This module exists to remove a fail-open defect.  Before it, three D3 conjuncts
were computed as `all(count["records"] == 0 ...)` over ledger files that NOTHING
ever wrote.  "The apparatus is absent" and "no provider opportunity occurred"
therefore produced the SAME true value, and the conjunct could never go false.

The fix is not a better assertion; it is to make the apparatus PRESENT and
MEASURED.  The D2 gate+mock fixtures are reused verbatim (env-driven entry
points, imported by path -- not re-implemented, because a third counting
mechanism is forbidden).  Sequence per arm:

  1. start mock boundary + provider gate (real D2 fixtures)
  2. make the cell's ONE authorized opportunity        -> ledgers read 1/1/1
  3. SNAPSHOT the counts                                -> "before"
  4. (legs run; harness owns this window)
  5. SNAPSHOT again                                     -> "after"

D1_PROVIDER_OPPORTUNITY_DELTA_ZERO then means exactly:

    after == before == 1/1/1   AND   the before snapshot was non-vacuous

Both halves are required.  `counts_present_and_nonzero` is what stops an empty
ledger from satisfying the conjunct, and `delta_zero` alone is no longer
sufficient.  A falsifier arm injects a real extra attempt to prove the conjunct
can go false.
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

BOUNDARY_VERSION = "D3_PROVIDER_BOUNDARY_REUSE_v1.0"

APPARATUS = Path(__file__).resolve().parent
GATE_FIXTURE = APPARATUS / "a12d2_d2_provider_gate.py"
MOCK_FIXTURE = APPARATUS / "a12d2_d2_mock_boundary.py"

LEDGER_NAMES = ("attempts", "dispatches", "receives")

# The binary the model cell spawns.  It must be a LEG, never the cell itself:
# pointing a cell's spawn target at its own binary makes it re-exec without
# bound.  Resolved as a SIBLING of the cell binary, because both are produced by
# the same build, so the cell can never be pointed at itself by path drift.
#
# It is one of D2's three leg identities -- `d3-leg-on` -- NOT a D3-only name.
# The earlier value, "d3-leg-clean", belonged to the pre-three-leg build, where
# a single per-arm leg binary existed under that name.  When the arms moved to
# D2's three shared identities the name stopped being produced, the cell's spawn
# target went missing, the cell never ran, and the measured count fell to 0 --
# so TOTAL_MODEL_CELL_COUNT_UNCHANGED failed for every arm.  The value now names
# a binary the build actually produces, and `run_model_cell` still verifies the
# target exists rather than assuming it.
CELL_LEG_TARGET_NAME = "d3-leg-on"

LEDGER_FILES = {
    "attempts": "gate-attempts.jsonl",
    "dispatches": "gate-dispatches.jsonl",
    "receives": "mock-receives.jsonl",
}

# The cell's single authorized opportunity, exactly as D2-A records it.
EXPECTED_BEFORE = {"attempts": 1, "dispatches": 1, "receives": 1}
EXPECTED_AFTER = {"attempts": 1, "dispatches": 1, "receives": 1}


def _replace(path, text):
    """Write via unlink-then-write so read-only artifacts can be replaced."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass
        os.replace(tmp, path)


def atomic_write_json(path, payload):
    _replace(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sha256_of(path):
    """Hash a real artifact. Returns '' when the file is absent, so a caller can
    distinguish 'absent' from 'hashed' rather than hashing an empty read."""
    path = Path(path)
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_ledger_records(path):
    """Count NON-EMPTY JSONL records. Reports existence separately from count,
    because 'the file is missing' must never read as 'zero opportunities'."""
    path = Path(path)
    info = {"path": str(path), "exists": path.exists(),
            "bytes": 0, "records": 0, "unparsable": 0}
    if not path.exists():
        return info
    raw = path.read_bytes()
    info["bytes"] = len(raw)
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
            info["records"] += 1
        except ValueError:
            info["unparsable"] += 1
    return info


def snapshot_counts(arm_dir):
    arm_dir = Path(arm_dir)
    snap = {name: count_ledger_records(arm_dir / LEDGER_FILES[name])
            for name in LEDGER_NAMES}
    digest = hashlib.sha256()
    for name in LEDGER_NAMES:
        info = snap[name]
        digest.update(("%s|%d|%d\n" % (name, info["records"],
                                       info["bytes"])).encode())
    snap["_sha256"] = digest.hexdigest()
    snap["_wall"] = time.time()
    return snap


def _start(fixture, env):
    return subprocess.Popen([sys.executable, str(fixture)],
                            env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True,
                            start_new_session=True)


def _await_path(path, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if Path(path).exists():
            return True
        time.sleep(0.02)
    return False


def make_authorized_opportunity(gate_socket, cell_id, payload,
                                timeout=15.0):
    """The cell's ONE authorized provider opportunity, made BEFORE the legs.

    This is the real boundary: an AF_UNIX request into the D2 gate, which
    records an attempt, dispatches to the mock, and returns response bytes.
    """
    request = json.dumps({"kind": "provider_request", "cell_id": cell_id,
                          "attempt_id": "cell-attempt-1",
                          "request_id": "cell-request-1",
                          "payload": payload}, sort_keys=True).encode() + b"\n"
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(gate_socket)
    client.sendall(request)
    chunks = []
    while True:
        try:
            chunk = client.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        chunks.append(chunk)
    client.close()
    response = b"".join(chunks)
    return {"request_bytes": len(request),
            "request_bytes_sha256": hashlib.sha256(request).hexdigest(),
            "response_bytes": len(response),
            "response_sha256": hashlib.sha256(response).hexdigest(),
            "response_head": response[:120].decode("utf-8", "replace")}


class ProviderBoundary:
    """Owns the real D2 gate+mock for ONE arm, for the arm's whole lifetime."""

    def __init__(self, arm_dir, cell_id, inject_extra_attempt=False):
        self.arm_dir = Path(arm_dir)
        self.cell_id = cell_id
        self.inject_extra_attempt = inject_extra_attempt
        self.gate = None
        self.mock = None
        # Fixture pids killed by the identity sweep rather than by the
        # normal stop path; published so a leak is visible, not silent.
        self.reaped_pids = []
        self.adopted = []
        self.env = {}
        self.paths = {}

    def start(self):
        d = self.arm_dir
        d.mkdir(parents=True, exist_ok=True)
        self.paths = {
            "gate_socket": str(d / "provider-gate.sock"),
            "mock_socket": str(d / "mock-boundary.sock"),
            "gate_ready": str(d / "gate-ready.json"),
            "gate_stop": str(d / "gate-stop"),
            "gate_policy": str(d / "gate-policy.json"),
            "policy": str(d / "d1-ledger-policy.json"),
            "mock_ready": str(d / "mock-ready.json"),
            "mock_stop": str(d / "mock-stop"),
            "response_decision": str(d / "response-decision.json"),
        }
        for name in LEDGER_NAMES:
            (d / LEDGER_FILES[name]).write_text("", encoding="utf-8")

        policy = {
            "authorized_attempt_limit": 1,
            "allow_dispatch": True,
            "provider_endpoint_identity": "d3-provider-endpoint",
        }
        atomic_write_json(self.paths["policy"], policy)

        gate_policy = {
            "gate_policy_sha256": hashlib.sha256(
                json.dumps(policy, sort_keys=True).encode()).hexdigest(),
            "authorized_attempt_limit": 1,
            "allow_dispatch": True,
            "provider_endpoint_identity": "d3-provider-endpoint",
        }
        atomic_write_json(self.paths["gate_policy"], gate_policy)

        base = dict(os.environ)
        base.update({
            "D2_ARM_DIR": str(d),
            "D2_GATE_SOCKET": self.paths["gate_socket"],
            "D2_MOCK_SOCKET": self.paths["mock_socket"],
            "D2_ATTEMPTS": str(d / LEDGER_FILES["attempts"]),
            "D2_DISPATCHES": str(d / LEDGER_FILES["dispatches"]),
            "D2_RECEIVES": str(d / LEDGER_FILES["receives"]),
            "D2_POLICY": self.paths["policy"],
            "D2_GATE_POLICY": self.paths["gate_policy"],
            "D2_GATE_READY": self.paths["gate_ready"],
            "D2_GATE_STOP": self.paths["gate_stop"],
            "D2_GATE_IDENTITY": "d3-provider-gate",
            "D2_MOCK_IDENTITY": "d3-provider-mock",
            "D2_MOCK_RECEIVES": str(d / LEDGER_FILES["receives"]),
            "D2_MOCK_READY": self.paths["mock_ready"],
            "D2_MOCK_STOP": self.paths["mock_stop"],
            "D2_RESPONSE_DECISION": self.paths["response_decision"],
        })
        self.env = base

        for stale in (self.paths["gate_stop"], self.paths["mock_stop"]):
            try:
                os.unlink(stale)
            except OSError:
                pass

        self.mock = _start(MOCK_FIXTURE, base)
        if not _await_path(self.paths["mock_socket"], timeout=20.0):
            raise RuntimeError("mock boundary did not bind %s"
                               % self.paths["mock_socket"])
        self.gate = _start(GATE_FIXTURE, base)
        if not _await_path(self.paths["gate_ready"], timeout=20.0):
            raise RuntimeError("provider gate did not become ready")
        return self

    def cell_opportunity(self):
        """The single authorized opportunity the cell is entitled to.

        This must happen BEFORE the before-snapshot, so the snapshot shows a
        POPULATED boundary (1/1/1).  A delta measured against an empty boundary
        would be the original fail-open.
        """
        return make_authorized_opportunity(
            self.paths["gate_socket"], self.cell_id,
            "d3-cell-authorized-payload")

    def inject_extra_opportunity(self):
        """The falsifier's hook: a REAL second opportunity, injected AFTER the
        before-snapshot and DURING the leg window.

        Ordering is the whole point.  If the extra attempt landed before the
        before-snapshot it would be absorbed into `before`, the delta would still
        read zero, and the conjunct would only flip because `after` deviated from
        the expected 1/1/1 -- proving nothing about the delta being a live
        measurement.  Injected here, `before` is untouched and `after` grows, so
        the DELTA ITSELF is what moves.
        """
        result = make_authorized_opportunity(
            self.paths["gate_socket"], self.cell_id,
            "d3-falsifier-injected-extra-attempt")
        result["injection_point"] = "during_leg_window_after_before_snapshot"
        return result

    def stop(self):
        for sock in self.adopted:
            try:
                sock.close()
            except OSError:
                pass
        self.adopted = []
        try:
            Path(self.paths["gate_stop"]).write_text("stop\n", encoding="utf-8")
        except OSError:
            pass
        for proc in (self.gate, self.mock):
            if proc is None:
                continue
            try:
                proc.wait(timeout=10)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
        # The Popen handles are not sufficient.  If the harness dies abruptly the
        # fixtures are reparented to the user systemd manager and keep their
        # sockets bound forever; a later run then finds its endpoint path already
        # listening (measured: two fixtures survived a crashed battery and wedged
        # every subsequent run with EADDRINUSE).  So sweep by IDENTITY -- the
        # fixture script plus this arm's own directory -- never by the stale
        # handle, and kill only exact matches.
        self._reap_by_identity()

    def adopt_socket(self, sock):
        """Take ownership of an extra listener so stop() closes it too.

        An arm that needs a second endpoint (D3-E's broker peer) would otherwise
        depend on the arm body reaching its own cleanup line; if the body raised,
        the listener would survive -- and a surviving listener is exactly what
        wedges the next run with EADDRINUSE.
        """
        if sock is not None:
            self.adopted.append(sock)

    def _reap_by_identity(self):
        """Kill any fixture process still rooted in THIS arm's directory."""
        arm_dir = str(self.arm_dir)
        for fixture in (GATE_FIXTURE.name, MOCK_FIXTURE.name):
            for pid in _pids_matching(fixture, arm_dir):
                try:
                    os.kill(pid, signal.SIGKILL)
                    self.reaped_pids.append(pid)
                except OSError:
                    pass
        if self.reaped_pids:
            # Record it: a reap means the normal stop path did not work, and a
            # silent reap would hide that the arm leaked a fixture.
            try:
                atomic_write_json(self.arm_dir / "fixture-reap.json", {
                    "reaped_pids": self.reaped_pids,
                    "reason": "fixture survived stop(); reparented to systemd",
                    "matched_by": "cmdline fixture script + arm_dir",
                })
            except OSError:
                pass


def _pids_matching(script_name, arm_dir_fragment):
    """Pids whose cmdline names `script_name` and contains `arm_dir_fragment`.

    Two independent conditions, so an unrelated fixture belonging to a different
    arm can never be swept up by this one.
    """
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as handle:
                cmdline = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        if script_name in cmdline and arm_dir_fragment in cmdline:
            found.append(int(entry))
    return found


def measured_delta(before, after):
    """The ONLY honest derivation of the delta conjunct.

    `delta_zero` alone is a fail-open: an absent apparatus yields 1/1/1 -> 0/0/0
    and would read as 'zero extra opportunity' while proving nothing. So the
    conjunct additionally requires that the boundary was REAL and POPULATED.
    """
    absent = [n for n in LEDGER_NAMES if not before[n]["exists"]
              or before[n]["bytes"] == 0]
    populated = {n: before[n]["records"] for n in LEDGER_NAMES}
    nonvacuous = (not absent) and populated == EXPECTED_BEFORE

    delta = {n: after[n]["records"] - before[n]["records"] for n in LEDGER_NAMES}
    delta_zero = all(v == 0 for v in delta.values())
    after_matches = {n: after[n]["records"] for n in LEDGER_NAMES} == EXPECTED_AFTER

    offenders = []
    for name in LEDGER_NAMES:
        if delta[name] > 0:
            offenders.append({"ledger": name, "delta": delta[name],
                              "before": before[name]["records"],
                              "after": after[name]["records"]})

    return {
        "before": {n: before[n]["records"] for n in LEDGER_NAMES},
        "after": {n: after[n]["records"] for n in LEDGER_NAMES},
        "delta": delta,
        "expected_before": dict(EXPECTED_BEFORE),
        "expected_after": dict(EXPECTED_AFTER),
        "before_snapshot_sha256": before["_sha256"],
        "after_snapshot_sha256": after["_sha256"],
        "ledgers_absent_or_empty_before": absent,
        "boundary_populated_before": nonvacuous,
        "delta_zero": delta_zero,
        "after_matches_expected": after_matches,
        "offending_records": offenders,
        "conjunct_value": bool(delta_zero and nonvacuous and after_matches),
        "derivation": ("after == before == 1/1/1 AND the before snapshot was "
                       "non-vacuous (real D2 fixture wrote real records)"),
        "vacuous_if_true_without_boundary_populated_before": True,
    }


def publish_offenders(arm_dir, snapshot_before, delta, extra_attempt=None):
    """A falsified delta must publish the offending record, not just a boolean."""
    arm_dir = Path(arm_dir)
    rows = []
    for name in LEDGER_NAMES:
        info = count_ledger_records(arm_dir / LEDGER_FILES[name])
        if info["records"] > snapshot_before[name]["records"]:
            raw = (arm_dir / LEDGER_FILES[name]).read_text(
                encoding="utf-8", errors="replace").splitlines()
            for line in raw[snapshot_before[name]["records"]:]:
                line = line.strip()
                if line:
                    try:
                        rows.append({"ledger": name, "record": json.loads(line)})
                    except ValueError:
                        rows.append({"ledger": name, "raw": line[:400]})
    doc = {"offending_records": rows, "delta": delta["delta"],
           "conjunct_value": delta["conjunct_value"]}
    if extra_attempt is not None:
        doc["injected_extra_attempt"] = extra_attempt
    atomic_write_json(arm_dir / "delta-offenders.json", doc)
    return doc


def run_model_cell(arm_dir, cell_id, leg_bin, timeout=60):
    """C: RUN the model cell and count the report it actually produced.

    Counting files by name would let "the apparatus is absent" produce the same
    value as "the cell ran and produced one report".  So the cell is executed and
    its report is read back: the count is of a real, parsed artifact.

    `leg_bin` must be the MODEL CELL binary itself, and D3_LEG_BIN must point at
    a LEG binary -- pointing the cell's spawn target at the cell binary makes it
    re-exec itself without bound.  That is checked against the spawn target, not
    assumed.
    """
    arm_dir = Path(arm_dir)
    report_path = arm_dir / "model-cell.report.json"
    marker = arm_dir / "model-cell.markers.txt"
    cell_bin = Path(leg_bin)
    leg_target = cell_bin.parent / CELL_LEG_TARGET_NAME
    env = dict(os.environ)
    env.update({
        "D3_MARKER_FILE": str(marker),
        "D3_ARM_DIR": str(arm_dir),
        "D3_LEG_ROLE": "model-cell",
        # The cell re-enters this same single TU to spawn its leg, so it needs
        # the label the spawn helper reads and the binary to exec.
        "D3_LEG_ROLE_LABEL": "clean",
        "D3_LEG_BIN": str(leg_target),
        "D3_CELL_ID": cell_id,
        "D3_CELL_REPORT": str(report_path),
        # The cell's leg has no tracer to release it from the arm's entry
        # barrier, so it is told to skip it.  Only the CELL sets this, and only
        # on its own child; the arm's measured legs always take the barrier.
        "D3_CELL_CHILD_NO_BARRIER": "1",
        "D3_MODEL_CELL_COUNT_AUTHORITY": "D2: MODEL_CELL_COUNT = 1",
    })
    result = {"ran": False, "returncode": None, "report_present": False,
              "report": None, "error": None, "cell_bin": str(cell_bin),
              "spawn_target": str(leg_target)}
    if not cell_bin.exists():
        result["error"] = "model cell binary absent: %s" % cell_bin
        return result
    if not leg_target.exists():
        result["error"] = "cell spawn target absent: %s" % leg_target
        return result
    # Refuse the self-exec configuration outright.  A silent unbounded re-exec
    # produced 14KB of markers and rc=255 before this guard existed; a corrupted
    # cell artifact must fail loudly, never be recorded as a cell that ran.
    #
    # This must be an INODE-IDENTITY test, not a path-text comparison.
    # `resolve()` only canonicalizes path TEXT, so two names for the same file
    # (e.g. a hardlink `d3-leg-clean -> d3-model-cell`) stay two different
    # strings and the guard stays silent.  Measured: that exact configuration
    # bypassed this guard and re-exec'd 30,228 times in 18.5s.  `samefile()`
    # compares st_dev/st_ino and catches it.  Both paths are known to exist
    # above, but samefile() is still guarded: a race that removes one must
    # fail closed, not raise.
    try:
        self_exec = os.path.samefile(cell_bin, leg_target)
    except OSError as exc:
        result["error"] = ("cannot establish spawn-target identity (%s: %s); "
                           "refusing to launch a cell whose spawn target cannot "
                           "be proven distinct from itself" % (type(exc).__name__, exc))
        result["self_exec_refused"] = True
        return result
    if self_exec:
        result["error"] = ("D3_LEG_BIN is the same file (same st_dev/st_ino) as the "
                           "model cell binary; this would re-exec the cell without "
                           "bound")
        result["self_exec_refused"] = True
        return result
    try:
        proc = subprocess.run([str(leg_bin)], cwd=str(arm_dir), env=env,
                              capture_output=True, text=True, timeout=timeout)
        result["ran"] = True
        result["returncode"] = proc.returncode
        result["stderr_tail"] = (proc.stderr or "")[-400:]
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        return result

    if report_path.exists():
        try:
            result["report"] = json.loads(report_path.read_text(encoding="utf-8"))
            result["report_present"] = True
            result["report_sha256"] = sha256_of(report_path)
        except (ValueError, OSError) as exc:
            result["error"] = "unreadable report: %s" % exc
    return result


def cell_artifacts(arm_dir, cwd=None):
    """C: count REAL cell artifacts. Model-cell report and ORDER-cell artifacts
    are counted as FILES ON DISK, never inferred from ledger emptiness."""
    roots = [Path(arm_dir)]
    if cwd:
        roots.append(Path(cwd))
    model_cells, order_cells = [], []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if name.endswith(".sock") or name.endswith(".tmp"):
                continue
            if "model-cell" in name or "model_cell" in name:
                model_cells.append(str(path))
            if "order-cell" in name or "order_cell" in name:
                order_cells.append(str(path))
    return {
        "model_cell_artifacts": sorted(set(model_cells)),
        "order_cell_artifacts": sorted(set(order_cells)),
        # Filesystem enumeration is the CROSS-CHECK, not the measurement: the
        # measured count comes from executed cell reports.  Both are published so
        # a discrepancy between them is visible rather than silently resolved.
        "model_cell_count": len(set(model_cells)),
        "order_cell_count": len(set(order_cells)),
        "counted_by": "filesystem enumeration of real cell artifacts",
    }
