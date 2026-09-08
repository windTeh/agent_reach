# -*- coding: utf-8 -*-
"""
Fetch VIDEO-OVERVIEW (video metrics) daily analytics for @anycubic3dprint
via X Analytics Video page (Delegate account through @Anycubic2024's Chrome
session via OpenCLI).

指标:
  Date, Views, Watch Time (ms), Completion Rate, Average Watch Time (ms),
  Estimated Revenue

Output: Doris Stream Load into ods_social_media.ods_twitter_video_analytics
  (UNIQUE KEY 模型，重复运行自动覆盖更新，只增改、绝不删除)

实现原理:
  1. 打开 https://x.com/i/account_analytics/video (Video overview 页)
  2. 注入 XMLHttpRequest 拦截器，记录页面自身发出的
     mediaMetricsQuery GraphQL 响应（页面自动携带合法鉴权头，故不会 403）
  3. 用日期范围选择器设定窗口 -> X 前端触发 mediaMetricsQuery
     (variables: from_timestamp/to_timestamp, metric_types 含
     Playback25/50/75/Complete/Start, VideoView, WatchTime)
  4. 解析 metric_values（按天）-> 过滤目标窗口 -> 写入 Doris
     - Views            = VideoView
     - Watch Time (ms)  = WatchTime
     - Completion Rate  = PlaybackComplete / PlaybackStart
     - Avg Watch Time   = WatchTime / VideoView
     - Estimated Revenue= amplify_revenue_by_day（无 Amplify 收入时全 0）

Usage:
  python ./scripts/twitter/fetch_anycubic3dprint_video_analytics.py --start-date 2026-08-01 --end-date 2026-08-10
  [--username anycubic3dprint] [--session ar]
      [--window-days 60] [--doris-config ../../config/credentials.ini]
      [--no-ensure-table] [--csv-out out.csv] [--create-table]

Prerequisites:
  - Chrome running with OpenCLI extension connected, logged in as @Anycubic2024
  - Delegate access to @anycubic3dprint (Admin role) already granted

注意事项:
  - mediaMetricsQuery 会把请求范围自动前移（约等于选择窗口长度），返回数据
    点必然覆盖目标窗口，脚本解析后裁剪回 [start, end]
  - X 按 UTC 日聚合视频指标，Date 取数据点 timestamp 的 UTC 日期
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# NODE = r'C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2\node.exe'
# MAIN = (r'C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2'
#         r'\node_modules\@jackwener\opencli\dist\src\main.js')

NODE = r"D:\Program Files\nodejs\node.exe"
MAIN = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"


VIDEO_URL = 'https://x.com/i/account_analytics/video'

# mediaMetricsQuery 返回的指标类型 -> 用户指标
METRIC_VIDEO_VIEW = 'VideoView'
METRIC_WATCH_TIME = 'WatchTime'
METRIC_PLAYBACK_START = 'PlaybackStart'
METRIC_PLAYBACK_COMPLETE = 'PlaybackComplete'

CSV_COLUMNS = ['Date', 'Views', 'Watch Time (ms)', 'Completion Rate',
               'Average Watch Time (ms)', 'Estimated Revenue']

DORIS_TABLE = 'ods_twitter_video_analytics'
DORIS_COLUMNS = [
    'date', 'page_name', 'views', 'watch_time_ms', 'completion_rate',
    'avg_watch_time_ms', 'estimated_revenue', 'etl_date',
]

CREATE_TABLE_SQL = """CREATE TABLE IF NOT EXISTS ods_twitter_video_analytics (
  `date` date NOT NULL COMMENT '报告日期',
  `page_name` varchar(100) NOT NULL COMMENT '账号(如 @anycubic3dprint)',
  `views` bigint NULL COMMENT '视频观看次数',
  `watch_time_ms` bigint NULL COMMENT '观看时长(毫秒)',
  `completion_rate` double NULL COMMENT '完成率(PlaybackComplete/PlaybackStart, 0~1)',
  `avg_watch_time_ms` double NULL COMMENT '平均观看时长(毫秒)',
  `estimated_revenue` double NULL COMMENT '预计收入(Amplify, 无收入时为0)',
  `etl_date` date NULL COMMENT '写入日期'
) ENGINE=OLAP
UNIQUE KEY(`date`, `page_name`)
COMMENT 'Twitter/X 视频总览日度分析数据'
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
    """按钮 aria-label 后缀, e.g. 'May 29th, 2026'（完整为 'Friday, May 29th, 2026'）"""
    return '%s %d%s, %d' % (MONTHS_EN[d.month - 1], d.day, ordinal(d.day), d.year)


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
def dialog_open(session, tab):
    return ev(session, tab, '!!document.querySelector("[role=dialog]")') is True


