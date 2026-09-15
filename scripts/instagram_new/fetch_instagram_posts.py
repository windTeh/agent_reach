# -*- coding: utf-8 -*-
"""通过 Agent Reach 项目内 OpenCLI 抓取 Meta Business Suite 的 Instagram 帖子洞察。

数据源是已登录的 Meta Business Suite 的 insights/content 页面；每个账号以其
Instagram asset_id 单独发起统一表格 GraphQL 查询（callerID=BIZWEB_INSIGHTS_ORGANIC_CONTENT），
该查询同时返回 IG_POST 与 IG_STORY。不按 owner_id 过滤；Facebook 节点仍会被排除。

跨发布的 IG_POST 在统一表格里返回的是 FB+IG 合并值，需要单独取 Instagram 平台值。
本脚本不打开 object_insights 页面，而是直接调用该页面背后的 GraphQL
（callerID=BIZWEB_OBJECT_INSIGHTS），在 content 页面上下文里发同源请求：
  - TofuObjectInsightsV2EntityQuery  一次返回该实体的全部指标；
    entity_insights 中不带 foa_ 前缀的字段即 Instagram 单独值，foa_ 前缀为 FB+IG 合并值。
  - useBizWebInsightsSingleValueQuery 补取 Instagram 侧的 Follows。
会话参数（fb_dtsg/lsd/__rev/c_user）从当前页面提取，无需预先捕获请求模板。

示例：
  E:\\CCProject\\agent_reach\\.agent-reach-venv\\Scripts\\python.exe fetch_instagram_posts.py ^
    --start-date 2026-08-01 --end-date 2026-08-07
"""
import argparse
import base64
import configparser
import json
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.request import Request, urlopen

BASE = Path(__file__).resolve().parent
WINDOWED_JS = BASE / "ig_inpage_windowed.js"
OBJECT_INSIGHTS_JS = BASE / "ig_object_insights.js"

# object_insights 背后的 GraphQL，callerID 均为 BIZWEB_OBJECT_INSIGHTS。
# doc_id 会随 Meta 前端版本更新，若调用报错可重新捕获一次页面请求再替换。
OI_ENTITY_DOC_ID = "28252130357723267"   # TofuObjectInsightsV2EntityQuery：一次返回实体全部指标
OI_SINGLE_DOC_ID = "31321294414185827"   # useBizWebInsightsSingleValueQuery：单指标，用于补 Follows
NODE = r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"
OPENCLI_JS = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"
DORIS_CONFIG = Path(__file__).resolve().parents[2] / "config" / "credentials.ini"

ACCOUNTS = (
    {"username": "anycubicofficial", "asset_id": "17841406045865168", "business_id": "800253393765350", "timezone": "America/Los_Angeles"},
    {"username": "anycubic_deutschland", "asset_id": "17841414725872019", "business_id": "761831987530602", "timezone": "Europe/Berlin"},
)

# Doris 目标表 ods_instagram_post_insights 的列顺序（与 scripts/ins/fetch_fb_insights.py 一致）。
DORIS_COLUMNS = [
    "date", "post_id", "post_type", "account_username", "account_name", "duration", "account_id",
    "title", "publish_time", "permalink",
    "views", "reach", "viewers", "interactions", "likes_reactions", "comments", "shares",
    "saves", "link_clicks", "replies", "new_follows", "video_play_time_min",
    "avg_play_time_sec", "video_3s_views", "instream_ads_earnings",
    "etl_date",
]

TYPE_NAMES = {"IG_STORY": "IG story", "IG_POST": "IG post", "FB_PAGE_POST": "FB Page Post"}
MEDIA_TYPE_NAMES = {1: "IG image", 2: "IG reel", 8: "IG carousel"}
MEDIA_PRODUCT_TYPE_NAMES = {
    "clips": "IG reel", "feed": "IG image", "story": "IG story",
    "stories": "IG story", "carousel_container": "IG carousel", "igtv": "IGTV",
    "feed_video": "IG reel", "reels": "IG reel",
}


def run(command, timeout=120):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def clean_cli(text):
    return "\n".join(line for line in text.splitlines() if not line.startswith(("Update available", "Run: ", "Extension update", "Download: ")))


def browser(session, *args, timeout=120):
    out, err, rc = run([NODE, OPENCLI_JS, "browser", session, *args], timeout=timeout)
    return clean_cli(out), err, rc


