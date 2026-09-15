import sys
import os
import hashlib
import json

def solve(manifest_path, files_dir, out_path):
    ok = []
    bad = []
    unverified = []

    try:
        with open(manifest_path, 'r') as f:
            content = f.read()
    except (IOError, OSError):
        with open(out_path, 'w') as f:
            json.dump({"ok": [], "bad": [], "unverified": []}, f)
        return

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(':', 2)
        if len(parts) != 3:
            unverified.append(line)
            continue

        path, expected_size_str, expected_sha256 = parts
        path = path.strip()
        expected_sha256 = expected_sha256.strip().lower()

        try:
            expected_size = int(expected_size_str.strip())
        except ValueError:
            unverified.append(path)
            continue

        full_path = os.path.join(files_dir, path)

        if not os.path.isfile(full_path):
            unverified.append(path)
            continue

        try:
            actual_size = os.path.getsize(full_path)
            h = hashlib.sha256()
            with open(full_path, 'rb') as fh:
                while True:
                    chunk = fh.read(65536)
                    if not chunk:
                        break
                    h.update(chunk)
            actual_sha256 = h.hexdigest()
        except (IOError, OSError):
            unverified.append(path)
            continue

        if actual_size != expected_size or actual_sha256 != expected_sha256:
            reasons = []
            if actual_size != expected_size:
                reasons.append("size {} != {}".format(actual_size, expected_size))
            if actual_sha256 != expected_sha256:
                reasons.append("sha256 {} != {}".format(actual_sha256, expected_sha256))
            bad.append({"path": path, "reason": "; ".join(reasons)})
        else:
            ok.append(path)

    result = {"ok": ok, "bad": bad, "unverified": unverified}
    with open(out_path, 'w') as f:
        json.dump(result, f)


if __name__ == "__main__":
    manifest_path = sys.argv[1]
    files_dir = sys.argv[2]
    out_path = sys.argv[3]
    solve(manifest_path, files_dir, out_path)
