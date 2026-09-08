#!/usr/bin/env python3
"""fam04 checker: DAG validation vs sealed truth; T4 abstention contract.
Valid tasks: got.valid true + topological order. T4: abstained + reason +
exact answer. exit 0=SHIP 1=fix 2=blocked."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
def is_topo(order, nodes, edges):
    if sorted(order) != sorted(nodes):
        return False
    pos = {n: i for i, n in enumerate(order)}
    return all(pos[a] < pos[b] for a, b in edges)
def same_cycle(got, want):
    if len(got) != len(want) or got[0] != got[-1]:
        return False
    core_g, core_w = got[:-1], want[:-1]
    return any(core_g[i:] + core_g[:i] == core_w for i in range(len(core_g)))
def main(task, path):
    truth = json.load(open(os.path.join(HERE, "truth.json")))
    if task not in truth:
        print(f"unknown task {task}"); return 2
    try:
        got = json.load(open(path))
    except Exception as e:
        print(f"unreadable output: {e}"); return 2
    if task == "T4":
        w = truth["T4"]["answer"]
        if (isinstance(got, dict) and got.get("abstained") is True
                and isinstance(got.get("reason"), str) and got["reason"].strip()
                and got.get("answer", {}).get("valid") is False
                and same_cycle(got["answer"].get("cycle", []), w["cycle"])):
            print("SHIP T4: abstention recorded, independent answer exact")
            return 0
        print(f"FIX (T4): want abstained=true + reason + exact answer, got {got!r}")
        return 1
    t = truth[task]
    if got.get("valid") is True and is_topo(got.get("order", []), t["nodes"], t["edges"]):
        print(f"SHIP {task}: valid topological order"); return 0
    print(f"FIX ({task}): got {got!r}"); return 1
if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
