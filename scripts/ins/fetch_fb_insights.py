# -*- coding: utf-8 -*-
"""
一键抓取 Meta Business Suite (Content → All content) 的全量帖子洞察数据。
流程：
  1. 打开/复用浏览器标签（business.facebook.com/latest/insights/content/）
  2. 注入请求捕获 hook，并通过切换时间范围触发表格 GraphQL 请求
  3. 保存请求模板到 window.__fbQBodyVar
  4. 注入“时间窗口二分”抓取脚本获取全量数据
  5. 轮询直到抓取完成
"""
import argparse
import base64
import configparser
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.path.dirname(os.path.abspath(__file__))
WINDOWED_JS = os.path.join(BASE, "fb_inpage_windowed.js")
DEFAULT_INSTAGRAM_BUSINESS_IDS = ('17841406045865168', '17841414725872019')
# 各 IG 账号归属的 Meta business（页面 URL 会重定向到真实归属 business）。
# 实测: 17841406045865168(anycubicofficial) 归属 800253393765350；
#       17841414725872019 归属 761831987530602（在 761831987530602 下可正常抓取）。
# 纯 ID 传入时优先查此映射，查不到再用 --business-id 兜底。
BUSINESS_MAP = {
    '17841406045865168': '800253393765350',
    '17841414725872019': '761831987530602',
}
TYPE_NAMES = {'IG_STORY': 'IG story', 'IG_POST': 'IG post', 'FB_PAGE_POST': 'FB Page Post'}
# IG media_type: 1=IMAGE, 2=VIDEO(Reel), 8=CAROUSEL_ALBUM
MEDIA_TYPE_NAMES = {1: 'IG image', 2: 'IG reel', 8: 'IG carousel'}
# GraphQL media_product_type -> 页面显示标签（Content 表格接口可能返回此字段）
MEDIA_PRODUCT_TYPE_NAMES = {
    'clips': 'IG reel', 'feed': 'IG image', 'story': 'IG story',
    'carousel_container': 'IG carousel', 'igtv': 'IGTV',
    'feed_video': 'IG reel', 'reels': 'IG reel',
}
# 各 IG 账号的 instagram 数字 pk（非 fbid_v2）。feed 接口 /api/v1/feed/user/{pk}
# 需要此 pk 才能拉取该账号帖子元数据（full_name/duration_in_ms/fbid_v2/media_type/product_type）。
# 由用户提供，实测可用。
IG_PK_MAP = {
    '17841406045865168': '6201345528',      # anycubicofficial
    '17841414725872019': '14736154862',     # anycubic_deutschland
}
# 静态账号 display name 映射（fbid_v2 -> full_name）。
# 当 feed 分页拉不到老帖子时，用此兜底补全 account_name。
ACCOUNT_NAME_MAP = {
    '17841406045865168': 'ANYCUBIC',
    '17841414725872019': 'Anycubic Deutschland',
}


def map_post_type(source_row):
    """Post type 细分：IG story / IG reel / IG carousel / IG image。

    优先级：
    1. dom_post_type：从页面 DOM 直接抓取的类型标签（最准确，与页面显示一致）
    2. media_product_type：GraphQL 响应中的媒体产品类型字段
    3. media_type：媒体级数据源的 media_type 键（1=image, 2=reel, 8=carousel）
    4. entity_type + video_play_time 推断（兜底）
    """
    # 优先级 1：DOM 提取的类型标签
    dom_pt = source_row.get('dom_post_type')
    if dom_pt:
        return dom_pt
    # 优先级 2：GraphQL media_product_type
    mpt = source_row.get('media_product_type')
    if mpt:
        mapped = MEDIA_PRODUCT_TYPE_NAMES.get(str(mpt).lower())
        if mapped:
            return mapped
    entity_type = source_row.get('entity_type')
    if entity_type == 'IG_STORY':
        return 'IG story'
    if entity_type == 'IG_POST':
        media_type = source_row.get('media_type')
        if media_type is not None:
            try:
                media_type = int(media_type)
            except (TypeError, ValueError):
                pass
            mapped = MEDIA_TYPE_NAMES.get(media_type)
            if mapped:
                return mapped
        metrics = source_row.get('metrics') or {}
        if metrics.get('video_play_time'):
            return 'IG reel'
        return 'IG image'
    return TYPE_NAMES.get(entity_type, entity_type or '')


DORIS_COLUMNS = [
    'date', 'post_id', 'post_type', 'account_username', 'account_name', 'duration', 'account_id',
    'title', 'publish_time', 'permalink',
    'views', 'reach', 'viewers', 'interactions', 'likes_reactions', 'comments', 'shares',
    'saves', 'link_clicks', 'replies', 'new_follows', 'video_play_time_min',
    'avg_play_time_sec', 'video_3s_views', 'instream_ads_earnings',
    'etl_date',
]

# CSV 输出列（对齐用户要求的输出字段；Content API 拿不到的字段留空/由映射表补齐）
CSV_COLUMNS = [
    'Post ID', 'Account ID', 'Account username', 'Account name', 'Description',
    'Duration (sec)', 'Replies', 'Link clicks',
]

# opencli 是 node CLI，用 node 直接执行入口文件，参数走列表形式，
# 彻底绕开 Windows cmd.exe 的 & / 引号解析问题。
NODE = r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"
OPENCLI_JS = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"


