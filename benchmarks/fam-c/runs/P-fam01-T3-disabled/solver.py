import json
import os

def main():
    import sys
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    
    with open(os.path.join(src_dir, 'input.env'), 'r') as f:
        content = f.read()
    
    records = []
    current_id = None
    current = {}
    
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('[') and line.endswith(']'):
            if current_id:
                records.append(finalize(current_id, current))
            current_id = line[1:-1]
            current = {}
        elif '=' in line:
            key, value = line.split('=', 1)
            current[key.strip()] = value.strip()
    
    if current_id:
        records.append(finalize(current_id, current))
    
    with open(dst_path, 'w') as f:
        json.dump(records, f, indent=2)

def finalize(rid, data):
    usd = float(data.get('usd', '0'))
    amount_cents = int(round(usd * 100))
    tags_str = data.get('tags', '')
    tags = [t for t in tags_str.split('|') if t]
    return {
        'id': rid,
        'name': data.get('name', ''),
        'amount_cents': amount_cents,
        'tags': tags,
    }

main()