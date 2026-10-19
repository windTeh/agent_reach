# -*- coding: utf-8 -*-
"""
Fetch ACCOUNT-LEVEL (page) daily analytics for @anycubic3dprint via X Analytics
(Delegate account accessed through @Anycubic2024's Chrome session via OpenCLI).

指标（与 X Analytics「Download CSV」导出完全一致）:
  Date, Impressions, Likes, Engagements, Bookmarks, Shares, New follows,
  Unfollows, Replies, Reposts, Profile visits, Create Post, Video views,
  Media views

Output: Doris Stream Load into ods_social_media.ods_twitter_page_analytics
  (UNIQUE KEY 模型，重复运行自动覆盖更新，只增改、绝不删除)

实现原理:
  1. 打开 https://x.com/i/account_analytics/overview
  2. 通过页面日期范围选择器(Date range picker)设定窗口，触发
     accountOverviewDailyQuery 重新加载
  3. 注入 URL.createObjectURL 钩子，点击「Download CSV」在内存中截获
     CSV 内容（无需真实落盘下载）
  4. 解析 CSV -> 校验日期窗口 -> 写入 Doris

Usage:
  python fetch_anycubic3dprint_page_analytics.py --start-date 2026-05-01 --end-date 2026-08-26
  [--username anycubic3dprint] [--session ar]
      [--window-days 90] [--doris-config ../../config/credentials.ini]
      [--no-ensure-table] [--csv-out out.csv] [--create-table]

Prerequisites:
  - Chrome running with OpenCLI extension connected, logged in as @Anycubic2024
  - Delegate access to @anycubic3dprint (Admin role) already granted

注意事项:
  - X 自定义日期范围上限约 90 天(3M)，脚本自动按 --window-days(默认90,
    上限90)分窗抓取
  - 本脚本只做 CREATE TABLE IF NOT EXISTS / Stream Load 追加(UNIQUE KEY
    upsert)，绝不执行 DELETE / DROP 等删除类操作
"""
import argparse
import base64
import configparser
import csv
import io
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# NODE = r'C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2\node.exe'
# MAIN = (r'C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2'
#         r'\node_modules\@jackwener\opencli\dist\src\main.js')

NODE = r"D:\Program Files\nodejs\node.exe"
MAIN = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"


OVERVIEW_URL = 'https://x.com/i/account_analytics/overview'
MAX_WINDOW_DAYS = 90  # X 自定义日期范围上限（超过会报 Something went wrong）

CSV_COLUMNS = ['Date', 'Impressions', 'Likes', 'Engagements', 'Bookmarks',
              'Shares', 'New follows', 'Unfollows', 'Replies', 'Reposts',
              'Profile visits', 'Create Post', 'Video views', 'Media views']

DORIS_TABLE = 'ods_twitter_page_analytics'
DORIS_COLUMNS = [
    'date', 'page_name', 'impressions', 'likes', 'engagements', 'bookmarks',
    'shares', 'new_follows', 'unfollows', 'replies', 'reposts',
    'profile_visits', 'create_post', 'video_views', 'media_views', 'etl_date',
]

CREATE_TABLE_SQL = """CREATE TABLE IF NOT EXISTS ods_twitter_page_analytics (
  `date` date NOT NULL COMMENT '报告日期',
  `page_name` varchar(100) NOT NULL COMMENT '账号(如 @anycubic3dprint)',
  `impressions` bigint NULL COMMENT '曝光次数',
  `likes` bigint NULL COMMENT '点赞数',
  `engagements` bigint NULL COMMENT '互动数',
  `bookmarks` bigint NULL COMMENT '收藏数',
  `shares` bigint NULL COMMENT '分享数',
  `new_follows` bigint NULL COMMENT '新增关注数',
  `unfollows` bigint NULL COMMENT '取消关注数',
  `replies` bigint NULL COMMENT '回复数',
  `reposts` bigint NULL COMMENT '转发数',
  `profile_visits` bigint NULL COMMENT '主页访问数',
  `create_post` bigint NULL COMMENT '发帖数',
  `video_views` bigint NULL COMMENT '视频观看数',
  `media_views` bigint NULL COMMENT '媒体查看数',
  `etl_date` date NULL COMMENT '写入日期'
) ENGINE=OLAP
UNIQUE KEY(`date`, `page_name`)
COMMENT 'Twitter/X 账号层级(页面)日度分析数据'
DISTRIBUTED BY HASH(`date`) BUCKETS 3
PROPERTIES (
    "replication_allocation" = "tag.location.default: 3"
);"""

MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
             'August', 'September', 'October', 'November', 'December']


# ---------------------------------------------------------------- opencli 基础
def oc(session, *args, timeout=120):
    """Run opencli via node directly (bypasses cmd.exe quoting issues)."""
    r = subprocess.run([NODE, MAIN, 'browser', session] + list(args),
                        capture_output=True, text=True, encoding='utf-8',
                        errors='replace', timeout=timeout)
    return (r.stdout or r.stderr).strip()


def ev(session, tab, js, timeout=90):
    out = oc(session, 'eval', js, '--tab', tab, timeout=timeout)
    try:
        return json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return out


def open_url(session, tab, url):
    return oc(session, 'open', url, '--tab', tab) if tab \
        else oc(session, 'open', url)


def get_tab(session, url):
    out = oc(session, 'open', url)
    try:
        return json.loads(out).get('page')
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------- 账号切换
def switch_to_delegate(session, tab, username):
    """Switch active X account to the delegated account."""
    print(f'  Switching active account to @{username} ...')
    open_url(session, tab, 'https://x.com/home')
    time.sleep(4)
    js0 = ('(function(){var b=document.querySelector("[data-testid=SideNav_AccountSwitcher_Button]");'
           'if(b){b.click();return "opened"}return "no_button"})()')
    ev(session, tab, 'JSON.stringify(%s)' % js0)
    time.sleep(2)
    js = ('(function(){var cs=Array.from(document.querySelectorAll("[data-testid=UserCell]"));'
          'var t=cs.find(function(c){return (c.innerText||"").toLowerCase().indexOf("%s")>-1});'
          'if(t){t.click();return "clicked"}return "not_found"})()') % username.lower()
    ev(session, tab, 'JSON.stringify(%s)' % js)
    time.sleep(4)
    js2 = ('(function(){var bs=Array.from(document.querySelectorAll("button"));'
           'var b=bs.find(function(x){return (x.textContent||"").trim()==="Switch accounts"});'
           'if(b){b.click();return "confirmed"}return "no_dialog"})()')
    ev(session, tab, 'JSON.stringify(%s)' % js2)
    time.sleep(6)


# ---------------------------------------------------------------- 日期工具
def ordinal(n):
    if 11 <= n % 100 <= 13:
        return 'th'
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def day_aria(d):
    """按钮 aria-label 匹配片段。

    X 新版日期选择器日期按钮 aria-label 为完整格式
    'Thursday, October 1, 2026'（带星期前缀、无 st/nd/rd/th 序数）。
    用「Month D, YYYY」片段做 indexOf 匹配即可兼容新旧两种格式。
    """
    return '%s %d, %d' % (MONTHS_EN[d.month - 1], d.day, d.year)


def month_label(d):
    return '%s %d' % (MONTHS_EN[d.month - 1], d.year)


def parse_date_range(start_date, end_date):
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('start-date and end-date must use YYYY-MM-DD') from exc
    if start > end:
        raise ValueError('start-date must not be after end-date')
    if end > date.today():
        raise ValueError('end-date must not be in the future')
    return start, end


def build_date_windows(start_date, end_date, window_days):
    """Yield inclusive date windows backwards without leaving the range."""
    if window_days < 1:
        raise ValueError('window-days must be at least 1')
    current_end = end_date
    while current_end >= start_date:
        current_start = max(start_date, current_end - timedelta(days=window_days - 1))
        yield current_start, current_end
        current_end = current_start - timedelta(days=1)


# ---------------------------------------------------------------- 页面操作
def dialog_rendered(session, tab):
    """弹窗真正渲染（日历里含 ', 2026' 日期按钮）。

    注意：role=dialog 的空壳节点会在弹窗关闭后残留，仅判存在会误判。
    """
    return ev(session, tab,
              '(function(){var d=document.querySelector("[role=dialog]");'
              'if(!d)return false;'
              'return Array.from(d.querySelectorAll("button[aria-label]"))'
              '.some(function(b){return (b.getAttribute("aria-label")||"")'
              '.indexOf(", 2026")>-1})})()') is True


def dialog_open(session, tab):
    return dialog_rendered(session, tab)


def open_picker(session, tab):
    """点击 'Select date range' 按钮并等待日历真正渲染。"""
    ev(session, tab,
       '(function(){var b=Array.from(document.querySelectorAll("[aria-label]"))'
       '.filter(function(e){return e.getAttribute("aria-label")==="Select date range"})[0];'
       'if(b){b.click();return 1}return 0})()')
    for _ in range(10):
        time.sleep(1.5)
        if dialog_rendered(session, tab):
            return True
    return False


