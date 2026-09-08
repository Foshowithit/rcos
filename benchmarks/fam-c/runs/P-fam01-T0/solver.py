import csv
import json
import os
from decimal import Decimal

def solve(src_dir, dst_path):
    input_path = os.path.join(src_dir, 'input.csv')
    with open(input_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        result = []
        for row in reader:
            amount_cents = int((Decimal(row['amount_usd']) * 100).to_integral_value())
            tags_str = row['tags']
            if tags_str:
                tags = tags_str.split('|')
            else:
                tags = []
            result.append({
                'id': row['id'],
                'name': row['name'],
                'amount_cents': amount_cents,
                'tags': tags
            })
    
    with open(dst_path, 'w') as f:
        json.dump(result, f, indent=2)

if __name__ == '__main__':
    import sys
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    solve(src_dir, dst_path)