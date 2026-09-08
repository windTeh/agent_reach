# -*- coding: utf-8 -*-
"""
抓取 Meta Business Suite Instagram 账号级每日概览数据。
页面: business.facebook.com/latest/insights/results

直接从页面 DOM 提取每日时间序列数据（包含 Unix 时间戳和指标值）。

指标:
  - Views (展示量)
  - Reach (覆盖人数)
  - Content interactions (内容互动)
  - Follows (关注)
  - Profile visits (主页访问)
  - Link clicks (链接点击)
  - Unfollows (取消关注)

用法:
    python fetch_account_overview.py --start-date 2026-07-01 --end-date 2026-07-31
"""
import argparse
import base64
import configparser
import csv
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.path.dirname(os.path.abspath(__file__))

# 两个 IG 账号配置
# tz: Meta 账户时区，用于把 Unix 时间戳正确转换为「账户本地日期」
#     避免 UTC 转换造成的日期偏移一天
ACCOUNTS = [
    {'name': 'anycubicofficial', 'instagram_business_id': '17841406045865168',
     'business_id': '800253393765350', 'tz': 'America/Los_Angeles'},
    {'name': 'anycubic_deutschland', 'instagram_business_id': '17841414725872019',
     'business_id': '761831987530602', 'tz': 'Europe/Berlin'},
]

# Doris 目标表与列定义
DORIS_TABLE = 'ods_instagram_page_insights_daily'
DORIS_COLUMNS = [
    'date', 'account_name', 'instagram_business_id',
    'views', 'reach', 'content_interactions',
    'follows', 'profile_visits', 'link_clicks', 'unfollows',
    'etl_date',
]

# opencli 路径
NODE = r"D:\Program Files\nodejs\node.exe"
OPENCLI_JS = r"E:\CCProject\agent_reach\.opencli-tmp\node_modules\@jackwener\opencli\dist\src\main.js"


# ─── opencli 浏览器操作 ─────────────────────────────────────────────

def opencli(session, *args, timeout=60):
    cmd = [NODE, OPENCLI_JS, "browser", session] + list(args)
    out, err, rc = run(cmd, timeout=timeout)
    return _filter_cli_lines(out), err, rc


def run(cmd, timeout=60, shell=False):
    result = subprocess.run(cmd, shell=shell, capture_output=True, text=False, timeout=timeout)
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    return stdout.strip(), stderr.strip(), result.returncode


def _filter_cli_lines(out):
    lines = [ln for ln in out.splitlines() if not (
        ln.startswith("Update available") or ln.startswith("Run: ") or
        ln.startswith("Extension update") or ln.startswith("Download: ")
    )]
    return "\n".join(lines)


def browser_eval(session, js_code, timeout=60):
    return opencli(session, "eval", js_code, timeout=timeout)


def current_url(session):
    out, _, _ = browser_eval(session, "location.href", timeout=10)
    return out


# ─── 页面操作 ─────────────────────────────────────────────────────

def open_results_page(session, business_id, instagram_business_id):
    """打开 insights/results 页面。

    关键：Results 页面用 URL 参数 asset_id（不是 instagram_business_id）
    指定要展示哪个 Instagram Business 账号。
    """
    url = (
        f"https://business.facebook.com/latest/insights/results/"
        f"?business_id={business_id}&asset_id={instagram_business_id}"
    )
    out, err, rc = opencli(session, "open", url, timeout=120)
    print(f"已打开 Results 页面 (rc={rc})")
    return url


def wait_for_account_switch(session, ig_business_id, account_name, max_wait=30):
    """等待页面真正切换到目标账号。

    open_results_page 后，URL 可能还是上一个账号的缓存，
    必须等 URL 的 asset_id=当前 instagram_business_id 才算切换成功。
    """
    target_marker = f"asset_id={ig_business_id}"
    for i in range(max_wait):
        url = current_url(session)
        if target_marker in url:
            # 再额外等 1 秒让 React 重新渲染
            time.sleep(1)
            print(f"  账号 {account_name} 页面已切换 ({i+1}s)")
            return True
        time.sleep(1)
    print(f"  账号 {account_name} 页面切换超时 ({max_wait}s)")
    return False