def evaluate(session, javascript, timeout=120):
    return browser(session, "eval", javascript, timeout=timeout)


def page_url(account):
    return "https://business.facebook.com/latest/insights/content/?business_id={}&asset_id={}".format(account["business_id"], account["asset_id"])


def wait_for_page(session, account, seconds=90):
    marker = "asset_id=" + account["asset_id"]
    for second in range(seconds):
        out, _, _ = evaluate(session, "JSON.stringify({url:location.href,grid:!!document.querySelector('[role=grid]')})", timeout=15)
        try:
            status = json.loads(out)
        except json.JSONDecodeError:
            status = {}
        if marker in status.get("url", "") and status.get("grid"):
            return
        time.sleep(1)
    raise RuntimeError("页面未在 {} 秒内加载到目标 Instagram 账号的帖子表格".format(seconds))


def install_request_hook(session):
    js = r'''(() => {
      if (window.__igPostsHook) return 'already installed';
      window.__igPostsBodies = [];
      const originalFetch = window.fetch;
      window.fetch = async function(...args) {
        const [url, options] = args;
        if (typeof url === 'string' && url.includes('/api/graphql/') && options && options.body) window.__igPostsBodies.push(String(options.body));
        return originalFetch.apply(this, args);
      };
      const originalOpen = XMLHttpRequest.prototype.open, originalSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function(method, url) { this.__igPostsUrl = url; return originalOpen.apply(this, arguments); };
      XMLHttpRequest.prototype.send = function(body) { if (String(this.__igPostsUrl || '').includes('/api/graphql/') && body) window.__igPostsBodies.push(String(body)); return originalSend.apply(this, arguments); };
      const frame = document.createElement('iframe'); frame.style.display = 'none'; document.body.appendChild(frame);
      window.__igPostsNativeFetch = frame.contentWindow.fetch.bind(frame.contentWindow);
      window.__igPostsHook = true;
      return 'installed';
    })()'''
    out, err, rc = evaluate(session, js, timeout=30)
    if rc:
        raise RuntimeError("无法安装页面请求捕获: {}".format(err or out))


def trigger_template_capture(session):
    js = r'''(async () => {
      const buttons = Array.from(document.querySelectorAll('[role=button]'));
      const button = buttons.find(x => /last\s+\d+\s+(day|week|month)/i.test(x.innerText || ''));
      if (!button) return 'date button not found';
      const current = button.innerText || '';
      button.click();
      await new Promise(resolve => setTimeout(resolve, 700));
      const choices = Array.from(document.querySelectorAll('div')).filter(x => /^(Last 7 days|Last 28 days)$/i.test((x.innerText || '').trim()));
      const target = choices.find(x => current.includes('Last 7 days') ? /^Last 28 days$/i.test((x.innerText || '').trim()) : /^Last 7 days$/i.test((x.innerText || '').trim()));
      if (!target) return 'date choice not found: ' + current;
      target.click();
      return 'triggered ' + current + ' -> ' + target.innerText;
    })()'''
    out, _, _ = evaluate(session, js, timeout=20)
    if out == "date button not found":
        raise RuntimeError("未找到日期范围控件，无法触发表格 GraphQL 请求")
    time.sleep(3)


def save_query_template(session):
    js = r'''(() => {
      const bodies = window.__igPostsBodies || [];
      const selected = bodies.find(body => decodeURIComponent((body.match(/fb_api_req_friendly_name=([^&]+)/) || [])[1] || '').includes('useBizWebUnifiedTableInitialLoad_data_refetchable')) ||
        bodies.find(body => decodeURIComponent((body.match(/fb_api_req_friendly_name=([^&]+)/) || [])[1] || '').includes('BizWebInsightsContentOrganicTableQueryRendererQuery'));
      window.__igPostsQueryTemplate = selected || null;
      return JSON.stringify({captured:bodies.length, saved:!!selected});
    })()'''
    out, err, rc = evaluate(session, js, timeout=30)
    if rc:
        raise RuntimeError("读取 GraphQL 模板失败: {}".format(err or out))
    status = json.loads(out)
    if not status.get("saved"):
        raise RuntimeError("未捕获帖子表格 GraphQL 模板；请确认 Meta Business Suite 已登录且页面可显示数据")


