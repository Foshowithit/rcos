import json, os, sys

src_dir = sys.argv[1]
dst_path = sys.argv[2]

seen = set()
total = 0
with open(os.path.join(src_dir, 'events.jsonl'), 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        total += 1
        seen.add((obj['ev'], obj['t']))

unique = len(seen)
removed = total - unique

with open(dst_path, 'w') as f:
    json.dump({'total': total, 'unique': unique, 'removed': removed}, f)