def opencli(session, *args, timeout=60):
    """执行 opencli browser <session> <args...>，返回 (stdout, stderr, rc)。"""
    cmd = [NODE, OPENCLI_JS, "browser", session] + list(args)
    out, err, rc = run(cmd, timeout=timeout)
    return _filter_cli_lines(out), err, rc


def run(cmd, timeout=60, shell=False):
    """执行命令并返回 stdout（字节模式，容错解码，避免 Windows 编码崩溃）。
    cmd 可以是字符串(需 shell=True)或参数列表(推荐，绕开 cmd.exe 的 & / 引号解析)。"""
    result = subprocess.run(
        cmd, shell=shell, capture_output=True, text=False, timeout=timeout
    )
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    return stdout.strip(), stderr.strip(), result.returncode


def _filter_cli_lines(out):
    """过滤 opencli 的更新提示行。"""
    lines = [ln for ln in out.splitlines() if not (
        ln.startswith("Update available") or ln.startswith("Run: ") or
        ln.startswith("Extension update") or ln.startswith("Download: ")
    )]
    return "\n".join(lines)


def browser_eval(session, js_code, timeout=60):
    """通过 opencli 在浏览器页面执行 JS（node 直调，参数安全）。"""
    return opencli(session, "eval", js_code, timeout=timeout)


def browser_eval_file(session, js_path, timeout=120):
    """执行本地 JS 文件内容（列表参数，不经 shell）。"""
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()
    return browser_eval(session, js, timeout=timeout)


def parse_instagram_business_ids(value, default_business_id):
    """解析 IG 账号列表，支持两种格式：
      - 纯 ID：'17841406045865168,17841414725872019' -> business 查 BUSINESS_MAP，查不到用 default 兜底
      - 配对：'17841406045865168:800253393765350,17841414725872019' -> 显式指定各自归属
    返回 [(instagram_business_id, business_id), ...]，保持输入顺序。
    """
    if value is None:
        return [(iid, BUSINESS_MAP.get(iid, default_business_id))
                for iid in DEFAULT_INSTAGRAM_BUSINESS_IDS]
    pairs = []
    for item in value.split(','):
        item = item.strip()
        if not item:
            continue
        if ':' in item:
            ig_id, _, biz_id = item.partition(':')
            pairs.append((ig_id.strip(), biz_id.strip() or default_business_id))
        else:
            pairs.append((item, BUSINESS_MAP.get(item, default_business_id)))
    if not pairs:
        raise ValueError('instagram-business-ids must contain at least one ID')
    return pairs


def parse_date_range(start_date, end_date):
    """Parse an inclusive YYYY-MM-DD date range."""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('start-date and end-date must use YYYY-MM-DD') from exc
    if start > end:
        raise ValueError('start-date must not be after end-date')
    return start, end


def load_account_map(path):
    """读取账号映射文件：JSON {"17841406045865168": "ANYCUBIC"} 或 CSV "account_id,name"。

    Content API 不返回账号 display name，需要此映射补齐 Account name 字段。
    """
    if not path:
        return {}
    text = Path(path).read_text(encoding='utf-8')
    stripped = text.lstrip()
    if stripped.startswith('{'):
        data = json.loads(text)
        return {str(k).strip(): str(v).strip() for k, v in data.items()}
    # CSV 格式：account_id,name（可带表头 account_id,name）
    result = {}
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        parts = line.split(',', 1)
        if len(parts) != 2:
            continue
        aid, name = parts[0].strip(), parts[1].strip()
        if i == 0 and aid.lower() in ('account_id', 'id'):
            continue
        result[aid] = name
    return result


