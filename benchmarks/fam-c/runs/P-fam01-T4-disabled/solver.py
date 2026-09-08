import csv, json, os
from decimal import Decimal

def solve(src_dir, dst_path):
    csv_path = os.path.join(src_dir, 'input.csv')
    records = []
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = (row.get('id') or '').strip()
            if not rid or rid.upper() == 'SUMMARY':
                continue
            amount_str = (row.get('amount_usd') or '0').strip() or '0'
            amount_cents = int((Decimal(amount_str) * 100).to_integral_value())
            tags_str = (row.get('tags') or '').strip()
            tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []
            name = (row.get('name') or '').strip()
            records.append({
                'id': rid,
                'name': name,
                'amount_cents': amount_cents,
                'tags': tags,
            })
    with open(dst_path, 'w') as f:
        json.dump(records, f, indent=2)

if __name__ == '__main__':
    import sys
    src = sys.argv[1]
    dst = sys.argv[2]
    solve(src, dst)
