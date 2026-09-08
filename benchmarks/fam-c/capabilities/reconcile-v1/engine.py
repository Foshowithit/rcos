#!/usr/bin/env python3
import json, sys

def get_field(rec, path):
    cur = rec
    for p in path.split('.'):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur

def norm(v):
    if v is None: return None
    if isinstance(v, (int, float)): return v
    return str(v).strip().lower()

def index_by(records, key_paths):
    idx, bad = {}, []
    for rec in records:
        key = tuple(get_field(rec, kp) for kp in key_paths)
        if all(v is not None for v in key):
            idx[key] = rec
        else:
            bad.append(rec)
    return idx, bad

def main():
    fmap_path, rec_path, out_path = sys.argv[1:4]
    fmap = json.load(open(fmap_path))
    data = json.load(open(rec_path))
    match_keys = fmap['match_keys']
    fmaps = fmap['field_mappings']
    a_idx, a_bad = index_by(data.get('a', []), match_keys)
    b_idx, b_bad = index_by(data.get('b', []), match_keys)
    matched, conflicts, miss_b, miss_a = [], [], [], []
    for key, a_rec in a_idx.items():
        if key not in b_idx:
            miss_b.append({'key': list(key), 'record_a': a_rec}); continue
        b_rec = b_idx[key]
        fields, ok = {}, True
        for canon, paths in fmaps.items():
            av = norm(get_field(a_rec, paths.get('a')))
            bv = norm(get_field(b_rec, paths.get('b')))
            fields[canon] = {'a': av, 'b': bv, 'equal': av == bv}
            if av != bv: ok = False
        entry = {'key': list(key), 'fields': fields}
        (matched if ok else conflicts).append(entry if ok else {'key': list(key), 'record_a': a_rec, 'record_b': b_rec, 'fields': fields})
    for key, b_rec in b_idx.items():
        if key not in a_idx:
            miss_a.append({'key': list(key), 'record_b': b_rec})
    unrecon = [{'source': s, 'record': r} for s, b in [('a', a_bad), ('b', b_bad)] for r in b]
    result = {'matched': matched, 'missing_in_b': miss_b, 'missing_in_a': miss_a,
              'conflicts': conflicts, 'unreconcilable': unrecon,
              'stats': {'total_a': len(data.get('a', [])), 'total_b': len(data.get('b', [])),
                        'matched': len(matched), 'conflicts': len(conflicts),
                        'missing_in_b': len(miss_b), 'missing_in_a': len(miss_a),
                        'unreconcilable': len(unrecon)}}
    json.dump(result, open(out_path, 'w'), indent=2)

if __name__ == '__main__': main()
