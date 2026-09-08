import csv, json, os, sys

def solve(src_dir, dst_path):
    csv_path = os.path.join(src_dir, 'events.csv')
    total = 0
    seen = set()
    with open(csv_path, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            seen.add((row['action'], row['target']))
    unique = len(seen)
    removed = total - unique
    with open(dst_path, 'w') as f:
        json.dump({'total': total, 'unique': unique, 'removed': removed}, f)

if __name__ == '__main__':
    solve(sys.argv[1], sys.argv[2])
