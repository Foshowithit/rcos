#!/usr/bin/env python3
"""Serve a directory on an ephemeral 127.0.0.1 port, fetch a path back, and
prove the bytes served are the bytes the AUTHoring side intended — then prove
the port is closed.

Exists because a "200 OK" proves nothing: 09-17 two http.servers split one
port across address families and a STALE snapshot answered IPv4 with old
bytes (local-preview-port-split-brain). Lesson from the attack run: comparing
served-vs-docroot-disk CANNOT catch a stale server (both sides are stale and
match). The gate that works is an expected sha256 pinned at authoring time.

Usage:
  serve_verify.py <docroot> <relpath> [--expect-sha256 <hex>] [port]

Exit 0 = status 200 + sha256 == expected (when given) + port closed after teardown.
Exit 3 = wrong status / hash mismatch / port still open (the gate caught it).
Exit 4 = could not start server.
"""
import hashlib
import http.server
import os
import socket
import sys
import threading
import urllib.request

args = [a for a in sys.argv[1:]]
docroot, relpath = os.path.abspath(args.pop(0)), args.pop(0)
expect_sha = None
port = 0
i = 0
while i < len(args):
    if args[i] == "--expect-sha256":
        expect_sha = args[i + 1].lower()
        i += 2
    else:
        port = int(args[i])
        i += 1


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=docroot, **kw)

    def log_message(self, *a):
        pass


httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
bound = httpd.server_address[1]
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()

url = f"http://127.0.0.1:{bound}/{relpath}"
fail = []
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        status = r.status
        served = r.read()
    print(f"GET {url} -> HTTP {status} ({len(served)} bytes)")
    if status != 200:
        fail.append(f"STATUS {status} != 200")
except urllib.error.HTTPError as e:
    fail.append(f"STATUS {e.code} != 200")
    served = b""
    print(f"GET {url} -> HTTP {e.code}")

h_served = hashlib.sha256(served).hexdigest()
disk_path = os.path.join(docroot, relpath)
disk = open(disk_path, "rb").read() if os.path.exists(disk_path) else b""
h_disk = hashlib.sha256(disk).hexdigest()
print(f"sha256 served {h_served[:16]}  docroot-disk {h_disk[:16]}")
if h_disk != h_served:
    fail.append("HASH_MISMATCH served != docroot-disk (transport mangling)")
if expect_sha:
    print(f"sha256 expect {expect_sha[:16]} (pinned at authoring time)")
    if h_served != expect_sha:
        fail.append("STALE_OR_WRONG_BYTES served != expected (split-brain catch)")

httpd.shutdown()
httpd.server_close()  # shutdown() only stops the loop; the socket stays bound without this
try:
    s = socket.create_connection(("127.0.0.1", bound), timeout=1)
    s.close()
    fail.append(f"PORT {bound} STILL OPEN after teardown")
except OSError:
    print(f"teardown: port {bound} refuses (closed)")

if fail:
    for f in fail:
        print("FAIL " + f)
    sys.exit(3)
print("SERVE_VERIFY_PASS")
