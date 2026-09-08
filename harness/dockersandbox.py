#!/usr/bin/env python3
"""H1 enforcement v2: kernel-boundary sandboxes via Docker. SUPERSEDES the
sitecustomize monkeypatch approach in sandbox.py (kept for reference only;
it was correctly identified as a Python-library policy, not isolation).

Enforcement actually in force per invocation:
  --network none      kernel netns: no interfaces except DOWN lo.
                      curl/wget/git/node/python/dns ALL fail identically
                      because there is no route, not because binaries
                      are missing.
  mounts              ONLY the lane workdir (rw) + declared visible
                      files (ro). The host tree — including truth,
                      sibling lanes, repos, vault — is not mounted and
                      therefore not addressable at any path.
  --user <invoking-uid> agent code never runs as container root; uid
                      separation across lanes is NOT claimed (same uid) —
                      filesystem isolation comes from the mount
                      restriction (peers simply unmounted), network
                      isolation from the netns.
  --read-only + tmpfs container rootfs immutable except /tmp + /work.
  --cap-drop=ALL, --pids-limit, --memory cap.
  env                 constructed minimal allowlist; host env (and all
                      secrets) never enters the container.
Model-API calls happen ONLY in the harness process (audited client);
agent containers have no network to exfiltrate through anyway.
Stdlib only on the harness side.
"""
import json
import os
import shutil
import subprocess
import uuid

IMAGE = "python:3.12-slim"
WHO = "%d:%d" % (os.getuid(), os.getgid())


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class DockerSandbox:
    """One lane/run kernel jail. `mounts` = list of (host_path, cont_path,
    mode) with mode 'ro' (default) or 'rw' for exactly one workdir."""

    def __init__(self, root, mounts=()):
        self.root = os.path.abspath(root)
        self.name = "rcos-" + uuid.uuid4().hex[:12]
        os.makedirs(self.root, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.mounts = list(mounts)
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
        ]
        for host, cont, mode in self.mounts:
            flag = "rw" if mode == "rw" else "ro"
            self._base += ["-v", f"{host}:{cont}:{flag}"]
        # NOTE: IMAGE is appended by run(), AFTER all -e flags.
        # Docker treats everything after IMAGE as the command.

    def run(self, argv, input_text=None, timeout=120, extra_env=None):
        """Execute inside the jail. Returns CompletedProcess (host side).
        Agent-visible env is constructed, never inherited."""
        env = ["-e", "PYTHONDONTWRITEBYTECODE=1",
               "-e", "PATH=/usr/local/bin:/usr/bin:/bin",
               "-e", f"SANDBOX_NAME={self.name}"]
        for k, v in (extra_env or {}).items():
            if any(s in k.upper() for s in
                   ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")):
                raise ValueError(f"refusing secret env into sandbox: {k}")
            env += ["-e", f"{k}={v}"]
        return _run(self._base + env + [IMAGE] + argv, input=input_text,
                    timeout=timeout)

    def inspect_mounts(self):
        """Harness-side audit: prove ONLY declared binds exist. Returns
        (source, destination) list from a live container view."""
        cid = _run(["docker", "create", "--network", "none"] + [
            x for triple in self.mounts for x in
            ("-v", f"{triple[0]}:{triple[1]}:{'rw' if triple[2] == 'rw' else 'ro'}")
        ] + [IMAGE, "true"], check=True).stdout.strip()
        try:
            data = json.loads(_run(
                ["docker", "inspect", cid], check=True).stdout)[0]
            return [(m["Source"], m["Destination"]) for m in data["Mounts"]]
        finally:
            _run(["docker", "rm", cid])


def unique_session():
    return "ses-" + uuid.uuid4().hex[:12]
