#!/usr/bin/env python3
import sys, json, hashlib

def sha256_hex(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()

def main():
    try:
        if len(sys.argv) != 4:
            print("usage: engine.py field_map_path records_path out_path", file=sys.stderr)
            return 1

        field_map_path, records_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

        with open(field_map_path, 'r') as f:
            field_map = json.load(f)
        with open(records_path, 'r') as f:
            records = json.load(f)

        ok, bad, unverified = [], [], []

        for path, record in records.items():
            if not isinstance(record, dict):
                bad.append({"path": path, "reason": f"not a dict: {type(record).__name__}"})
                continue

            spec = field_map.get(path)
            if spec is None:
                unverified.append(path)
                continue

            reasons = []
            has_any_check = False
            all_checks_passed = True

            for field, value in record.items():
                expected = spec.get(field)
                if not isinstance(expected, dict):
                    continue

                exp_size = expected.get('size')
                exp_sha = expected.get('sha256')

                if exp_size is not None:
                    has_any_check = True
                    if isinstance(value, str):
                        actual_size = len(value.encode('utf-8'))
                    elif isinstance(value, (bytes, bytearray)):
                        actual_size = len(value)
                    else:
                        actual_size = len(str(value).encode('utf-8'))
                    if actual_size != exp_size:
                        all_checks_passed = False
                        reasons.append(f"{field}: size {actual_size} != {exp_size}")

                if exp_sha is not None:
                    has_any_check = True
                    if sha256_hex(value) != exp_sha:
                        all_checks_passed = False
                        reasons.append(f"{field}: sha256 mismatch")

            if not all_checks_passed:
                bad.append({"path": path, "reason": "; ".join(reasons)})
            elif not has_any_check:
                unverified.append(path)
            else:
                ok.append(path)

        with open(out_path, 'w') as f:
            json.dump({"ok": ok, "bad": bad, "unverified": unverified}, f, indent=2)
        return 0
    except Exception as e:
        print(f"crash: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
