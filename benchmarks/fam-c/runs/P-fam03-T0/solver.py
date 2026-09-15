import json
import sys
import os

def main():
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    
    with open(os.path.join(src_dir, 'events.txt'), 'r') as f:
        lines = f.read().splitlines()
    
    total = len(lines)
    unique = len(set(lines))
    removed = total - unique
    
    output = {
        "total": total,
        "unique": unique,
        "unique_list": sorted(set(lines)),  # Not requested, but might be useful
        "removed": removed
    }
    
    # Actually, just emit what's requested
    output = {
        "total": total,
        "unique": unique,
        "removed": removed
    }
    
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, 'w') as f:
        json.dump(output, f)

if __name__ == '__main__':
    main()