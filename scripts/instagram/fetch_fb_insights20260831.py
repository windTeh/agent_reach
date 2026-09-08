# -*- coding: utf-8 -*-
"""
一键抓取 Meta Business Suite (Content → All content) 的全量帖子洞察数据。
流程：
  1. 打开/复用浏览器标签（business.facebook.com/latest/insights/content/）
  2. 注入请求捕获 hook，并通过切换时间范围触发表格 GraphQL 请求
  3. 保存请求模板到 window.__fbQBodyVar
  4. 注入“时间窗口二分”抓取脚本获取全量数据
  5. 轮询直到抓取完成
  6. 导出 JSON + 生成 Excel

用法示例：
    python fetch_fb_insights.py \
        --session dqg7tk9s \
        --business-id 761831987530602 \
        --asset-id 213562039049926 \
        --from 2016-01-01 \
        --to 2026-08-24 \
        --json-out fb_all_rows.json \
        --xlsx-out fb_all.xlsx

依赖：
    - opencli 已安装且能操作浏览器会话
    - fb_inpage_windowed20260831.js 与本脚本同目录
    - fb_to_excel.py 与本脚本同目录（用于生成 Excel）
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
WINDOWED_JS = os.path.join(BASE, "../tmp/content_version/fb_inpage_windowed.js")
EXCEL_PY = os.path.join(BASE, "fb_to_excel.py")
DEFAULT_INSTAGRAM_BUSINESS_IDS = ('17841406045865168', '17841414725872019')
# 各 IG 账号归属的 Meta business（页面 URL 会重定向到真实归属 business）。
# 实测: 17841406045865168(anycubicofficial) 归属 800253393765350；
#       17841414725872019 归属 761831987530602（在 761831987530602 下可正常抓取）。
# 纯 ID 传入时优先查此映射，查不到再用 --business-id 兜底。
BUSINESS_MAP = {
    '17841406045865168': '800253393765350',
    '17841414725872019': '761831987530602',
}
TYPE_NAMES = {'IG_STORY': 'IG Story', 'IG_POST': 'IG Post', 'FB_PAGE_POST': 'FB Page Post'}
DORIS_COLUMNS = [
    'date', 'post_id', 'post_type', 'owner', 'title', 'publish_time', 'thumbnail_url',
    'views', 'reach', 'viewers', 'interactions', 'likes_reactions', 'comments', 'shares',
    'saves', 'link_clicks', 'replies', 'new_follows', 'video_play_time_min',
    'avg_play_time_sec', 'video_3s_views', 'instream_ads_earnings', 'etl_date',
]

# opencli 是 node CLI，用 node 直接执行入口文件，参数走列表形式，
# 彻底绕开 Windows cmd.exe 的 & / 引号解析问题。
NODE = r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2\node.exe"
OPENCLI_JS = (r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2"
              r"\node_modules\@jackwener\opencli\dist\src\main.js")


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


def to_doris_row(source_row, execution_date):
    """Map one Meta Business Suite insight row to the Doris target schema."""
    metrics = source_row.get('metrics') or {}
    created_at = source_row.get('created_at')
    publish_time = ''
    if created_at:
        publish_time = datetime.fromtimestamp(created_at, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    execution_day = execution_date.isoformat()
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
        'post_type': TYPE_NAMES.get(source_row.get('entity_type'), source_row.get('entity_type', '')),
        'owner': source_row.get('owner') or '',
        'title': source_row.get('title') or '',
        'publish_time': publish_time,
        'thumbnail_url': source_row.get('image_uri') or '',
        'video_play_time_min': (metrics.get('video_play_time') or 0) / 60000.0,
        'avg_play_time_sec': (metrics.get('video_average_play_time') or 0) / 1000.0,
        'instream_ads_earnings': (metrics.get('instream_ads_estimated_earnings') or 0) / 100.0,
        'etl_date': execution_day,
    }
    result.update({column: metrics.get(metric) or 0 for column, metric in metric_map.items()})
    return result


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
    out, err, rc = opencli(session, "open", url, timeout=30)
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


def generate_excel(json_path, xlsx_path):
    """调用 fb_to_excel.py 生成 Excel。"""
    python_exe = sys.executable
    cmd = f"\"{python_exe}\" \"{EXCEL_PY}\" \"{json_path}\" \"{xlsx_path}\""
    out, err, rc = run(cmd, timeout=600)
    print(out)
    if rc != 0:
        print("Excel 生成失败:", err)
        return False
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
    print(f'账号抓取完成: {len(rows)} 行')
    return rows


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
    parser.add_argument('--skip-capture', action='store_true', help='页面已保存模板时跳过 UI 捕获（仅单账号模式生效）')
    args = parser.parse_args()
    try:
        start_date, end_date = parse_date_range(args.start_date, args.end_date)
        instagram_business_ids = parse_instagram_business_ids(args.instagram_business_ids, args.business_id)
    except ValueError as exc:
        parser.error(str(exc))

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
    for ig_id, biz_id in instagram_business_ids:
        try:
            rows = fetch_rows(args.session, biz_id, ig_id,
                              start_date.isoformat(), end_date.isoformat(),
                              use_skip_capture)
            doris_rows = [to_doris_row(row, execution_date) for row in rows]
            result = stream_load_rows(doris_rows, Path(args.doris_config))
            loaded = int(result.get('NumberLoadedRows', 0))
            loaded_total += loaded
            print('账号 %s: 抓取 %d 行 -> Doris loaded=%d, filtered=%s, unselected=%s'
                  % (ig_id, len(rows), loaded,
                     result.get('NumberFilteredRows', 0), result.get('NumberUnselectedRows', 0)))
        except (RuntimeError, ValueError) as exc:
            failures.append('%s: %s' % (ig_id, exc))
            print('ERROR [%s]: %s' % (ig_id, exc), file=sys.stderr)

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
