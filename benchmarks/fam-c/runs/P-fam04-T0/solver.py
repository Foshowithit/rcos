import json
import os
import sys

def main():
    src_dir = sys.argv[1]
    dst_path = sys.argv[2]
    
    with open(os.path.join(src_dir, 'graph.json'), 'r') as f:
        graph = json.load(f)
    
    nodes = graph['nodes']
    edges = graph['edges']
    
    # Build adjacency list
    adj = {node: [] for node in nodes}
    in_degree = {node: 0 for node in nodes}
    
    for u, v in edges:
        adj[u].append(v)
        in_degree[v] = in_degree.get(v, 0) + 1
    
    # Kahn's algorithm
    queue = [node for node in nodes if in_degree[node] == 0]
    order = []
    
    while queue:
        # Sort for deterministic order (optional)
        queue.sort()
        u = queue.pop(0)
        order.append(u)
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
    
    if len(order) == len(nodes):
        result = {"valid": True, "order": order}
    else:
        # Find a cycle using DFS on remaining nodes
        # Nodes with in_degree > 0 are part of or reachable from cycles
        remaining = [n for n in nodes if in_degree[n] > 0]
        # DFS to find a cycle
        cycle = find_cycle(adj, remaining, nodes)
        result = {"valid": False, "cycle": cycle}
    
    with open(dst_path, 'w') as f:
        json.dump(result, f)

def find_cycle(adj, remaining, all_nodes):
    # Standard DFS cycle detection
    visited = set()
    rec_stack = set()
    parent = {}
    cycle = None
    
    def dfs(u):
        nonlocal cycle
        visited.add(u)
        rec_stack.add(u)
        for v in adj.get(u, []):
            if v not in visited:
                parent[v] = u
                dfs(v)
                if cycle:
                    return
            elif v in rec_stack:
                # Found cycle: trace back from u to v
                path = [v]
                x = u
                while x != v:
                    path.append(x)
                    x = parent[x]
                path.append(v)
                path.reverse()
                cycle = path
                return
        rec_stack.remove(u)
    
    for node in remaining:
        if node not in visited and cycle is None:
            parent[node] = None
            dfs(node)
            if cycle:
                break
    
    return cycle

if __name__ == '__main__':
    main()