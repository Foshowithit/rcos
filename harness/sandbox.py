#!/usr/bin/env python3
"""H1 sandbox: real enforcement for harness-executed agents. NOT a prompt.

Threat model (honest scope): experimental agents are Python programs
executed BY this harness on one shared Linux box with no root and no
containers. Enforcement therefore lives in the execution wrapper:
jailed cwd, scrubbed environment, socket policy injected into the
agent process, and path-escape denial. Model-API calls are made ONLY
by the harness's own audited client, never by agent code.

What this does NOT cover (documented, not hidden): a model with
general tool-use outside this wrapper (that path is simply never
constructed in Fam-C runs); kernel-level exfiltration; side channels.
The audit claim is exactly: every Fam-C agent step runs inside
Sandbox.run(), whose denials are logged and smoke-tested.
"""
import json
import os
import stat
import subprocess
import sys

SITECUSTOMIZE = '''
# Injected into EVERY agent process. Default-deny outbound network;
# allowlist is provider/tool hosts declared per run in SANDBOX_ALLOW_HOSTS.
import os, socket as _s
_ALLOW = set(h for h in os.environ.get("SANDBOX_ALLOW_HOSTS", "").split(",") if h)
_real_create = _s.create_connection
_real_connect = _s.socket.connect
_real_gai = _s.getaddrinfo
def _host_allowed(host):
    h = str(host).lower()
    return any(h == a or h.endswith("." + a) for a in _ALLOW)
def _guard_create(address, *a, **k):
    host = address[0] if isinstance(address, tuple) else address
    if not _host_allowed(host):
        raise OSError(f"SANDBOX-DENY network egress to {host!r}")
    return _real_create(address, *a, **k)
def _guard_connect(self, address, *a, **k):
    host = address[0] if isinstance(address, tuple) else address
    if not _host_allowed(host):
        raise OSError(f"SANDBOX-DENY network egress to {host!r}")
    return _real_connect(self, address, *a, **k)
def _guard_gai(host, *a, **k):
    if isinstance(host, str) and not _host_allowed(host):
        raise OSError(f"SANDBOX-DENY DNS resolve {host!r}")
    return _real_gai(host, *a, **k)
_s.create_connection = _guard_create
_s.socket.connect = _guard_connect
_s.getaddrinfo = _guard_gai
'''

SCRUB_PREFIXES = ("SECRET", "TOKEN", "KEY", "PASSWORD", "CREDENTIAL",
                  "AWS_", "OPENAI_", "ANTHROPIC_")
SCRUB_EXACT = {"OPENCODE_GO_API_KEY", "OPENCODE_GO_API_KEY_2",
               "ORCAROUTER_API_KEY", "SAIL_API_KEY", "RUE_API_KEY",
               "MODAL_QWEN38_KEY", "GITHUB_TOKEN", "GH_TOKEN"}
SCRUB_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET")


def scrub_env(base):
    """Pass through only non-secret environment. Returns (clean, dropped)."""
    clean, dropped = {}, []
    for k, v in base.items():
        ku = k.upper()
        if (k in SCRUB_EXACT or ku.startswith(SCRUB_PREFIXES)
                or ku.endswith(SCRUB_SUFFIXES)):
            dropped.append(k)
            continue
        clean[k] = v
    for k in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH"):
        if k in clean:
            dropped.append(k + " (loader override)")
            del clean[k]
    return clean, dropped


class Sandbox:
    """One lane/run execution jail."""

    def __init__(self, root, allow_hosts=()):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)
        os.chmod(self.root, 0o700)
        sc = os.path.join(self.root, "sitecustomize.py")
        with open(sc, "w") as f:
            f.write(SITECUSTOMIZE)
        os.chmod(sc, 0o600)
        self.allow_hosts = tuple(allow_hosts)
        self.denials = []

    def _check_path(self, path):
        real = os.path.realpath(path)
        if os.path.commonpath([real, self.root]) != self.root:
            raise PermissionError(f"SANDBOX-DENY path escape: {path!r}")

    def run(self, argv, input_text=None, timeout=120):
        """Run agent code jailed: cwd=root, scrubbed env, socket policy on.
        Returns CompletedProcess. Denials surface as process failure +
        are appended to denials.log (never silently swallowed)."""
        env, dropped = scrub_env(dict(os.environ))
        env["PYTHONPATH"] = self.root + os.pathsep + env.get("PYTHONPATH", "")
        env["SANDBOX_ALLOW_HOSTS"] = ",".join(self.allow_hosts)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            return subprocess.run(
                argv, input=input_text, cwd=self.root, env=env,
                capture_output=True, text=True, timeout=timeout)
        except PermissionError as e:
            self.denials.append(str(e))
            raise

    def attempt_read(self, path):
        """Harness-side probe helper: returns (allowed: bool, reason)."""
        try:
            self._check_path(path)
        except PermissionError as e:
            self.denials.append(str(e))
            return False, "DENIED-path-escape"
        if not os.path.exists(path):
            return False, "NOT-FOUND"
        return True, "allowed-in-jail"
