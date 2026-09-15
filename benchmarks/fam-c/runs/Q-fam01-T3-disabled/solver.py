import json, re
with open('input.env') as f:
    content = f.read()
sections = re.findall(r'\[([^\]]+)\]\n(?:.*?\n)*?(?=\n\[|\Z)', content, re.DOTALL)
result = []
for sec in sections:
    lines = sec.strip().split('\n')
    if not lines:
        continue
    sid = lines[0].strip()
    name = usd = tags = ''
    for line in lines[1:]:
        if line.startswith('name='):
            name = line[5:]
        elif line.startswith('usd='):
            usd = line[4:]
        elif line.startswith('tags='):
            tags = line[5:]
    amount_cents = round(float(usd) * 100)
    tag_list = [t for t in tags.split('|') if t] if tags else []
    result.append({'id': sid, 'name': name, 'amount_cents': amount_cents, 'tags': tag_list})
with open('OUTPUT.json', 'w') as f:
    json.dump(result, f, indent=2)