import json, os, sys

src_dir, dst_path = sys.argv[1], sys.argv[2]
with open(os.path.join(src_dir, 'batch.json')) as f:
    data = json.load(f)

events = data['events']
total = len(events)
seen = set()
for e in events:
    seen.add((e['kind'], e['target']))
unique = len(seen)
removed = total - unique

with open(dst_path, 'w') as f:
    json.dump({'total': total, 'unique': unique, 'removed': removed}, f)
