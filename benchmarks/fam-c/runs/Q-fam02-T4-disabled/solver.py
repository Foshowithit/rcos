#!/usr/bin/env python3
import json, os

src_dir = "TASK_DIR"
dst_path = "OUTPUT.json"

# Read policy
policy = "latest-wins"
policy_file = os.path.join(src_dir, "POLICY")
if os.path.exists(policy_file):
    with open(policy_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("duplicate_policy:"):
                policy = line.split(":", 1)[1].strip()

# Collect pages in order
pages_dir = os.path.join(src_dir, "pages")
page_files = sorted(f for f in os.listdir(pages_dir) if f.startswith("t") and f.endswith(".json"))

# Traverse via next links
all_items = []
cur = page_files[0] if page_files else None
visited = set()
while cur and cur not in visited:
    visited.add(cur)
    path = os.path.join(pages_dir, cur)
    with open(path) as f:
        data = json.load(f)
    all_items.extend(data.get("items", []))
    cur = data.get("next")

# Merge with policy
merged = {}
for i, item in enumerate(all_items):
    key = item.get("k", item.get("id"))
    if policy == "latest-wins":
        merged[key] = item
    else:
        merged.setdefault(key, item)

# Build output
output = {"items": list(merged.values())}

with open(dst_path, "w") as f:
    json.dump(output, f, indent=2)
print(json.dumps(output, indent=2))