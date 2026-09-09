# -*- coding: utf-8 -*-
"""通过 Agent Reach 项目内 OpenCLI 抓取 Meta Business Suite 的 Instagram 帖子洞察。

数据源是已登录的 Meta Business Suite 的 Published posts 页面；每个账号以其
Instagram asset_id 单独发起 Content GraphQL 查询，并保留响应中的所有 entity_type=IG_POST
记录，不按 owner_id 过滤；Facebook 节点仍会被排除。跨发布帖另行进入 object_insights 获取 IG 专属指标。

示例：
  E:\\CCProject\\agent_reach\\.agent-reach-venv\\Scripts\\python.exe fetch_instagram_posts.py ^
    --start-date 2026-08-01 --end-date 2026-08-07
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE = Path(__file__).resolve().parent
WINDOWED_JS = BASE / "ig_inpage_windowed.js"
NODE = r"C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"
OPENCLI_JS = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"

ACCOUNTS = (
    {"username": "anycubicofficial", "asset_id": "17841406045865168", "business_id": "800253393765350", "timezone": "America/Los_Angeles"},
    {"username": "anycubic_deutschland", "asset_id": "17841414725872019", "business_id": "761831987530602", "timezone": "Europe/Berlin"},
)
COLUMNS = [
    "date", "post_id", "account_id", "account_username", "title", "publish_time",
    "views", "reach", "interactions", "likes_reactions", "comments", "shares", "saves",
    "link_clicks", "replies", "new_follows", "video_play_time_min", "avg_play_time_sec",
    "video_3s_views", "instream_ads_earnings", "etl_date",
]


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
    return "https://business.facebook.com/latest/posts/published_posts/?business_id={}&asset_id={}".format(account["business_id"], account["asset_id"])


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


def fetch_cross_post_ig_metrics(session, account, post_id):
    """从 object_insights 的 Instagram 标签读取跨发帖的 IG 专属指标。

    Content 表格对跨发帖返回 FB+IG 合并值；object_insights 在 Instagram 标签
    展示同一 IG 对象的专属数值，因此以该页面返回值覆盖合并值。
    """
    url = (
        "https://business.facebook.com/latest/insights/object_insights/"
        "?asset_id={}&business_id={}&content_id={}&nav_ref=bizweb_insights_uta_table"
    ).format(account["asset_id"], account["business_id"], post_id)
    out, err, rc = browser(session, "open", url, timeout=120)
    if rc:
        raise RuntimeError("打开跨发帖 IG 洞察页失败: {}".format(err or out))
    # Total performance 页的 Views 分拆会给出精确的 "N from Instagram"；Instagram
    # 标签仅显示缩写（如 46.3K），所以先读取该精确 IG 分项，再切换标签读取其余指标。
    exact_views_js = r'''(() => {
      const text = (document.body && document.body.innerText) || '';
      const match = text.match(/([\d,]+)\s+from Instagram/i);
      return JSON.stringify({views: match ? Number(match[1].replace(/,/g, '')) : null});
    })()'''

    def read_exact_views():
        out, err, rc = evaluate(session, exact_views_js, timeout=45)
        if rc:
            raise RuntimeError("读取跨发帖 Instagram 精确 Views 失败: {}".format(err or out))
        return json.loads(out).get("views")

    exact_views = read_exact_views()
    # Published posts 已明确判定为跨发布，但 object_insights 有时会延迟加载平台分拆。
    # 首次未出现时，每隔 30 秒刷新页面并再尝试，最多重试 3 次（共 4 次读取）。
    for retry in range(1, 4):
        if exact_views is not None:
            break
        print("      {}: 未找到 Instagram 分拆，30 秒后刷新第 {}/3 次...".format(post_id, retry), flush=True)
        time.sleep(30)
        out, err, rc = browser(session, "open", url, timeout=120)
        if rc:
            raise RuntimeError("刷新跨发帖 IG 洞察页失败: {}".format(err or out))
        exact_views = read_exact_views()

    # 三次刷新后依旧没有 Instagram 分拆，无法可靠覆写合并值；按约定回退
    # Published posts 的 Content 表格指标，而不是清空或中断账号处理。
    if exact_views is None:
        print("      {}: 重试 3 次仍未找到 Instagram 分拆，回退 Content 表格指标".format(post_id), file=sys.stderr, flush=True)
        return None
    switch_js = r'''(async () => {
      const deadline = Date.now() + 60000;
      while (Date.now() < deadline) {
        const choices = Array.from(document.querySelectorAll('[role=tab],div,span,button')).filter(x =>
          (x.innerText || '').trim() === 'Instagram' && !Array.from(x.children).some(c => (c.innerText || '').trim() === 'Instagram'));
        if (choices.length) { choices[0].click(); await new Promise(r => setTimeout(r, 2500)); return 'switched'; }
        await new Promise(r => setTimeout(r, 500));
      }
      return 'Instagram tab not found';
    })()'''
    out, err, rc = evaluate(session, switch_js, timeout=90)
    if rc or "switched" not in out:
        raise RuntimeError("切换跨发帖到 Instagram 标签失败: {}".format(err or out))
    extract_js = r'''(() => {
      const text = (document.body && document.body.innerText) || '';
      const number = raw => {
        const s = String(raw || '').replace(/,/g, '').trim();
        const m = s.match(/^([0-9]+(?:\.[0-9]+)?)([KM])?$/i);
        if (!m) return null;
        const base = Number(m[1]); return m[2] && m[2].toUpperCase() === 'K' ? Math.round(base * 1000) : (m[2] ? Math.round(base * 1000000) : base);
      };
      const afterLabel = label => {
        const index = text.indexOf(label); if (index < 0) return null;
        const tail = text.slice(index + label.length, index + label.length + 120);
        const values = tail.split(/\n+/).map(x => x.trim()).filter(Boolean);
        return number(values.find(x => /^\d[\d,.]*[KM]?$/i.test(x)));
      };
      const totalMatch = text.match(/Views\s*\n\s*[\u200B\s]*\n\s*([\d,.]+[KM]?)/i) || text.match(/Views\s*\n\s*([\d,.]+[KM]?)/i);
      return JSON.stringify({
        views: totalMatch ? number(totalMatch[1]) : null,
        reach: afterLabel('Reach'), interactions: afterLabel('Interactions'),
        net_reactions: afterLabel('Likes and reactions'), net_comments: afterLabel('Comments'),
        shares: afterLabel('Shares'), net_saves: afterLabel('Saves'), new_follows: afterLabel('Follows')
      });
    })()'''
    out, err, rc = evaluate(session, extract_js, timeout=45)
    if rc:
        raise RuntimeError("读取跨发帖 Instagram 指标失败: {}".format(err or out))
    metrics = json.loads(out)
    if exact_views is not None:
        metrics["views"] = exact_views
    if metrics.get("views") is None or metrics.get("net_reactions") is None:
        raise RuntimeError("跨发帖 Instagram 页面未返回必要指标: {}".format(metrics))
    return {key: value for key, value in metrics.items() if value is not None}


def enrich_cross_post_metrics(session, account, rows):
    """依据 Published posts 响应的 cross_post 字段决定是否访问 object_insights。

    普通 IG 帖子完全使用 Content 表格已返回的 IG 指标；只有明确带跨发布关联的
    帖子才进入 object_insights，读取 Instagram 标签的专属数值。
    """
    if not rows:
        return
    cross_rows = [row for row in rows if row.get("is_cross_post")]
    for row in rows:
        if row not in cross_rows:
            row["ig_metrics_source"] = "content_table_ig_only"
    print("  Published posts 预判：{} 条普通 IG 帖子直接用 Content 表格；{} 条跨发布帖进入 object_insights。".format(len(rows) - len(cross_rows), len(cross_rows)))
    for index, row in enumerate(cross_rows, 1):
        metrics = fetch_cross_post_ig_metrics(session, account, row["row_id"])
        if metrics is None:
            # object_insights 已按 30 秒间隔刷新重试 3 次，仍无 Instagram 分拆时，
            # 按业务约定回退 Published posts Content 表格的原始指标。
            row["ig_metrics_source"] = "content_table_fallback_after_ig_split_retry"
            print("    [{}/{}] {}: 重试后仍无 Instagram 分拆，回退 Content 表格指标".format(index, len(cross_rows), row["row_id"]), file=sys.stderr)
            continue
        row["metrics"] = {key: None for key in row.get("metrics", {})}
        row["metrics"].update(metrics)
        row["ig_metrics_source"] = "object_insights_instagram_tab"
        print("    [{}/{}] {}: views={}，likes_reactions={}".format(index, len(cross_rows), row["row_id"], metrics.get("views"), metrics.get("net_reactions")))


def account_timezone(timezone_name):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # Windows 的项目 Python 未安装 tzdata 时仍保持可运行；该回退仅影响夏令时边界日。
        offsets = {"America/Los_Angeles": -7, "Europe/Berlin": 2}
        return timezone(timedelta(hours=offsets.get(timezone_name, 0)))


def format_publish_time(epoch, timezone_name):
    if not epoch:
        return ""
    return datetime.fromtimestamp(float(epoch), timezone.utc).astimezone(account_timezone(timezone_name)).strftime("%Y-%m-%d %H:%M:%S%z")


def local_date(epoch, timezone_name):
    if not epoch:
        return ""
    return datetime.fromtimestamp(float(epoch), timezone.utc).astimezone(account_timezone(timezone_name)).date().isoformat()


def value(metrics, key, divisor=1):
    raw = metrics.get(key)
    if raw in (None, ""):
        return 0
    try:
        return float(raw) / divisor if divisor != 1 else raw
    except (TypeError, ValueError):
        return 0


def to_export_row(raw, account, etl_date):
    metrics = raw.get("metrics") or {}
    # account_username 优先取接口返回值，缺失时回退到脚本配置的账号名。
    username = raw.get("owner_username") or account["username"]
    return {
        "date": local_date(raw.get("created_at"), account["timezone"]),
        "post_id": raw.get("row_id", ""), "account_id": account["asset_id"], "account_username": username,
        "title": (raw.get("title") or "").replace("\r", " ").replace("\n", " ").strip(), "publish_time": format_publish_time(raw.get("created_at"), account["timezone"]),
        "views": value(metrics, "views"), "reach": value(metrics, "reach"), "interactions": value(metrics, "interactions"),
        "likes_reactions": value(metrics, "net_reactions"), "comments": value(metrics, "net_comments"), "shares": value(metrics, "shares"),
        "saves": value(metrics, "net_saves"), "link_clicks": value(metrics, "link_clicks"), "replies": value(metrics, "replies"),
        "new_follows": value(metrics, "new_follows"), "video_play_time_min": value(metrics, "video_play_time", 60000),
        "avg_play_time_sec": value(metrics, "video_average_play_time", 1000), "video_3s_views": value(metrics, "video_three_second_views"),
        "instream_ads_earnings": value(metrics, "instream_ads_estimated_earnings", 100), "etl_date": etl_date,
    }


def write_csv(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


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
    parser = argparse.ArgumentParser(description="通过 Agent Reach 抓取两个 Instagram 账号的帖子级洞察")
    parser.add_argument("--start-date", required=True, help="包含边界，YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="包含边界，YYYY-MM-DD")
    parser.add_argument("--session", default="dqg7tk9s", help="项目已连接的 OpenCLI 浏览器 session")
    parser.add_argument("--accounts", default="anycubicofficial,anycubic_deutschland", help="可选账号列表")
    parser.add_argument("--output", default=None, help="CSV 输出路径")
    parser.add_argument("--raw-output", default=None, help="原始 JSON 输出路径，用于审计")
    args = parser.parse_args()
    start_date, end_date = parse_dates(args)
    selected = {x.strip() for x in args.accounts.split(",") if x.strip()}
    accounts = [a for a in ACCOUNTS if a["username"] in selected]
    if not accounts or len(accounts) != len(selected):
        raise SystemExit("--accounts 仅支持: {}".format(", ".join(a["username"] for a in ACCOUNTS)))
    stamp = "{}_{}".format(start_date.replace("-", ""), end_date.replace("-", ""))
    output = Path(args.output) if args.output else BASE / "output" / "instagram_posts_{}.csv".format(stamp)
    raw_output = Path(args.raw_output) if args.raw_output else BASE / "output" / "instagram_posts_{}_raw.json".format(stamp)
    etl_date = date.today().isoformat()
    all_export, all_raw, failures = [], {}, []
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
            enrich_cross_post_metrics(args.session, account, rows)
            all_raw[account["username"]] = {"account": account, "report": report, "rows": rows}
            all_export.extend(to_export_row(row, account, etl_date) for row in rows)
            print("  完成：{} 条 IG 帖子，GraphQL 请求 {} 次，拒绝 {} 条非 IG 记录".format(len(rows), report.get("requests", 0), report.get("rejected", 0)))
        except Exception as error:
            failures.append("{}: {}".format(account["username"], error))
            print("ERROR: {}".format(failures[-1]), file=sys.stderr)
    all_export.sort(key=lambda row: (row["account_username"], row["publish_time"]), reverse=True)
    write_csv(all_export, output)
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(json.dumps(all_raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已导出 {} 行: {}".format(len(all_export), output))
    print("原始审计数据: {}".format(raw_output))
    if failures:
        print("失败账号：\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
