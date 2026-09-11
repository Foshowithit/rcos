#!/usr/bin/env python3
"""D2 TEST-ONLY mock provider boundary.  NOT A13, NOT a real provider.

This is the ONLY cell-level provider endpoint in the apparatus.  It is a local
unix socket fixture: no network, no real provider, no model.  It receives a
request, decides the response bytes deterministically from the request, writes
the response-decision record, and answers.  A counterfactual leg that could
reach this endpoint on its own would create a second provider opportunity; the
gate -- not the mock -- owns that boundary, and the mock records the ORIGIN of
every request it sees so a declared direct path can be told apart from a gate
dispatch.
"""
import base64
import hashlib
import json
import os
import socket
import sys
import time


def write_json(path, payload):
    temporary = path + ".partial"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main():
    arm = os.environ["D2_ARM_DIR"]
    socket_path = os.environ["D2_MOCK_SOCKET"]
    decision_path = os.environ["D2_RESPONSE_DECISION"]
    receives_path = os.environ["D2_MOCK_RECEIVES"]
    stop_path = os.environ["D2_MOCK_STOP"]
    identity = os.environ["D2_MOCK_IDENTITY"]

    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(16)
    server.settimeout(0.05)
    write_json(os.environ["D2_MOCK_READY"], {
        "role": "MOCK_PROVIDER_BOUNDARY",
        "socket": socket_path,
        "mock_endpoint_identity": identity,
        "is_real_provider": False,
    })

    receive_index = 0
    while not os.path.exists(stop_path):
        try:
            connection, _address = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with connection:
            connection.settimeout(0.5)
            buffer = b""
            while b"\n" not in buffer:
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buffer += chunk
            if not buffer:
                continue
            line = buffer.split(b"\n", 1)[0].decode("utf-8", "replace")
            try:
                request = json.loads(line)
            except ValueError:
                continue
            receive_index += 1
            receive_id = "mock-receive-%d" % receive_index
            peer_pid = 0
            peer_tgid = 0
            try:
                credentials = connection.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                # struct ucred is {pid, uid, gid}: pid is the FIRST field.
                peer_pid = int.from_bytes(credentials[0:4], "little")
                peer_tgid = peer_pid
            except OSError:
                pass
            attempt_id = str(request.get("attempt_id") or "")
            request_id = str(request.get("request_id") or "")
            kind = str(request.get("kind") or "")
            if kind == "adapter_passthrough":
                origin = "adapter_direct"
                path = "direct"
            elif kind == "gate_dispatch":
                origin = "gate_dispatch"
                path = "provider_path"
            else:
                origin = "unclassified"
                path = "direct"
            request_bytes = line.encode("utf-8")
            request_hash = hashlib.sha256(request_bytes).hexdigest()
            record = {
                "receive_id": receive_id,
                "dispatch_id": str(request.get("dispatch_id") or ""),
                "attempt_id": attempt_id,
                "request_id": request_id,
                "origin": origin,
                "path": path,
                "kind": kind,
                "peer_pid": peer_pid,
                "peer_tgid": peer_tgid,
                "mock_endpoint_identity": identity,
                "request_bytes_sha256": request_hash,
                "mock_request_bytes_sha256": request_hash,
                "ok": True,
                "received_wall": time.time(),
            }
            with open(receives_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            body = ("D2-CAPTURED-RESPONSE|request_id=%s|attempt=%s|origin=%s|"
                    "mock=%s|payload=d2-local-fixture"
                    % (request_id, attempt_id, origin, identity))
            response_bytes = json.dumps({
                "provider_response": "captured",
                "request_id": request_id,
                "attempt_id": attempt_id,
                "origin": origin,
                "mock_endpoint_identity": identity,
                "body": body,
                "is_real_provider": False,
            }, sort_keys=True).encode("utf-8")
            write_json(decision_path, {
                "request_id": request_id,
                "attempt_id": attempt_id,
                "origin": origin,
                "response_path": path,
                "response_bytes_sha256":
                    hashlib.sha256(response_bytes).hexdigest(),
                "response_size": len(response_bytes),
                "response_b64": base64.b64encode(response_bytes).decode("ascii"),
                "mock_endpoint_identity": identity,
                "is_real_provider": False,
                "scope": "provider_boundary_response",
                "scope_reconciliation": "one_response_per_captured_request",
            })
            try:
                connection.sendall(response_bytes + b"\n")
            except OSError:
                pass
    server.close()
    if os.path.exists(socket_path):
        os.unlink(socket_path)


main()
