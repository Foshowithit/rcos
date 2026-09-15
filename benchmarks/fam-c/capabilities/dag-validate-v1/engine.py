#!/usr/bin/env python3
import sys, json

def gv(o, ks, df):
    for k in ks:
        if k in o: return o[k]
    for k in df:
        if k in o: return o[k]
    return None

def norm(g, fm):
    nk = fm.get('nodes', ['nodes', 'vertices'])
    ek = fm.get('edges', ['edges', 'links', 'arcs'])
    nodes = next((g[k] for k in nk if k in g), [])
    edges = next((g[k] for k in ek if k in g), [])
    nk2 = fm.get('node_id', []) + ['id', 'name', 'node_id', 'vertex_id']
    sk = fm.get('edge_source', []) + ['source', 'from', 'src', 'u', 'tail']
    tk = fm.get('edge_target', []) + ['target', 'to', 'dst', 'v', 'head']
    nlist, seen = [], set()
    for n in nodes:
        nid = gv(n, nk2, ['id', 'name']) or f"__n{len(nlist)}"
        nlist.append(nid); seen.add(nid)
    elist = []
    for e in edges:
        s, t = gv(e, sk, ['source']), gv(e, tk, ['target'])
        if s is None or t is None: continue
        for x in (s, t):
            if x not in seen: nlist.append(x); seen.add(x)
        elist.append((s, t))
    return nlist, elist

def valid(ns, es):
    ids = set(ns)
    for s, t in es: ids.update([s, t])
    adj = {i: [] for i in ids}
    ind = {i: 0 for i in ids}
    for s, t in es:
        adj[s].append(t); ind[t] += 1
    q = sorted([i for i in ids if ind[i] == 0])
    order = []
    while q:
        u = q.pop(0); order.append(u)
        for v in adj[u]:
            ind[v] -= 1
            if ind[v] == 0: q.append(v)
        q.sort()
    if len(order) == len(ids):
        return {'valid': True, 'order': order}
    color = {i: 0 for i in ids}
    par = {}
    cycle = []
    def dfs(u):
        color[u] = 1
        for v in adj[u]:
            if color[v] == 1:
                c, x = [u], u
                while x != v:
                    x = par[x]; c.append(x)
                cycle.extend(list(reversed(c)) + [v])
                return True
            if color[v] == 0:
                par[v] = u
                if dfs(v): return True
        color[u] = 2
        return False
    for i in ids:
        if color[i] == 0 and dfs(i):
            return {'valid': False, 'cycle': cycle}
    return {'valid': False, 'cycle': []}

def main():
    fm = json.load(open(sys.argv[1]))
    rec = json.load(open(sys.argv[2]))
    ns, es = norm(rec, fm)
    r = valid(ns, es)
    json.dump(r, open(sys.argv[3], 'w'))
    sys.exit(0)

if __name__ == '__main__':
    main()
