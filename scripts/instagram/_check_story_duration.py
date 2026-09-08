# -*- coding: utf-8 -*-
"""检查 raw JSON 中 IG_STORY 行的完整结构，找 duration 相关字段。"""
import json

path = r'E:\CCProject\fb_raw_20250713_20250731_17841406045865168.json'
with open(path, encoding='utf-8') as f:
    rows = json.load(f)

# 找 IG_STORY 行
stories = [r for r in rows if r.get('entity_type') == 'IG_STORY']
print(f"IG_STORY 行数: {len(stories)}")

if stories:
    # 打印第一个 story 的所有顶层 key
    s = stories[0]
    print(f"\n== Story 示例 (row_id={s.get('row_id')}) ==")
    print(f"顶层 keys: {list(s.keys())}")
    
    # 检查 metrics
    print(f"\nmetrics keys: {list((s.get('metrics') or {}).keys())}")
    print(f"metrics: {json.dumps(s.get('metrics'), indent=2)}")
    
    # 检查所有非空字段
    print(f"\n非空字段:")
    for k, v in s.items():
        if v is not None and v != '' and v != 0 and v != {} and v != []:
            print(f"  {k}: {repr(v)[:200]}")
    
    # 检查 duration 相关字段
    print(f"\nduration 相关:")
    for k in ['duration', 'duration_in_ms', 'video_duration', 'length', 'video_length']:
        print(f"  {k}: {s.get(k, '<NOT PRESENT>')}")
    
    # 检查 metrics 中 duration 相关
    metrics = s.get('metrics') or {}
    for k in metrics:
        if 'duration' in k.lower() or 'time' in k.lower() or 'length' in k.lower():
            print(f"  metrics.{k}: {metrics[k]}")

# 也检查 IG_POST 行做对比
posts = [r for r in rows if r.get('entity_type') == 'IG_POST']
if posts:
    p = posts[0]
    print(f"\n== IG_POST 示例 (row_id={p.get('row_id')}) ==")
    print(f"duration: {p.get('duration')}")
    print(f"metrics keys: {list((p.get('metrics') or {}).keys())}")