def month_visible(session, tab, label):
    """判断目标月份是否可见。

    注意：新版 X 日期选择器月份标题按钮的 aria-label 是 'January 2022'
    这种带空格的格式，而 innerText 中月份名与年份被换行符分隔
    （'January\n2022'），用 innerText.indexOf 会匹配失败导致死循环翻页。
    故改用月份标题按钮的 aria-label 精确匹配。
    """
    return ev(session, tab,
              '(function(){var d=document.querySelector("[role=dialog]");'
              'if(!d)return false;'
              'var m=d.querySelector("button[aria-haspopup=menu]");'
              'return !!m && (m.getAttribute("aria-label")||"")==="%s"})()' % label) is True


def nav_until(session, tab, label, direction, max_clicks=24):
    """点击 Previous/Next 月导航直到目标月份可见。

    X 新版月份导航按钮 aria-label 为 'Previous month' / 'Next month'
    （旧版为 'Go to the Previous Month' / 'Go to the Next Month'）。
    """
    prev_aria = {'prev': 'Previous month', 'next': 'Next month'}[direction]
    for _ in range(max_clicks):
        if month_visible(session, tab, label):
            return True
        ev(session, tab,
           '(function(){var d=document.querySelector("[role=dialog]");if(!d)return;'
           'var b=Array.from(d.querySelectorAll("button")).find(function(x)'
           '{var a=x.getAttribute("aria-label")||"";'
           'return a==="%s"||a==="Go to the %s Month"});'
           'if(b){b.click()}})()' % (prev_aria,
                                    'Previous' if direction == 'prev' else 'Next'))
        time.sleep(1.2)
    return month_visible(session, tab, label)


def click_date(session, tab, d):
    js = (
        '(function(){var d=document.querySelector("[role=dialog]");if(!d)return "no dialog";'
        'var b=Array.from(d.querySelectorAll("button")).find(function(x){'
        'return (x.getAttribute("aria-label")||"").indexOf("%s")>-1});'
        'if(b){b.click();return "clicked"}return "not found"})()'
    ) % day_aria(d)
    return ev(session, tab, js)


def close_dialog(session, tab):
    """关闭日期弹窗：优先 toggle 'Select date range' 按钮，Escape 兜底。"""
    ev(session, tab,
       '(function(){var b=Array.from(document.querySelectorAll("[aria-label]"))'
       '.filter(function(e){return e.getAttribute("aria-label")==='
       '"Select date range"})[0];'
       'if(b&&b.getAttribute("aria-expanded")==="true"){b.click();return 1}return 0})()')
    time.sleep(2)
    if dialog_rendered(session, tab):
        ev(session, tab,
           '(function(){document.dispatchEvent(new KeyboardEvent("keydown",'
           '{key:"Escape",code:"Escape"}));return 1})()')
        time.sleep(2)


def page_has_error(session, tab):
    txt = str(ev(session, tab,
                 '(function(){var m=document.querySelector("[data-testid=primaryColumn]");'
                 'return m?m.innerText.slice(0,200):""})()'))
    return 'Something went wrong' in txt


def recover_page_error(session, tab, max_retry=6):
    """X 的 accountOverviewDailyQuery 会间歇性失败（瞬态 Something went
    wrong，与范围大小无关），点 Retry 重试同一查询直到恢复。"""
    for _ in range(max_retry):
        if not page_has_error(session, tab):
            return True
        ev(session, tab,
           '(function(){var bs=Array.from(document.querySelectorAll("button"));'
           'var b=bs.find(function(x){return /Retry/i.test(x.textContent||"")});'
           'if(b){b.click();return 1}return 0})()')
        time.sleep(8)
    return not page_has_error(session, tab)


def reset_range_7d(session, tab):
    """点 7D 预设重置选区。

    X 的日期选择器对「已选范围内」的日期点击无效（no-op），所以每次
    选新范围前必须先重置成默认 7D，保证后续点击都落在选区外。
    """
    close_dialog(session, tab)
    r = ev(session, tab,
           '(function(){var bs=Array.from(document.querySelectorAll("button"));'
           'var b=bs.find(function(x){return (x.textContent||"").trim()==="7D"});'
           'if(b){b.click();return 1}return 0})()')
    time.sleep(5)
    return r == 1