def switch_to_instagram(session):
    """Results 页面默认显示 Facebook Page 数据，需切换到 Instagram 账号。

    页面顶部 Entity selector 默认显示 'Facebook'，点击后选择 'Instagram'。
    如果当前已经是 Instagram，则跳过。
    """
    js = r"""
(async () => {
  function text(el) { return (el.innerText || el.textContent || '').trim(); }
  function norm(s) { return s.replace(/[^a-z]/gi, '').toLowerCase(); }

  // 检查当前实体
  const bodyText = document.body ? document.body.innerText : '';
  const header = bodyText.split('\n').slice(0, 20).join(' ');
  if (/Entity selector.*Instagram/.test(header) || /\bInstagram\b/.test(header) && !/Facebook visits/.test(bodyText)) {
    return JSON.stringify({ok: true, action: 'already_instagram'});
  }

  // 1. 点 'Facebook' 展开 Entity selector
  const all = Array.from(document.querySelectorAll('div'));
  const fb = all.find(el => /^Facebook$/i.test(text(el)) && el.children.length <= 2);
  if (!fb) {
    return JSON.stringify({ok: false, step: 'find_facebook_btn', msg: 'Facebook entity button not found'});
  }
  fb.click();
  await new Promise(r => setTimeout(r, 1000));

  // 2. 选择 Instagram
  const opts = Array.from(document.querySelectorAll('div, span, button, [role="option"], [role="menuitem"]'));
  const igOpt = opts.find(el => /^Instagram$/i.test(text(el)));
  if (!igOpt) {
    return JSON.stringify({ok: false, step: 'find_instagram_opt', msg: 'Instagram option not found'});
  }
  igOpt.click();
  await new Promise(r => setTimeout(r, 2000));

  return JSON.stringify({ok: true, action: 'switched'});
})()
"""
    out, err, rc = browser_eval(session, js, timeout=30)
    if err and rc != 0:
        print(f"  切换实体错误: {err.strip()[:200]}")
        return {'ok': False, 'step': 'browser_eval', 'msg': err.strip()[:200]}
    try:
        result = json.loads(out)
        if result.get('ok'):
            print(f"  实体: {result.get('action')}")
        else:
            print(f"  ⚠️  切换实体失败: step={result.get('step')}, msg={result.get('msg')}")
        return result
    except Exception as e:
        print(f"  切换实体解析失败: {e}")
        return {'ok': False, 'step': 'parse', 'msg': str(e)}


def wait_for_overview(session, max_wait=90):
    """等待概览页面加载完成。"""
    for i in range(max_wait):
        out, _, _ = browser_eval(
            session,
            "document.body ? document.body.innerText.length : 0",
            timeout=10,
        )
        body_len = int(out) if out.isdigit() else 0
        if body_len > 3000:
            print(f"概览页面已加载 ({i+1}s, bodyLen={body_len})")
            return True
        time.sleep(1)
    print(f"页面加载超时 ({max_wait}s)")
    return False


# ─── 数据提取 ─────────────────────────────────────────────────────

def set_account_timezone(session, tz):
    """把账户时区注入到页面 window，供后续 extract 阶段读取。"""
    js = f"window.__IG_ACCOUNT_TZ__ = {json.dumps(tz)}; window.__IG_ACCOUNT_TZ__;"
    out, _, _ = browser_eval(session, js, timeout=10)
    return out


