import json
c = open('fb_20rows_full2.json', encoding='utf-8').read()
blocks = [b.strip() for b in c.split('\n\n') if b.strip()]
for b in blocks:
    try:
        o = json.loads(b)
    except:
        continue
    t = (o.get('data') or {}).get('tofu_unified_table') or {}
    content = t.get('content') or {}
    if not (isinstance(content, dict) and content.get('edges')):
        continue
    node = content['edges'][0]['node']
    fields = node.get('fields') or {}
    print('field count:', len(fields))
    for k in sorted(fields.keys()):
        cell = fields.get(k)
        if not isinstance(cell, dict):
            print('  str cell:', k, repr(cell)[:80]); continue
        r = cell.get('renderer')
        if not isinstance(r, dict):
            print('  str renderer:', k, repr(r)[:80]); continue
        tn = r.get('__typename', '')
        if 'Noop' in tn:
            continue
        res = r.get('result')
        val = None
        fmt = None
        if isinstance(res, dict):
            val = res.get('value')
            fmt = res.get('singleValueFormatter')
            if isinstance(fmt, dict):
                fmt = fmt.get('full_formatted_result')
        if 'date_time' in r:
            print('  ', k, '= date:', r['date_time'])
        else:
            print('  ', k, '=', val if val is not None else fmt)
    break
