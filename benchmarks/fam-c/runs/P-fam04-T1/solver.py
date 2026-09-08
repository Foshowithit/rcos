import json, os, sys

def main():
    src_dir, dst_path = sys.argv[1], sys.argv[2]
    with open(os.path.join(src_dir, 'graph.json')) as f:
        g = json.load(f)
    vertices = g['vertices']
    links = g['links']
    name_to_id = {v: i for i, v in enumerate(vertices)}
    n = len(vertices)
    adj = [[] for _ in range(n)]
    indeg = [0] * n
    for l in links:
        u = name_to_id[l['from']]
        v = name_to_id[l['to']]
        adj[u].append(v)
        indeg[v] += 1
    # Kahn's algorithm
    queue = [i for i in range(n) if indeg[i] == 0]
    order = []
    while queue:
        queue.sort()  # deterministic
        u = queue.pop(0)
        order.append(vertices[u])
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    if len(order) != n:
        # cycle detected
        result = {"valid": False, "order": []}
    else:
        result = {"valid": True, "order": order}
    with open(dst_path, 'w') as f:
        json.dump(result, f)

if __name__ == '__main__':
    main()
