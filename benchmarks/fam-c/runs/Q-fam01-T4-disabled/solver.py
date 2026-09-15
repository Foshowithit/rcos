import csv, json
src='input.csv'
dst='OUTPUT.json'
records=[]
with open(src, newline='') as f:
    for row in csv.DictReader(f):
        try:
            amt=float(row['amount_usd'])
        except (ValueError, TypeError):
            continue
        records.append({'id':row['id'],'name':row['name'],'amount_cents':int(round(amt*100)),'tags':[t for t in row['tags'].split(',') if t]})
with open(dst,'w') as f:
    json.dump(records,f,separators=(',',':'))