def set_date_range_ui(session, start_date, end_date):
    """在 Results 页面通过 UI 设置自定义日期范围。

    流程（基于对 Results 页面的实际探索）：
      1. 找到时间按钮（"Last 28 days: ..."），点击展开日历面板
      2. 日历面板是双月视图，显示两个月 + Previous month / Next month 翻页按钮
      3. 每个日期按钮的 aria-label 形如 "Saturday, 1 August 2026"
      4. 翻月到 start_date 所在月份，点击对应日期（设为起始）
      5. 翻月到 end_date 所在月份，点击对应日期（设为结束）
      6. 找 Apply 按钮（或 Update/Done）点击提交
      7. 等待 React 重渲染完成（页面时间范围会更新）

    失败兜底：返回错误信息，由 fetch_account_overview 决定是否回退到默认窗口。

    参数:
      start_date, end_date: 'YYYY-MM-DD' 字符串
    返回:
      dict: {ok: bool, step: str, msg: str, ...}
    """
    js = r"""
(async () => {
  const sd = __SD_START__;
  const ed = __SD_END__;

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function text(el) { return (el.innerText || el.textContent || '').trim(); }
  function aria(el) { return el.getAttribute('aria-label') || ''; }
  const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  function ymIdx(d) {
    const [y, m] = d.split('-').map(Number);
    return y * 12 + (m - 1);
  }
  function toYM(label) {
    // label = "August 2026"
    const parts = label.split(/\s+/);
    const mi = MONTHS.findIndex(x => x.toLowerCase() === (parts[0]||'').toLowerCase());
    return mi < 0 ? null : Number(parts[1]) * 12 + mi;
  }

  // ── 步骤 1: 点时间按钮展开日历面板 ──
  const allBtns = () => Array.from(document.querySelectorAll('div[role="button"], span[role="button"]'));
  const dateBtn = allBtns().find(b => /Last\s+\d+\s+(day|week|month|year)s?/i.test(text(b)));
  if (!dateBtn) {
    return JSON.stringify({ok: false, step: 'find_date_btn', msg: 'no date range button found'});
  }
  dateBtn.click();
  await sleep(800);

  // ── 读取当前可见的月份（取面板最上方的 "Month Year" 标题） ──
  function visibleMonths() {
    const heads = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,div,span'))
      .map(el => text(el))
      .filter(t => new RegExp('^(January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{4}$', 'i').test(t));
    return heads.slice(0, 2);
  }

  // ── 翻月工具 ──
  // 注意: Meta 按钮文本带零宽空格 U+200B，需用 replace(/[^a-z]/gi,'') 归一化
  function norm(s) { return s.replace(/[^a-z]/gi, '').toLowerCase(); }
  function clickPrev() {
    const b = allBtns().find(x =>
      norm(text(x)) === 'previousmonth' ||
      norm(aria(x)).includes('previousmonth'));
    if (b) { b.click(); return true; }
    return false;
  }
  function clickNext() {
    const b = allBtns().find(x =>
      norm(text(x)) === 'nextmonth' ||
      norm(aria(x)).includes('nextmonth'));
    if (b) { b.click(); return true; }
    return false;
  }

  // ── 翻到目标月：左面板为起始月 ──
  async function navigateTo(targetYM) {
    let safety = 60;
    while (safety-- > 0) {
      const v = visibleMonths();
      if (!v.length) break;
      const leftYM = toYM(v[0]);
      if (leftYM == null) break;
      if (leftYM <= targetYM) break;
      if (!clickPrev()) break;
      await sleep(300);
    }
  }

  // ── 步骤 2: 翻到 start_date 所在月 ──
  const sdYM = ymIdx(sd);
  await navigateTo(sdYM);
  await sleep(400);

  // ── 步骤 3: 点开始日期 ──
  const sdParts = sd.split('-').map(Number);
  function findDateBtn(y, m, d) {
    const mName = MONTHS[m];
    return allBtns().find(b => {
      const al = aria(b);
      // aria-label 格式: "Weekday, D Month YYYY" (e.g. "Thursday, 20 August 2026")
      return al.includes(d + ' ' + mName + ' ' + y);
    });
  }
  const sdBtn = findDateBtn(sdParts[0], sdParts[1] - 1, sdParts[2]);
  if (!sdBtn) {
    return JSON.stringify({ok: false, step: 'find_start_date',
      msg: 'start date button not found', sd, visibleMonths: visibleMonths()});
  }
  sdBtn.click();
  await sleep(400);

  // ── 步骤 4: 翻到 end_date 所在月（如不同） ──
  const edYM = ymIdx(ed);
  if (edYM > sdYM) {
    await navigateTo(edYM);
    await sleep(400);
  }

  // ── 步骤 5: 点结束日期 ──
  const edParts = ed.split('-').map(Number);
  const edBtn = findDateBtn(edParts[0], edParts[1] - 1, edParts[2]);
  if (!edBtn) {
    return JSON.stringify({ok: false, step: 'find_end_date',
      msg: 'end date button not found', ed, visibleMonths: visibleMonths()});
  }
  edBtn.click();
  await sleep(400);

  // ── 步骤 6: 找 Apply/Update/Done 按钮 ──
  const applyBtn = allBtns().find(b => {
    const t = text(b).toLowerCase();
    return t === 'apply' || t === 'update' || t === 'done';
  });
  if (!applyBtn) {
    return JSON.stringify({ok: false, step: 'find_apply', msg: 'Apply button not found'});
  }
  applyBtn.click();
  await sleep(1500);

  return JSON.stringify({ok: true, clickedStart: sd, clickedEnd: ed});
})()
"""
    js = js.replace('__SD_START__', json.dumps(start_date))
    js = js.replace('__SD_END__', json.dumps(end_date))

    out, err, rc = browser_eval(session, js, timeout=60)
    if err and rc != 0:
        print(f"  set_date_range_ui 错误: {err.strip()[:200]}")
        return {'ok': False, 'step': 'browser_eval', 'msg': err.strip()[:200]}
    try:
        result = json.loads(out)
        if result.get('ok'):
            print(f"  日期范围设置成功: {result.get('clickedStart')} ~ {result.get('clickedEnd')}")
        else:
            print(f"  ⚠️  日期范围设置失败: step={result.get('step')}, msg={result.get('msg')}")
            if result.get('visibleMonths'):
                print(f"     可见月份: {result['visibleMonths']}")
        return result
    except Exception as e:
        print(f"  set_date_range_ui 解析失败: {e}")
        print(f"  原始输出: {out[:500] if out else 'empty'}")
        return {'ok': False, 'step': 'parse', 'msg': str(e), 'raw': out[:500]}


