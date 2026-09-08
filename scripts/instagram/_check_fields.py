# -*- coding: utf-8 -*-
"""检查指定日期范围内 Doris 数据的字段完整性。"""
import pymysql

conn = pymysql.connect(
    host='218.245.97.251', port=9030, user='root', password='Dse#nfw7*Bb',
    database='ods_social_media', charset='utf8mb4'
)
cur = conn.cursor()

START, END = '2025-07-13', '2025-07-31'

# 1. 总行数 — 用 publish_time 筛选实际数据日期
cur.execute(
    "SELECT COUNT(*) FROM ods_instagram_post_insights_test "
    "WHERE publish_time >= %s AND publish_time <= %s",
    (START + ' 00:00:00', END + ' 23:59:59')
)
total = cur.fetchone()[0]
print(f"== publish_time 在 {START} ~ {END}: 共 {total} 行 ==\n")

if total == 0:
    # 回退：看全表
    cur.execute("SELECT COUNT(*) FROM ods_instagram_post_insights_test")
    all_total = cur.fetchone()[0]
    print(f"(全表共 {all_total} 行)")
    cur.execute(
        "SELECT MIN(publish_time), MAX(publish_time) FROM ods_instagram_post_insights_test "
        "WHERE publish_time IS NOT NULL AND publish_time != ''"
    )
    mn, mx = cur.fetchone()
    print(f"publish_time 范围: {mn} ~ {mx}")
    cur.execute("SELECT DISTINCT date FROM ods_instagram_post_insights_test ORDER BY date")
    print("date 列值:", [r[0] for r in cur.fetchall()])
    if all_total == 0:
        print("无数据，退出")
        conn.close()
        exit()
    # 用全表继续检查
    total = all_total
    print(f"\n改用全表 {total} 行检查字段完整性:\n")

# 2. 逐字段统计空值/零值
str_columns = [
    'post_id', 'post_type', 'owner', 'account_name', 'account_id',
    'title', 'publish_time', 'thumbnail_url',
]
num_columns = [
    'duration', 'views', 'reach', 'viewers', 'interactions', 'likes_reactions',
    'comments', 'shares', 'saves', 'link_clicks', 'replies', 'new_follows',
    'video_play_time_min', 'avg_play_time_sec', 'video_3s_views',
    'instream_ads_earnings',
]
columns = str_columns + num_columns

hdr = '字段'
hdr2 = '有值'
hdr3 = '为空/0'
hdr4 = '有值率'
print(f"{hdr:<25s} {hdr2:>6s} {hdr3:>6s} {hdr4:>8s}")
print("-" * 50)
# 用 publish_time 筛选目标日期范围的数据
WHERE_CLAUSE = "WHERE publish_time >= %s AND publish_time <= %s"
WHERE_PARAMS = (START + ' 00:00:00', END + ' 23:59:59')

for col in columns:
    if col in str_columns:
        cond = "`{col}` IS NOT NULL AND `{col}` != ''".format(col=col)
    else:
        cond = "`{col}` IS NOT NULL AND `{col}` != 0".format(col=col)
    sql = (
        "SELECT SUM(CASE WHEN " + cond + " "
        "THEN 1 ELSE 0 END) AS has_val, COUNT(*) AS total "
        "FROM ods_instagram_post_insights_test "
        "WHERE publish_time >= %s AND publish_time <= %s"
    )
    cur.execute(sql, WHERE_PARAMS)
    row = cur.fetchone()
    has_val = int(row[0] or 0)
    pct = "%.1f%%" % (has_val / total * 100) if total else "N/A"
    empty = total - has_val
    flag = " <--" if has_val < total * 0.5 else ""
    print(f"  {col:<23s} {has_val:>6d} {empty:>6d} {pct:>8s}{flag}")

# 3. 按 post_type 分布
print("\n== 按 post_type 分布 ==")
cur.execute(
    "SELECT post_type, COUNT(*) FROM ods_instagram_post_insights_test "
    "WHERE publish_time >= %s AND publish_time <= %s "
    "GROUP BY post_type ORDER BY COUNT(*) DESC",
    WHERE_PARAMS
)
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# 4. 按 owner 分布
print("\n== 按 owner 分布 ==")
cur.execute(
    "SELECT owner, COUNT(*) FROM ods_instagram_post_insights_test "
    "WHERE publish_time >= %s AND publish_time <= %s "
    "GROUP BY owner ORDER BY COUNT(*) DESC",
    WHERE_PARAMS
)
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# 5. 抽样 5 行看完整数据
print("\n== 抽样 5 行 ==")
cur.execute(
    "SELECT post_id, owner, account_name, post_type, views, reach, "
    "interactions, likes_reactions, comments, shares, saves, replies, "
    "link_clicks, new_follows, video_play_time_min, avg_play_time_sec, "
    "video_3s_views, duration, publish_time "
    "FROM ods_instagram_post_insights_test "
    "WHERE publish_time >= %s AND publish_time <= %s LIMIT 5",
    WHERE_PARAMS
)
desc = [d[0] for d in cur.description]
for r in cur.fetchall():
    d = dict(zip(desc, r))
    print(d)

conn.close()
