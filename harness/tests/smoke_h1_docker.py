#!/usr/bin/env python3
"""H1 adversarial smoke v2 — kernel-boundary edition. EVERY probe must
FAIL CLOSED (or prove absence). Exit 0 only if all green. Stdlib only.
No models, no external network (the point)."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from dockersandbox import DockerSandbox, unique_session
from isolation import scan_outputs_for_canaries
from symmetry import build_context, diff_contexts
from seal import build_visible_root

BASE = "/tmp/h1-docker"
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


PY = ["python3", "-c"]

# --- network matrix: identical denial regardless of tool ---
sb = DockerSandbox(BASE + "/net", [])
net_probes = {
    "python-socket": "import socket;s=socket.create_connection(('8.8.8.8',53),timeout=5)",
    "python-urllib": "import urllib.request;urllib.request.urlopen('https://example.com',timeout=8)",
    "python-dns": "import socket;socket.getaddrinfo('example.com',443)",
    "shell-ping": None,  # filled below (no ping binary in slim: absence is fine, kernel is the claim)
    "iface-scan": ("import os;ifs=sorted(os.listdir('/sys/class/net'));"
                   "print('IFACES:'+','.join(ifs))"),
}
for name, code in net_probes.items():
    if code is None:
        continue
    p = sb.run(PY + [code], timeout=30)
    if name == "iface-scan":
        check("no usable interfaces (only down lo)",
              "IFACES:lo" in (p.stdout or ""), (p.stdout or "").strip()[:60])
    else:
        check(f"net denied: {name}", p.returncode != 0)
p = sb.run(["sh", "-c", "command -v curl wget git node gcc cc python3; echo ---; cat /etc/resolv.conf 2>/dev/null | head -3"])
print("   tool-availability note (all must still fail by kernel, not absence):")
print("   " + (p.stdout or "").strip().replace("\n", " | ")[:160])

# --- filesystem matrix: unmounted = unaddressable ---
truth = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam01/truth.json"
p = sb.run(PY + [f"open({truth!r}).read()"])
check("truth path absent in jail", p.returncode != 0)
p = sb.run(["cat", truth])
check("cat truth from jail fails", p.returncode != 0)
p = sb.run(PY + ["import os;print(os.path.exists('/home/chow'))"])
check("host home not mounted", "False" in (p.stdout or ""))
p = sb.run(PY + ["import os;print(os.listdir('/'))"])
check("jail root is image fs, not host",
      p.returncode == 0 and "home" not in (p.stdout or "").split())

# --- env: constructed, secret-free ---
p = sb.run(PY + ["import os,json;print(json.dumps(dict(os.environ)))"])
env = json.loads(p.stdout)
# host secret NAMES (never values) must not cross; image-baked defaults
# (e.g. python:slim GPG_KEY) are pinned as known-benign allowlist below.
host_secret_names = {k for k in os.environ
                     if any(s in k.upper() for s in
                            ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
IMAGE_BAKED = {"GPG_KEY", "PYTHON_VERSION", "PYTHON_PIP_VERSION"}
leak = [k for k in env if k in host_secret_names]
unknown = [k for k in env if k not in host_secret_names
           and k not in IMAGE_BAKED
           and any(s in k.upper() for s in
                   ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))]
check("no host secret names in jail", not leak, str(leak))
check("no unexpected secret-like env", not unknown, str(unknown))
check("no inherited host env (HOME!=/home/chow)",
      env.get("HOME", "") != "/home/chow", env.get("HOME", "?"))

# --- user separation ---
p = sb.run(["id", "-u"])
check("agent not container-root (uid!=0)", (p.stdout or "").strip() != "0",
      (p.stdout or "").strip()[:20])

# --- sessions unique + canary scan (detection layer, kept) ---
a, b = unique_session(), unique_session()
check("session ids unique", a != b and a.startswith("ses-"))
check("clean scan clean",
      scan_outputs_for_canaries({"A": ["x"], "B": ["y"]},
                                {"A": "cA", "B": "cB"}) == [])
check("planted leak detected",
      scan_outputs_for_canaries({"A": ["x"], "B": ["has cA here"]},
                                {"A": "cA", "B": "cB"}) != [])

# --- symmetry (unchanged mechanism) ---
t, _ = build_context("t", "do X", ["read"], {"cap": "K"})
c, _ = build_context("t", "do X", ["read"], None)
check("identical-except-capability passes", diff_contexts(t, c) == [])
t2, _ = build_context("t", "do X please", ["read"], {"cap": "K"})
check("injected asymmetry fails", diff_contexts(t2, c) != [])

# --- seal over VISIBLE root, bound read-only into jail ---
fam = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam01"
task = os.path.join(fam, "T0")
vis = os.path.join(BASE, "visible-T0")
copied, refused = build_visible_root(task, vis)
check("visible root built", len(copied) > 0, str(copied))
sb2 = DockerSandbox(BASE + "/seal",
                    [(os.path.join(BASE, "sealwork"), "/work", "rw"),
                     (vis, "/task", "ro")])
os.makedirs(os.path.join(BASE, "sealwork"), exist_ok=True)
p = sb2.run(PY + ["import os;print(sorted(os.listdir('/task')))"])
check("visible files present ro", p.returncode == 0, (p.stdout or "").strip()[:80])
p = sb2.run(["sh", "-c", "echo hacked >> /task/input.csv"])
check("visible mount read-only", p.returncode != 0)
p = sb2.run(PY + [f"open('/task/../truth.json').read()"])
check("truth not smuggled via task mount", p.returncode != 0)
p = sb2.run(PY + ["import hashlib;print(hashlib.sha256(open('/task/input.csv','rb').read()).hexdigest()[:12])"])
import hashlib as _hl
host_h = _hl.sha256(open('/tmp/h1-docker/visible-T0/input.csv','rb').read()).hexdigest()[:12]
check("visible content matches host bytes",
      (p.stdout or "").strip() == host_h,
      (p.stdout or "").strip()[:20])

# --- mount audit: prove declared binds only ---
mounts = sb2.inspect_mounts()
srcs = sorted(s for s, _ in mounts)
check("mount audit shows exactly work+task",
      len(mounts) == 2 and any("sealwork" in s for s in srcs)
      and any("visible-T0" in s for s in srcs), str(srcs))

bad = [n for n, ok_ in results if not ok_]
print(f"\nH1-docker smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)