def extract_metrics_from_dom(session):
    """从页面 DOM 提取所有指标的时间序列数据。

    关键改进:
      1. document.body 防御: 避免 body 还未挂载时抛 TypeError
      2. 时区感知: 使用账户 TZ (window.__IG_ACCOUNT_TZ__) 把 Unix 时间戳转为本地日期，
         避免 toISOString().slice(0,10) 用 UTC 导致日期偏移一天
      3. 位置锚定: 每个 metric 用 indexOf(pattern) 定位，再在 2000 字符窗口内
         找 Primary 数据行，杜绝 [\\s\\S]*? 跨块误匹配（Views 时间戳错抓 Reach 数值）

    返回: {metric_name: {date_str: value, ...}, ...}
    注意: 提取的日期范围取决于页面当前设置的日期（由 set_date_range_ui 控制）
    """
    js = r"""
(() => {
  if (!document.body) return JSON.stringify({_meta: {error: 'no body'}});
  const text = document.body.innerText;
  if (!text) return JSON.stringify({_meta: {error: 'no text'}});

  const results = {_dates: []};

  // 1. 提取日期范围
  const dateRangeMatch = text.match(/(?:Last\s+\d+\s+days|Performance)[:\s]+([A-Za-z]+\s+\d+,\s+\d+)\s*[-–]\s*([A-Za-z]+\s+\d+,\s+\d+)/);
  if (dateRangeMatch) {
    results._meta = {
      dateRange: `${dateRangeMatch[1]} - ${dateRangeMatch[2]}`,
      startDate: dateRangeMatch[1],
      endDate: dateRangeMatch[2]
    };
  }

  // 2. 时区（python 端注入；fallback 为美西 PT）
  const tz = window.__IG_ACCOUNT_TZ__ || 'America/Los_Angeles';
  results._meta = results._meta || {};
  results._meta.timezone = tz;

  // 3. 找时间戳行（全文唯一一组，所有指标共享）
  const tsMatch = text.match(/(\d{10}(?:\t\d{10})+)/);
  if (!tsMatch) return JSON.stringify({_meta: {...results._meta, error: 'no timestamps'}});
  const timestamps = tsMatch[1].split('\t').map(t => parseInt(t));

  // 4. 用账户 TZ 把时间戳转为日期字符串（YYYY-MM-DD）
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit'
  });
  results._dates = timestamps.map(ts => {
    const d = new Date(ts * 1000);
    const parts = fmt.formatToParts(d);
    const y = parts.find(p => p.type === 'year').value;
    const m = parts.find(p => p.type === 'month').value;
    const day = parts.find(p => p.type === 'day').value;
    return `${y}-${m}-${day}`;
  });

  // 5. 指标定义
  // Results 页面账号级指标实际显示名（按页面 innerText 顺序）：
  //   Views / Viewers(=Reach) / Content interactions / Link clicks / Visits / Follows
  //   注意：Results 页面不展示 Unfollows（需到 Audience 子页或 Graph API 才有）
  //   anchor 用「主标题」（出现在 Primary 数据行之前），不用 "Facebook xxx" 描述文字
  //   （描述文字在 Primary 之后，作为 anchor 会错过数据行）
  const metrics = [
    {name: 'views', patterns: ['Views']},
    {name: 'reach', patterns: ['Viewers', 'Reach']},
    {name: 'content_interactions', patterns: ['Content interactions']},
    {name: 'follows', patterns: ['Follows']},
    {name: 'unfollows', patterns: ['Unfollows']},
    {name: 'profile_visits', patterns: ['Visits', 'Profile visits']},
    {name: 'link_clicks', patterns: ['Link clicks']},
  ];

  // 6. 位置锚定提取：每个 metric 在自身窗口内找 Primary 数据
  //    2000 字符足够覆盖一个 metric chart 块，且不会跨入下一个 metric
  const MAX_LOOKAHEAD = 2000;
  for (const metric of metrics) {
    let matched = false;
    for (const pattern of metric.patterns) {
      const idx = text.indexOf(pattern);
      if (idx === -1) continue;
      const window = text.slice(idx, idx + MAX_LOOKAHEAD);
      const primaryMatch = window.match(/Primary\t([\d.]+(?:\t[\d.]+)*)/);
      if (!primaryMatch) continue;
      const values = primaryMatch[1].split('\t').map(v => parseFloat(v.replace(/,/g, '')));
      if (values.length !== timestamps.length) continue;
      const dailyData = {};
      for (let i = 0; i < values.length; i++) {
        dailyData[results._dates[i]] = values[i];
      }
      results[metric.name] = dailyData;
      matched = true;
      break;
    }
  }

  results._meta.metricsFound = Object.keys(results).filter(
    k => !k.startsWith('_')
  ).length;
  results._meta.availableDates = results._dates;

  return JSON.stringify(results);
})()
"""
    out, err, rc = browser_eval(session, js, timeout=30)
    try:
        data = json.loads(out)
        return data
    except Exception as e:
        print(f"DOM 提取解析错误: {e}")
        print(f"原始输出: {out[:500] if out else 'empty'}")
        return {}