def to_doris_row(source_row, execution_date, account_map=None):
    """Map one Meta Business Suite insight row to the Doris target schema."""
    metrics = source_row.get('metrics') or {}
    created_at = source_row.get('created_at')
    publish_time = ''
    if created_at:
        publish_time = datetime.fromtimestamp(created_at, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    execution_day = execution_date.isoformat()
    account_map = account_map or {}
    # account_name 优先取媒体级数据源的 full_name 键；Content API 无此键时回退账号映射表
    account_name = source_row.get('account_name') or ''
    owner_id = source_row.get('_owner_id') or ''
    if not account_name and owner_id in account_map:
        account_name = account_map[owner_id]
    # account_id 取 fbid_v2 键；Content API 的 _owner_id 即去前缀的 fbid_v2，可用作回退
    account_id = source_row.get('account_id') or ''
    if not account_id and owner_id:
        account_id = owner_id
    # duration 取 duration_in_ms 键（毫秒）；Content API 无此键时为 0
    duration_ms = source_row.get('duration')
    duration_ms = int(duration_ms) if duration_ms not in (None, '') else 0
    metric_map = {
        'views': 'views', 'reach': 'reach', 'viewers': 'viewers',
        'interactions': 'interactions', 'likes_reactions': 'net_reactions',
        'comments': 'net_comments', 'shares': 'shares', 'saves': 'net_saves',
        'link_clicks': 'link_clicks', 'replies': 'replies', 'new_follows': 'new_follows',
        'video_3s_views': 'video_three_second_views',
    }
    result = {
        'date': execution_day,
        'post_id': source_row.get('row_id', ''),
        'post_type': map_post_type(source_row),
        # owner = 账号用户名（对齐 Doris 表列名 owner）
        'account_username': source_row.get('owner') or '',
        'account_name': account_name,
        'duration': duration_ms,
        'account_id': account_id,
        'title': source_row.get('title') or '',
        'publish_time': publish_time,
        'permalink': source_row.get('permalink') or '',
        'video_play_time_min': (metrics.get('video_play_time') or 0) / 60000.0,
        'avg_play_time_sec': (metrics.get('video_average_play_time') or 0) / 1000.0,
        'instream_ads_earnings': (metrics.get('instream_ads_estimated_earnings') or 0) / 100.0,
        'etl_date': execution_day,
    }
    result.update({column: metrics.get(metric) or 0 for column, metric in metric_map.items()})
    return result


def to_csv_row(source_row, account_map=None):
    """Map one row to the user-requested CSV columns.

    Content API 可提供: Post ID / Account username / Description / Replies / Link clicks
    Account name: 媒体级数据源的 full_name 键，缺失时回退 --account-map 映射表
    Duration (sec): duration_in_ms 键换算（毫秒->秒）
    Account ID: fbid_v2 键（Content API 无此键，留空）
    """
    metrics = source_row.get('metrics') or {}
    account_map = account_map or {}
    account_name = source_row.get('account_name') or ''
    owner_id = source_row.get('_owner_id') or ''
    if not account_name and owner_id in account_map:
        account_name = account_map[owner_id]
    # account_id：feed 补全的 fbid_v2 优先，缺失时用 _owner_id（去前缀 fbid_v2）
    account_id = source_row.get('account_id') or ''
    if not account_id and owner_id:
        account_id = owner_id
    duration_ms = source_row.get('duration')
    duration_sec = ''
    if duration_ms not in (None, ''):
        try:
            duration_sec = round(float(duration_ms) / 1000.0, 2)
        except (TypeError, ValueError):
            duration_sec = ''
    return {
        'Post ID': source_row.get('row_id', ''),
        'Account ID': account_id,
        'Account username': source_row.get('owner') or '',
        'Account name': account_name,
        'Description': (source_row.get('title') or '').replace('\r', ' ').replace('\n', ' ').strip(),
        'Duration (sec)': duration_sec,
        'Replies': metrics.get('replies') if metrics.get('replies') is not None else '',
        'Link clicks': metrics.get('link_clicks') if metrics.get('link_clicks') is not None else '',
    }


def write_csv(rows, out_path, account_map=None):
    """将所有行按 CSV_COLUMNS 写出（utf-8-sig 保证 Excel 打开不乱码）。"""
    import csv
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(to_csv_row(row, account_map))
    size = os.path.getsize(out_path)
    print('已导出 CSV: %s (%d 行, %.2f KB)' % (out_path, len(rows), size / 1024))
    return True


def load_doris_config(config_path):
    parser = configparser.ConfigParser()
    if not parser.read(config_path, encoding='utf-8') or not parser.has_section('doris'):
        raise ValueError('missing [doris] configuration in %s' % config_path)
    required = ('host', 'be_port', 'user', 'password')
    missing = [key for key in required if not parser.get('doris', key, fallback='').strip()]
    if missing:
        raise ValueError('missing Doris configuration: %s' % ', '.join(missing))
    return {key: parser.get('doris', key).strip() for key in required}


def stream_load_rows(rows, config_path):
    """Write Meta insight rows to Doris using NDJSON Stream Load."""
    if not rows:
        return {'Status': 'Success', 'NumberLoadedRows': 0, 'Label': ''}
    config = load_doris_config(config_path)
    url = ('http://%s:%s/api/ods_social_media/ods_instagram_post_insights/_stream_load'
           % (config['host'], config['be_port']))
    payload = '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows).encode('utf-8')
    credentials = ('%s:%s' % (config['user'], config['password'])).encode('utf-8')
    request = Request(url, data=payload, method='PUT')
    request.add_header('Content-Type', 'application/json')
    request.add_header('Authorization', 'Basic ' + base64.b64encode(credentials).decode('ascii'))
    request.add_header('format', 'json')
    request.add_header('read_json_by_line', 'true')
    request.add_header('columns', ','.join(DORIS_COLUMNS))
    request.add_header('label', 'instagram_post_insights_' + uuid.uuid4().hex)
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


def current_url(session):
    out, _, _ = browser_eval(session, "location.href", timeout=10)
    return out


def open_page(session, business_id, asset_id):
    url = (
        f"https://business.facebook.com/latest/insights/content/"
        f"?business_id={business_id}&asset_id={asset_id}"
    )
    # node 直调 opencli，URL 作为单一参数传递，避免 cmd.exe 把 & 拆成多条命令
    out, err, rc = opencli(session, "open", url, timeout=120)
    print(f"已打开页面: {url} (rc={rc} {out[:80]})")


def wait_for_grid(session, max_wait=60):
    """等待表格加载完成。"""
    for i in range(max_wait):
        out, _, _ = browser_eval(
            session,
            "JSON.stringify({url: location.href.slice(0,80), hasGrid: !!document.querySelector('[role=grid]')})",
            timeout=10,
        )
        try:
            data = json.loads(out)
        except Exception:
            data = {}
        if data.get("hasGrid"):
            print(f"表格已加载 ({i+1}s)")
            return True
        time.sleep(1)
    return False


def install_capture_hook(session):
    """注入 fetch + XHR 请求体捕获 hook。"""
    js = r"""
(() => {
  if (window.__fbHookInstalled) return 'already';
  window.__fbReqBodies = [];
  const f1 = window.fetch;
  window.fetch = async function(...a) {
    const [u, o] = a;
    if (typeof u === 'string' && u.includes('/api/graphql/') && o && o.body) {
      window.__fbReqBodies.push({t:'fetch', body: o.body, len: o.body.length});
    }
    return f1.apply(this, a);
  };
  const o1 = window.XMLHttpRequest.prototype.open;
  const s1 = window.XMLHttpRequest.prototype.send;
  window.XMLHttpRequest.prototype.open = function(m, u) { this.__uuu = u; return o1.apply(this, arguments); };
  window.XMLHttpRequest.prototype.send = function(b) {
    if (this.__uuu && this.__uuu.includes('/api/graphql/') && b) {
      window.__fbReqBodies.push({t:'xhr', body: b, len: b.length});
    }
    return s1.apply(this, arguments);
  };
  window.__fbHookInstalled = true;
  return 'hook installed';
})()
"""
    out, err, rc = browser_eval(session, js, timeout=20)
    print("请求捕获 hook:", out or err)
    return rc == 0


def click_time_range_option(session, current_label, target_label):
    """点击时间范围按钮并选择目标选项，触发新查询。"""
    js_open = f"""
(() => {{
  const btn = Array.from(document.querySelectorAll('div[role=button]')).find(el => el.innerText && el.innerText.includes({json.dumps(current_label)}));
  if (btn) {{ btn.click(); return 'opened'; }}
  return 'not found';
}})()
"""
    out, _, _ = browser_eval(session, js_open, timeout=10)
    time.sleep(0.5)
    js_click = f"""
(() => {{
  const ls = Array.from(document.querySelectorAll('div')).filter(el => (el.innerText||'').trim() === {json.dumps(target_label)} && !Array.from(el.querySelectorAll('div')).some(d => (d.innerText||'').trim() === {json.dumps(target_label)}));
  if (!ls.length) return 'no leaf';
  const leaf = ls[0];
  leaf.click();
  if (leaf.parentElement) leaf.parentElement.click();
  return 'clicked';
}})()
"""
    out, _, _ = browser_eval(session, js_click, timeout=10)
    time.sleep(2)
    return out


def save_template(session):
    """从已捕获的请求体中保存 useBizWebUnifiedTableInitialLoad_data_refetchable 模板。"""
    js = r"""
(() => {
  const list = (window.__fbReqBodies || []).map(b => {
    const friendlyMatch = b.body.match(/fb_api_req_friendly_name=([^&]+)/);
    const friendly = friendlyMatch ? decodeURIComponent(friendlyMatch[1]) : '';
    const docId = (b.body.match(/doc_id=([^&]+)/) || [])[1];
    return {docId, friendly, len: b.len};
  });
  const refetch = (window.__fbReqBodies || []).find(b => {
    const m = b.body.match(/fb_api_req_friendly_name=([^&]+)/);
    return m && decodeURIComponent(m[1]).includes('useBizWebUnifiedTableInitialLoad_data_refetchable');
  });
  const initial = (window.__fbReqBodies || []).find(b => {
    const m = b.body.match(/fb_api_req_friendly_name=([^&]+)/);
    return m && decodeURIComponent(m[1]).includes('BizWebInsightsContentOrganicTableQueryRendererQuery');
  });
  window.__fbQBodyVar = refetch ? refetch.body : (initial ? initial.body : null);
  return JSON.stringify({bodies: (window.__fbReqBodies || []).length, list, saved: !!window.__fbQBodyVar});
})()
"""
    out, err, rc = browser_eval(session, js, timeout=20)
    print("模板保存结果:", out)
    try:
        data = json.loads(out)
        return data.get("saved", False)
    except Exception:
        return False


def ensure_native_fetch(session):
    js = r"""
(() => {
  if (window.__nativeFetch) return 'already';
  const fr = document.createElement('iframe');
  fr.style.display = 'none';
  document.body.appendChild(fr);
  window.__nativeFetch = fr.contentWindow.fetch.bind(fr.contentWindow);
  return 'nativeFetch ready';
})()
"""
    out, _, _ = browser_eval(session, js, timeout=10)
    return out


def run_windowed_fetch(session, from_date, to_date):
    """注入并启动窗口二分抓取，支持自定义时间范围。"""
    with open(WINDOWED_JS, "r", encoding="utf-8") as f:
        js = f.read()
    # 替换默认 CONFIG 日期
    js = js.replace("from: '2016-01-01',", f"from: '{from_date}',")
    js = js.replace("to: '2026-08-24',", f"to: '{to_date}',")
    out, err, rc = browser_eval(session, js, timeout=120)
    print("启动抓取:", out or err)
    return rc == 0


def poll_progress(session, interval=30, max_wait=1800):
    """轮询直到抓取完成或超时。"""
    for _ in range(0, max_wait, interval):
        out, err, rc = browser_eval(
            session,
            "JSON.stringify(window.__fbWinProgress || {phase:'missing'})",
            timeout=30,
        )
        try:
            data = json.loads(out)
        except Exception:
            data = {}
        phase = data.get("phase", "unknown")
        rows = data.get("rows", 0)
        reqs = data.get("requests", 0)
        print(f"[{phase}] requests={reqs}, rows={rows}")
        if phase == "done":
            return True
        if phase and "error" in str(phase).lower():
            print("抓取出错:", phase)
            return False
        time.sleep(interval)
    print("轮询超时")
    return False


def export_json(session, out_path):
    """将 window.__fbAllRows 导出到本地 JSON（捕获 stdout，Python 写文件）。"""
    out, err, rc = browser_eval(
        session, "JSON.stringify(window.__fbAllRows)", timeout=600
    )
    if rc != 0 or not out.startswith("["):
        print("JSON 导出失败:", (err or out)[:300])
        return False
    try:
        data = json.loads(out)
    except Exception as e:
        print("JSON 内容不完整(可能被截断), 长度:", len(out), "错误:", e)
        return False
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    size = os.path.getsize(out_path)
    print(f"已导出 JSON: {out_path} ({size/1024/1024:.2f} MB, {len(data)} rows)")
    return True


def fetch_rows(session, business_id, instagram_business_id, start_date, end_date, skip_capture=False):
    """Fetch all insight rows for one Instagram Business ID from the active browser session."""
    print(f'\n== Instagram Business ID: {instagram_business_id} ==')
    open_page(session, business_id, instagram_business_id)
    if not wait_for_grid(session, max_wait=60):
        raise RuntimeError('表格未加载，请检查页面状态后重试。')

    if not skip_capture:
        install_capture_hook(session)
        out, _, _ = browser_eval(
            session,
            "JSON.stringify({text: Array.from(document.querySelectorAll('div[role=button]')).map(e => e.innerText).find(t => t && (t.includes('Last') || t.includes('days')))})",
            timeout=10,
        )
        try:
            current = json.loads(out).get('text', '')
        except Exception:
            current = 'Last 7 days'
        current_label = (current.split(':')[0] if current else 'Last 7 days').strip()
        target_label = 'Last 28 days' if current_label == 'Last 7 days' else 'Last 7 days'
        print(f'切换时间范围: {current_label} -> {target_label}')
        click_time_range_option(session, current_label, target_label)
        if not save_template(session):
            raise RuntimeError('未能保存请求模板，请确认 hook 是否捕获到表格查询。')
    else:
        out, _, _ = browser_eval(session, 'typeof window.__fbQBodyVar', timeout=10)
        if out != 'string':
            raise RuntimeError('页面没有已保存的模板，不能跳过捕获。')

    ensure_native_fetch(session)
    # 在窗口抓取前，从当前可见的表格 DOM 提取 post_type 标签
    dom_post_types = extract_post_types_from_dom(session)
    if not run_windowed_fetch(session, start_date, end_date):
        raise RuntimeError('启动抓取失败。')
    if not poll_progress(session):
        raise RuntimeError('抓取未完成。')

    out, err, rc = browser_eval(session, 'JSON.stringify(window.__fbAllRows)', timeout=600)
    if rc != 0 or not out.startswith('['):
        raise RuntimeError('读取抓取结果失败: %s' % (err or out)[:300])
    try:
        rows = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError('抓取结果 JSON 不完整，长度: %s' % len(out)) from exc
    # 回填 DOM 提取的 post_type 标签
    if dom_post_types:
        apply_dom_post_types(rows, dom_post_types)
    print(f'账号抓取完成: {len(rows)} 行')
    return rows


def _ig_feed_js(pk, start_ts, end_ts):
    """返回在 instagram 页面翻 feed 分页、按日期筛选并收集媒体元数据的 JS。

    从 /api/v1/feed/user/{pk}/ 分页拉取该账号全部帖子（reel/image/carousel），
    收集 fbid -> {full_name, fbid_v2, duration_in_ms, media_type, product_type, caption}。
    只保留 taken_at 落在 [start_ts, end_ts] 时间范围内的帖子。
    """
    return r"""
(async () => {
  const pk = %s;
  const startTs = %d, endTs = %d;
  const out = {};
  let maxId = '';
  for (let page = 0; page < 200; page++) {
    const url = '/api/v1/feed/user/' + pk + '/' + (maxId ? '?max_id=' + encodeURIComponent(maxId) : '');
    const r = await fetch(url, {headers: {'x-ig-app-id': '936619743392459'}, credentials: 'include'});
    if (r.status !== 200) break;
    const t = await r.text();
    let o; try { o = JSON.parse(t); } catch(e) { break; }
    const items = o.items || [];
    if (!items.length) break;
    let pageOldCount = 0;
    for (const it of items) {
      const ts = it.taken_at;
      if (!ts) continue;
      if (ts < startTs) { pageOldCount++; continue; }
      if (ts > endTs) continue;
      const u = it.user || {};
      const caption = it.caption && it.caption.text ? it.caption.text : '';
      out[it.fbid] = {
        full_name: u.full_name || '',
        fbid_v2: u.fbid_v2 || '',
        duration_in_ms: (it.duration_in_ms != null) ? it.duration_in_ms
                     : ((it.video_duration != null) ? Math.round(it.video_duration * 1000) : null),
        media_type: it.media_type != null ? it.media_type : null,
        product_type: it.product_type || '',
        code: it.code || '',
        caption: caption,
      };
    }
    if (pageOldCount >= items.length && page > 5) return JSON.stringify({done: true, count: Object.keys(out).length, meta: out});
    if (!o.more_available || !o.next_max_id) break;
    maxId = o.next_max_id;
  }
  return JSON.stringify({done: true, count: Object.keys(out).length, meta: out});
})()
""" % (json.dumps(pk), start_ts, end_ts)


def fetch_ig_feed_meta(session, ig_pk, start_date, end_date):
    """在 instagram 页面翻 feed 分页，获取该账号时间范围内帖子的媒体元数据。

    返回 {fbid: {full_name, fbid_v2, duration_in_ms, media_type, product_type, code, caption}}。
    只含正式帖子（reel/image/carousel），不含 story。
    """
    if not ig_pk:
        return {}
    # 打开账号主页以确保 instagram 域登录态 + 接口可用
    opencli(session, "open", "https://www.instagram.com/", timeout=30)
    time.sleep(3)
    # 时间参数按北京时间（GMT+8）解析，避免 UTC 转换导致 end_date 少 8 小时
    tz_bj = timezone(timedelta(hours=8))
    start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=tz_bj).timestamp())
    # 含 end_date 当天 23:59
    end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=tz_bj).timestamp())
    js = _ig_feed_js(ig_pk, start_ts, end_ts)
    out, err, rc = browser_eval(session, js, timeout=600)
    if rc != 0:
        print('  [ig feed] 调用失败 rc=%s err=%s' % (rc, err[:200]))
        return {}
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        print('  [ig feed] 响应解析失败: %s (len=%s)' % (exc, len(out)))
        return {}
    meta = data.get('meta') or {}
    print('  [ig feed] pk=%s 拉到 %d 条帖子元数据' % (ig_pk, len(meta)))
    return meta


