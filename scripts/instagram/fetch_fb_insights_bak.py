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
import json
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
WINDOWED_JS = os.path.join(BASE, "../tmp/content_version/fb_inpage_windowed.js")
EXCEL_PY = os.path.join(BASE, "fb_to_excel.py")

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


def main():
    parser = argparse.ArgumentParser(description="一键抓取 Meta Business Suite 全量帖子洞察")
    parser.add_argument("--session", default="dqg7tk9s", help="opencli 浏览器 session id")
    parser.add_argument("--business-id", default="761831987530602", help="Meta business ID")
    parser.add_argument("--asset-id", default="213562039049926", help="Meta asset/page ID")
    parser.add_argument("--from", dest="from_date", default="2016-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default="2026-08-24", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--json-out", default=os.path.join(BASE, "fb_all_rows.json"), help="输出 JSON 路径")
    parser.add_argument("--xlsx-out", default=os.path.join(BASE, "fb_all.xlsx"), help="输出 Excel 路径")
    parser.add_argument("--skip-capture", action="store_true", help="如果页面已保存过模板，跳过 UI 触发捕获")
    args = parser.parse_args()

    print("=" * 60)
    print("Meta Business Suite 全量帖子一键抓取")
    print("=" * 60)

    # 1. 页面
    url = current_url(args.session)
    if "business.facebook.com" not in url:
        open_page(args.session, args.business_id, args.asset_id)
    else:
        print(f"复用当前页面: {url[:80]}")

    if not wait_for_grid(args.session, max_wait=60):
        print("表格未加载，请检查页面状态后重试。")
        return 1

    # 2. 捕获模板
    if not args.skip_capture:
        install_capture_hook(args.session)
        # 当前时间范围按钮文本
        out, _, _ = browser_eval(
            args.session,
            "JSON.stringify({text: Array.from(document.querySelectorAll('div[role=button]')).map(e => e.innerText).find(t => t && (t.includes('Last') || t.includes('days')))})",
            timeout=10,
        )
        try:
            current = json.loads(out).get("text", "")
        except Exception:
            current = "Last 7 days"
        current_label = (current.split(":")[0] if current else "Last 7 days").strip()
        target_label = "Last 28 days" if current_label == "Last 7 days" else "Last 7 days"
        print(f"切换时间范围: {current_label} -> {target_label}")
        click_time_range_option(args.session, current_label, target_label)
        if not save_template(args.session):
            print("未能保存请求模板，请确认 hook 是否捕获到表格查询。")
            return 1
    else:
        out, _, _ = browser_eval(args.session, "typeof window.__fbQBodyVar", timeout=10)
        if out != "string":
            print("页面没有已保存的模板，不能跳过捕获。")
            return 1
        print("使用页面已保存模板")

    # 3. 抓取
    ensure_native_fetch(args.session)
    if not run_windowed_fetch(args.session, args.from_date, args.to_date):
        return 1
    if not poll_progress(args.session):
        return 1

    # 4. 导出
    if not export_json(args.session, args.json_out):
        return 1
    if not generate_excel(args.json_out, args.xlsx_out):
        return 1

    print("=" * 60)
    print("完成！")
    print(f"JSON: {args.json_out}")
    print(f"Excel: {args.xlsx_out}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