def extract_metrics_via_hook(session):
    """通过 hook 捕获 GraphQL 响应并提取数据（备用方案）。"""
    # 安装 hook
    hook_js = r"""
(() => {
  if (window.__ovHookInstalled) return 'already';
  window.__ovResponses = [];
  const f1 = window.fetch;
  window.fetch = async function(...a) {
    const [u, o] = a;
    if (typeof u === 'string' && u.includes('/api/graphql/')) {
      try {
        const resp = await f1.apply(this, a);
        const clone = resp.clone();
        const text = await clone.text();
        window.__ovResponses.push({body: text, len: text.length});
        return resp;
      } catch (e) { throw e; }
    }
    return f1.apply(this, a);
  };
  window.__ovHookInstalled = true;
  return 'hook installed';
})()
"""
    out, _, _ = browser_eval(session, hook_js, timeout=20)
    print(f"Hook: {out}")
    
    # 触发页面刷新或日期变更来产生新请求
    # 这里简单地重新加载页面数据
    refresh_js = r"""
(() => {
  // 查找并点击日期按钮触发新请求
  const buttons = document.querySelectorAll('div[role="button"], button');
  for (const btn of buttons) {
    const text = (btn.innerText || '').trim();
    if (text && (text.includes('Last') || text.includes('days'))) {
      btn.click();
      return 'clicked: ' + text.slice(0, 50);
    }
  }
  return 'no button found';
})()
"""
    out, _, _ = browser_eval(session, refresh_js, timeout=15)
    print(f"触发: {out}")
    
    time.sleep(3)
    
    # 提取捕获的响应
    extract_js = r"""
(() => {
  const responses = window.__ovResponses || [];
  // 找到包含指标数据的响应
  for (const resp of responses) {
    const body = resp.body;
    // 查找包含时间戳和指标值的响应
    if (body.includes('Primary') || body.includes('timestamp') || body.includes('values')) {
      return JSON.stringify({
        found: true,
        len: resp.len,
        preview: body.slice(0, 2000)
      });
    }
  }
  return JSON.stringify({found: false, responseCount: responses.length});
})()
"""
    out, _, _ = browser_eval(session, extract_js, timeout=20)
    try:
        return json.loads(out)
    except:
        return {'raw': out}


