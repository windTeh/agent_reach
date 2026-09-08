# -*- coding: utf-8 -*-
"""
Twitter/X 帖子分析数据（Excel）导入 Doris

读取 Twitter Analytics 导出的帖子分析 Excel（Posts Analytics），写入
ods_social_media 库的 ods_twitter_posts_analytics 表。

表设计:
  - 主键: page_name + post_id（同一页面帖子ID唯一）
  - 新增 page_name 列，标识数据来源页面（如 @anycubic3dprint）
  - UNIQUE KEY 模型，重复运行自动覆盖更新

用法:
    # 默认导入 @anycubic3dprint 的 Excel
    python sinker/Twitter/twitter_to_doris.py

    # 指定文件与页面名
    python sinker/Twitter/twitter_to_doris.py --file E:/xxx/xxx.xlsx --page-name @xxx

    # 打印建表语句
    python sinker/Twitter/twitter_to_doris.py --create-table
"""
import argparse
import configparser
import datetime
import json
import os
import sys

import pandas as pd
import requests

try:
    import pymysql
except ImportError:
    pymysql = None

CONFIG_PATH = os.path.join(os.path.split(__file__)[0], '..', '..', 'config', 'credentials.ini')
DORIS_DATABASE = 'ods_social_media'

DEFAULT_FILE = r'E:\CCProject\agent_reach\scripts\twitter\anycubic3dprint.xlsx'
DEFAULT_PAGE_NAME = '@anycubic3dprint'

# ==================== 表结构配置 ====================

TABLE_CONFIG = {
    'table_name': 'ods_twitter_posts_analytics',
    'comment': 'Twitter/X帖子分析数据',
    'pk': 'page_name,post_id',
    'columns': [
        ('date', 'date', '数据日期'),
        ('page_name', 'VARCHAR(100)', '页面名称'),
        ('post_id', 'VARCHAR(50)', '帖子ID'),
        ('post_date', 'DATETIME', '发布时间'),
        ('post_text', 'STRING', '帖子内容'),
        ('post_link', 'VARCHAR(500)', '帖子链接'),
        ('impressions', 'BIGINT', '曝光次数'),
        ('likes', 'BIGINT', '点赞数'),
        ('engagements', 'BIGINT', '互动数'),
        ('bookmarks', 'BIGINT', '收藏数'),
        ('shares', 'BIGINT', '分享数'),
        ('new_follows', 'BIGINT', '新增关注数'),
        ('replies', 'BIGINT', '回复数'),
        ('reposts', 'BIGINT', '转发数'),
        ('profile_visits', 'BIGINT', '主页访问数'),
        ('detail_expands', 'BIGINT', '详情展开数'),
        ('url_clicks', 'BIGINT', '链接点击数'),
        ('hashtag_clicks', 'BIGINT', '话题标签点击数'),
        ('permalink_clicks', 'BIGINT', '永久链接点击数'),
        ('etl_date', 'DATE', '写入日期'),
    ],
}

# Excel 列名 -> Doris 列名映射（数值列）
NUMERIC_COLUMN_MAP = [
    ('Impressions', 'impressions'),
    ('Likes', 'likes'),
    ('Engagements', 'engagements'),
    ('Bookmarks', 'bookmarks'),
    ('Shares', 'shares'),
    ('New follows', 'new_follows'),
    ('Replies', 'replies'),
    ('Reposts', 'reposts'),
    ('Profile visits', 'profile_visits'),
    ('Detail Expands', 'detail_expands'),
    ('URL Clicks', 'url_clicks'),
    ('Hashtag Clicks', 'hashtag_clicks'),
    ('Permalink Clicks', 'permalink_clicks'),
]


# ==================== 建表 SQL ====================

def generate_create_table_sql() -> str:
    """生成 Doris 建表 SQL（表与列均带 COMMENT）"""
    table_config = TABLE_CONFIG
    table_name = table_config['table_name']
    pk = table_config['pk']
    comment = table_config['comment']

    column_defs = []
    for col_name, col_type, col_comment in table_config['columns']:
        column_defs.append(f"    `{col_name}` {col_type} COMMENT '{col_comment}'")

    columns_str = ",\n".join(column_defs)
    pk_columns = [c.strip() for c in pk.split(',')]
    pk_str = ','.join(f"`{c}`" for c in pk_columns)

    sql = f"""CREATE TABLE IF NOT EXISTS `{table_name}` (
{columns_str}
) ENGINE=OLAP
UNIQUE KEY({pk_str})
COMMENT '{comment}'
DISTRIBUTED BY HASH(`{pk_columns[0]}`) BUCKETS 3
PROPERTIES (
    "replication_allocation" = "tag.location.default: 3"
);"""
    return sql


# ==================== 配置加载 ====================

def load_doris_config():
    """从 credentials.ini 加载 Doris 连接配置"""
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH, encoding='utf-8')

    return {
        'host': config.get('doris', 'host', fallback='localhost'),
        'be_port': config.get('doris', 'be_port', fallback='8040'),
        'fe_port': config.get('doris', 'fe_port', fallback='9030'),
        'user': config.get('doris', 'user', fallback='root'),
        'password': config.get('doris', 'password', fallback=''),
        'database': DORIS_DATABASE,
    }


# ==================== 数据转换 ====================

