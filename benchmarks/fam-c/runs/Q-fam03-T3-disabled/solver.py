import json, os
src_dir = '.'
dst_path = os.path.join(src_dir, 'OUTPUT.json')
lines = open(os.path.join(src_dir, 'events.jsonl')).read().strip().split('\n')
total = len(lines)
seen = set()
for line in lines:
    obj = json.loads(line)
    seen.add((obj['ev'], obj['t']))
unique = len(seen)
removed = total - unique
out = {'total': total, 'unique': unique, 'removed': removed}
with open(dst_path, 'w') as f:
    json.dump(out, f)