def open_picker(session, tab):
    """点击 'Select date range' 按钮并等待日历弹出。"""
    ev(session, tab,
       '(function(){var b=Array.from(document.querySelectorAll("[aria-label]"))'
       '.filter(function(e){return e.getAttribute("aria-label")==="Select date range"})[0];'
       'if(b){b.click();return 1}return 0})()')
    for _ in range(10):
        time.sleep(1.5)
        if dialog_open(session, tab):
            return True
    return False


def month_visible(session, tab, label):
    return ev(session, tab,
              '(function(){var d=document.querySelector("[role=dialog]");'
              'return !!d && d.innerText.indexOf("%s")>-1})()' % label) is True


def nav_until(session, tab, label, direction, max_clicks=24):
    """点击 Previous/Next 月导航直到目标月份可见。"""
    for _ in range(max_clicks):
        if month_visible(session, tab, label):
            return True
        ev(session, tab,
           '(function(){var d=document.querySelector("[role=dialog]");if(!d)return;'
           'var b=Array.from(d.querySelectorAll("button")).find(function(x)'
           '{return x.getAttribute("aria-label")==="Go to the %s Month"});'
           'if(b){b.click()}})()' % ('Previous' if direction == 'prev' else 'Next'))
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
    ev(session, tab,
       '(function(){document.dispatchEvent(new KeyboardEvent("keydown",'
       '{key:"Escape",code:"Escape"}));return 1})()')
    time.sleep(2)


def page_has_error(session, tab):
    txt = str(ev(session, tab,
                 '(function(){var m=document.querySelector("[data-testid=primaryColumn]");'
                 'return m?m.innerText.slice(0,200):""})()'))
    return 'Something went wrong' in txt


def reset_range_7d(session, tab):
    """点 7D 预设重置选区。

    X 的日期选择器对「已选范围内」的日期点击可能无效（no-op），所以每次
    选新范围前先重置成默认 7D，保证后续点击都落在选区外。
    """
    close_dialog(session, tab)
    r = ev(session, tab,
           '(function(){var bs=Array.from(document.querySelectorAll("button"));'
           'var b=bs.find(function(x){return (x.textContent||"").trim()==="7D"});'
           'if(b){b.click();return 1}return 0})()')
    time.sleep(5)
    return r == 1


def select_range(session, tab, start, end):
    """在日期选择器上选定覆盖 [start, end] 的范围。

    实际点击的起点是 start - 30 天（lead），保证起点落在 7D 选区之外；
    mediaMetricsQuery 会再把请求范围自动前移约一个窗口长度，返回数据点
    必然覆盖 [start, end]，解析后裁剪即可。
    """
    if not open_picker(session, tab):
        return 'picker open failed'
    clicked = False
    for lead_days in (30, 14, 7, 0):
        lead = start - timedelta(days=lead_days)
        if not nav_until(session, tab, month_label(lead), 'prev'):
            continue  # 太早无法翻页，缩小前移量重试
        r = click_date(session, tab, lead)
        if 'clicked' in str(r):
            clicked = True
            break
    if not clicked:
        return 'start click failed'
    time.sleep(2)
    # 有些情况下点击 start 后日历会自动关闭 -> 重新打开
    if not dialog_open(session, tab):
        if not open_picker(session, tab):
            return 'picker reopen failed'
    # 翻到 end 所在月
    if not nav_until(session, tab, month_label(end), 'next'):
        return 'nav to end month failed'
    r = click_date(session, tab, end)
    if 'clicked' not in str(r):
        return 'end click failed: %s' % r
    # 等待 mediaMetricsQuery 完成、页面重渲染（避免过早 Escape 中断请求）
    for _ in range(8):
        time.sleep(3)
        if page_has_error(session, tab):
            return 'page error (range may exceed X limit)'
        txt = str(ev(session, tab,
                     '(function(){var m=document.querySelector("[data-testid=primaryColumn]");'
                     'return m?m.innerText.slice(0,150):""})()'))
        if 'Video overview' in txt and txt.count('2026') >= 1:
            break
    time.sleep(3)
    return 'ok'


