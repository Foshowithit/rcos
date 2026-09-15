import os, json, sys

def solve(src_dir, dst_path):
    env_file = os.path.join(src_dir, 'graph.env')
    with open(env_file, 'r') as f:
        content = f.read()
    
    errors = []
    nodes = []
    edges = []
    
    for line in content.strip().splitlines():
        line = line.strip()
        if not line or '=' not in line:
            continue
        key, val = line.split('=', 1)
        key = key.strip()
        val = val.strip()
        if key == 'NODES':
            nodes = [n.strip() for n in val.split(',') if n.strip()]
        elif key == 'EDGES':
            edges = [(e.strip().split('>') if '>' in e.strip() else None) for e in val.split(',') if e.strip()]
            edges = [e for e in edges if e is not None]
    
    node_set = set(nodes)
    for src, dst in edges:
        if src not in node_set or dst not in node_set:
            errors.append(f'edge {src}>{dst} references invalid node')
    
    # Cycle detection via DFS
    adj = {n: [] for n in nodes}
    for src, dst in edges:
        adj[src].append(dst)
    
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    has_cycle = False
    
    def dfs(u):
        nonlocal has_cycle
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                has_cycle = True
                return
            elif color[v] == WHITE:
                dfs(v)
                if has_cycle:
                    return
        color[u] = BLACK
    
    for n in nodes:
        if color[n] == WHITE:
            dfs(n)
    
    result = {
        'valid': len(errors) == 0 and not has_cycle,
        'is_dag': not has_cycle,
        'nodes': nodes,
        'edges': [{'from': e[0], 'to': e[1]} for e in edges],
        'errors': errors
    }
    
    with open(dst_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    return result

if __name__ == '__main__':
    src_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    dst_path = sys.argv[2] if len(sys.argv) > 2 else 'OUTPUT.json'
    solve(src_dir, dst_path)