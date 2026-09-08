import json
import os
from decimal import Decimal

def main():
    src_dir = os.environ.get('SRC_DIR', '.')  # or pass via args
    # The task says "reading (src_dir, dst_path)"
    # I need to figure out how src_dir and dst_path are passed.
    # Typically, the harness passes them as command line arguments or environment variables.
    # Looking at the task: "reading (src_dir, dst_path) — src_dir contains the task files"
    # Common pattern: sys.argv[1] = src_dir, sys.argv[2] = dst_path
    import sys
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    
    input_path = os.path.join(src_dir, 'input.psv')
    with open(input_path, 'r') as f:
        lines = f.read().splitlines()
    
    header = lines[0]
    # Header columns: NAME|ID|TAGS|AMOUNT_USD
    # But we don't really need to parse the header since we know the order from the data,
    # but to be robust, let's map header names to indices.
    cols = header.split('|')
    name_idx = cols.index('NAME')
    id_idx = cols.index('ID')
    tags_idx = cols.index('TAGS')
    amount_idx = cols.index('AMOUNT_USD')
    
    result = []
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split('|')
        name = parts[name_idx]
        record_id = parts[id_idx]
        amount_str = parts[amount_idx]
        # Tags are everything between tags_idx and amount_idx (exclusive of amount_idx)
        # Actually, if we use indices, we know exactly which parts are tags.
        # But tags themselves might contain pipes? No, we split by pipe, so each part is either name, id, a single tag, or amount.
        # The tags column in the original data is "bulk|sale" which when split by pipe becomes separate fields.
        # So if TAGS is at index tags_idx and AMOUNT_USD is at index amount_idx, and there are more fields between them,
        # that means there were multiple tags.
        # So tags are parts[tags_idx:amount_idx]
        # But wait: tags_idx < amount_idx. So tags = parts[tags_idx:amount_idx]
        # However, if the original TAGS field was empty, then parts[tags_idx] would be "" and there would be no extra fields.
        # So tags = parts[tags_idx:amount_idx] should work.
        tags_raw = parts[tags_idx:amount_idx]
        tags = [t for t in tags_raw if t]  # filter empty strings? Or keep?
        # If TAGS is empty, parts[tags_idx] is "", and tags_raw = [""], filtered gives [].
        # If TAGS has values, tags_raw = ["bulk"] or ["bulk", "sale"], filtered gives those.
        # But what if a tag is intentionally empty? Unlikely. Filter empty seems right.
        
        amount_cents = int(Decimal(amount_str) * 100)
        
        result.append({
            'id': record_id,
            'name': name,
            'amount_cents': amount_cents,
            'tags': tags
        })
    
    with open(dst_path, 'w') as f:
        json.dump(result, f)

if __name__ == '__main__':
    main()