import json
import sys

def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def main():
    try:
        field_map = load(sys.argv[1])
        records = load(sys.argv[2])
        identity = field_map.get('identity') if isinstance(field_map, dict) else None
        events = records.get('events') if isinstance(records, dict) else None
        if not isinstance(events, list):
            raise ValueError('records must contain an events list')

        if identity == 'line':
            keys = []
            for event in events:
                value = event if isinstance(event, str) else event.get('line') if isinstance(event, dict) else None
                keys.append(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
        else:
            fields = identity if isinstance(identity, list) else identity.get('fields') if isinstance(identity, dict) else None
            if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
                raise ValueError('identity must be line or a list of field names')
            keys = [tuple(json.dumps(event.get(field), ensure_ascii=False, sort_keys=True, separators=(',', ':')) for field in fields) for event in events]

        total = len(events)
        unique = len(set(keys))
        result = {'total': total, 'unique': unique, 'removed': total - unique}
        with open(sys.argv[3], 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
            f.write('\n')
        return 0
    except Exception as exc:
        print('crash: ' + str(exc), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())