def fetch_story_durations(session, business_id, asset_id, rows, max_wait=15):
    """逐个打开 IG_STORY 的 object_insights 页面，从 <video> 元素读取 duration。

    Story 的 duration 不在 Content API / IG Feed API 中返回，
    但 object_insights 页面会加载视频元素，其 duration 属性即视频时长（秒）。
    将 duration 转为毫秒存入 row['duration']，与 IG Feed 的 duration_in_ms 一致。
    """
    stories_no_dur = [r for r in rows
                      if r.get('entity_type') == 'IG_STORY' and not r.get('duration')]
    if not stories_no_dur:
        print('  [story dur] 所有 story 已有 duration，跳过')
        return 0

    print('  [story dur] 需要获取 %d 个 story 的 duration...' % len(stories_no_dur))
    filled = 0
    for i, row in enumerate(stories_no_dur):
        rid = row.get('row_id', '')
        url = ('https://business.facebook.com/latest/insights/object_insights/'
               '?asset_id=%s&business_id=%s&content_id=%s&nav_ref=bizweb_insights_uta_table'
               % (asset_id, business_id, rid))
        opencli(session, 'open', url, timeout=60)
        # 等待 video 元素加载并获取 duration
        video_dur = None
        for attempt in range(max_wait):
            js = ("(async()=>{"
                  "for(let w=0;w<3;w++){"
                  "const v=document.querySelector('video');"
                  "if(v&&v.duration&&v.duration>0&&isFinite(v.duration))"
                  "return JSON.stringify({dur:v.duration});"
                  "await new Promise(r=>setTimeout(r,1000));"
                  "}"
                  "return JSON.stringify({dur:null});"
                  "})()")
            out, _, rc = browser_eval(session, js, timeout=20)
            try:
                data = json.loads(out)
                video_dur = data.get('dur')
            except Exception:
                video_dur = None
            if video_dur:
                break
            time.sleep(1)

        if video_dur and video_dur > 0:
            row['duration'] = round(video_dur * 1000)  # 秒 -> 毫秒
            filled += 1
            print('    [%d/%d] story %s: %.2f sec -> %d ms'
                  % (i + 1, len(stories_no_dur), rid, video_dur, row['duration']))
        else:
            print('    [%d/%d] story %s: 未获取到 duration (可能是图片 story)'
                  % (i + 1, len(stories_no_dur), rid))

    print('  [story dur] 获取完成: %d/%d 个 story 获得 duration'
          % (filled, len(stories_no_dur)))
    return filled


