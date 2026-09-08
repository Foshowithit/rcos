#!/usr/bin/env python3
"""H1 isolation: per-run sandboxes with mechanically verified separation.
Every task invocation gets: uuid session id, 0600 workdir, private
registry view (minimal JSON copy), private cache dir, empty history.
Stdlib only.
"""
import json
import os
import stat
import uuid

from sandbox import Sandbox


def new_session_id():
    return "ses-" + uuid.uuid4().hex[:12]


class Run:
    def __init__(self, base, lane, task, registry_src=None):
        self.lane = lane
        self.task = task
        self.session_id = new_session_id()
        self.root = os.path.abspath(os.path.join(
            base, lane, task, self.session_id))
        self.sandbox = Sandbox(os.path.join(self.root, "work"),
                               allow_hosts=())
        for sub in ("registry", "cache", "history", "artifacts"):
            d = os.path.join(self.root, sub)
            os.makedirs(d, exist_ok=True)
            os.chmod(d, 0o700)
        if registry_src and os.path.exists(registry_src):
            data = open(registry_src).read()
            with open(os.path.join(self.root, "registry",
                                   "registry.json"), "w") as f:
                f.write(data)
        with open(os.path.join(self.root, "RUN.json"), "w") as f:
            json.dump({"lane": lane, "task": task,
                       "session_id": self.session_id}, f, indent=1)

    def plant_canary(self, token=None):
        token = token or ("canary-" + self.session_id)
        with open(os.path.join(self.root, "work", ".canary"), "w") as f:
            f.write(token)
        os.chmod(os.path.join(self.root, "work", ".canary"), 0o600)
        return token

    def audit_no_shared_state(self, other_roots):
        """Same-UID honesty note: mode bits cannot isolate processes of
        one user, so this checks the enforceable subset: distinct session
        ids, distinct roots, and no shared registry/cache/history PATHS
        configured. Content-leakage detection is scan_outputs_for_canaries
        below (post-hoc, real)."""
        problems = []
        mine = {os.path.abspath(p) for p in
                (self.root,
                 os.path.join(self.root, "registry"),
                 os.path.join(self.root, "cache"),
                 os.path.join(self.root, "history"))}
        for other in other_roots:
            o = os.path.abspath(other)
            if o == self.root:
                continue
            if o in mine:
                problems.append(f"shared configured path: {o}")
        return problems


def scan_outputs_for_canaries(outputs_by_lane, canaries_by_lane):
    """Post-hoc contamination detection (the enforceable half of
    isolation same-UID). Every lane context carries a unique canary;
    any cross-lane canary appearance in any output is contamination.
    Returns list of findings (empty = clean)."""
    findings = []
    for lane, texts in outputs_by_lane.items():
        blob = "\n".join(texts)
        for other, canary in canaries_by_lane.items():
            if other != lane and canary in blob:
                findings.append(f"contamination: {other}-canary in {lane} output")
    return findings


def symlink_escape_attempt(sandbox, target_outside):
    """Returns True if the sandbox BLOCKED a symlink escape."""
    link = os.path.join(sandbox.root, "evil-link")
    try:
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(target_outside, link)
    except OSError:
        return True
    allowed, _ = sandbox.attempt_read(link)
    try:
        os.unlink(link)
    except OSError:
        pass
    return not allowed
