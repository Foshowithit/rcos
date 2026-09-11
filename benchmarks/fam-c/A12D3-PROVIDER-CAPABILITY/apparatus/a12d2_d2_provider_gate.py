#!/usr/bin/env python3
"""D2 TEST-ONLY provider gate.  NOT A13, NOT a real provider.

The gate is the EXCLUSIVE provider opportunity boundary.  Its authority is
frozen before the arm runs: the policy names how many attempts may be
dispatched and to which endpoint.  Every request it accepts becomes exactly one
provider attempt; it dispatches at most `authorized_attempt_limit` of them, and
writes a D1-compatible dispatch record per attempt (using the D1 outcome
vocabulary) so an independent checker can recompute the count from the RAW
records rather than trusting a summary boolean.
"""
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


def append_jsonl(path, payload):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def dispatch_to_mock(socket_path, body):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5.0)
    client.connect(socket_path)
    client.sendall(body)
    buffer = b""
    while b"\n" not in buffer:
        chunk = client.recv(65536)
        if not chunk:
            break
        buffer += chunk
    client.close()
    return buffer


def main():
    arm = os.environ["D2_ARM_DIR"]
    socket_path = os.environ["D2_GATE_SOCKET"]
    attempts_path = os.environ["D2_ATTEMPTS"]
    dispatches_path = os.environ["D2_DISPATCHES"]
    policy_path = os.environ["D2_POLICY"]
    stop_path = os.environ["D2_GATE_STOP"]
    mock_socket = os.environ["D2_MOCK_SOCKET"]
    gate_identity = os.environ["D2_GATE_IDENTITY"]

    with open(policy_path, encoding="utf-8") as handle:
        policy = json.load(handle)
    limit = int(policy["authorized_attempt_limit"])
    allow_dispatch = bool(policy["allow_dispatch"])
    endpoint = policy["provider_endpoint_identity"]

    if os.path.exists(socket_path):
        os.unlink(socket_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(socket_path)
    server.listen(16)
    server.settimeout(0.05)
    write_json(os.environ["D2_GATE_READY"], {
        "role": "PROVIDER_GATE",
        "socket": socket_path,
        "gate_identity": gate_identity,
        "authorized_attempt_limit": limit,
        "allow_dispatch": allow_dispatch,
        "provider_endpoint_identity": endpoint,
        "gate_policy_sha256": policy.get("gate_policy_sha256", ""),
    })

    attempt_index = 0
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
            request_bytes = line.encode("utf-8")
            request_hash = hashlib.sha256(request_bytes).hexdigest()
            attempt_index += 1
            attempt_id = str(request.get("attempt_id")
                             or "attempt-%d" % attempt_index)
            request_id = str(request.get("request_id")
                             or "req-%d" % attempt_index)
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
            append_jsonl(attempts_path, {
                "attempt_id": attempt_id,
                "request_id": request_id,
                "request_bytes_sha256": request_hash,
                "gate_identity": gate_identity,
                "provider_endpoint_identity": endpoint,
                "path": "provider_path",
                "authorized": attempt_index <= limit,
                "peer_pid": peer_pid,
                "peer_tgid": peer_tgid,
                "received_wall": time.time(),
            })
            dispatch_id = "dispatch-%d" % attempt_index
            if attempt_index > limit:
                append_jsonl(dispatches_path, {
                    "attempt_id": attempt_id,
                    "dispatch_id": dispatch_id,
                    "mock_receive_id": "",
                    "outcome": "BLOCKED_ATTEMPT_LIMIT",
                    "request_bytes_sha256": request_hash,
                    "mock_request_bytes_sha256": "",
                    "path": "provider_path",
                    "gate_identity": gate_identity,
                })
                try:
                    connection.sendall(b'{"outcome":"BLOCKED_ATTEMPT_LIMIT"}\n')
                except OSError:
                    pass
                continue
            if not allow_dispatch:
                # D2 negative fixture knob: the gate is authorized, but its
                # opaque precommit says this attempt gets NO response.  It
                # writes a REAL dispatch record with outcome NO_RESPONSE and
                # never contacts the mock, so the attempt exists as a genuine
                # opportunity at the provider boundary while producing no
                # response bytes at all.
                append_jsonl(dispatches_path, {
                    "attempt_id": attempt_id,
                    "dispatch_id": dispatch_id,
                    "mock_receive_id": "",
                    "outcome": "NO_RESPONSE",
                    "request_bytes_sha256": request_hash,
                    "mock_request_bytes_sha256": "",
                    "path": "provider_path",
                    "gate_identity": gate_identity,
                })
                try:
                    connection.sendall(b'{"outcome":"NO_RESPONSE"}\n')
                except OSError:
                    pass
                continue
            dispatch_body = json.dumps({
                "kind": "gate_dispatch",
                "dispatch_id": dispatch_id,
                "attempt_id": attempt_id,
                "request_id": request_id,
                "cell_id": request.get("cell_id", ""),
                "payload": request.get("payload", ""),
                "gate_identity": gate_identity,
            }, sort_keys=True).encode("utf-8") + b"\n"
            try:
                response = dispatch_to_mock(mock_socket, dispatch_body)
            except OSError:
                response = b""
            if not response:
                outcome = "NO_RESPONSE"
                receive_id = ""
            else:
                outcome = "SUCCESS"
                receive_id = "mock-receive-%d" % attempt_index
            append_jsonl(dispatches_path, {
                "attempt_id": attempt_id,
                "dispatch_id": dispatch_id,
                "mock_receive_id": receive_id,
                "outcome": outcome,
                "request_bytes_sha256": request_hash,
                "mock_request_bytes_sha256":
                    hashlib.sha256(dispatch_body).hexdigest(),
                "path": "provider_path",
                "gate_identity": gate_identity,
            })
            try:
                connection.sendall(response)
            except OSError:
                pass
    server.close()
    if os.path.exists(socket_path):
        os.unlink(socket_path)


main()
