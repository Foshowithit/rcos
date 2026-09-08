import hashlib
import json
import os
import sys
from pathlib import Path


def main():
    manifest_path = Path(sys.argv[1])
    files_dir = Path(sys.argv[2])
    out_path = Path(sys.argv[3])

    try:
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result = {"ok": [], "bad": [], "unverified": [{"path": str(manifest_path), "reason": f"manifest error: {exc}"}]}
    else:
        entries = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(entries, list):
            result = {"ok": [], "bad": [], "unverified": [{"path": str(manifest_path), "reason": "manifest has no files list"}]}
        else:
            result = {"ok": [], "bad": [], "unverified": []}
            for entry in entries:
                if not isinstance(entry, dict):
                    result["unverified"].append({"path": "<invalid entry>", "reason": "entry is not an object"})
                    continue

                raw_path = entry.get("path")
                expected_size = entry.get("size")
                expected_hash = entry.get("sha256")

                if not isinstance(raw_path, str) or not raw_path:
                    result["unverified"].append({"path": str(raw_path), "reason": "invalid file path"})
                    continue
                if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
                    result["unverified"].append({"path": raw_path, "reason": "invalid expected size"})
                    continue
                if not isinstance(expected_hash, str) or len(expected_hash) != 64:
                    result["unverified"].append({"path": raw_path, "reason": "invalid SHA-256"})
                    continue

                candidate = Path(raw_path)
                if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
                    result["unverified"].append({"path": raw_path, "reason": "path escapes files directory"})
                    continue

                file_path = files_dir / candidate
                try:
                    digest = hashlib.sha256()
                    with file_path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    actual_hash = digest.hexdigest()
                    actual_size = file_path.stat().st_size
                except (OSError, PermissionError) as exc:
                    result["unverified"].append({"path": raw_path, "reason": f"cannot read file: {exc}"})
                    continue

                if actual_size != expected_size or actual_hash != expected_hash.lower():
                    reason = f"size: expected {expected_size}, actual {actual_size}; sha256: expected {expected_hash.lower()}, actual {actual_hash}"
                    result["bad"].append({"path": raw_path, "reason": reason})
                else:
                    result["ok"].append(raw_path)

    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, separators=(",", ":"))
        handle.write("\n")


if __name__ == "__main__":
    main()