def run_windowed_fetch(session, start_date, end_date, asset_id):
    js = WINDOWED_JS.read_text(encoding="utf-8")
    js = js.replace("__START_DATE__", json.dumps(start_date)).replace("__END_DATE__", json.dumps(end_date)).replace("__ASSET_ID__", json.dumps(asset_id))
    out, err, rc = evaluate(session, js, timeout=120)
    if rc:
        raise RuntimeError("无法启动窗口抓取: {}".format(err or out))


def wait_for_fetch(session, seconds=3600):
    for elapsed in range(0, seconds, 10):
        out, _, _ = evaluate(session, "JSON.stringify(window.__igPostsProgress || {phase:'missing'})", timeout=30)
        try:
            progress = json.loads(out)
        except json.JSONDecodeError:
            progress = {}
        phase = progress.get("phase", "unknown")
        print("  [{}] 请求={}，保留帖子={}，拒绝非 IG 节点={}".format(phase, progress.get("requests", 0), progress.get("rows", 0), progress.get("rejected", 0)), flush=True)
        if phase == "done":
            return
        if "error" in phase.lower():
            raise RuntimeError("页面抓取失败: " + phase)
        time.sleep(10)
    raise RuntimeError("抓取超时（{} 秒）".format(seconds))


def read_rows(session):
    out, err, rc = evaluate(session, "JSON.stringify({rows:window.__igPostsRows||[], report:window.__igPostsReport||{}})", timeout=600)
    if rc:
        raise RuntimeError("读取抓取结果失败: {}".format(err or out))
    data = json.loads(out)
    if data["report"].get("errors"):
        print("  警告：{}".format("; ".join(data["report"]["errors"])), file=sys.stderr)
    return data["rows"], data["report"]


def fetch_ig_only_metrics(session, post_id, timeout=180):
    """不打开 object_insights，直接调用其背后的 GraphQL 取 Instagram 单独指标。

    统一表格（BIZWEB_INSIGHTS_ORGANIC_CONTENT）对跨发布帖返回 FB+IG 合并值，且
    响应里不含平台拆分字段。object_insights 页面自身也是调 BIZWEB_OBJECT_INSIGHTS
    的 TofuObjectInsightsV2EntityQuery 取数，其中 entity_insights 里不带 foa_ 前缀的
    字段就是 Instagram 单独值（带 foa_ 前缀的是 FB+IG 合并值）。该请求可在 content
    页面上下文直接发起（同源 + 页面会话参数），无需任何页面导航或请求模板捕获。

    返回 (ig_metrics, diagnostics)：
      - ig_metrics：包含 IG 单值的 dict（含 None 表示该指标业务无数据）；
      - diagnostics：包含 ok / views_unavailable / got_keys / got_count 等。
    调用方需根据 diagnostics.ok 决定是否走回退路径。
    """
    js = OBJECT_INSIGHTS_JS.read_text(encoding="utf-8")
    js = (js.replace("__POST_ID__", json.dumps(post_id))
            .replace("__ENTITY_DOC__", json.dumps(OI_ENTITY_DOC_ID))
            .replace("__SINGLE_DOC__", json.dumps(OI_SINGLE_DOC_ID)))
    out, err, rc = evaluate(session, js, timeout=timeout)
    if rc:
        raise RuntimeError("调用 object_insights GraphQL 失败: {}".format(err or out))
    try:
        data = json.loads(out)
    except json.JSONDecodeError as error:
        raise RuntimeError("object_insights 返回值无法解析: {}".format(out[:200])) from error
    diagnostics = {
        "ok": bool(data.get("ok")),
        "entity_type": data.get("entity_type"),
        "views_unavailable": bool(data.get("views_unavailable")),
        "got_keys": list(data.get("got_keys") or []),
        "got_count": int(data.get("got_count") or 0),
        "error": data.get("error"),
    }
    if not data["ok"]:
        raise RuntimeError("object_insights 未返回 Instagram 指标: {}".format(diagnostics["error"] or data))
    # 全字段返回（含 None）。调用方需要把 None 显式清掉，避免 IG 单值字段保留
    # Content 表格的 FB+IG 合并值。
    ig = dict(data.get("ig") or {})
    return ig, diagnostics


