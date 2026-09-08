# -*- coding: utf-8 -*-
"""诊断 account_name 缺失原因。"""
import json
import os

BASE = r'E:\CCProject'

# 检查最新 raw JSON 的 _owner_id 分布
for fn in sorted(os.listdir(BASE)):
    if fn.startswith('fb_raw_20250713') and fn.endswith('.json'):
        path = os.path.join(BASE, fn)
        with open(path, encoding='utf-8') as f:
            rows = json.load(f)
        print(f'\n== {fn}: {len(rows)} rows ==')
        # _owner_id 分布
        owner_ids = {}
        missing_name = 0
        for r in rows:
            oid = r.get('_owner_id', '<MISSING>')
            owner_ids.setdefault(oid, 0)
            owner_ids[oid] += 1
            if not r.get('account_name'):
                missing_name += 1
                print(f'  NO account_name: row_id={r.get("row_id")}, _owner_id={r.get("_owner_id")}, '
                      f'owner={r.get("owner")}, post_type={r.get("entity_type")}')
        print(f'  _owner_id 分布: {owner_ids}')
        print(f'  缺少 account_name: {missing_name}/{len(rows)}')
