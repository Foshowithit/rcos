#!/usr/bin/env python3
import sys, json

def parse_usd_to_cents(s):
    if s is None:
        return 0
    s = str(s).strip()
    neg = s.startswith('-') or (s.startswith('(') and s.endswith(')'))
    if s.startswith('('):
        s = s[1:-1].strip()
    s = s.lstrip('$').strip()
    s = s.replace(',', '')
    if neg and not s.startswith('-'):
        s = '-' + s
    neg = s.startswith('-')
    if neg:
        s = s[1:]
    if '.' in s:
        a, b = s.split('.', 1)
        b = (b + '00')[:2]
    else:
        a, b = s, '00'
    cents = (int(a) if a else 0) * 100 + int(b)
    return -cents if neg else cents

def pick(rec, keys):
    if isinstance(keys, str):
        keys = [keys]
    if not keys:
        return None
    for k in keys:
        if k in rec and rec[k] is not None:
            return rec[k]
    return None

def main():
    try:
        with open(sys.argv[1]) as f:
            fmap = json.load(f)
        with open(sys.argv[2]) as f:
            records = json.load(f)
        sep = fmap.get('tag_sep', ',')
        out = []
        for rec in records:
            name_val = pick(rec, fmap.get('name', ''))
            tags_val = pick(rec, fmap.get('tags', ''))
            if isinstance(tags_val, list):
                tags = [str(t).strip() for t in tags_val if str(t).strip()]
            elif tags_val is None:
                tags = []
            else:
                tags = [t.strip() for t in str(tags_val).split(sep) if t.strip()]
            out.append({
                'id': pick(rec, fmap.get('id', '')),
                'name': name_val if name_val is not None else '',
                'amount_cents': parse_usd_to_cents(pick(rec, fmap.get('amount', ''))),
                'tags': tags,
            })
        with open(sys.argv[3], 'w') as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(str(e) + '\n')
        sys.exit(1)

if __name__ == '__main__':
    main()