# ─── 数据转换 ─────────────────────────────────────────────────────

def merge_daily_data(dom_data, available_dates=None, start_date=None, end_date=None):
    """将 DOM 提取的数据合并为每日行。

    dom_data: {metric_name: {date_str: value, ...}, ...}
    available_dates: 页面实际可用的日期列表（extract_metrics_from_dom 返回的 _dates）
    start_date/end_date: 请求的日期范围（仅当 available_dates 为空时作为 fallback）

    返回: {date_str: {metric: value, ...}, ...}
    """
    # 优先使用页面实际可用的日期；fallback 到请求的日期范围
    if available_dates:
        dates = available_dates
    else:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        dates = []
        current = start
        while current <= end:
            dates.append(current.isoformat())
            current += timedelta(days=1)

    # 合并数据：缺失的指标填 0
    daily_data = {}
    for date_str in dates:
        daily_data[date_str] = {}
        for metric_name, metric_data in dom_data.items():
            if metric_name.startswith('_'):
                continue
            if isinstance(metric_data, dict) and date_str in metric_data:
                daily_data[date_str][metric_name] = metric_data[date_str]
            else:
                daily_data[date_str][metric_name] = 0

    return daily_data


def to_doris_rows(daily_data, account_name, instagram_business_id, execution_date):
    """将每日数据转换为 Doris 行格式。"""
    rows = []
    etl_date = execution_date.isoformat()
    for date_str in sorted(daily_data.keys()):
        metrics = daily_data[date_str]
        row = {
            'date': date_str,
            'account_name': account_name,
            'instagram_business_id': instagram_business_id,
            'views': int(metrics.get('views', 0) or 0),
            'reach': int(metrics.get('reach', 0) or 0),
            'content_interactions': int(metrics.get('content_interactions', 0) or 0),
            'follows': int(metrics.get('follows', 0) or 0),
            'profile_visits': int(metrics.get('profile_visits', 0) or 0),
            'link_clicks': int(metrics.get('link_clicks', 0) or 0),
            'unfollows': int(metrics.get('unfollows', 0) or 0),
            'etl_date': etl_date,
        }
        rows.append(row)
    return rows


# ─── Doris 写入 ─────────────────────────────────────────────────────

def load_doris_config(config_path):
    parser = configparser.ConfigParser()
    if not parser.read(config_path, encoding='utf-8') or not parser.has_section('doris'):
        raise ValueError('missing [doris] configuration in %s' % config_path)
    required = ('host', 'be_port', 'user', 'password')
    missing = [key for key in required if not parser.get('doris', key, fallback='').strip()]
    if missing:
        raise ValueError('missing Doris configuration: %s' % ', '.join(missing))
    return {key: parser.get('doris', key).strip() for key in required}


