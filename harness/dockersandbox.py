#!/usr/bin/env python3
"""H1 enforcement v3: kernel-boundary sandboxes via Docker. The LAUNCHER
owns the mount policy — callers cannot express an unsafe configuration
because the constructor signature makes it unrepresentable.

Trusted computing base (explicit): host kernel (netns/mount isolation),
Docker daemon + runtime (boundary construction), this launcher module
(policy), and the pinned image digest below. Agent code, model outputs,
and caller-constructed paths are OUTSIDE the TCB.

Enforcement actually in force per invocation:
  --network none      isolated netns: no external interface, no default
                      route, no gateway, no DNS. curl/wget/git/node/python
                      ALL fail identically for lack of route, not lack of
                      binaries. Loopback-listener presence is NOT treated
                      as contamination either way.
  mounts              EXACTLY: assigned_workdir -> /work (rw) +
                      visible_root -> /task (ro). Nothing else, enforced
                      in __init__ (see _check_source).
  image               pinned by digest (reproducibility; tag drift cannot
                      change paired-invocation bytes). Digest recorded in
                      every run manifest.
  --user <invoking-uid>, --read-only, --tmpfs /tmp, --cap-drop=ALL,
  --pids-limit 64, --memory 1g.
  env                 constructed minimal allowlist; host env (and all
                      secrets) never enters the container.
Model-API calls happen ONLY in the harness process (audited client).
Stdlib only on the harness side.
"""
import json
import os
import stat
import subprocess
import time
import uuid

IMAGE = ("python:3.12-slim@sha256:"
         "78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea")
WHO = "%d:%d" % (os.getuid(), os.getgid())

# Host roots the launcher trusts sources under. Workdirs must live
# under WORK_ROOT; visible roots under VISIBLE_ROOT. Anything else is
# refused no matter what the caller passes.
WORK_ROOT = "/tmp/rcos-runs"
VISIBLE_ROOT = "/tmp/rcos-visible"

BANNED_BASENAMES = {"docker.sock", "daemon.json"}
BANNED_PREFIXES = ("/var/run", "/run/docker", "/home/chow/.agent-vault",
                   "/home/chow/.dsh", "/home/chow/.pi", "/home/chow/.ssh",
                   "/home/chow/chow-work/rcos/benchmarks")


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ensure_roots():
    """Fail-closed trusted-namespace bootstrap. Creates WORK_ROOT and
    VISIBLE_ROOT iff absent; asserts root-is-real-dir, not-a-symlink,
    owned-by-harness-uid, and not group/world-writable. Called once per
    harness process before any sandbox exists."""
    uid = os.getuid()
    for root in (WORK_ROOT, VISIBLE_ROOT):
        if os.path.lexists(root) and not os.path.isdir(root):
            raise PermissionError(f"ROOT-DENY not a directory: {root}")
        os.makedirs(root, exist_ok=True)
        if os.path.islink(root):
            raise PermissionError(f"ROOT-DENY symlink root: {root}")
        st = os.stat(root)
        if st.st_uid != uid:
            raise PermissionError(
                f"ROOT-DENY {root} owned by uid {st.st_uid}, want {uid}")
        if st.st_mode & 0o077:
            raise PermissionError(
                f"ROOT-DENY {root} group/world-accessible "
                f"(mode {oct(st.st_mode & 0o777)})")
        os.chmod(root, 0o700)


def _hash_tree(top):
    """Canonical stability manifest: sorted `type|relpath|sha256` lines.
    Directories are represented (type=dir, sha of empty string) so
    structural changes register; file types/metadata beyond
    regular-file-ness are out of scope and documented as such."""
    import hashlib
    out = {}
    if os.path.isfile(top):
        with open(top, "rb") as f:
            return {"file|.": hashlib.sha256(f.read()).hexdigest()}
    for base, dirs, files in os.walk(top):
        for d in sorted(dirs):
            rel = os.path.relpath(os.path.join(base, d), top)
            out["dir|" + rel] = hashlib.sha256(b"").hexdigest()
        for fn in sorted(files):
            p = os.path.join(base, fn)
            rel = os.path.relpath(p, top)
            with open(p, "rb") as f:
                out["file|" + rel] = hashlib.sha256(f.read()).hexdigest()
    return out


def _copy_tree(src, dst):
    """Copy a source tree into a fresh dir (fail closed if dst exists).
    Copying fixes bytes at construction time: later mutations of the
    source cannot reach the staged copy (TOCTOU closure)."""
    import shutil
    os.makedirs(dst, exist_ok=False)
    for base, _dirs, files in os.walk(src):
        for fn in files:
            s = os.path.join(base, fn)
            if not os.path.isfile(s) or os.path.islink(s):
                raise PermissionError(
                    f"STAGE-DENY non-regular staged file: {s}")
            d = os.path.join(dst, os.path.relpath(s, src))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)
    os.chmod(dst, 0o700)