def select_range(session, tab, start, end):
    """在日期选择器上选定 [start, end]（新版 X 日历，2026-10 验证）。

    新版交互（须先经 reset_range_7d 重置为 7D）：
      1. 弹窗打开后日历显示 Start 所在月；
      2. 点第一个日期 -> 设为 Start（End 自动变为原 Start）；
      3. 点第二个日期 -> 设为 End，选区完成；
      4. 日历月份标题按钮 aria-label 即 'October 2026'（带空格）；
      5. 日期按钮 aria-label 为 'Thursday, October 1, 2026'（带星期前缀）。
    """
    if not open_picker(session, tab):
        return 'picker open failed'
    # 翻到 start 所在月（日历初始在 7D Start 的月份，通常 >= start，向 prev 翻）
    if not nav_until(session, tab, month_label(start), 'prev'):
        # 兜底：向 next 翻
        if not nav_until(session, tab, month_label(start), 'next'):
            return 'nav to start month failed'
    r = click_date(session, tab, start)
    if 'clicked' not in str(r):
        return 'start click failed: %s' % r
    time.sleep(2)
    if not dialog_rendered(session, tab):
        return 'dialog closed after start click'
    # 翻到 end 所在月
    if not nav_until(session, tab, month_label(end), 'next'):
        return 'nav to end month failed'
    r = click_date(session, tab, end)
    if 'clicked' not in str(r):
        return 'end click failed: %s' % r
    time.sleep(3)
    close_dialog(session, tab)
    # 等待 accountOverviewDailyQuery 完成（瞬态错误自动 Retry）
    if not recover_page_error(session, tab):
        return 'page error after range apply'
    return 'ok'


def download_csv(session, tab):
    """注入 createObjectURL 钩子 -> 点击 Download CSV -> 内存中截获 CSV 文本。"""
    ev(session, tab,
       '(function(){window.__csv=null;var orig=URL.createObjectURL.bind(URL);'
       'URL.createObjectURL=function(obj){'
       'try{if(obj instanceof Blob){obj.text().then(function(t){window.__csv=t})'
       '.catch(function(){})}}catch(e){}'
       'return orig(obj)};return 1})()')
    r = ev(session, tab,
           '(function(){var b=Array.from(document.querySelectorAll("[aria-label]"))'
           '.filter(function(e){return e.getAttribute("aria-label")==="Download CSV"})[0];'
           'if(b){b.click();return "clicked"}return "not_found"})()')
    if 'clicked' not in str(r):
        return None
    for _ in range(15):
        time.sleep(3)
        csv_text = ev(session, tab, 'window.__csv')
        if isinstance(csv_text, str) and csv_text.startswith('Date'):
            return csv_text
    return None


def fetch_window(session, tab, start, end, attempts=3):
    """抓取一个日期窗口的账号级日度 CSV，带重试。

    新版流程：reset_range_7d 重置选区 -> select_range 点选 [start, end] ->
    Download CSV 内存截获 -> 解析校验。
    """
    for i in range(attempts):
        if page_has_error(session, tab):
            recover_page_error(session, tab)
        reset_range_7d(session, tab)
        status = select_range(session, tab, start, end)
        if status != 'ok':
            print(f'    range select: {status}', end=' ')
            time.sleep(5)
            continue
        csv_text = download_csv(session, tab)
        rows = parse_csv(csv_text)
        # 只保留目标窗口内的日期
        rows = {d: r for d, r in rows.items() if start <= d <= end}
        if rows and validate_rows(rows, start, end):
            return rows
        print(f'    csv invalid (rows={len(rows)})', end=' ')
        time.sleep(5)
    return None


def parse_csv(csv_text):
    """解析 X Analytics 导出的账号级 CSV -> {date: {col: value}}"""
    if not csv_text:
        return {}
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = {}
    for r in reader:
        raw = (r.get('Date') or '').strip().strip('"')
        try:
            d = datetime.strptime(raw, '%a, %b %d, %Y').date()
        except ValueError:
            continue
        row = {}
        for col in CSV_COLUMNS[1:]:
            v = (r.get(col) or '').strip()
            try:
                row[col] = int(v) if v != '' else 0
            except ValueError:
                row[col] = 0
        rows[d] = row
    return rows