def enrich_cross_post_metrics(session, rows):
    """跨发布帖改用 object_insights 背后的 GraphQL 取 IG 单独指标。

    普通 IG 帖子完全使用 Content 表格返回的值（本身已是 IG 单值）；只有明确带
    跨发布关联的帖子才额外发一次请求。

    关键的"调用失败"判定（明确 vs 业务数据缺失）：
      - 探针拿不到任何 IG 字段（network/auth 中断）→ 回退 Content 表格指标；
      - 探针成功但 view 字段 TofuErrorQueryResult（Meta 老帖数据缺失）→ 视为成功，
        用 IG 单值字段覆盖 row['metrics']，views 字段清空（绝不沿用 Content 的合
        并值，否则会把 86,232 这种合并数当 IG 单值写入 Doris）。
    """
    if not rows:
        return
    cross_rows = [row for row in rows if row.get("is_cross_post")]
    for row in rows:
        if row not in cross_rows:
            row["ig_metrics_source"] = "content_table_ig_only"
    print("  Published posts 预判：{} 条普通 IG 帖子直接用 Content 表格；{} 条跨发布帖改用 object_insights GraphQL。".format(len(rows) - len(cross_rows), len(cross_rows)))
    for index, row in enumerate(cross_rows, 1):
        try:
            ig, diagnostics = fetch_ig_only_metrics(session, row["row_id"])
        except Exception as error:
            ig = None
            diagnostics = None
            print("    [{}/{}] {}: 调用失败（{}）".format(index, len(cross_rows), row["row_id"], error), file=sys.stderr, flush=True)
        if ig is None:
            # 整次探针失败（网络/会话/GraphQL errors），按业务约定回退 Content 表格
            # 合并指标，并标记来源；这里不能识别为跨发布后清洗，因为回退值就是合
            # 并的，标记为 fallback 让上层链路可观测。
            row["ig_metrics_source"] = "content_table_fallback_after_api_failure"
            print("    [{}/{}] {}: 回退 Content 表格指标".format(index, len(cross_rows), row["row_id"]), file=sys.stderr, flush=True)
            continue
        # 拿到 IG 单值（部分字段可能为 None）。先把 row['metrics'] 中所有 Content
        # 合并值清掉，再用 IG 单值覆盖；None 字段保持 None，避免 FB+IG 合并值残留。
        if row.get("metrics"):
            for key in list(row["metrics"]):
                row["metrics"][key] = None
        for key, value in ig.items():
            row.setdefault("metrics", {})[key] = value
        row["ig_metrics_source"] = "object_insights_api_ig_only"
        if diagnostics and diagnostics.get("views_unavailable"):
            row["ig_metrics_views_unavailable"] = True
            print("    [{}/{}] {}: views 业务无数据（Meta 老帖常见），其他 IG 字段已取到：got={}，reach={}，interaction={}，net_reactions={}".format(
                index, len(cross_rows), row["row_id"], diagnostics["got_keys"],
                ig.get("reach"), ig.get("interactions"), ig.get("net_reactions")), flush=True)
        else:
            print("    [{}/{}] {}: views={}，net_reactions={}，new_follows={}".format(
                index, len(cross_rows), row["row_id"], ig.get("views"), ig.get("net_reactions"), ig.get("new_follows")), flush=True)


def value(metrics, key, divisor=1):
    raw = metrics.get(key)
    if raw in (None, ""):
        return None  # 数据缺失（Meta 老帖 views 业务无数据常见）写 NULL，不写 0
    try:
        return float(raw) / divisor if divisor != 1 else raw
    except (TypeError, ValueError):
        return None


def map_post_type(source_row):
    """细分帖子类型：IG reel / IG image / IG carousel / IG story 等。"""
    mpt = source_row.get("media_product_type")
    if mpt:
        mapped = MEDIA_PRODUCT_TYPE_NAMES.get(str(mpt).lower())
        if mapped:
            return mapped
    entity_type = source_row.get("entity_type")
    if entity_type == "IG_STORY":
        return "IG story"
    if entity_type == "IG_POST":
        media_type = source_row.get("media_type")
        if media_type is not None:
            try:
                media_type = int(media_type)
            except (TypeError, ValueError):
                pass
            mapped = MEDIA_TYPE_NAMES.get(media_type)
            if mapped:
                return mapped
        metrics = source_row.get("metrics") or {}
        if metrics.get("video_play_time"):
            return "IG reel"
        return "IG image"
    return TYPE_NAMES.get(entity_type, entity_type or "")