def extract_post_types_from_dom(session, max_rows=50):
    """从页面表格 DOM 提取每行的 post_type 标签（Reel/Photo/Story 等）。

    页面表格每行在标题旁显示类型标签（如 "Reel"、"Photo"、"Story"），
    本函数通过 JS 遍历表格行，提取标题文本和对应的类型标签，
    返回 {title_text: post_type_label} 映射。
    仅对当前页面可见的行有效（默认时间范围最多 50 行）。
    """
    js = r"""
(() => {
  const rows = document.querySelectorAll('[role=row]');
  const result = {};
  let count = 0;
  const typeLabels = ['Reel', 'Photo', 'Story', 'Carousel', 'Album', 'Video', 'Image'];
  for (const row of rows) {
    if (count >= %d) break;
    const text = row.innerText || '';
    if (!text) continue;
    // 查找类型标签
    let postType = '';
    for (const label of typeLabels) {
      if (text.includes(label)) {
        postType = label;
        break;
      }
    }
    if (!postType) continue;
    // 提取标题文本（第一个 \n 之前的内容，或第一个长文本片段）
    const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
    // 标题通常是第一行或第二行（第一行可能是 "POV: ..."，第二行可能是 "Reel ● account"）
    // 取第一个长度 > 10 且不含类型标签的行作为标题
    let titleText = '';
    for (const line of lines) {
      const cleanLine = line.replace(/\s*(Reel|Photo|Story|Carousel|Album|Video|Image)\s*/i, '').trim();
      if (cleanLine.length > 5 && !cleanLine.startsWith('Boost') && !cleanLine.startsWith('●')) {
        titleText = cleanLine;
        break;
      }
    }
    if (titleText) {
      result[titleText] = postType;
      count++;
    }
  }
  return JSON.stringify({count, map: result});
})()
""" % max_rows
    out, err, rc = browser_eval(session, js, timeout=30)
    if rc != 0:
        print('  [dom post_type] 提取失败 rc=%s err=%s' % (rc, err[:200]))
        return {}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        print('  [dom post_type] 响应解析失败: %s' % out[:200])
        return {}
    result = data.get('map') or {}
    print('  [dom post_type] 从 DOM 提取 %d 行的 post_type 标签' % len(result))
    return result


