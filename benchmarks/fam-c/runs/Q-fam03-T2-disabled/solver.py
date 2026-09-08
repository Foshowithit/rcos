import json
from collections import Counter

src_dir = '.'
dst_path = 'OUTPUT.json'

with open(f'{src_dir}/batch.json', 'r') as f:
    data = json.load(f)

events = data.get('events', [])
total = len(events)

seen = set()
for event in events:
    key = (event['kind'], event['target'])
    seen.add(key)
unique = len(seen)
removed = total - unique

output = {'total': total, 'unique': unique, 'removed': removed}
with open(dst_path, 'w') as f:
    json.dump(output, f)