def account_timezone(timezone_name):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # 项目 Python 未安装 tzdata 时保持可运行；该回退仅影响夏令时边界日。
        offsets = {"America/Los_Angeles": -7, "Europe/Berlin": 2}
        return timezone(timedelta(hours=offsets.get(timezone_name, 0)))


def format_publish_time(epoch, timezone_name):
    """按账号业务时区格式化发布时间，保留时区偏移（如 2026-03-31 18:02:50+0200）。"""
    if not epoch:
        return ""
    return datetime.fromtimestamp(float(epoch), timezone.utc).astimezone(account_timezone(timezone_name)).strftime("%Y-%m-%d %H:%M:%S%z")


def to_doris_row(raw, account, etl_date):
    """Map one Published posts row to the Doris target schema (ods_instagram_post_insights)."""
    metrics = raw.get("metrics") or {}
    created_at = raw.get("created_at")
    publish_time = format_publish_time(created_at, account["timezone"])
    duration_ms = raw.get("video_duration_in_sec")
    try:
        duration_ms = int(round(float(duration_ms) * 1000)) if duration_ms not in (None, "") else 0
    except (TypeError, ValueError):
        duration_ms = 0
    # account_id / account_username 均取接口返回值，缺失时回退脚本配置。
    username = raw.get("owner_username") or account["username"]
    account_id = raw.get("owner_id") or account["asset_id"]
    return {
        "date": etl_date,
        "post_id": raw.get("row_id", ""),
        "post_type": map_post_type(raw),
        "account_username": username,
        "account_name": "",
        "duration": duration_ms,
        "account_id": account_id,
        "title": (raw.get("title") or "").replace("\r", " ").replace("\n", " ").strip(),
        "publish_time": publish_time,
        "permalink": raw.get("permalink") or "",
        "views": value(metrics, "views"), "reach": value(metrics, "reach"), "viewers": value(metrics, "viewers"),
        "interactions": value(metrics, "interactions"),
        "likes_reactions": value(metrics, "net_reactions"), "comments": value(metrics, "net_comments"),
        "shares": value(metrics, "shares"), "saves": value(metrics, "net_saves"),
        "link_clicks": value(metrics, "link_clicks"), "replies": value(metrics, "replies"),
        "new_follows": value(metrics, "new_follows"),
        "video_play_time_min": value(metrics, "video_play_time", 60000),
        "avg_play_time_sec": value(metrics, "video_average_play_time", 1000),
        "video_3s_views": value(metrics, "video_three_second_views"),
        "instream_ads_earnings": value(metrics, "instream_ads_estimated_earnings", 100),
        "etl_date": etl_date,
    }


def load_doris_config(config_path):
    parser = configparser.ConfigParser()
    if not parser.read(config_path, encoding="utf-8") or not parser.has_section("doris"):
        raise ValueError("missing [doris] configuration in %s" % config_path)
    required = ("host", "be_port", "user", "password")
    missing = [key for key in required if not parser.get("doris", key, fallback="").strip()]
    if missing:
        raise ValueError("missing Doris configuration: %s" % ", ".join(missing))
    return {key: parser.get("doris", key).strip() for key in required}


def stream_load_rows(rows, config_path):
    """Write insight rows to Doris table ods_instagram_post_insights using NDJSON Stream Load."""
    if not rows:
        return {"Status": "Success", "NumberLoadedRows": 0, "Label": ""}
    config = load_doris_config(config_path)
    url = ("http://%s:%s/api/ods_social_media/ods_instagram_post_insights/_stream_load"
           % (config["host"], config["be_port"]))
    payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8")
    credentials = ("%s:%s" % (config["user"], config["password"])).encode("utf-8")
    request = Request(url, data=payload, method="PUT")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))
    request.add_header("format", "json")
    request.add_header("read_json_by_line", "true")
    request.add_header("columns", ",".join(DORIS_COLUMNS))
    request.add_header("label", "instagram_post_insights_" + uuid.uuid4().hex)
    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError("Doris Stream Load HTTP %s: %s" % (exc.code, body)) from exc
    except (URLError, OSError) as exc:
        raise RuntimeError("Doris Stream Load request failed: %s" % exc) from exc
    if result.get("Status") != "Success":
        raise RuntimeError("Doris Stream Load failed: %s" % result.get("Message", result))
    loaded_rows = int(result.get("NumberLoadedRows", 0))
    if loaded_rows != len(rows):
        raise RuntimeError("Doris Stream Load loaded %s of %s rows" % (loaded_rows, len(rows)))
    return result