def apply_dom_post_types(rows, dom_map):
    """将 DOM 提取的 post_type 标签回填到 rows 中。

    通过标题文本前缀匹配（DOM 提取的标题可能与 GraphQL 返回的 title 略有差异）。
    """
    if not dom_map:
        return 0
    # 建立 title 前缀 -> row 索引（取前 60 字符）
    title_prefix_map = {}
    for row in rows:
        t = (row.get('title') or '').strip()
        if t:
            title_prefix_map[t[:60].lower()] = row
    matched = 0
    for dom_title, dom_type in dom_map.items():
        dom_key = dom_title.strip().lower()[:60]
        # 精确前缀匹配
        if dom_key in title_prefix_map:
            title_prefix_map[dom_key]['dom_post_type'] = dom_type
            matched += 1
            continue
        # 模糊匹配：DOM title 是 row title 的子串或反之
        for prefix, row in title_prefix_map.items():
            if dom_key in prefix or prefix in dom_key or dom_key[:30] == prefix[:30]:
                row['dom_post_type'] = dom_type
                matched += 1
                break
    print('  [dom post_type] 回填 %d/%d 行' % (matched, len(dom_map)))
    return matched


def enrich_with_ig_meta(rows, ig_meta, account_name_map=None):
    """用 instagram feed 元数据按 fbid(=row_id) 合并回 Content 表格行。

    补全 account_name(full_name)、account_id(fbid_v2)、duration(duration_in_ms)、
    media_type/media_product_type（用于 post_type 细分）。
    未匹配到 feed 的帖子（如 IG_STORY）保持原字段，但会用 feed 里该账号的
    full_name 回填 Account name（story 虽不在 feed，但账号名与正式帖一致）。
    最终兜底：静态 ACCOUNT_NAME_MAP（覆盖 feed 拉不到老帖子的场景）。
    """
    account_name_map = account_name_map or {}
    matched = 0
    # 建立 owner.username -> full_name 映射（取 feed 里该账号任一帖子的 full_name）
    username_fullname = {}
    if ig_meta:
        for m in ig_meta.values():
            if m.get('full_name') and m.get('fbid_v2'):
                username_fullname.setdefault(m['fbid_v2'], m['full_name'])
    for row in rows:
        rid = str(row.get('row_id') or '')
        m = (ig_meta or {}).get(rid)
        owner_id = row.get('_owner_id') or ''
        if m:
            matched += 1
            if not row.get('account_name') and m.get('full_name'):
                row['account_name'] = m['full_name']
            if not row.get('account_id') and m.get('fbid_v2'):
                row['account_id'] = m['fbid_v2']
            if not row.get('duration') and m.get('duration_in_ms') is not None:
                row['duration'] = m['duration_in_ms']
            if row.get('media_type') is None and m.get('media_type') is not None:
                row['media_type'] = m['media_type']
            if not row.get('media_product_type') and m.get('product_type'):
                row['media_product_type'] = m['product_type']
            # 若 Description 为空且 feed 有 caption，补上（IG_POST 通常已有 title）
            if not row.get('title') and m.get('caption'):
                row['title'] = m['caption']
            # 构造 Instagram 永久链接（shortcode -> permalink）
            if not row.get('permalink') and m.get('code'):
                code = m['code']
                product_type = m.get('product_type') or ''
                if product_type == 'clips' or row.get('entity_type') == 'IG_POST' and m.get('media_type') == 2:
                    row['permalink'] = 'https://www.instagram.com/reel/%s/' % code
                else:
                    row['permalink'] = 'https://www.instagram.com/p/%s/' % code
        # 未匹配到 feed 的行（如 IG_STORY）：用该账号的 full_name 回填 Account name
        if not row.get('account_name') and owner_id in username_fullname:
            row['account_name'] = username_fullname[owner_id]
        # 最终兜底：静态 ACCOUNT_NAME_MAP
        if not row.get('account_name') and owner_id in account_name_map:
            row['account_name'] = account_name_map[owner_id]
    print('  [ig meta] 按 row_id 匹配合并 %d/%d 行' % (matched, len(rows)))
    if username_fullname:
        print('  [ig meta] 账号 full_name 映射: %s'
              % ', '.join('%s=%s' % (k, v) for k, v in username_fullname.items()))
    # 统计静态映射兜底补了多少
    static_filled = sum(1 for r in rows if r.get('account_name') and r.get('_owner_id') in account_name_map
                        and r.get('_owner_id') not in username_fullname)
    if static_filled:
        print('  [ig meta] 静态映射兜底补全 account_name: %d 行' % static_filled)


