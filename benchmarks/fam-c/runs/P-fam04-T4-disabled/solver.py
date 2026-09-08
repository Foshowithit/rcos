import json
import os
import sys

def solve(src_dir, dst_path):
    graph_path = os.path.join(src_dir, "graph.json")
    with open(graph_path) as f:
        data = json.load(f)

    nodes = list(data.get("nodes", []))
    edges = data.get("edges", [])

    all_nodes = set(nodes)
    for u, v in edges:
        all_nodes.add(u)
        all_nodes.add(v)

    adj = {n: [] for n in all_nodes}
    for u, v in edges:
        adj[u].append(v)

    nodes = list(all_nodes)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    parent = {}
    cycle = None

    def dfs(u):
        nonlocal cycle
        if cycle is not None:
            return
        color[u] = GRAY
        for v in adj[u]:
            if cycle is not None:
                return
            if color[v] == WHITE:
                parent[v] = u
                dfs(v)
            elif color[v] == GRAY:
                path = [u]
                x = u
                while x != v:
                    x = parent[x]
                    path.append(x)
                cycle = list(reversed(path)) + [v]
                return
        color[u] = BLACK

    for n in nodes:
        if cycle is not None:
            break
        if color[n] == WHITE:
            parent[n] = None
            dfs(n)

    if cycle is not None:
        result = {"valid": False, "cycle": cycle}
    else:
        in_degree = {n: 0 for n in nodes}
        for u, v in edges:
            in_degree[v] = in_degree.get(v, 0) + 1
        queue = [n for n in nodes if in_degree.get(n, 0) == 0]
        order = []
        while queue:
            u = queue.pop(0)
            order.append(u)
            for v in adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    queue.append(v)
        result = {"valid": True, "order": order}

    with open(dst_path, "w") as f:
        json.dump(result, f)

if __name__ == "__main__":
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    solve(src_dir, dst_path)
