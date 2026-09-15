import json, os, glob
src_dir = 'pages'
output = {}
cur = 'r1'
while cur:
    path = os.path.join(src_dir, f'{cur}.json')
    with open(path) as f:
        page = json.load(f)
    for item in page['data']:
        output[item['product']] = item['count']
    cur = page['paging']['next']
with open('OUTPUT.json', 'w') as f:
    json.dump(output, f)