def main():
    parser = argparse.ArgumentParser(description='抓取 Instagram 帖子洞察并写入 Doris')
    parser.add_argument('--session', default='dqg7tk9s', help='opencli 浏览器 session id')
    parser.add_argument('--business-id', default='761831987530602',
                        help='Meta business ID（纯 ID 账号的兜底归属；内置账号与显式配对可各自指定）')
    parser.add_argument('--instagram-business-ids', default=None,
                        help='逗号分隔的 IG 账号；支持 "id" 或 "id:business_id" 配对格式；'
                             '默认抓取两个内置账号（各自归属已内置）')
    parser.add_argument('--start-date', required=True, metavar='YYYY-MM-DD')
    parser.add_argument('--end-date', required=True, metavar='YYYY-MM-DD')
    parser.add_argument('--doris-config', default=str(Path(__file__).resolve().parents[2] / 'config' / 'credentials.ini'))
    parser.add_argument('--csv-out', default=None, metavar='PATH',
                        help='可选：将所有账号的帖子级明细合并导出为 CSV（对齐目标输出字段）')
    parser.add_argument('--account-map', default=None, metavar='PATH',
                        help='可选：账号 display name 映射文件（JSON {"id":"name"} 或 CSV "id,name"），'
                             '用于补齐 Content API 不返回的 Account name 字段')
    parser.add_argument('--skip-capture', action='store_true', help='页面已保存模板时跳过 UI 捕获（仅单账号模式生效）')
    args = parser.parse_args()
    try:
        start_date, end_date = parse_date_range(args.start_date, args.end_date)
        instagram_business_ids = parse_instagram_business_ids(args.instagram_business_ids, args.business_id)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        account_map = load_account_map(args.account_map)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error('account-map 读取失败: %s' % exc)
    if account_map:
        print('账号映射已加载: %d 个' % len(account_map))

    # --skip-capture 复用页面里已保存的模板，而模板内嵌 asset_id；
    # 多账号必须逐账号重新捕获，否则会拿到上一个账号的模板/数据。
    use_skip_capture = args.skip_capture and len(instagram_business_ids) == 1
    if args.skip_capture and not use_skip_capture:
        print('多账号模式：忽略 --skip-capture（模板内嵌 asset_id，需逐账号捕获）')

    print('=' * 60)
    print('Meta Business Suite Instagram 洞察抓取并写入 Doris')
    print('=' * 60)
    print('账号配置: ' + ', '.join('%s@%s' % (ig, biz) for ig, biz in instagram_business_ids))
    execution_date = date.today()
    failures = []
    loaded_total = 0
    all_csv_rows = []
    for ig_id, biz_id in instagram_business_ids:
        try:
            rows = fetch_rows(args.session, biz_id, ig_id,
                              start_date.isoformat(), end_date.isoformat(),
                              use_skip_capture)
            # 双源打通：用 instagram 账号 feed 补全 full_name/duration/media_type 等字段
            # 需要登录ig账号，暂时注释掉
            # ig_pk = IG_PK_MAP.get(ig_id, '')
            # ig_meta = fetch_ig_feed_meta(args.session, ig_pk,
            #                              start_date.isoformat(), end_date.isoformat())
            # enrich_with_ig_meta(rows, ig_meta, ACCOUNT_NAME_MAP)


            # Story duration 补全：逐个打开 object_insights 页面从 <video> 元素读取
            # fetch_story_durations需要逐个打开页面获取快拍的duration，耗时较长，暂时注释掉
            # fetch_story_durations(args.session, biz_id, ig_id, rows)


            all_csv_rows.extend(rows)
            doris_rows = [to_doris_row(row, execution_date, account_map) for row in rows]
            result = stream_load_rows(doris_rows, Path(args.doris_config))
            loaded = int(result.get('NumberLoadedRows', 0))
            loaded_total += loaded
            print('账号 %s: 抓取 %d 行 -> Doris loaded=%d, filtered=%s, unselected=%s'
                  % (ig_id, len(rows), loaded,
                     result.get('NumberFilteredRows', 0), result.get('NumberUnselectedRows', 0)))
        except (RuntimeError, ValueError) as exc:
            failures.append('%s: %s' % (ig_id, exc))
            print('ERROR [%s]: %s' % (ig_id, exc), file=sys.stderr)

    if args.csv_out and all_csv_rows:
        write_csv(all_csv_rows, args.csv_out, account_map)

    if failures:
        print('存在失败的账号 (%d/%d)，其余账号已正常写入：' % (len(failures), len(instagram_business_ids)),
              file=sys.stderr)
        for fail in failures:
            print('  - ' + fail, file=sys.stderr)
        return 1

    print('全部账号处理完成: 共写入 %d 行到 Doris' % loaded_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
