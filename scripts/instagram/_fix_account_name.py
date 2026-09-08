# -*- coding: utf-8 -*-
"""通过 INSERT OVERWRITE 直接按 owner 字段补全 Doris 中的 account_name。"""
import pymysql

conn = pymysql.connect(
    host='218.245.97.251', port=9030, user='root', password='Dse#nfw7*Bb',
    database='ods_social_media', charset='utf8mb4'
)
cur = conn.cursor()

# owner -> account_name 映射
OWNER_NAME_MAP = {
    'anycubicofficial': 'ANYCUBIC',
    'anycubic_deutschland': 'Anycubic Deutschland',
}

cur.execute("SELECT COUNT(*) FROM ods_instagram_post_insights_test")
print("Before:", cur.fetchone()[0])

# 创建临时表
cur.execute("DROP TABLE IF EXISTS ods_instagram_post_insights_test_tmp")
cur.execute("""
CREATE TABLE ods_instagram_post_insights_test_tmp
DUPLICATE KEY(date, post_id)
DISTRIBUTED BY HASH(date) BUCKETS 10
AS SELECT * FROM ods_instagram_post_insights_test
""")
conn.commit()

# INSERT OVERWRITE: 用 CASE WHEN 按 owner 补全 account_name
cur.execute("""
INSERT OVERWRITE TABLE ods_instagram_post_insights_test
SELECT
    date, post_id, post_type, owner,
    CASE
        WHEN account_name IS NOT NULL AND account_name != '' THEN account_name
        WHEN owner = 'anycubicofficial' THEN 'ANYCUBIC'
        WHEN owner = 'anycubic_deutschland' THEN 'Anycubic Deutschland'
        ELSE account_name
    END AS account_name,
    duration, account_id, title, publish_time, thumbnail_url,
    views, reach, viewers, interactions, likes_reactions, comments, shares,
    saves, link_clicks, replies, new_follows, video_play_time_min,
    avg_play_time_sec, video_3s_views, instream_ads_earnings, etl_date
FROM ods_instagram_post_insights_test_tmp
""")
conn.commit()

cur.execute("DROP TABLE IF EXISTS ods_instagram_post_insights_test_tmp")
conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM ods_instagram_post_insights_test")
total = cur.fetchone()[0]
cur.execute(
    "SELECT SUM(CASE WHEN account_name IS NOT NULL AND account_name != '' THEN 1 ELSE 0 END) "
    "FROM ods_instagram_post_insights_test"
)
filled = cur.fetchone()[0]
print(f"After: {total} rows, account_name filled: {filled} ({filled/total*100:.1f}%)")

# 按 owner 检查
cur.execute("""
SELECT owner, COUNT(*) AS total,
       SUM(CASE WHEN account_name IS NOT NULL AND account_name != '' THEN 1 ELSE 0 END) AS filled
FROM ods_instagram_post_insights_test
GROUP BY owner ORDER BY total DESC
""")
for r in cur.fetchall():
    pct = r[2] / r[1] * 100 if r[1] else 0
    print(f"  {r[0]}: {r[2]}/{r[1]} ({pct:.0f}%)")

conn.close()
print("Done!")