# ---------------------------------------------------------------- mediaMetricsQuery 拦截
MMQ_HOOK_JS = """(function(){
  window.__mmq = [];
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u) {
    this.__u = u;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function() {
    var self = this;
    this.addEventListener('load', function() {
      try {
        var u = self.__u || '';
        if (u.indexOf('mediaMetricsQuery') > -1) {
          window.__mmq.push({url: u, body: JSON.parse(self.responseText)});
        }
      } catch (e) {}
    });
    return origSend.apply(this, arguments);
  };
  return 'hooked';
})()"""


def install_mmq_hook(session, tab):
    """注入 XHR 拦截器（幂等），记录页面自身发出的 mediaMetricsQuery 响应。"""
    ev(session, tab, MMQ_HOOK_JS)


def clear_mmq(session, tab):
    ev(session, tab, 'window.__mmq=[];1')


def read_mmq(session, tab):
    """返回最新一条 mediaMetricsQuery 响应（dict），无则 None。

    注意：ev() 会对 JSON 字符串做 json.loads，因此这里同时兼容
    str（未解析）与 list（已解析）两种返回。
    """
    raw = ev(session, tab, 'JSON.stringify(window.__mmq)')
    if isinstance(raw, str):
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            return None
    elif isinstance(raw, list):
        items = raw
    else:
        return None
    if not items:
        return None
    return items[-1].get('body')


def parse_media_metrics(body, start, end):
    """解析 mediaMetricsQuery 响应 -> {date: {views, watch_time_ms,
    completion_rate, avg_watch_time_ms, estimated_revenue}}。

    数据点 timestamp 为 UTC 日 00:00，Date 取 UTC 日期；只保留 [start, end]。
    """
    rows = {}
    try:
        result = ((body.get('data') or {}).get('viewer_v2') or {}) \
            .get('user_results') or {}
        result = result.get('result') or {}
        series = result.get('media_metrics_time_series_for_publisher') or {}
        points = series.get('metric_values') or []
        revenue_by_day = result.get('amplify_revenue_by_day') or []
    except AttributeError:
        return rows

    # revenue: 兼容两种形态（空对象数组 / 带日期 key 的对象数组）
    revenue_map = {}
    for item in revenue_by_day:
        if isinstance(item, dict) and item:
            for k, v in item.items():
                try:
                    d = datetime.strptime(str(k), '%Y-%m-%d').date()
                    revenue_map[d] = float(v)
                except (ValueError, TypeError):
                    continue

    for point in points:
        ts = point.get('timestamp')
        if not ts:
            continue
        d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date()
        if not (start <= d <= end):
            continue
        vals = {m.get('metric_type'): m.get('metric_value')
                for m in point.get('metric_values', [])}
        views = int(vals.get(METRIC_VIDEO_VIEW) or 0)
        watch_time = int(vals.get(METRIC_WATCH_TIME) or 0)
        starts = int(vals.get(METRIC_PLAYBACK_START) or 0)
        completes = int(vals.get(METRIC_PLAYBACK_COMPLETE) or 0)
        rows[d] = {
            'views': views,
            'watch_time_ms': watch_time,
            'completion_rate': round(completes / starts, 6) if starts else 0.0,
            'avg_watch_time_ms': round(watch_time / starts, 2) if views else 0.0,
            'estimated_revenue': revenue_map.get(d, 0.0),
        }
    return rows