def validate_rows(rows, start, end):
    """校验 CSV 日期都在窗口内且覆盖窗口内所有天（X 有数据的时段）。"""
    if not rows:
        return False
    for d in rows:
        if not (start <= d <= end):
            return False
    # 覆盖天数：窗口应完整覆盖（除非 X 保留期外）
    expected = (end - start).days + 1
    if len(rows) != expected:
        # 最近一天可能尚未出数据，允许缺最后 1 天
        if not (len(rows) == expected - 1 and
                all(d < end for d in rows)):
            return False
    return True


# ---------------------------------------------------------------- Doris 写入
def load_doris_config(config_path):
    parser = configparser.ConfigParser()
    if not parser.read(config_path, encoding='utf-8') or not parser.has_section('doris'):
        raise ValueError('missing [doris] configuration in %s' % config_path)
    required = ('host', 'be_port', 'user', 'password')
    missing = [key for key in required if not parser.get('doris', key, fallback='').strip()]
    if missing:
        raise ValueError('missing Doris configuration: %s' % ', '.join(missing))
    return {key: parser.get('doris', key).strip() for key in required}


def ensure_table(config_path):
    """幂等建表（CREATE TABLE IF NOT EXISTS，无任何删除）。pymysql 可选。"""
    try:
        import pymysql
    except ImportError:
        print('  [跳过] 未安装 pymysql，请手动执行 --create-table 输出的 SQL 建表')
        return False
    cfg = load_doris_config(config_path)
    fe_port = '9030'
    parser = configparser.ConfigParser()
    if parser.read(config_path, encoding='utf-8') and parser.has_section('doris'):
        fe_port = parser.get('doris', 'fe_port', fallback='9030').strip()
    conn = pymysql.connect(host=cfg['host'], port=int(fe_port),
                           user=cfg['user'], password=cfg['password'],
                           database='ods_social_media')
    try:
        with conn.cursor() as cursor:
            cursor.execute(CREATE_TABLE_SQL)
        conn.commit()
        print(f'  [建表] ods_social_media.{DORIS_TABLE} 已就绪')
        return True
    finally:
        conn.close()


def to_doris_rows(rows, username, execution_date):
    result = []
    for d in sorted(rows):
        r = rows[d]
        result.append({
            'date': d.isoformat(),
            'page_name': '@%s' % username,
            'impressions': r.get('Impressions', 0),
            'likes': r.get('Likes', 0),
            'engagements': r.get('Engagements', 0),
            'bookmarks': r.get('Bookmarks', 0),
            'shares': r.get('Shares', 0),
            'new_follows': r.get('New follows', 0),
            'unfollows': r.get('Unfollows', 0),
            'replies': r.get('Replies', 0),
            'reposts': r.get('Reposts', 0),
            'profile_visits': r.get('Profile visits', 0),
            'create_post': r.get('Create Post', 0),
            'video_views': r.get('Video views', 0),
            'media_views': r.get('Media views', 0),
            'etl_date': execution_date.isoformat(),
        })
    return result


