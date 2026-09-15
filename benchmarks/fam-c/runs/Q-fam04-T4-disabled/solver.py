import json, os

def solve(src_dir, dst_path):
    with open(os.path.join(src_dir, 'graph.json')) as f:
        data = json.load(f)
    nodes = data['nodes']
    adj = {n: [] for n in nodes}
    for u, v in data['edges']:
        adj[u].append(v)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    parent = {n: None for n in nodes}
    cycle = []

    def dfs(u):
        color[u] = GRAY
        for v in adj[u]:
            if cycle:
                return
            if color[v] == GRAY:
                cycle.append(v)
                cur = u
                while cur != v:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.reverse()
                return
            if color[v] == WHITE:
                parent[v] = u
                dfs(v)
        color[u] = BLACK

    for n in nodes:
        if color[n] == WHITE and not cycle:
            dfs(n)

    if cycle:
        result = {'valid': False, 'cycle': cycle}
    else:
        result = {'valid': True, 'order': nodes}
    with open(dst_path, 'w') as f:
        json.dump(result, f)

solve('.', 'OUTPUT.json')