def _norm_datetime(val):
    """'YYYY-MM-DD HH:MM' 字符串 -> Doris DATETIME 字符串（补齐秒）"""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    try:
        dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M')
    except ValueError:
        try:
            dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def _to_bigint(val):
    """数值 -> int（NaN/空 -> 0）"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def read_excel_rows(excel_file, page_name, etl_date):
    """读取 Excel 并转换为 Doris 行格式"""
    df = pd.read_excel(excel_file, dtype={'Post id': str})

    rows = []
    for _, r in df.iterrows():
        row = {
            'date': etl_date,
            'page_name': page_name,
            'post_id': str(r.get('Post id') or '').strip(),
            'post_date': _norm_datetime(r.get('Date')),
            'post_text': '' if r.get('Post text') is None else str(r['Post text']),
            'post_link': '' if r.get('Post Link') is None else str(r['Post Link']).strip(),
            'etl_date': etl_date,
        }
        for excel_col, doris_col in NUMERIC_COLUMN_MAP:
            row[doris_col] = _to_bigint(r.get(excel_col))
        rows.append(row)
    return rows


# ==================== Doris 写入 ====================

class DorisStreamLoader:
    """Doris Stream Load 工具类"""

    def __init__(self, host, be_port, fe_port, user, password, database):
        self.host = host
        self.port = be_port
        self.user = user
        self.password = password
        self.database = database
        self.url = f"http://{host}:{be_port}/api/{database}"

    def stream_load(self, table_name, data_list, columns=None):
        """Stream Load 写入数据（JSON 格式）"""
        if not data_list:
            print(f"[警告] {table_name} 数据为空，跳过写入")
            return None

        json_data = json.dumps(data_list, ensure_ascii=False, default=str)

        load_url = f"{self.url}/{table_name}/_stream_load"
        headers = {
            'Content-Type': 'application/json',
            'format': 'json',
            'strip_outer_array': 'true',
            'Expect': '100-continue'
        }
        if columns:
            headers['columns'] = ','.join(columns)

        try:
            resp = requests.put(
                load_url,
                data=json_data.encode('utf-8'),
                headers=headers,
                auth=(self.user, self.password),
                timeout=600
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get('Status') == 'Success':
                print(f"[成功] {table_name} 写入 {len(data_list)} 条")
            else:
                print(f"[失败] {table_name} 写入失败: {result}")
            return result
        except Exception as e:
            print(f"[错误] {table_name} Stream Load 失败: {e}")
            return None


def ensure_table(doris_config):
    """自动建表（CREATE TABLE IF NOT EXISTS，幂等）"""
    if pymysql is None:
        print("[警告] 未安装 pymysql，跳过自动建表（请手动执行 --create-table 输出的 SQL）")
        return
    conn = None
    try:
        conn = pymysql.connect(
            host=doris_config['host'],
            port=int(doris_config['fe_port']),
            user=doris_config['user'],
            password=doris_config['password'],
            database=doris_config['database'],
        )
        with conn.cursor() as cursor:
            cursor.execute(generate_create_table_sql())
            print(f"[建表] {TABLE_CONFIG['table_name']} 已就绪")
        conn.commit()
    except Exception as e:
        print(f"[错误] 建表失败: {e}")
    finally:
        if conn:
            conn.close()


# ==================== 主流程 ====================

def main():
    parser = argparse.ArgumentParser(
        description='Twitter/X 帖子分析 Excel 导入 Doris（ods_social_media.ods_twitter_posts_analytics）'
    )
    parser.add_argument('--file', type=str, default=DEFAULT_FILE,
                        help=f'Excel 文件路径（默认: {DEFAULT_FILE}）')
    parser.add_argument('--page-name', type=str, default=DEFAULT_PAGE_NAME,
                        help=f'页面名称，写入 page_name 列（默认: {DEFAULT_PAGE_NAME}）')
    parser.add_argument('--create-table', action='store_true', help='打印建表语句后退出')
    args = parser.parse_args()

    if args.create_table:
        print("=" * 80)
        print(f"Doris 建表语句: {DORIS_DATABASE}.{TABLE_CONFIG['table_name']}")
        print("=" * 80)
        print(generate_create_table_sql())
        print()
        print(">>> 在 Doris 中执行上述 SQL 建表后，即可正常写入。")
        return

    if not os.path.isfile(args.file):
        print(f"[错误] Excel 文件不存在: {args.file}")
        return

    print("=" * 80)
    print(f"Twitter/X 帖子分析数据导入 Doris")
    print(f"Excel 文件: {args.file}")
    print(f"页面名称:   {args.page_name}")
    print(f"目标表:     {DORIS_DATABASE}.{TABLE_CONFIG['table_name']}")
    print("=" * 80)

    # 读取并转换 Excel
    print("\n>>> 读取 Excel ...")
    df_rows = read_excel_rows(
        args.file, args.page_name,
        datetime.date.today().isoformat()
    )
    print(f"    共 {len(df_rows)} 条数据")

    # 建表 + 写入
    doris_config = load_doris_config()
    # ensure_table(doris_config)
    doris = DorisStreamLoader(**doris_config)

    print(f"\n>>> 写入 Doris 表 {TABLE_CONFIG['table_name']} ...")
    result = doris.stream_load(
        TABLE_CONFIG['table_name'], df_rows,
        columns=[c[0] for c in TABLE_CONFIG['columns']]
    )

    if result is not None and result.get('Status') == 'Success':
        print("\n>>> 完成！")
    else:
        print("\n[警告] Doris 写入失败，请检查 [doris] 配置、建表是否完成、网络是否可达")


if __name__ == '__main__':
    main()
