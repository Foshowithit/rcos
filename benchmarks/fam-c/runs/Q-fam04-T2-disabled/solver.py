#!/usr/bin/env python3
import json, os
from collections import defaultdict, deque

src_dir = os.environ.get('SRC_DIR', '.')
dst_path = os.environ.get('DST_PATH', 'OUTPUT.json')

# Parse graph.txt
edges = []
adj = defaultdict(list)
in_degree = defaultdict(int)
nodes = set()

with open(os.path.join(src_dir, 'graph.txt')) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('->')
        u = parts[0].strip()
        v = parts[1].strip()
        edges.append((u, v))
        adj[u].append(v)
        in_degree[v] += 1
        nodes.add(u)
        nodes.add(v)

# Ensure all nodes have an entry in in_degree
for n in nodes:
    if n not in in_degree:
        in_degree[n] = 0

# Kahn's algorithm for topological sort / cycle detection
queue = deque([n for n in nodes if in_degree[n] == 0])
topo_order = []
while queue:
    u = queue.popleft()
    topo_order.append(u)
    for v in adj[u]:
        in_degree[v] -= 1
        if in_degree[v] == 0:
            queue.append(v)

is_dag = len(topo_order) == len(nodes)

result = {
    'is_dag': is_dag,
    'num_nodes': len(nodes),
    'num_edges': len(edges),
    'topological_order': topo_order if is_dag else [],
    'edges': [list(e) for e in edges]
}

with open(dst_path, 'w') as f:
    json.dump(result, f, indent=2)
