-- Instagram 账号级每日概览指标
-- 数据来源: Meta Business Suite insights/overview 页面
-- 账号: anycubicofficial, anycubic_deutschland

CREATE TABLE IF NOT EXISTS ods_social_media.ods_instagram_page_insights_daily (
    `date`                    DATE         NOT NULL  COMMENT '数据日期',
    `account_name`            VARCHAR(100) NOT NULL  COMMENT '账号名称 (anycubicofficial / anycubic_deutschland)',
    `instagram_business_id`   VARCHAR(32)  NOT NULL  COMMENT 'Instagram Business ID',
    `views`                   BIGINT       DEFAULT 0 COMMENT '展示量 (Impressions)',
    `reach`                   BIGINT       DEFAULT 0 COMMENT '覆盖人数',
    `content_interactions`    BIGINT       DEFAULT 0 COMMENT '内容互动次数',
    `follows`                 BIGINT       DEFAULT 0 COMMENT '新增关注数',
    `profile_visits`          BIGINT       DEFAULT 0 COMMENT '主页访问次数',
    `link_clicks`             BIGINT       DEFAULT 0 COMMENT '链接点击次数',
    `unfollows`               BIGINT       DEFAULT 0 COMMENT '取消关注数',
    `etl_date`                DATE         NOT NULL  COMMENT 'ETL 执行日期'
)
DUPLICATE KEY(`date`, `account_name`, `instagram_business_id`)
DISTRIBUTED BY HASH(`account_name`) BUCKETS 1
PROPERTIES (
    "replication_allocation" = "tag.location.default: 3"
);
