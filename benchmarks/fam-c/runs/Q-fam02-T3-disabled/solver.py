import json, os, sys, time

src_dir = sys.argv[1]
dst_path = sys.argv[2]

failure_log = []
all_items = []

def fetch(path):
    retries = 3
    for attempt in range(retries):
        try:
            with open(os.path.join(src_dir, path), 'r') as f:
                return json.load(f)
        except Exception as e:
            if attempt == retries - 1:
                failure_log.append({'path': path, 'error': str(e)})
            time.sleep(0.1)
    return None

cursor = 's1'
while cursor:
    data = fetch(f'pages/{cursor}.json')
    if data is None:
        break
    all_items.extend(data.get('items', []))
    cursor = data.get('next')

with open(dst_path, 'w') as f:
    json.dump({'items': all_items}, f)

with open('retry.log', 'w') as f:
    json.dump({'failures': failure_log}, f)