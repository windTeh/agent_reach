# -*- coding: utf-8 -*-
"""
抓取 Instagram 主页（账号）级洞察数据，Stream Load 写入 Doris 表 ods_instagram_page_insights。

数据源：Instagram Graph API  /{ig-user-id}/insights （账号级，period=day）。

指标映射（账号级）：
  报告日期 report_date      -> 各指标 value 的 end_time 日期（Meta 按太平洋时区切日）
  Views                    -> views        （新指标，已替代废弃的 impressions）
  Reach                    -> reach
  Content interactions     -> total_interactions
  Follows                  -> follows_and_unfollows.value.follows
  Unfollows                -> follows_and_unfollows.value.unfollows
  Net follows              -> follows - unfollows（脚本计算得出）
  Link clicks              -> profile_links_taps
  Visits                   -> profile_views

用法：
  # 拉取某个日期区间的两个内置账号并写入 Doris
  python fetch_instagram_page_insights.py --start-date 2026-08-20 --end-date 2026-08-26

  # 预览数据、不写 Doris（调试用）
  python fetch_instagram_page_insights.py --start-date 2026-08-20 --end-date 2026-08-26 --dry-run

  # 指定其他账号（username 或 username:id 逗号分隔）
  python fetch_instagram_page_insights.py --start-date 2026-08-20 --end-date 2026-08-26 \
      --accounts anycubicofficial:17841406045865168,anycubic_deutschland:17841414725872019

依赖：
  - 仅标准库（urllib / json / configparser），无第三方包。
  - 一个能访问目标 IG 账号的 Instagram Graph API 访问令牌（建议用长期 page access token）。
    提供方式三选一（优先级从高到低）：
      1) --access-token 命令行参数
      2) 环境变量 IG_ACCESS_TOKEN
      3) 配置文件 [instagram] access_token（默认 E:\\CCProject\\agent_reach\\config\\credentials.ini）

注意：
  - 若你的账号 Insights 仍以 impressions 作为 Views（旧账号），把 FETCH_METRICS 里的
    'views' 改成 'impressions'，或通过 --metrics 覆盖。
  - 数据存在 24~48 小时处理延迟，今天的数据通常要次日才能取到。

Doris 目标表 DDL（供参考）：
  CREATE TABLE ods_social_media.ods_instagram_page_insights (
      report_date         DATE        COMMENT '报告日期',
      account_id          VARCHAR(64) COMMENT 'Instagram business account id',
      account_username    VARCHAR(128) COMMENT 'Instagram username',
      views               BIGINT      COMMENT '浏览量',
      reach               BIGINT      COMMENT '触达',
      content_interactions BIGINT     COMMENT '内容互动',
      follows             BIGINT      COMMENT '新增关注',
      unfollows           BIGINT      COMMENT '取消关注',
      net_follows         BIGINT      COMMENT '净关注',
      link_clicks         BIGINT      COMMENT '链接点击',
      visits              BIGINT      COMMENT '主页访问',
      etl_date            DATE        COMMENT 'ETL 日期'
  ) ...;
"""

import argparse
import base64
import calendar
import configparser
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = os.path.dirname(os.path.abspath(__file__))
# 默认配置文件：E:\CCProject\agent_reach\config\credentials.ini
# DEFAULT_CONFIG = str(Path(BASE).resolve().parents[2] / 'config' / 'credentials.ini')
DEFAULT_CONFIG = 'E:\\CCProject\\agent_reach\\config\\credentials.ini'


# 已知账号：username -> Instagram business account id
KNOWN_ACCOUNTS = {
    'anycubicofficial': '17841406045865168',
    'anycubic_deutschland': '17841414725872019',
}
DEFAULT_ACCOUNTS = 'anycubicofficial,anycubic_deutschland'

# 账号级 insights 指标（period=day）。
# Views 用新指标 views（已替代废弃的 impressions）；旧账号若仍返回 impressions，改这里或用 --metrics 覆盖。
FETCH_METRICS = [
    'reach',
    'views',
    'total_interactions',
    'follows_and_unfollows',
    'profile_views',
    'profile_links_taps',
]

# Doris 目标列（顺序需与表结构一致，也用于 Stream Load 的 columns 头）
DORIS_COLUMNS = [
    'report_date', 'account_id', 'account_username',
    'views', 'reach', 'content_interactions', 'follows', 'unfollows',
    'net_follows', 'link_clicks', 'visits', 'etl_date',
]

DORIS_TABLE = 'ods_instagram_page_insights'
DORIS_DATABASE = 'ods_social_media'

GRAPH_API_VERSION = 'v23.0'
GRAPH_BASE = 'https://graph.facebook.com'

