# -*- coding: utf-8 -*-
"""检查 raw JSON 中 _owner_id 的实际值，确认是否与 ACCOUNT_NAME_MAP 的 key 匹配。"""
import json

path = r'E:\CCProject\fb_raw_20250713_20250731_17841406045865168.json'
with open(path, encoding='utf-8') as f:
    rows = json.load(f)

print(f"总行数: {len(rows)}")
print("\n前 5 行的关键字段:")
for r in rows[:5]:
    print(f"  row_id={r.get('row_id')}, _owner_id={r.get('_owner_id')}, "
          f"owner={r.get('owner')}, account_name={r.get('account_name')!r}, "
          f"entity_type={r.get('entity_type')}")

# 检查 _owner_id 的唯一值
owner_ids = set()
for r in rows:
    owner_ids.add(r.get('_owner_id'))
print(f"\n_owner_id 唯一值: {owner_ids}")

# 检查静态映射的 key 是否在 owner_ids 中
ACCOUNT_NAME_MAP = {
    '17841406045865168': 'ANYCUBIC',
    '17841414725872019': 'Anycubic Deutschland',
}
for key, name in ACCOUNT_NAME_MAP.items():
    match = key in owner_ids
    print(f"  ACCOUNT_NAME_MAP key '{key}' -> '{name}': 匹配={match}")