def parse_dates(args):
    try:
        start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    except ValueError as error:
        raise SystemExit("--start-date 与 --end-date 必须是 YYYY-MM-DD") from error
    if start > end:
        raise SystemExit("--start-date 不能晚于 --end-date")
    return start.isoformat(), end.isoformat()


def main():
    parser = argparse.ArgumentParser(description="通过 Agent Reach 抓取两个 Instagram 账号的帖子级洞察并写入 Doris")
    parser.add_argument("--start-date", required=True, help="包含边界，YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="包含边界，YYYY-MM-DD")
    parser.add_argument("--session", default="dqg7tk9s", help="项目已连接的 OpenCLI 浏览器 session")
    parser.add_argument("--accounts", default="anycubicofficial,anycubic_deutschland", help="可选账号列表")
    parser.add_argument("--doris-config", default=str(DORIS_CONFIG), help="Doris 连接配置路径（credentials.ini）")
    parser.add_argument("--dry-run", action="store_true", help="只抓取并打印结果，不写入 Doris")
    args = parser.parse_args()
    start_date, end_date = parse_dates(args)
    selected = {x.strip() for x in args.accounts.split(",") if x.strip()}
    accounts = [a for a in ACCOUNTS if a["username"] in selected]
    if not accounts or len(accounts) != len(selected):
        raise SystemExit("--accounts 仅支持: {}".format(", ".join(a["username"] for a in ACCOUNTS)))
    etl_date = date.today().isoformat()
    all_doris_rows, failures = [], []
    for account in accounts:
        print("\n=== @{} | asset_id={} | business_id={} ===".format(account["username"], account["asset_id"], account["business_id"]))
        try:
            out, err, rc = browser(args.session, "open", page_url(account), timeout=120)
            if rc:
                raise RuntimeError("打开页面失败: {}".format(err or out))
            wait_for_page(args.session, account)
            install_request_hook(args.session)
            trigger_template_capture(args.session)
            save_query_template(args.session)
            run_windowed_fetch(args.session, start_date, end_date, account["asset_id"])
            wait_for_fetch(args.session)
            rows, report = read_rows(args.session)
            enrich_cross_post_metrics(args.session, rows)
            account_doris_rows = [to_doris_row(row, account, etl_date) for row in rows]
            all_doris_rows.extend(account_doris_rows)
            print("  完成：{} 条 IG 帖子/Story，GraphQL 请求 {} 次，拒绝 {} 条非 IG 记录".format(len(rows), report.get("requests", 0), report.get("rejected", 0)))
        except Exception as error:
            failures.append("{}: {}".format(account["username"], error))
            print("ERROR: {}".format(failures[-1]), file=sys.stderr)
            continue

    loaded_total = 0
    if all_doris_rows:
        all_doris_rows.sort(key=lambda row: (row["account_username"], row["publish_time"]), reverse=True)
        if args.dry_run:
            print("\n[dry-run] 跳过 Doris 写入，共 {} 行：".format(len(all_doris_rows)))
            # dry-run 在 Windows Python 默认 GBK stdout 下，打印字典会因字符触发编码错。
            # 改为写到临时 utf-8 文件，并在 stdout 概要展示，避免 emoji/CJK 抛错。
            preview = sorted(all_doris_rows, key=lambda r: (r.get("account_username") or "", r.get("publish_time") or ""), reverse=True)[:5]
            print("  前 5 行预览：")
            for row in preview:
                print("    " + json.dumps(row, ensure_ascii=False))
            dump_path = Path(args.doris_config).parent / "dry_run_dump.json"
            dump_path.write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in all_doris_rows),
                encoding="utf-8")
            print("  全量数据已写入临时文件: {}".format(dump_path))
        else:
            result = stream_load_rows(all_doris_rows, Path(args.doris_config))
            loaded_total = int(result.get("NumberLoadedRows", 0))
            print("\n已写入 Doris(ods_instagram_post_insights): {} 行，filtered={}，unselected={}".format(
                loaded_total, result.get("NumberFilteredRows", 0), result.get("NumberUnselectedRows", 0)))
    else:
        print("\n无数据可写入 Doris")

    if failures:
        print("失败账号：\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    sys.exit(main())