def _check_source(path, kind):
    """Launcher-side mount policy. Raises PermissionError on violation."""
    real = os.path.realpath(path)
    root = WORK_ROOT if kind == "work" else VISIBLE_ROOT
    if os.path.commonpath([real, os.path.abspath(root)]) != os.path.abspath(root):
        raise PermissionError(
            f"MOUNT-POLICY-DENY {kind} source outside {root}: {path!r}")
    base = os.path.basename(real.rstrip("/"))
    if base in BANNED_BASENAMES:
        raise PermissionError(f"MOUNT-POLICY-DENY banned basename: {base}")
    if any(real == p or real.startswith(p.rstrip("/") + "/")
           for p in BANNED_PREFIXES):
        raise PermissionError(f"MOUNT-POLICY-DENY banned prefix: {real}")
    try:
        st = os.stat(real)
    except FileNotFoundError:
        raise PermissionError(f"MOUNT-POLICY-DENY missing source: {path!r}")
    if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
        raise PermissionError(
            f"MOUNT-POLICY-DENY not a regular file/dir: {path!r} "
            f"(no devices, sockets, FIFOs)")
    return real


class DockerSandbox:
    """One lane/run kernel jail. ONLY representable configuration:
    assigned_workdir -> /work (rw) + visible_root -> /task (ro).

    NOTE (abstraction-claim precision): the production constructor
    exposes no arbitrary-mount interface. Module-level helpers remain
    importable Python (no real privacy), but the trust boundary is
    correct: caller code is outside the TCB, this launcher is inside
    it, and experimental agents never execute in the harness process."""

    def __init__(self, assigned_workdir, visible_root):
        ensure_roots()
        work = _check_source(assigned_workdir, "work")
        vis = _check_source(visible_root, "task")
        if work == vis:
            raise PermissionError("MOUNT-POLICY-DENY work == visible")
        # Source-stability binding: the staged copy must equal ONE stable
        # source state. Hash before, copy, hash after; refuse on any drift.
        # Concurrent source mutation becomes fail-closed, never a hybrid.
        #
        # REAL guarantee (exactly this, no more): the mounted tree equals a
        # source state observed identical at two distinct times spanning the
        # copy (the pre-copy source hash, the post-copy source hash, the
        # staged-copy hash against the CURRENT source, and a quiescence
        # confirmation read). Residual limit: a source frozen in a torn
        # state for the entire window is indistinguishable from a stable
        # source; the guard never proves "the source never changed".
        source_before = _hash_tree(vis)
        os.makedirs(work, exist_ok=True)
        os.chmod(work, 0o700)
        # TOCTOU closure: stage a private copy of the visible source NOW
        # (fail-closed fresh dir), hash it, and mount ONLY the copy.
        # Later mutations of the caller's source cannot reach the jail.
        self.name = "rcos-" + uuid.uuid4().hex
        self.staged = os.path.join(WORK_ROOT, ".stage-" + self.name)
        if os.path.isdir(vis):
            _copy_tree(vis, self.staged)
        else:
            os.makedirs(self.staged, exist_ok=False)
            import shutil
            shutil.copy2(vis, os.path.join(
                self.staged, os.path.basename(vis)))
        os.chmod(self.staged, 0o700)
        source_after = _hash_tree(vis)
        if source_after != source_before:
            import shutil as _sh0
            _sh0.rmtree(self.staged, ignore_errors=True)
            raise PermissionError(
                "STABILITY-DENY source mutated during staging; refused")
        self.task_snapshot = _hash_tree(self.staged)
        if self.task_snapshot != source_after:
            import shutil as _sh2
            _sh2.rmtree(self.staged, ignore_errors=True)
            raise PermissionError(
                "STABILITY-DENY staged copy differs from current source; "
                "refused")
        # Quiescence confirmation: the source must still read as the same
        # state after a bounded settle (total sleep <= 50 ms, at most 3
        # attempts). A source that never settles is refused, never mounted.
        _quiescent = False
        for _attempt in range(3):
            time.sleep(0.015)
            if _hash_tree(vis) == source_after:
                _quiescent = True
                break
        if not _quiescent:
            import shutil as _sh3
            _sh3.rmtree(self.staged, ignore_errors=True)
            raise PermissionError(
                "STABILITY-DENY source not quiescent; refused")
        self.mounts = [(work, "/work", "rw"), (self.staged, "/task", "ro")]
        self.work = work
        self.source = vis
        self.image = IMAGE
        self._base = [
            "docker", "run", "--rm", "--name", self.name,
            "--network", "none",
            "--user", WHO,
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--cap-drop=ALL",
            "--pids-limit", "64",
            "--memory", "1g",
            "--workdir", "/work",
            "-v", f"{work}:/work:rw",
            "-v", f"{self.staged}:/task:ro",
        ]
        self._snap_verified = False
        # NOTE: IMAGE is appended by run(), AFTER all -e flags.
        # Docker treats everything after IMAGE as the command.

    def manifest(self):
        return {"sandbox": self.name, "image": self.image,
                "task_snapshot": self.task_snapshot,
                "mounts": [{"host": h, "container": c, "mode": m}
                           for h, c, m in self.mounts]}

    def attempt_read(self, host_path):
        """Jail-visibility oracle (no daemon): would this HOST path be
        readable from inside the jail? Only the staged copy (/task, ro)
        and the workdir (/work, rw) are mounted. The caller's visible
        SOURCE is byte-identical to the staged copy (proved at
        construction: task_snapshot == source hash), so it answers in the
        same /task namespace — that is what makes a planted sealed file
        a detectable finding. Symlinks and `..` traversal resolve via
        realpath first, so escape attempts report DENIED."""
        p = os.path.realpath(host_path)
        for src, mnt in ((self.staged, "/task"), (self.source, "/task"),
                         (self.work, "/work")):
            src_r = os.path.realpath(src)
            if p == src_r or p.startswith(src_r + os.sep):
                rel = os.path.relpath(p, src_r)
                if os.path.exists(p):
                    return True, mnt + ("/" + rel if rel != "." else "")
                return False, f"not found under {mnt}"
        return False, "outside jail mounts"

    def verify_task_snapshot(self):
        """Byte binding: hash /task INSIDE a fresh jail container and
        require equality with the construction-time snapshot. Proves the
        bytes validated are the bytes consumed. Raises on mismatch."""
        code = ("import hashlib,os;"
                "d={}\n"
                "for b,ds,fs in os.walk('/task'):\n"
                " for x in sorted(ds):\n"
                "  d['dir|'+os.path.relpath(os.path.join(b,x),'/task')]=hashlib.sha256(b'').hexdigest()\n"
                " for fn in sorted(fs):\n"
                "  p=os.path.join(b,fn)\n"
                "  d['file|'+os.path.relpath(p,'/task')]=hashlib.sha256(open(p,'rb').read()).hexdigest()\n"
                "import json;print(json.dumps(d,sort_keys=True))")
        p = self._run_raw(["python3", "-c", code])
        if p.returncode != 0:
            raise PermissionError(
                "SNAPSHOT-DENY in-jail hashing failed: "
                + (p.stderr or "")[:200])
        inside = json.loads(p.stdout)
        if inside != self.task_snapshot:
            raise PermissionError(
                "SNAPSHOT-DENY /task bytes differ from construction "
                f"snapshot: {[k for k in set(inside) | set(self.task_snapshot) if inside.get(k) != self.task_snapshot.get(k)][:5]}")
        self._snap_verified = True
        return True

    def _run_raw(self, argv, **kw):
        env = ["-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "PATH=/usr/local/bin:/usr/bin:/bin"]
        return _run(self._base + env + [self.image] + argv, **kw)

    def run(self, argv, input_text=None, timeout=120, extra_env=None):
        """Execute inside the jail. Returns CompletedProcess (host side).
        Agent-visible env is constructed, never inherited. The FIRST
        run() on an instance verifies the /task byte binding before
        executing the requested command (fail closed)."""
        env = ["-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "PATH=/usr/local/bin:/usr/bin:/bin",
               "-e", f"SANDBOX_NAME={self.name}"]
        for k, v in (extra_env or {}).items():
            if any(s in k.upper() for s in
                   ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                raise ValueError(f"refusing secret env into sandbox: {k}")
            env += ["-e", f"{k}={v}"]
        if not self._snap_verified:
            self.verify_task_snapshot()
        return _run(self._base + env + [self.image] + argv,
                    input=input_text, timeout=timeout)

    def inspect_mounts(self):
        """Harness-side audit: prove ONLY the two declared binds exist."""
        cid = _run(["docker", "create", "--network", "none",
                    "-v", f"{self.mounts[0][0]}:/work:rw",
                    "-v", f"{self.mounts[1][0]}:/task:ro",
                    self.image, "true"], check=True).stdout.strip()
        try:
            data = json.loads(_run(
                ["docker", "inspect", cid], check=True).stdout)[0]
            return [(m["Source"], m["Destination"]) for m in data["Mounts"]]
        finally:
            _run(["docker", "rm", cid])


def unique_session():
    return "ses-" + uuid.uuid4().hex[:12]
