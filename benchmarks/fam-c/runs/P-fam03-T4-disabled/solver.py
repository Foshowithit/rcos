import json, os, sys

def solve(src_dir, dst_path):
    src = os.path.join(src_dir, 'events.txt')
    with open(src, 'rb') as f:
        data = f.read()
    # Split into lines, preserving only non-empty stripped lines like typical counting.
    # Each line is a distinct event; use splitlines so trailing newline doesn't yield empty.
    lines = data.splitlines()
    total = len(lines)
    unique = len(set(lines))
    removed = total - unique
    out = {'total': total, 'unique': unique, 'removed': removed}
    with open(dst_path, 'w') as f:
        json.dump(out, f)

if __name__ == '__main__':
    solve(sys.argv[1], sys.argv[2])