def stream_load_rows(rows, config_path, table_name=DORIS_TABLE):
    """写入 Doris 使用 NDJSON Stream Load。"""
    if not rows:
        return {'Status': 'Success', 'NumberLoadedRows': 0}
    config = load_doris_config(config_path)
    url = ('http://%s:%s/api/ods_social_media/%s/_stream_load'
           % (config['host'], config['be_port'], table_name))
    payload = '\n'.join(json.dumps(row, ensure_ascii=False) for row in rows).encode('utf-8')
    credentials = ('%s:%s' % (config['user'], config['password'])).encode('utf-8')
    request = Request(url, data=payload, method='PUT')
    request.add_header('Content-Type', 'application/json')
    request.add_header('Authorization', 'Basic ' + base64.b64encode(credentials).decode('ascii'))
    request.add_header('format', 'json')
    request.add_header('read_json_by_line', 'true')
    request.add_header('columns', ','.join(DORIS_COLUMNS))
    request.add_header('label', table_name + '_' + uuid.uuid4().hex)
    # 容错：允许 10% 行被过滤，避免一行格式错误整批拒（Doris 默认 0.0）
    request.add_header('max_filter_ratio', '0.1')
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
    return result


# ─── 主流程 ─────────────────────────────────────────────────────

def fetch_account_overview(session, account, start_date, end_date):
    """抓取单个账号的概览数据。

    路径：agent reach + DOM（/insights/results 页面）。
    抓取流程：
      1. 打开 Results 页面
      2. 切换 Entity selector 到 Instagram（默认是 Facebook Page）
      3. 通过 UI 设置自定义日期范围（让页面渲染请求的 start_date ~ end_date）
      4. 等待数据加载完成
      5. 从 DOM innerText 提取指标时间序列

    set_date_range_ui 通过翻月 + 点选日期支持任意自定义范围（实测 7 天 / 31 天跨月均通过）。
    """
    account_name = account['name']
    business_id = account['business_id']
    ig_business_id = account['instagram_business_id']
    tz = account.get('tz', 'America/Los_Angeles')

    print(f"\n{'='*50}")
    print(f"抓取账号: {account_name} (IG: {ig_business_id}, TZ: {tz})")
    print(f"路径: agent reach + DOM (/insights/results)")
    print(f"{'='*50}")

    # 1. 打开 Results 页面
    url = current_url(session)
    if 'insights/results' not in url or f'asset_id={ig_business_id}' not in url:
        open_results_page(session, business_id, ig_business_id)
    else:
        print(f"复用当前页面")

    # 2. 等待页面初始加载
    if not wait_for_overview(session, max_wait=90):
        raise RuntimeError(f'页面未加载完成: {account_name}')

    # 2.5. 确保页面已切换到当前账号（上一个账号的内容可能还在缓存中）
    if not wait_for_account_switch(session, ig_business_id, account_name, max_wait=30):
        raise RuntimeError(f'页面未切换到目标账号: {account_name}')

    # 3. 切换到 Instagram 实体（Results 页面默认展示 Facebook Page 数据）
    print("切换实体到 Instagram...")
    switch_result = switch_to_instagram(session)
    if not switch_result.get('ok'):
        raise RuntimeError(f"无法切换到 Instagram: {switch_result.get('msg')}")

    # 4. UI 设置日期范围（核心：让页面渲染请求的日期窗口）
    print(f"设置日期范围: {start_date} ~ {end_date}")
    set_date_range_ui(session, start_date, end_date)

    # 4. 注入账户时区（必须在 extract 之前，否则 fallback 到默认 PT）
    set_account_timezone(session, tz)

    # 5. 从 DOM 提取数据
    print("从页面提取指标数据...")
    time.sleep(3)  # 等 React 重渲染完成
    dom_data = extract_metrics_from_dom(session)

    meta = dom_data.pop('_meta', {})
    available_dates = dom_data.pop('_dates', [])

    print(f"  页面日期范围: {meta.get('dateRange', 'unknown')}")
    print(f"  找到 {meta.get('metricsFound', 0)} 个指标")
    if meta.get('error'):
        raise RuntimeError(f"DOM 提取失败: {meta['error']}")

    for metric_name, data in dom_data.items():
        if isinstance(data, dict):
            print(f"    - {metric_name}: {len(data)} 天数据")

    # 6. 合并为每日数据（使用页面实际可用的日期）
    daily_data = merge_daily_data(
        dom_data,
        available_dates=available_dates,
        start_date=start_date,
        end_date=end_date
    )

    # 统计有数据的天数
    days_with_data = sum(1 for d in daily_data.values() if any(v != 0 for v in d.values()))
    print(f"  合并后: {len(daily_data)} 天, {days_with_data} 天有数据")

    # 检查日期范围是否匹配（set_date_range_ui 失败时会 fallback 到默认窗口）
    if available_dates:
        page_start = min(available_dates)
        page_end = max(available_dates)
        requested_start = start_date
        requested_end = end_date
        if requested_start < page_start or requested_end > page_end:
            span = (datetime.strptime(requested_end, '%Y-%m-%d').date() -
                    datetime.strptime(requested_start, '%Y-%m-%d').date()).days + 1
            print(f"\n  ⚠️  请求范围 {requested_start} ~ {requested_end}（{span} 天）与页面实际窗口 {page_start} ~ {page_end} 不一致")
            print(f"     说明日期范围设置未生效（可能日历交互失败），抓到的仍是默认窗口数据")

    return daily_data