# 可重试（瞬时）的 Graph API 错误码：限流/临时/系统繁忙等
RETRYABLE_ERROR_CODES = {1, 2, 4, 17, 32, 341, 368, 80000, 80001}


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------
def load_config(config_path):
    parser = configparser.ConfigParser()
    if not parser.read(config_path, encoding='utf-8'):
        raise ValueError('无法读取配置文件: %s' % config_path)

    doris = {}
    if parser.has_section('doris'):
        for key in ('host', 'be_port', 'user', 'password', 'database'):
            if parser.get('doris', key, fallback=''):
                doris[key] = parser.get('doris', key).strip()

    instagram = {}
    if parser.has_section('instagram'):
        for key in ('access_token', 'app_id', 'app_secret', 'api_version'):
            if parser.get('instagram', key, fallback=''):
                instagram[key] = parser.get('instagram', key).strip()

    return doris, instagram


def require_doris(doris):
    missing = [k for k in ('host', 'be_port', 'user', 'password') if not doris.get(k)]
    if missing:
        raise ValueError('缺少 Doris 配置: %s（请检查 [doris] 段）' % ', '.join(missing))
    return doris


# ---------------------------------------------------------------------------
# 账号解析
# ---------------------------------------------------------------------------
def parse_accounts(value):
    """解析账号列表，返回 [(ig_user_id, username), ...]，保持输入顺序。

    支持三种写法：
      - username                -> 查 KNOWN_ACCOUNTS（未知则报错）
      - username:id             -> 显式指定 business id
      - id                      -> 纯 id（username 反查，查不到填空）
    """
    if value is None:
        names = [n.strip() for n in DEFAULT_ACCOUNTS.split(',') if n.strip()]
    else:
        names = [n.strip() for n in value.split(',') if n.strip()]
    if not names:
        raise ValueError('--accounts 必须至少包含一个账号')

    reverse = {v: k for k, v in KNOWN_ACCOUNTS.items()}
    accounts = []
    for item in names:
        if ':' in item:
            username, _, ig_id = item.partition(':')
            username = username.strip()
            ig_id = ig_id.strip()
            if not ig_id:
                raise ValueError('账号 %r 缺少 business id' % item)
        elif item in KNOWN_ACCOUNTS:
            username, ig_id = item, KNOWN_ACCOUNTS[item]
        elif item in reverse:
            username, ig_id = reverse[item], item
        else:
            # 纯数字 id 兜底
            if item.isdigit():
                username, ig_id = reverse.get(item, ''), item
            else:
                raise ValueError('未知账号 %r（不在 KNOWN_ACCOUNTS 中，请用 username:id 显式指定）' % item)
        accounts.append((ig_id, username))
    return accounts


def parse_date_range(start_date, end_date):
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('--start-date / --end-date 必须为 YYYY-MM-DD') from exc
    if start > end:
        raise ValueError('--start-date 不能晚于 --end-date')
    return start, end


def iter_chunks(start_date, end_date, chunk_days):
    """把日期区间切成不超过 chunk_days 天的小窗口，规避 insights 区间上限。"""
    d = start_date
    while d <= end_date:
        chunk_end = min(d + timedelta(days=chunk_days - 1), end_date)
        yield d, chunk_end
        d = chunk_end + timedelta(days=1)


