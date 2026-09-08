# -*- coding: utf-8 -*-
"""用 INSERT OVERWRITE 去重清理表数据（保留每个 post_id 最新的一行）。"""
import pymysql

conn = pymysql.connect(
    host='218.245.97.251', port=9030, user='root', password='Dse#nfw7*Bb',
    database='ods_social_media', charset='utf8mb4'
)
cur = conn.cursor()

# 先看当前状态
cur.execute("SELECT COUNT(*) FROM ods_instagram_post_insights_test")
print("清理前总行数:", cur.fetchone()[0])

cur.execute("SELECT COUNT(DISTINCT post_id) FROM ods_instagram_post_insights_test")
print("去重 post_id 数:", cur.fetchone()[0])

# Doris DUPLICATE KEY 表不支持 INSERT OVERWRITE 带子查询，
# 需要用临时表中转
cur.execute("DROP TABLE IF EXISTS ods_instagram_post_insights_test_dedup")
cur.execute("""
CREATE TABLE ods_instagram_post_insights_test_dedup
DUPLICATE KEY(date, post_id)
DISTRIBUTED BY HASH(date) BUCKETS 10
AS SELECT * FROM ods_instagram_post_insights_test
""")
conn.commit()
print("临时表已创建")

# 用 INSERT OVERWRITE 写回去重后的数据
# 通过窗口函数取每个 post_id 的最后一行（按 publish_time 或 etl_date 排序）
cur.execute("""
INSERT OVERWRITE TABLE ods_instagram_post_insights_test
SELECT date, post_id, post_type, owner, account_name, duration, account_id,
       title, publish_time, thumbnail_url, views, reach, viewers, interactions,
       likes_reactions, comments, shares, saves, link_clicks, replies, new_follows,
       video_play_time_min, avg_play_time_sec, video_3s_views, instream_ads_earnings,
       etl_date
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY etl_date DESC, publish_time DESC) AS rn
    FROM ods_instagram_post_insights_test_dedup
) t WHERE rn = 1
""")
conn.commit()
print("INSERT OVERWRITE 完成")

# 清理临时表
cur.execute("DROP TABLE IF EXISTS ods_instagram_post_insights_test_dedup")
conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM ods_instagram_post_insights_test")
print("清理后总行数:", cur.fetchone()[0])

cur.execute(
    "SELECT SUM(CASE WHEN account_name IS NOT NULL AND account_name != '' THEN 1 ELSE 0 END) "
    "FROM ods_instagram_post_insights_test"
)
print("account_name 有值行数:", cur.fetchone()[0])

conn.close()
print("完成!")