def stream_load_rows(rows, config_path):
    """NDJSON Stream Load 写入 Doris（UNIQUE KEY upsert，无删除）。"""
    if not rows:
        return {'Status': 'Success', 'NumberLoadedRows': 0, 'Label': ''}
    config = load_doris_config(config_path)
    url = ('http://%s:%s/api/ods_social_media/%s/_stream_load'
           % (config['host'], config['be_port'], DORIS_TABLE))
    payload = '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows).encode('utf-8')
    credentials = ('%s:%s' % (config['user'], config['password'])).encode('utf-8')
    import uuid
    request = Request(url, data=payload, method='PUT')
    request.add_header('Content-Type', 'application/json')
    request.add_header('Authorization', 'Basic ' + base64.b64encode(credentials).decode('ascii'))
    request.add_header('format', 'json')
    request.add_header('read_json_by_line', 'true')
    request.add_header('columns', ','.join(DORIS_COLUMNS))
    request.add_header('label', 'twitter_page_analytics_' + uuid.uuid4().hex)
    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError('Doris Stream Load HTTP %s: %s' % (exc.code, body)) from exc
    except (URLError, OSError) as exc:
        raise RuntimeError('Doris Stream Load request failed: %s' % exc) from exc
    if result.get('Status') != 'Success':
        raise RuntimeError('Doris Stream Load failed: %s' % result.get('Message', result))
    loaded_rows = int(result.get('NumberLoadedRows', 0))
    if loaded_rows != len(rows):
        raise RuntimeError('Doris Stream Load loaded %s of %s rows' % (loaded_rows, len(rows)))
    return result


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description='抓取 X 账号层级日度分析数据 -> Doris ods_twitter_page_analytics')
    ap.add_argument('--username', default='anycubic3dprint')
    ap.add_argument('--start-date', required=True, metavar='YYYY-MM-DD')
    ap.add_argument('--end-date', required=True, metavar='YYYY-MM-DD')
    ap.add_argument('--window-days', type=int, default=MAX_WINDOW_DAYS,
                    help='分窗大小（X 上限 90 天，默认 90）')
    ap.add_argument('--session', default='ar')
    ap.add_argument('--doris-config',
                    default=str(Path(__file__).resolve().parents[2] / 'config' / 'credentials.ini'))
    ap.add_argument('--no-ensure-table', action='store_true',
                    help='跳过自动建表（默认尝试 CREATE TABLE IF NOT EXISTS）')
    ap.add_argument('--csv-out', default='',
                    help='可选：将合并后的 CSV 保存到本地文件')
    ap.add_argument('--create-table', action='store_true',
                    help='打印建表语句后退出')
    args = ap.parse_args()

    if args.create_table:
        print(CREATE_TABLE_SQL)
        return

    try:
        start_date, end_date = parse_date_range(args.start_date, args.end_date)
        window_days = min(args.window_days, MAX_WINDOW_DAYS)
    except ValueError as exc:
        ap.error(str(exc))

    print(f'== X Account Analytics fetcher for @{args.username} ==')
    print(f'   range {start_date} -> {end_date} (window {window_days}d)')

    if not args.no_ensure_table:
        try:
            ensure_table(args.doris_config)
        except Exception as exc:
            print(f'  [警告] 建表失败（将继续尝试写入）: {exc}')

    session = args.session
    tab = get_tab(session, OVERVIEW_URL)
    if not tab:
        print('ERROR: cannot open browser tab. Is Chrome + OpenCLI extension running?')
        sys.exit(1)
    print(f'  tab: {tab}')
    time.sleep(12)

    # 检查是否 Premium 墙（当前激活账号不对）-> 切换到委托账号
    body = str(ev(session, tab, 'JSON.stringify(document.body.innerText.slice(0,400))'))
    if 'Upgrade to continue' in body or "doesn’t exist" in body:
        switch_to_delegate(session, tab, args.username)
        open_url(session, tab, OVERVIEW_URL)
        time.sleep(10)
        body = str(ev(session, tab, 'JSON.stringify(document.body.innerText.slice(0,400))'))
        if 'Upgrade to continue' in body:
            print('ERROR: still seeing Premium wall. Delegate switch failed.')
            sys.exit(1)

    # 逐窗口抓取（从最近窗口往回）
    all_rows = {}
    failed_windows = []
    for from_d, to_d in build_date_windows(start_date, end_date, window_days):
        print(f'  window {from_d} -> {to_d} ...', end=' ', flush=True)
        rows = fetch_window(session, tab, from_d, to_d)
        if rows is None:
            print('FAILED')
            failed_windows.append((from_d, to_d))
            continue
        new_days = [d for d in rows if d not in all_rows]
        all_rows.update(rows)
        print(f'{len(rows)} days ({len(new_days)} new)')

    if not all_rows:
        print('ERROR: no data fetched at all.')
        sys.exit(1)
    if failed_windows:
        print(f'WARNING: {len(failed_windows)} window(s) failed and were skipped: '
              f'{failed_windows}')

    # 只保留请求范围内的日期
    all_rows = {d: r for d, r in all_rows.items() if start_date <= d <= end_date}
    days = sorted(all_rows)
    print(f'\nTotal unique days: {len(days)} ({days[0]} .. {days[-1]})')

    # 可选保存 CSV
    if args.csv_out:
        with open(args.csv_out, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(CSV_COLUMNS)
            for d in days:
                r = all_rows[d]
                w.writerow([d.strftime('%a, %b %d, %Y')] + [r[c] for c in CSV_COLUMNS[1:]])
        print(f'CSV saved to: {args.csv_out}')

    # 写入 Doris
    doris_rows = to_doris_rows(all_rows, args.username, date.today())
    try:
        result = stream_load_rows(doris_rows, args.doris_config)
    except (RuntimeError, ValueError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)
    print('Doris Stream Load succeeded: label=%s, loaded=%s, filtered=%s, unselected=%s'
          % (result.get('Label', ''), result.get('NumberLoadedRows', 0),
             result.get('NumberFilteredRows', 0), result.get('NumberUnselectedRows', 0)))


if __name__ == '__main__':
    main()
