import json, os, sys

def main():
    src_dir, dst_path = sys.argv[1], sys.argv[2]
    env_path = os.path.join(src_dir, 'graph.env')
    with open(env_path, 'r') as f:
        content = f.read()
    cfg = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        k, v = line.split('=', 1)
        cfg[k.strip()] = v.strip()
    nodes = [n.strip() for n in cfg.get('NODES', '').split(',') if n.strip()]
    edges_raw = [e.strip() for e in cfg.get('EDGES', '').split(',') if e.strip()]
    edges = []
    for e in edges_raw:
        if '>' in e:
            a, b = e.split('>', 1)
            edges.append({'from': a.strip(), 'to': b.strip()})
    adj = {n: [] for n in nodes}
    for e in edges:
        if e['from'] in adj:
            adj[e['from']].append(e['to'])
    # Cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    is_dag = True
    def dfs(u):
        nonlocal is_dag
        if not is_dag:
            return
        color[u] = GRAY
        for v in adj.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                is_dag = False
                return
            if color[v] == WHITE:
                dfs(v)
        color[u] = BLACK
    for n in nodes:
        if color[n] == WHITE:
            dfs(n)
            if not is_dag:
                break
    out = {
        'nodes': nodes,
        'edges': edges,
        'is_dag': is_dag,
        'num_nodes': len(nodes),
        'num_edges': len(edges),
    }
    with open(dst_path, 'w') as f:
        json.dump(out, f, indent=2)

if __name__ == '__main__':
    main()
