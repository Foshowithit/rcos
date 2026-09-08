import json
import os
import sys

def main():
    src_dir, dst_path = sys.argv[1], sys.argv[2]
    input_path = os.path.join(src_dir, "input.json")
    with open(input_path, 'r') as f:
        data = json.load(f)
    
    records = data.get("records", [])
    result = []
    for rec in records:
        item = {
            "id": rec["code"],
            "name": rec["label"],
            "amount_cents": int(round(rec["price"]["usd"] * 100)),
            "tags": rec.get("labels", [])
        }
        result.append(item)
    
    with open(dst_path, 'w') as f:
        json.dump(result, f)

if __name__ == "__main__":
    main()