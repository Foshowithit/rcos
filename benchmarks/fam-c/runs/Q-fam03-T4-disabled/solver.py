import json, pathlib
p = pathlib.Path('events.txt')
lines = p.read_text().splitlines()
total = len(lines)
unique = len(set(lines))
removed = total - unique
(pathlib.Path('OUTPUT.json').write_text(json.dumps({'total': total, 'unique': unique, 'removed': removed})))