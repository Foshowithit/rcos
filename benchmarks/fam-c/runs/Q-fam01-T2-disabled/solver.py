import json, os
src, dst = 'V:/mnt/task', '/tmp/OUTPUT.json'
rows=[]
with open(os.path.join(src,'input.psv')) as f:
    lines=[l.strip() for l in f if l.strip()]
for line in lines[1:]:
    parts=line.split('|')
    name,id_,last=parts[0],parts[1],parts[-1]
    tags=parts[2:-1]
    cents=int(round(float(last)*100))
    rows.append({'id':id_,'name':name,'2_cents':cents,'tags':tags})
with open(dst,'w') as f:
    json.dump(rows,f,separators=(',',':'))