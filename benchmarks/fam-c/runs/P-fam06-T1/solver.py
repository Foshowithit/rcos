import json, os, sys

def to_number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    return None

def main(src_dir, dst_path):
    with open(os.path.join(src_dir, 'a.json'), 'r') as f:
        a = json.load(f)
    with open(os.path.join(src_dir, 'b.json'), 'r') as f:
        b = json.load(f)

    orders = a.get('orders', [])
    ships = b.get('ships', [])

    a_map = {o['oid']: o['amt'] for o in orders}
    b_map = {s['id']: s['total'] for s in ships}

    a_ids = set(a_map.keys())
    b_ids = set(b_map.keys())

    matched, conflicts, missing_in_b, missing_in_a, unreconcilable = [], [], [], [], []

    for oid in sorted(a_ids & b_ids):
        a_val, b_val = a_map[oid], b_map[oid]
        a_num, b_num = to_number(a_val), to_number(b_val)
        if a_num is not None and b_num is not None:
            if a_num == b_num:
                matched.append(oid)
            else:
                conflicts.append({'id': oid, 'a': a_val, 'b': b_val})
        else:
            unreconcilable.append(oid)

    for oid in sorted(a_ids - b_ids):
        missing_in_b.append(oid)
    for oid in sorted(b_ids - a_ids):
        missing_in_a.append(oid)

    result = {
        'matched': matched,
        'missing_in_b': missing_in_b,
        'missing_in_a': missing_in_a,
        'conflicts': conflicts,
        'unreconcilable': unreconcilable,
    }
    with open(dst_path, 'w') as f:
        json.dump(result, f)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