def fetch_window(session, tab, start, end, attempts=3):
    """抓取一个日期窗口的视频总览日度数据，带重试。

    若某次尝试拦截不到 mediaMetricsQuery（SPA 状态异常），整页刷新并
    重新注入 hook 后重试。
    """
    for i in range(attempts):
        if page_has_error(session, tab):
            close_dialog(session, tab)
            ev(session, tab,
               '(function(){var bs=Array.from(document.querySelectorAll("button"));'
               'var b=bs.find(function(x){return /Retry/i.test(x.textContent||"")});'
               'if(b){b.click();return 1}return 0})()')
            time.sleep(10)
        reset_range_7d(session, tab)
        clear_mmq(session, tab)
        status = select_range(session, tab, start, end)
        if status != 'ok':
            print(f'    range select: {status}', end=' ')
            continue
        # 先轮询读取响应，成功后再关闭对话框（避免 Escape 中断请求）
        body = None
        for _ in range(10):
            time.sleep(3)
            body = read_mmq(session, tab)
            if body:
                break
        close_dialog(session, tab)
        rows = parse_media_metrics(body, start, end)
        if rows:
            return rows
        # SPA 状态异常 -> 刷新页面并重注 hook 后重试
        print(f'    empty response (rows={len(rows)}), refreshing page ...', end=' ')
        ev(session, tab, 'location.reload();1')
        time.sleep(14)
        install_mmq_hook(session, tab)
    return None


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
            'views': r.get('views', 0),
            'watch_time_ms': r.get('watch_time_ms', 0),
            'completion_rate': r.get('completion_rate', 0.0),
            'avg_watch_time_ms': r.get('avg_watch_time_ms', 0.0),
            'estimated_revenue': r.get('estimated_revenue', 0.0),
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
    request.add_header('label', 'twitter_video_analytics_' + uuid.uuid4().hex)
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
        description='抓取 X 视频总览日度分析数据 -> Doris ods_twitter_video_analytics')
    ap.add_argument('--username', default='anycubic3dprint')
    ap.add_argument('--start-date', required=True, metavar='YYYY-MM-DD')
    ap.add_argument('--end-date', required=True, metavar='YYYY-MM-DD')
    ap.add_argument('--window-days', type=int, default=60,
                    help='分窗大小（mediaMetricsQuery 会自动前移请求范围，'
                         '建议不超过 60，默认 60）')
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
        window_days = min(args.window_days, 90)
    except ValueError as exc:
        ap.error(str(exc))

    print(f'== X Video Analytics fetcher for @{args.username} ==')
    print(f'   range {start_date} -> {end_date} (window {window_days}d)')

    if not args.no_ensure_table:
        try:
            ensure_table(args.doris_config)
        except Exception as exc:
            print(f'  [警告] 建表失败（将继续尝试写入）: {exc}')

    session = args.session
    tab = get_tab(session, VIDEO_URL)
    if not tab:
        print('ERROR: cannot open browser tab. Is Chrome + OpenCLI extension running?')
        sys.exit(1)
    print(f'  tab: {tab}')
    # 强制整页刷新，重置 X 前端 SPA 状态（否则点击日期不会触发 mediaMetricsQuery）
    ev(session, tab, 'location.reload();1')
    time.sleep(15)

    # 检查是否 Premium 墙（当前激活账号不对）-> 切换到委托账号
    body = str(ev(session, tab, 'JSON.stringify(document.body.innerText.slice(0,400))'))
    if 'Upgrade to continue' in body or "doesn’t exist" in body:
        switch_to_delegate(session, tab, args.username)
        open_url(session, tab, VIDEO_URL)
        time.sleep(10)
        body = str(ev(session, tab, 'JSON.stringify(document.body.innerText.slice(0,400))'))
        if 'Upgrade to continue' in body:
            print('ERROR: still seeing Premium wall. Delegate switch failed.')
            sys.exit(1)

    # 注入拦截器（页面刷新后需重注，放循环外即可，钩子对后续请求均生效）
    install_mmq_hook(session, tab)

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
                w.writerow([d.strftime('%a, %b %d, %Y'), r['views'],
                            r['watch_time_ms'], r['completion_rate'],
                            r['avg_watch_time_ms'], r['estimated_revenue']])
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
