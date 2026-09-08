# -*- coding: utf-8 -*-
"""重新去重：优先保留 account_name 有值的行。"""
import pymysql

conn = pymysql.connect(
    host='218.245.97.251', port=9030, user='root', password='Dse#nfw7*Bb',
    database='ods_social_media', charset='utf8mb4'
)
cur = conn.cursor()

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

# INSERT OVERWRITE: 优先按 account_name 有值排序，其次按 duration 有值排序
cur.execute("""
INSERT OVERWRITE TABLE ods_instagram_post_insights_test
SELECT date, post_id, post_type, owner, account_name, duration, account_id,
       title, publish_time, thumbnail_url, views, reach, viewers, interactions,
       likes_reactions, comments, shares, saves, link_clicks, replies, new_follows,
       video_play_time_min, avg_play_time_sec, video_3s_views, instream_ads_earnings,
       etl_date
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY post_id
        ORDER BY
            CASE WHEN account_name IS NOT NULL AND account_name != '' THEN 0 ELSE 1 END,
            CASE WHEN duration IS NOT NULL AND duration != '0' AND duration != '' THEN 0 ELSE 1 END,
            publish_time DESC
    ) AS rn
    FROM ods_instagram_post_insights_test_tmp
) t WHERE rn = 1
""")
conn.commit()

# 清理临时表
cur.execute("DROP TABLE IF EXISTS ods_instagram_post_insights_test_tmp")
conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM ods_instagram_post_insights_test")
total = cur.fetchone()[0]
print("After:", total)

cur.execute(
    "SELECT SUM(CASE WHEN account_name IS NOT NULL AND account_name != '' THEN 1 ELSE 0 END) "
    "FROM ods_instagram_post_insights_test"
)
print("account_name filled:", cur.fetchone()[0])

cur.execute(
    "SELECT SUM(CASE WHEN duration IS NOT NULL AND duration != '0' AND duration != '' THEN 1 ELSE 0 END) "
    "FROM ods_instagram_post_insights_test"
)
print("duration filled:", cur.fetchone()[0])

conn.close()
print("Done!")
