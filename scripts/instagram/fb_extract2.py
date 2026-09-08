# -*- coding: utf-8 -*-
"""从 Facebook Business GraphQL 响应提取已发布帖子表格数据（完整版）
页面列映射：Likes and reactions=net_reactions, Comments=net_comments, Saves=net_saves
"""
import json, sys
from datetime import datetime

def load_blocks(path):
    c = open(path, encoding='utf-8').read()
    blocks = [b.strip() for b in c.split('\n\n') if b.strip()]
    objs = []
    for b in blocks:
        try: objs.append(json.loads(b))
        except Exception: pass
    return objs

def cell_value(cell):
    """提取单元格数值"""
    if not isinstance(cell, dict):
        return None
    r = cell.get('renderer')
    if not isinstance(r, dict):
        return None
    tn = r.get('__typename', '')
    if 'Noop' in tn:
        return None
    if 'date_time' in r:
        return r['date_time']
    res = r.get('result')
    if isinstance(res, dict):
        val = res.get('value')
        if val is not None:
            return val
        fmt = res.get('singleValueFormatter')
        if isinstance(fmt, dict):
            return fmt.get('full_formatted_result')
    return None

def extract_entity(node):
    header = node.get('header') or {}
    entity = header.get('entity') or {}
    info = entity.get('entity_info') or {}
    out = {
        'row_id': node.get('row_id'),
        'entity_type': entity.get('entity_type'),
        'title': info.get('title') or '',
        'created_at': info.get('created_at'),
        'image_uri': (info.get('image_source') or {}).get('uri') if isinstance(info.get('image_source'), dict) else None,
        'owner': None,
        'cross_posts': [],
    }
    owner = info.get('owner')
    if isinstance(owner, dict):
        oi = owner.get('entity_info') or {}
        out['owner'] = oi.get('title') or oi.get('id')
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
    metrics = {
        'views': cell_value(fields.get('views')),
        'reach': cell_value(fields.get('reach')),
        'viewers': cell_value(fields.get('viewers')),
        'interactions': cell_value(fields.get('interactions')),
        'net_reactions': cell_value(fields.get('net_reactions')),
        'net_comments': cell_value(fields.get('net_comments')),
        'shares': cell_value(fields.get('shares')),
        'net_saves': cell_value(fields.get('net_saves')),
        'link_clicks': cell_value(fields.get('link_clicks')),
        'replies': cell_value(fields.get('replies')),
        'new_follows': cell_value(fields.get('new_follows')),
        'video_play_time': cell_value(fields.get('video_play_time')),
        'video_average_play_time': cell_value(fields.get('video_average_play_time')),
        'video_three_second_views': cell_value(fields.get('video_three_second_views')),
        'instream_ads_estimated_earnings': cell_value(fields.get('instream_ads_estimated_earnings')),
    }
    row = {
        'row_id': ent['row_id'],
        'entity_type': ent['entity_type'],
        'title': ent['title'],
        'created_at': ent['created_at'],
        'image_uri': ent['image_uri'],
        'owner': ent['owner'],
        'cross_posts': ent['cross_posts'],
        'metrics': metrics,
    }
    return row

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'fb_20rows_full2.json'
    objs = load_blocks(path)
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
    for r in rows:
        m = r['metrics']
        print('|'.join([str(r['row_id']), r['entity_type'], (r['owner'] or ''),
                        datetime.fromtimestamp(r['created_at']).strftime('%m-%d %H:%M') if r['created_at'] else '',
                        str(m['views']), str(m['reach']), str(m['viewers']), str(m['interactions']),
                        str(m['net_reactions']), str(m['net_comments']), str(m['shares']), str(m['net_saves']),
                        str(m['link_clicks']), str(m['replies']), str(m['new_follows'])]))
    with open('fb_rows_final.json', 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print('saved fb_rows_final.json')