def main():
    parser = argparse.ArgumentParser(description='抓取 Instagram 账号级每日概览数据')
    parser.add_argument('--session', default='dqg7tk9s', help='opencli 浏览器 session id')
    parser.add_argument('--start-date', required=True, metavar='YYYY-MM-DD', help='开始日期')
    parser.add_argument('--end-date', required=True, metavar='YYYY-MM-DD', help='结束日期')
    parser.add_argument('--accounts', default=None,
                        help='逗号分隔的账号名；默认抓取全部两个账号')
    parser.add_argument('--doris-config', default=str(Path(__file__).resolve().parents[2] / 'config' / 'credentials.ini'))
    parser.add_argument('--skip-doris', action='store_true', help='跳过写入 Doris')
    args = parser.parse_args()

    # 解析日期
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        if start_date > end_date:
            raise ValueError('start-date must not be after end-date')
    except ValueError as exc:
        parser.error(str(exc))

    # 筛选账号
    accounts = ACCOUNTS
    if args.accounts:
        selected = [a.strip() for a in args.accounts.split(',')]
        accounts = [a for a in ACCOUNTS if a['name'] in selected]
        if not accounts:
            parser.error(f'未找到匹配的账号: {args.accounts}')

    span_days = (end_date - start_date).days + 1

    print('='*60)
    print('Meta Business Suite Instagram 账号级概览数据抓取')
    print('='*60)
    print(f'日期范围: {start_date} ~ {end_date}（{span_days} 天）')
    print(f'账号: {", ".join(a["name"] for a in accounts)}')
    print(f'路径: agent reach + DOM（/insights/results, session={args.session}）')

    execution_date = date.today()
    all_rows = []
    failures = []

    for account in accounts:
        try:
            daily_data = fetch_account_overview(
                args.session, account,
                start_date.isoformat(), end_date.isoformat(),
            )

            # 转换为 Doris 格式
            doris_rows = to_doris_rows(
                daily_data,
                account['name'],
                account['instagram_business_id'],
                execution_date
            )
            all_rows.extend(doris_rows)

            print(f"账号 {account['name']}: {len(doris_rows)} 行数据")

        except Exception as exc:
            failures.append(f"{account['name']}: {exc}")
            print(f"ERROR [{account['name']}]: {exc}", file=sys.stderr)

    # 写入 Doris
    if not args.skip_doris and all_rows:
        try:
            result = stream_load_rows(all_rows, Path(args.doris_config))
            loaded = int(result.get('NumberLoadedRows', 0))
            print(f"\nDoris 写入完成: loaded={loaded}")
        except Exception as exc:
            print(f"Doris 写入失败: {exc}", file=sys.stderr)
            failures.append(f"Doris: {exc}")

    # 汇总
    print('\n' + '='*60)
    if failures:
        print(f'存在失败 ({len(failures)})')
        for fail in failures:
            print(f'  - {fail}')
        return 1
    else:
        print(f'全部完成! 共 {len(all_rows)} 行数据写入 Doris')
    print('='*60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
