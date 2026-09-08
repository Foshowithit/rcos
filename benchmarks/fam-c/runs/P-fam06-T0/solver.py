import csv
import json
import os
import sys

def main():
    if len(sys.argv) != 3:
        print('Usage: python solver.py <src_dir> <dst_path>')
        sys.exit(1)
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    
    a_path = os.path.join(src_dir, 'a.csv')
    b_path = os.path.join(src_dir, 'b.csv')
    
    a_data = {}
    with open(a_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            a_data[row['id']] = row['amount']
    
    b_data = {}
    with open(b_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            b_data[row['id']] = row['amount']
    
    matched = []
    missing_in_b = []
    missing_in_a = []
    conflicts = []
    unreconcilable = []
    
    all_ids = set(a_data.keys()) | set(b_data.keys())
    
    for id in sorted(all_ids):
        a = a_data.get(id)
        b = b_data.get(id)
        if a is None:
            missing_in_a.append(id)
        elif b is None:
            missing_in_b.append(id)
        else:
            a_strip = a.strip()
            b_strip = b.strip()
            try:
                a_num = float(a_strip)
                b_num = float(b_strip)
                if a_num == b_num:
                    matched.append(id)
                else:
                    conflicts.append({'id': id, 'a': a, 'b': b})
            except ValueError:
                if a_strip == b_strip:
                    matched.append(id)
                else:
                    conflicts.append({'id': id, 'a': a, 'b': b})
    
    result = {
        'matched': matched,
        'missing_in_b': missing_in_b,
        'missing_in_a': missing_in_a,
        'conflicts': conflicts,
        'unreconcilable': unreconcilable
    }
    
    with open(dst_path, 'w') as f:
        json.dump(result, f, indent=2)

if __name__ == '__main__':
    main()