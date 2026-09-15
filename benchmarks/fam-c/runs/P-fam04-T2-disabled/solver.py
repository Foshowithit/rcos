import os, json

def main():
    src_dir, dst_path = os.environ.get('SRC_DIR', '.'), os.environ.get('DST_PATH', 'OUTPUT.json')
    # Allow positional args fallback via sys.argv
    import sys
    if len(sys.argv) >= 3:
        src_dir, dst_path = sys.argv[1], sys.argv[2]
    graph_path = os.path.join(src_dir, 'graph.txt')
    edges = []
    nodes = []
    node_set = set()
    with open(graph_path, 'r') as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            # format: a -> b
            parts = s.split('->')
            if len(parts) != 2:
                continue
            a, b = parts[0].strip(), parts[1].strip()
            edges.append([a, b])
            if a not in node_set:
                node_set.add(a); nodes.append(a)
            if b not in node_set:
                node_set.add(b); nodes.append(b)
    # DAG validation via Kahn's algorithm
    indeg = {n: 0 for n in nodes}
    adj = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
        indeg[b] = indeg.get(b, 0) + 1
    from collections import deque
    q = deque([n for n in nodes if indeg[n] == 0])
    visited = 0
    while q:
        n = q.popleft()
        visited += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    is_dag = (visited == len(nodes))
    out = {"edges": edges, "nodes": nodes, "is_dag": is_dag}
    with open(dst_path, 'w') as f:
        json.dump(out, f, indent=2)

if __name__ == '__main__':
    main()