# ---------------------------------------------------------------------------
# Graph API 调用
# ---------------------------------------------------------------------------
def graph_get(url, timeout=60, retries=3):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with urlopen(url, timeout=timeout) as resp:
                body = resp.read().decode('utf-8')
                return json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace')
            try:
                payload = json.loads(body)
            except ValueError:
                payload = {}
            code = (payload.get('error') or {}).get('code')
            if code in RETRYABLE_ERROR_CODES and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError('Graph API HTTP %s: %s' % (exc.code, body)) from exc
        except (URLError, OSError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
    raise RuntimeError('Graph API 请求失败: %s' % last_exc)


def fetch_insights(ig_user_id, access_token, api_version, since_ts, until_ts, metrics):
    """调用 /{ig-user-id}/insights，返回 data 列表 [{name, period, values:[{end_time, value}]}]。"""
    params = urlencode({
        'metric': ','.join(metrics),
        'period': 'day',
        'since': since_ts,
        'until': until_ts,
        'access_token': access_token,
    })
    url = '%s/%s/%s/insights?%s' % (GRAPH_BASE, api_version, ig_user_id, params)
    data = graph_get(url)
    if 'data' not in data:
        raise RuntimeError('Graph API 返回异常: %s' % json.dumps(data, ensure_ascii=False)[:300])
    return data['data']


# ---------------------------------------------------------------------------
# 指标合并
# ---------------------------------------------------------------------------
def merge_metric_data(daily, metric_data):
    """把一次 insights 响应合并进 daily（daily: report_date -> 指标 dict）。"""
    for metric in metric_data:
        name = metric.get('name')
        for item in metric.get('values', []):
            end_time = item.get('end_time') or ''
            day = end_time[:10]
            if not day:
                continue
            val = item.get('value')
            row = daily.setdefault(day, {})
            if name == 'follows_and_unfollows':
                if isinstance(val, dict):
                    row['follows'] = val.get('follows', 0)
                    row['unfollows'] = val.get('unfollows', 0)
            elif name in ('views', 'impressions'):
                row['views'] = val if val is not None else 0
            elif name == 'reach':
                row['reach'] = val
            elif name == 'total_interactions':
                row['content_interactions'] = val
            elif name in ('profile_links_taps', 'website_clicks'):
                row['link_clicks'] = val
            elif name == 'profile_views':
                row['visits'] = val


def fetch_account_daily(ig_user_id, username, access_token, api_version,
                        start_date, end_date, metrics, chunk_days=30):
    """分窗口抓取单账号 daily 指标，返回 daily dict（report_date -> 指标 dict）。"""
    daily = {}
    for chunk_start, chunk_end in iter_chunks(start_date, end_date, chunk_days):
        since_ts = calendar.timegm(chunk_start.timetuple())
        until_ts = calendar.timegm(chunk_end.timetuple()) + 86400 - 1
        metric_data = fetch_insights(ig_user_id, access_token, api_version,
                                     since_ts, until_ts, metrics)
        merge_metric_data(daily, metric_data)
        print('    [%s] %s ~ %s 抓取完成' % (username, chunk_start, chunk_end), flush=True)
        time.sleep(0.3)
    return daily


def build_rows(daily, ig_user_id, username, start_date, end_date, execution_date):
    """把 daily dict 转成 Doris 行，并按 [start_date, end_date] 过滤。"""
    rows = []
    for day in sorted(daily.keys()):
        try:
            d = datetime.strptime(day, '%Y-%m-%d').date()
        except ValueError:
            continue
        if d < start_date or d > end_date:
            continue
        r = daily[day]
        follows = int(r.get('follows') or 0)
        unfollows = int(r.get('unfollows') or 0)
        rows.append({
            'report_date': day,
            'account_id': ig_user_id,
            'account_username': username,
            'views': int(r.get('views') or 0),
            'reach': int(r.get('reach') or 0),
            'content_interactions': int(r.get('content_interactions') or 0),
            'follows': follows,
            'unfollows': unfollows,
            'net_follows': follows - unfollows,
            'link_clicks': int(r.get('link_clicks') or 0),
            'visits': int(r.get('visits') or 0),
            'etl_date': execution_date.isoformat(),
        })
    return rows


# ---------------------------------------------------------------------------
# Doris Stream Load
# ---------------------------------------------------------------------------
def stream_load_rows(rows, doris, database, table):
    """用 NDJSON Stream Load 写 Doris。返回 Stream Load 结果 dict。"""
    if not rows:
        return {'Status': 'Success', 'NumberLoadedRows': 0, 'Label': ''}

    host = doris['host']
    be_port = doris['be_port']
    url = 'http://%s:%s/api/%s/%s/_stream_load' % (host, be_port, database, table)

    payload = '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows).encode('utf-8')
    credentials = ('%s:%s' % (doris['user'], doris['password'])).encode('utf-8')

    request = Request(url, data=payload, method='PUT')
    request.add_header('Content-Type', 'application/json')
    request.add_header('Authorization', 'Basic ' + base64.b64encode(credentials).decode('ascii'))
    request.add_header('format', 'json')
    request.add_header('read_json_by_line', 'true')
    request.add_header('columns', ','.join(DORIS_COLUMNS))
    request.add_header('label', 'instagram_page_insights_' + uuid.uuid4().hex)

    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError('Doris Stream Load HTTP %s: %s' % (exc.code, body)) from exc
    except (URLError, OSError) as exc:
        raise RuntimeError('Doris Stream Load 请求失败: %s' % exc) from exc

    if result.get('Status') != 'Success':
        raise RuntimeError('Doris Stream Load 失败: %s' % result.get('Message', result))
    loaded_rows = int(result.get('NumberLoadedRows', 0))
    if loaded_rows != len(rows):
        raise RuntimeError('Doris Stream Load 只写入 %s / %s 行' % (loaded_rows, len(rows)))
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description='抓取 Instagram 主页洞察并 Stream Load 写入 Doris',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--start-date', required=True, metavar='YYYY-MM-DD')
    ap.add_argument('--end-date', required=True, metavar='YYYY-MM-DD')
    ap.add_argument('--accounts', default=None,
                    help='逗号分隔账号，支持 username / username:id / id；默认抓取两个内置账号')
    ap.add_argument('--access-token', default=None,
                    help='Instagram Graph API 访问令牌（优先于环境变量/配置文件）')
    ap.add_argument('--api-version', default=None, help='Graph API 版本，默认 v23.0')
    ap.add_argument('--metrics', default=None,
                    help='逗号分隔的 insights 指标（覆盖默认），如 reach,views,total_interactions')
    ap.add_argument('--config', default=DEFAULT_CONFIG, metavar='PATH', help='配置文件路径')
    ap.add_argument('--database', default=None, help='Doris 库名（默认取配置或 ods_social_media）')
    ap.add_argument('--chunk-days', type=int, default=30, help='单次请求的日期窗口天数，默认 30')
    ap.add_argument('--dry-run', action='store_true', help='只抓取并打印，不写 Doris')
    ap.add_argument('--json-out', default=None, metavar='PATH', help='可选：把结果行导出为 JSON（调试用）')
    args = ap.parse_args()

    try:
        start_date, end_date = parse_date_range(args.start_date, args.end_date)
        accounts = parse_accounts(args.accounts)
        doris, instagram = load_config(args.config)
    except ValueError as exc:
        ap.error(str(exc))

    # 解析 token / 版本 / 指标
    access_token = (args.access_token
                    or os.environ.get('IG_ACCESS_TOKEN')
                    or instagram.get('access_token', ''))
    if not access_token:
        print('ERROR: 未找到 Instagram Graph API access token。'
              '请通过 --access-token / 环境变量 IG_ACCESS_TOKEN / 配置 [instagram] access_token 提供。',
              file=sys.stderr)
        return 2

    api_version = (args.api_version
                   or os.environ.get('IG_API_VERSION')
                   or instagram.get('api_version')
                   or GRAPH_API_VERSION)
    metrics = [m.strip() for m in (args.metrics or ','.join(FETCH_METRICS)).split(',') if m.strip()]

    database = args.database or doris.get('database') or DORIS_DATABASE

    print('=' * 64)
    print('Instagram 主页洞察抓取 -> Doris 表 %s.%s' % (database, DORIS_TABLE))
    print('=' * 64)
    print('日期区间 : %s ~ %s' % (start_date, end_date))
    print('账号数量 : %d' % len(accounts))
    print('指标     : %s' % ', '.join(metrics))
    print('API 版本 : %s' % api_version)
    print('模式     : %s' % ('dry-run（不写库）' if args.dry_run else 'Stream Load 写库'))
    print('-' * 64)

    execution_date = date.today()
    failures = []
    all_rows = []
    loaded_total = 0

    for ig_id, username in accounts:
        try:
            print('\n== @%s (%s) ==' % (username or ig_id, ig_id))
            daily = fetch_account_daily(ig_id, username, access_token, api_version,
                                        start_date, end_date, metrics, args.chunk_days)
            rows = build_rows(daily, ig_id, username, start_date, end_date, execution_date)
            print('  合并出 %d 行日报数据' % len(rows))
            all_rows.extend(rows)

            if args.dry_run:
                for r in rows:
                    print('    %s views=%s reach=%s interactions=%s '
                          'follows=%s unfollows=%s net=%s link=%s visits=%s'
                          % (r['report_date'], r['views'], r['reach'],
                             r['content_interactions'], r['follows'], r['unfollows'],
                             r['net_follows'], r['link_clicks'], r['visits']))
                continue

            if not rows:
                print('  无数据，跳过写库')
                continue

            require_doris(doris)
            result = stream_load_rows(rows, doris, database, DORIS_TABLE)
            loaded = int(result.get('NumberLoadedRows', 0))
            loaded_total += loaded
            print('  账号 @%s: 写入 Doris loaded=%d, filtered=%s, unselected=%s'
                  % (username, loaded,
                     result.get('NumberFilteredRows', 0), result.get('NumberUnselectedRows', 0)))
        except (RuntimeError, ValueError) as exc:
            failures.append('%s: %s' % (username or ig_id, exc))
            print('ERROR [%s]: %s' % (username or ig_id, exc), file=sys.stderr)

    if args.json_out and all_rows:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(all_rows, f, ensure_ascii=False, indent=2)
        print('\n结果已导出: %s (%d 行)' % (args.json_out, len(all_rows)))

    if failures:
        print('\n存在失败的账号 (%d/%d)：' % (len(failures), len(accounts)), file=sys.stderr)
        for fail in failures:
            print('  - ' + fail, file=sys.stderr)
        return 1

    if args.dry_run:
        print('\n[dry-run] 共生成 %d 行（未写库）' % len(all_rows))
    else:
        print('\n全部完成：共写入 %d 行到 Doris 表 %s.%s'
              % (loaded_total, database, DORIS_TABLE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
