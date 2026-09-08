# -*- coding: utf-8 -*-
"""从 Facebook Business GraphQL 响应提取已发布帖子表格数据"""
import json, sys
from datetime import datetime, timezone

def load_blocks(path):
    c = open(path, encoding='utf-8').read()
    blocks = [b.strip() for b in c.split('\n\n') if b.strip()]
    objs = []
    for b in blocks:
        try: objs.append(json.loads(b))
        except Exception: pass
    return objs

def get_val(fields, key):
    """从 fields dict 中提取指标的数值（兼容 NoopCell 和单值 cell）"""
    cell = fields.get(key)
    if not cell: return None
    r = cell.get('renderer') or {}
    if r.get('__typename') == 'TofuUnifiedTableNoopCellDoNotRenderThis':
        return None
    result = r.get('result') or {}
    if 'value' in result:
        return result['value']
    if 'date_time' in r:
        return r['date_time']
    # 尝试 formatter
    fmt = result.get('singleValueFormatter') or {}
    return fmt.get('full_formatted_result')

def extract_entity(node):
    """提取实体信息"""
    header = node.get('header') or {}
    entity = header.get('entity') or {}
    info = entity.get('entity_info') or {}
    out = {
        'row_id': node.get('row_id'),
        'entity_type': entity.get('entity_type'),
        'title': info.get('title') or '',
        'created_at': info.get('created_at'),
        'image_uri': (info.get('image_source') or {}).get('uri') if info.get('image_source') else None,
        'owner': None,
        'cross_posts': [],
    }
    # owner info
    owner = info.get('owner')
    if owner and isinstance(owner, dict):
        oi = owner.get('entity_info') or {}
        out['owner'] = oi.get('title') or oi.get('id')
    # cross posted entities
    for cp in entity.get('cross_posted_entities') or []:
        oi = cp.get('entity_info') or {}
        out['cross_posts'].append({
            'type': cp.get('entity_type'),
            'title': oi.get('title') or '',
            'owner': ((oi.get('owner') or {}).get('entity_info') or {}).get('title'),
        })
    return out

def extract_row(node):
    fields = node.get('fields') or {}
    ent = extract_entity(node)
    row = {
        'row_id': ent['row_id'],
        'entity_type': ent['entity_type'],
        'title': ent['title'],
        'created_at': ent['created_at'],
        'image_uri': ent['image_uri'],
        'owner': ent['owner'],
        'cross_posts': ent['cross_posts'],
        'metrics': {k: get_val(fields, k) for k in [
            'views', 'reach', 'viewers', 'interactions', 'reactions', 'comments',
            'shares', 'saves', 'link_clicks', 'replies', 'new_follows',
            'video_play_time', 'video_average_play_time', 'video_three_second_views',
            'instream_ads_estimated_earnings', 'video_one_minute_views', 'results',
        ]},
    }
    return row

if __name__ == '__main__':
    objs = load_blocks('fb_20rows_full.json')
    content = None
    for o in objs:
        t = (o.get('data') or {}).get('tofu_unified_table') or {}
        if isinstance(t.get('content'), dict) and 'edges' in t['content']:
            content = t['content']
            break
    if not content:
        print('NO CONTENT'); sys.exit(1)
    rows = [extract_row(e['node']) for e in content['edges']]
    print('total rows:', len(rows))
    for r in rows[:5]:
        print('---')
        print('id:', r['row_id'], '| type:', r['entity_type'], '| owner:', r['owner'])
        print('created:', datetime.fromtimestamp(r['created_at']).strftime('%Y-%m-%d %H:%M') if r['created_at'] else None)
        print('title:', (r['title'] or '')[:80])
        print('metrics:', json.dumps(r['metrics'], ensure_ascii=False))
    # save
    with open('fb_rows_extracted.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print('saved fb_rows_extracted.json')
