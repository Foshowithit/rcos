#!/usr/bin/env python3
"""Slice-3 generator: shipment-manifest fixtures + sealed truth.
Usage: python3 generator.py  (writes tasks/<id>/input.* + truth.json + sha256)
Formats rotate by task: csv, json, pipe, tsv, altjson, csv-reorder, kv,
pipe-alt, json-flat, tsv-alt.
"""
import hashlib
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = os.path.join(HERE, "tasks")
ORIGINS = ["OSLO", "PORTO", "GDANSK", "HAIFA"]
DESTS = ["ROTTERDAM", "SINGAPORE", "SANTOS", "BUSAN"]
SKUS = ["SKU-101", "SKU-207", "SKU-330", "SKU-410", "SKU-555"]


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    return path


def facts(seed):
    r = random.Random(1000 + seed)
    return {"shipment_id": f"S-{200 + seed}",
            "origin": r.choice(ORIGINS), "destination": r.choice(DESTS),
            "weight_kg": round(r.uniform(50, 900), 1),
            "items": [{"sku": s, "qty": r.randint(1, 9)}
                      for s in r.sample(SKUS, 3)]}


def emit(task_id, fmt, t):
    items = t["items"]
    if fmt == "csv":
        det = "\n".join(f"{i['sku']}:{i['qty']}" for i in items)
        return (f"input.csv",
                f"ship_id,from,to,weight_kg\n{t['shipment_id']},{t['origin']},"
                f"{t['destination']},{t['weight_kg']}\n\nsku:qty\n{det}\n")
    if fmt == "json":
        return ("input.json", json.dumps({
            "id": t["shipment_id"],
            "route": {"src": t["origin"], "dst": t["destination"]},
            "mass_kg": t["weight_kg"],
            "contents": [{"code": i["sku"], "n": i["qty"]} for i in items],
            "notes": "handle with care"} , indent=1) + "\n")
    if fmt == "pipe":
        det = ";".join(f"{i['sku']}|{i['qty']}" for i in items)
        return ("input.psv",
                f"SID|ORG|DST|KG|DET\n{t['shipment_id']}|{t['origin']}|"
                f"{t['destination']}|{t['weight_kg']}|{det}\n")
    if fmt == "tsv":
        det = ",".join(f"{i['sku']}#{i['qty']}" for i in items)
        return ("input.tsv",
                f"SHIPID\tFROM\tTO\tWEIGHT\tITEMS\tJUNK\n{t['shipment_id']}\t"
                f"{t['origin']}\t{t['destination']}\t{t['weight_kg']}\t{det}\tzzz\n")
    if fmt == "altjson":
        return ("input.json", json.dumps({
            "shipment": t["shipment_id"], "from": t["origin"],
            "to": t["destination"], "kg": t["weight_kg"],
            "lines": [{"s": i["sku"], "q": i["qty"]} for i in items],
            "extra": [1, 2]} , indent=1) + "\n")
    if fmt == "csv-reorder":
        det = "\n".join(f"{i['qty']},{i['sku']}" for i in items)
        return ("input.csv",
                f"to,from,weight_kg,ship_id\n{t['destination']},{t['origin']},"
                f"{t['weight_kg']},{t['shipment_id']}\n\nqty,sku\n{det}\n")
    if fmt == "kv":
        det = ",".join(f"{i['sku']}={i['qty']}" for i in items)
        return ("input.env",
                f"# manifest\nSHIP={t['shipment_id']}\nORIG={t['origin']}\n"
                f"DEST={t['destination']}\nKG={t['weight_kg']}\n"
                f"ITEMS={det}\nNOISE=1\n")
    if fmt == "pipe-alt":
        det = ",".join(f"{i['qty']}x{i['sku']}" for i in items)
        return ("input.psv",
                f"DST|SID|DET|KG|ORG\n{t['destination']}|{t['shipment_id']}|"
                f"{det}|{t['weight_kg']}|{t['origin']}\n")
    if fmt == "json-flat":
        return ("input.json", json.dumps({
            "sid": t["shipment_id"], "o": t["origin"], "d": t["destination"],
            "w": t["weight_kg"],
            "i": [[i["sku"], i["qty"]] for i in items]} , indent=1) + "\n")
    if fmt == "tsv-alt":
        det = ";".join(f"{i['sku']}:{i['qty']}" for i in items)
        return ("input.tsv",
                f"X\tDEST\tSHIP\tW\tSRC\tLIST\n0\t{t['destination']}\t"
                f"{t['shipment_id']}\t{t['weight_kg']}\t{t['origin']}\t{det}\n")
    raise ValueError(fmt)


PLAN = [("s1-csv", "csv", 1), ("s2-json", "json", 2),
        ("h01", "pipe", 11), ("h02", "tsv", 12), ("h03", "altjson", 13),
        ("h04", "csv-reorder", 14), ("h05", "kv", 15), ("h06", "pipe-alt", 16),
        ("h07", "json-flat", 17), ("h08", "tsv-alt", 18),
        ("h09", "pipe", 19), ("h10", "altjson", 20)]


def gen():
    truth = {}
    made = []
    for tid, fmt, seed in PLAN:
        t = facts(seed)
        truth[tid] = t
        fn, text = emit(tid, fmt, t)
        made.append(w(f"{TASKS}/{tid}/{fn}", text))
    made.append(w(f"{TASKS}/truth.json", json.dumps(truth, indent=1) + "\n"))
    for p in made:
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        print(f"{h[:12]}  {os.path.relpath(p, HERE)}")


if __name__ == "__main__":
    gen()
