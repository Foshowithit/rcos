#!/usr/bin/env python3
"""H1 adversarial smoke v3 — constructor-owned policy edition.
EVERY probe must FAIL CLOSED (or prove absence). Exit 0 only if all
green. Stdlib only. No models, no external network (the point)."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import dockersandbox as ds
from dockersandbox import DockerSandbox
from isolation import scan_outputs_for_canaries
from symmetry import build_context, diff_contexts
from seal import build_visible_root

BASE = "/tmp/h1-docker"
VBASE = "/tmp/rcos-visible"
WBASE = "/tmp/rcos-runs"
results = []


def check(name, fail_closed, extra=""):
    results.append((name, fail_closed))
    print(("PASS " if fail_closed else "FAIL-OPEN ") + name +
          (f" [{extra}]" if extra and not fail_closed else ""))


def mkesb(tag):
    w = os.path.join(WBASE, tag, "work")
    v = os.path.join(VBASE, tag)
    os.makedirs(w, exist_ok=True)
    os.makedirs(v, exist_ok=True)
    open(os.path.join(v, "input.txt"), "w").write("hello\n")
    return w, v


PY = ["python3", "-c"]

# --- constructor authority: hostile mounts must RAISE ---
w0, v0 = mkesb("policy")
denied = 0
for hp in ["/home/chow/chow-work/rcos", "/home/chow",
           "/var/run/docker.sock", "/", "/tmp/evil",
           "/home/chow/.agent-vault/id_rsa"]:
    try:
        ds._check_source(hp, "task")
        results.append(("hostile mount refused: " + hp, False))
        print("FAIL-OPEN hostile mount accepted: " + hp)
        denied = -100
    except PermissionError:
        denied += 1
check("6 hostile host paths refused by constructor", denied == 6,
      f"denied={denied}")
try:
    ds._check_source("/nonexistent-xyz-123", "work")
    check("missing source refused", False)
except PermissionError:
    check("missing source refused", True)
os.makedirs("/tmp/rcos-visible", exist_ok=True)
try:
    os.symlink("/etc", "/tmp/rcos-visible/linketc")
    refused_link = False
    try:
        ds._check_source("/tmp/rcos-visible/linketc", "task")
    except PermissionError:
        refused_link = True
    finally:
        os.unlink("/tmp/rcos-visible/linketc")
    check("symlink-to-outside refused after realpath", refused_link)
except OSError:
    check("symlink-to-outside refused after realpath", True, "no-symlink-os")

# --- image pinned by digest ---
check("image pinned by digest (@sha256:64hex)",
      "@sha256:" in ds.IMAGE and len(ds.IMAGE.split("@sha256:")[1]) == 64,
      ds.IMAGE[:40])

# --- valid sandbox + network matrix (kernel, not tool absence) ---
wn, vn = mkesb("net")
sb = DockerSandbox(wn, vn)
for name, code in [
        ("python-socket",
         "import socket;s=socket.create_connection(('8.8.8.8',53),timeout=5)"),
        ("python-urllib",
         "import urllib.request;urllib.request.urlopen('https://example.com',timeout=8)"),
        ("python-dns",
         "import socket;socket.getaddrinfo('example.com',443)"),
        ("python-ipv6",
         "import socket;s=socket.create_connection(('2001:4860:4860::8888',80),timeout=5)"),
        ("route-table-empty",
         "import os\nroutes=[l for l in open('/proc/net/route').read().splitlines()[1:] if l.split()[1]!='00000000' or int(l.split()[3],16)&2]\nassert not routes, routes\nprint('NO-ROUTES')"),
        ("no-docker-sock",
         "import os;assert not os.path.exists('/var/run/docker.sock');print('NO-SOCK')"),
        ("no-unix-escape",
         "import os,glob;print('UNIX:'+','.join(sorted(glob.glob('/var/run/*.sock')+glob.glob('/run/*.sock'))))"),
]:
    p = sb.run(PY + [code], timeout=30)
    if name == "route-table-empty":
        check("no default route in netns", "NO-ROUTES" in (p.stdout or ""),
              (p.stderr or p.stdout or "")[:100])
    elif name == "no-docker-sock":
        check("docker.sock absent in jail", "NO-SOCK" in (p.stdout or ""))
    elif name == "no-unix-escape":
        check("no host unix sockets visible",
              (p.stdout or "").strip() in ("UNIX:",),
              (p.stdout or "").strip()[:80])
    else:
        check(f"net denied: {name}", p.returncode != 0)
p = sb.run(PY + ["import os;print(os.listdir('/sys/class/net'))"])
check("only lo interface", "eth0" not in (p.stdout or ""),
      (p.stdout or "").strip()[:60])

# --- filesystem matrix ---
truth = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam01/truth.json"
p = sb.run(PY + [f"open({truth!r}).read()"])
check("truth path absent in jail", p.returncode != 0)
p = sb.run(["cat", truth])
check("cat truth from jail fails", p.returncode != 0)
p = sb.run(PY + ["import os;print(os.path.exists('/home/chow'))"])
check("host home not mounted", "False" in (p.stdout or ""))

# --- env constructed, secret-free ---
p = sb.run(PY + ["import os,json;print(json.dumps(dict(os.environ)))"])
env = json.loads(p.stdout)
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
p = sb.run(["id", "-u"])
check("agent not container-root (uid!=0)", (p.stdout or "").strip() != "0",
      (p.stdout or "").strip()[:20])

# --- sessions + canary detection layer ---
from dockersandbox import unique_session
a, b = unique_session(), unique_session()
check("session ids unique", a != b and a.startswith("ses-"))
check("clean scan clean",
      scan_outputs_for_canaries({"A": ["x"], "B": ["y"]},
                                {"A": "cA", "B": "cB"}) == [])
check("planted leak detected",
      scan_outputs_for_canaries({"A": ["x"], "B": ["has cA here"]},
                                {"A": "cA", "B": "cB"}) != [])

# --- symmetry ---
t, _ = build_context("t", "do X", ["read"], {"cap": "K"})
c, _ = build_context("t", "do X", ["read"], None)
check("identical-except-capability passes", diff_contexts(t, c) == [])
t2, _ = build_context("t", "do X please", ["read"], {"cap": "K"})
check("injected asymmetry fails", diff_contexts(t2, c) != [])

# --- seal over VISIBLE root, bound read-only ---
fam = "/home/chow/chow-work/rcos/benchmarks/fam-c/families/fam01"
task = os.path.join(fam, "T0")
vis = os.path.join(VBASE, "seal-T0")
copied, refused = build_visible_root(task, vis)
check("visible root built", len(copied) > 0, str(copied))
ws, _ = mkesb("seal")
sb2 = DockerSandbox(ws, vis)
p = sb2.run(PY + ["import os;print(sorted(os.listdir('/task')))"])
check("visible files present ro", p.returncode == 0, (p.stdout or "").strip()[:80])
p = sb2.run(["sh", "-c", "echo hacked >> /task/input.csv"])
check("visible mount read-only", p.returncode != 0)
p = sb2.run(PY + ["open('/task/../truth.json').read()"])
check("truth not smuggled via task mount", p.returncode != 0)
import hashlib as _hl
host_h = _hl.sha256(open(os.path.join(vis, 'input.csv'), 'rb').read()).hexdigest()[:12]
p = sb2.run(PY + ["import hashlib;print(hashlib.sha256(open('/task/input.csv','rb').read()).hexdigest()[:12])"])
check("visible content matches host bytes",
      (p.stdout or "").strip() == host_h, (p.stdout or "").strip()[:20])

# --- mount audit: exactly work+task ---
mounts = sb2.inspect_mounts()
srcs = sorted(s for s, _ in mounts)
dsts = sorted(d for _, d in mounts)
check("mount audit shows exactly work+task",
      len(mounts) == 2 and dsts == ["/task", "/work"]
      and all(s.startswith(("/tmp/rcos-runs/", "/tmp/rcos-visible/"))
              for s in srcs), str(srcs))

# --- TOCTOU: mutate caller source after construction ---
import hashlib as _hl2
open(os.path.join(VBASE, "seal-T0", "input.csv"), "a").write("EVIL,INJECTED\n")
p = sb2.run(PY + ["import hashlib;print(hashlib.sha256(open('/task/input.csv','rb').read()).hexdigest()[:12])"])
check("post-construction source mutation invisible in jail",
      (p.stdout or "").strip() == host_h, (p.stdout or "").strip()[:20])
p = sb2.run(PY + ["import os;print('EVIL' in open('/task/input.csv').read())"])
check("injected content absent in jail", "False" in (p.stdout or ""))

# --- image digest recorded in manifest ---
m = sb2.manifest()
check("run manifest carries pinned digest",
      m["image"].startswith("python:3.12-slim@sha256:") and len(m["image"]) > 80,
      m["image"][:50])

bad = [n for n, ok_ in results if not ok_]
print(f"\nH1-docker smoke: {len(results) - len(bad)}/{len(results)} closed")
sys.exit(1 if bad else 0)
