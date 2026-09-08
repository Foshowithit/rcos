#!/usr/bin/env python3
import sys, json

def get_path(records, path):
    cur = records
    for p in path.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur

def main():
    fmap_path, rec_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        with open(fmap_path) as f:
            fmap = json.load(f)
        with open(rec_path) as f:
            records = json.load(f)

        items_cfg = fmap.get('items', {})
        raw_items = get_path(records, items_cfg.get('__list__', 'items'))
        if raw_items is None:
            parsed_items = []
        elif isinstance(raw_items, str):
            parsed_items = json.loads(raw_items)
        else:
            parsed_items = raw_items

        items = []
        for entry in parsed_items:
            sku = str(entry[items_cfg.get('sku', 'sku')])
            q = entry[items_cfg.get('qty', 'qty')]
            items.append({'sku': sku, 'qty': int(q)})

        shipment_id = str(get_path(records, fmap['shipment_id']))
        origin = str(get_path(records, fmap['origin']))
        destination = str(get_path(records, fmap['destination']))
        weight_kg = float(get_path(records, fmap['weight_kg']))

        if not (weight_kg > 0):
            sys.exit(1)

        out = {
            'shipment_id': shipment_id,
            'origin': origin,
            'destination': destination,
            'weight_kg': weight_kg,
            'items': items,
        }

        with open(out_path, 'w') as f:
            json.dump(out, f)
            f.write('\n')

        with open(out_path) as f:
            verify = json.load(f)
        if not (verify['weight_kg'] > 0):
            sys.exit(1)
        if not isinstance(verify['items'], list):
            sys.exit(1)
        sys.exit(0)
    except Exception:
        sys.exit(1)

if __name__ == '__main__':
    main()
