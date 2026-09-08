# -*- coding: utf-8 -*-
"""
Fetch ALL posts + full analytics metrics for @anycubic3dprint via X Analytics
(Delegate account accessed through @Anycubic2024's Chrome session via OpenCLI).

Output: Excel with 17 columns:
Post id, Date, Post text, Post Link, Impressions, Likes, Engagements, Bookmarks,
Shares, New follows, Replies, Reposts, Profile visits, Detail Expands,
URL Clicks, Hashtag Clicks, Permalink Clicks

Usage:
  python fetch_anycubic3dprint_analytics.py [--output out.xlsx]
      [--window-days 180] [--max-years 6] [--username anycubic3dprint]

Prerequisites:
  - Chrome running with OpenCLI extension connected, logged in as @Anycubic2024
  - Delegate access to @anycubic3dprint (Admin role) already granted
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote

NODE = r'C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2\node.exe'
MAIN = (r'C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2'
        r'\node_modules\@jackwener\opencli\dist\src\main.js')

COLUMNS = ['Post id', 'Date', 'Post text', 'Post Link', 'Impressions', 'Likes',
           'Engagements', 'Bookmarks', 'Shares', 'New follows', 'Replies',
           'Reposts', 'Profile visits', 'Detail Expands', 'URL Clicks',
           'Hashtag Clicks', 'Permalink Clicks']

# X Analytics metric name -> Excel column
METRIC_MAP = {
    'Impressions': 'Impressions',
    'Likes': 'Likes',
    'Engagements': 'Engagements',
    'Bookmark': 'Bookmarks',
    'Share': 'Shares',
    'Follows': 'New follows',
    'Replies': 'Replies',
    'Retweets': 'Reposts',
    'ProfileVisits': 'Profile visits',
    'DetailExpands': 'Detail Expands',
    'UrlClicks': 'URL Clicks',
    'HashtagClicks': 'Hashtag Clicks',
    'PermalinkClicks': 'Permalink Clicks',
}


def oc(*args, timeout=180):
    """Run opencli via node directly (bypasses cmd.exe quoting issues)."""
    r = subprocess.run([NODE, MAIN] + list(args), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout)
    return (r.stdout or r.stderr).strip()


def ev(session, tab, js, timeout=60):
    out = oc('browser', session, 'eval', js, '--tab', tab, timeout=timeout)
    try:
        return json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return out


def open_url(session, tab, url):
    return oc('browser', session, 'open', url, '--tab', tab)


def get_tab(session, url):
    """Open a URL, return the tab id."""
    out = open_url(session, None, url) if False else oc('browser', session, 'open', url)
    try:
        return json.loads(out).get('page')
    except (json.JSONDecodeError, TypeError):
        return None


def click_js(session, tab, js):
    """Click an element via in-page JS (most reliable for dynamic UI)."""
    return ev(session, tab, js)


def switch_to_delegate(session, tab, username):
    """Switch active X account to the delegated account."""
    print(f'  Switching active account to @{username} ...')
    open_url(session, tab, 'https://x.com/home')
    time.sleep(4)
    # 1. open account switcher
    js0 = ('(function(){var b=document.querySelector("[data-testid=SideNav_AccountSwitcher_Button]");'
           'if(b){b.click();return "opened"}return "no_button"})()')
    print(f'  switcher: {click_js(session, tab, "JSON.stringify(%s)" % js0)}')
    time.sleep(2)
    # 2. click delegate account cell
    js = ('(function(){var cs=Array.from(document.querySelectorAll("[data-testid=UserCell]"));'
          'var t=cs.find(function(c){return (c.innerText||"").toLowerCase().indexOf("%s")>-1});'
          'if(t){t.click();return "clicked"}return "not_found"})()') % username.lower()
    r = click_js(session, tab, 'JSON.stringify(%s)' % js)
    print(f'  delegate cell: {r}')
    time.sleep(4)
    # 3. confirm "Switch accounts" dialog if present
    js2 = ('(function(){var bs=Array.from(document.querySelectorAll("button"));'
           'var b=bs.find(function(x){return (x.textContent||"").trim()==="Switch accounts"});'
           'if(b){b.click();return "confirmed"}return "no_dialog"})()')
    r2 = click_js(session, tab, 'JSON.stringify(%s)' % js2)
    print(f'  switch dialog: {r2}')
    time.sleep(6)


def parse_query_from_time(url):
    """Extract from_time from the GraphQL query URL."""
    try:
        qs = parse_qs(urlparse(url).query)
        variables = json.loads(unquote(qs['variables'][0]))
        return variables.get('from_time', '')
    except Exception:
        return ''


def entry_from_time(entry):
    """from_time for a network entry dict (listing or detail)."""
    return parse_query_from_time(entry.get('url', '') if isinstance(entry, dict) else '')


def list_recent_entries(session, since='90s'):
    """Return recent network entries (shape previews, small output)."""
    out = oc('browser', session, 'network', '--since', since, timeout=120)
    try:
        return json.loads(out).get('entries', [])
    except (json.JSONDecodeError, TypeError):
        return []


def fetch_window(session, tab, from_d, to_d):
    """Navigate to the analytics content page for a date window and capture
    the contentPageQuery response.

    Strategy (robust against opencli --detail's long TTL cache):
      1. navigate
      2. check the network LISTING for a freshly-fired contentPageQuery
         entry whose from_time matches this window
      3. only then fetch --detail (and verify from_time again)
    Returns list of tweet result dicts, or None on failure.
    """
    url = ('https://x.com/i/account_analytics/content?type=posts&sort=date'
           '&dir=desc&from=%s&to=%s') % (from_d, to_d)
    open_url(session, tab, url)
    # wait for the app to fire the query (fresh URL only; cached URLs fire
    # nothing, which is exactly what the listing check detects)
    for i in range(3):
        time.sleep(8 if i == 0 else 4)
        fired = any(e.get('key') == 'contentPageQuery' and from_d in entry_from_time(e)
                    for e in list_recent_entries(session, '90s'))
        if fired:
            break
    else:
        print('    ! no fresh request fired (cached?)', end=' ')
        return None
    # request fired -> pull the body
    for j in range(3):
        out = oc('browser', session, 'network', '--detail', 'contentPageQuery',
                 timeout=120)
        try:
            data = json.loads(out)
            if from_d in entry_from_time(data):
                return (data['body']['data']['viewer_v2']['user_results']
                        ['result'].get('tweets_results', []))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        time.sleep(3)
    print('    ! detail body stale', end=' ')
    return None


def tweets_to_rows(tweets, username):
    rows = []
    for t in tweets:
        r = t.get('result') or {}
        if not r.get('details'):
            continue  # unavailable/deleted tweet entries
        d = r['details']
        ms = d.get('created_at_ms')
        if not ms:
            continue
        row = {c: '' for c in COLUMNS}
        row['Post id'] = r.get('rest_id', '')
        row['Date'] = datetime.fromtimestamp(ms / 1000).strftime('%Y-%m-%d %H:%M')
        row['Post text'] = (d.get('full_text') or '').replace('\r', '')
        row['Post Link'] = 'https://x.com/%s/status/%s' % (username, r.get('rest_id', ''))
        for m in r.get('organic_metrics_total', []):
            col = METRIC_MAP.get(m.get('metric_type'))
            if col:
                row[col] = m.get('metric_value') or 0
        rows.append(row)
    return rows


def write_excel(rows, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = 'Posts Analytics'
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill('solid', fgColor='1D9BF0')
    for ci, col in enumerate(COLUMNS, 1):
        c = ws.cell(row=1, column=ci, value=col)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal='center', vertical='center')
    for ri, row in enumerate(rows, 2):
        for ci, col in enumerate(COLUMNS, 1):
            v = row[col]
            if col not in ('Post text',) and isinstance(v, (int, float)):
                ws.cell(row=ri, column=ci, value=v).number_format = '#,##0'
            else:
                ws.cell(row=ri, column=ci, value=v)
    widths = {'Post id': 22, 'Date': 17, 'Post text': 60, 'Post Link': 45}
    for ci, col in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(ci)].width = widths.get(col, 12)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = 'A1:%s%d' % (get_column_letter(len(COLUMNS)), max(2, len(rows) + 1))
    wb.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--username', default='anycubic3dprint')
    ap.add_argument('--output', default=None)
    ap.add_argument('--window-days', type=int, default=180)
    ap.add_argument('--max-years', type=float, default=6)
    ap.add_argument('--session', default='ar')
    args = ap.parse_args()

    out_path = args.output or (r'E:\CCProject\agent_reach\scripts\twitter\%s.xlsx'
                               % args.username)
    session = args.session
    print(f'== X Analytics fetcher for @{args.username} ==')

    # Get a tab on the analytics page
    tab = get_tab(session, 'https://x.com/i/account_analytics/content')
    if not tab:
        print('ERROR: cannot open browser tab. Is Chrome + OpenCLI extension running?')
        sys.exit(1)
    print(f'  tab: {tab}')
    time.sleep(8)

    # Check whether the analytics page shows the Premium wall (wrong active account)
    body = ev(session, tab, 'JSON.stringify(document.body.innerText.slice(0,400))') or ''
    if 'Upgrade to continue' in str(body) or "doesn’t exist" in str(body):
        switch_to_delegate(session, tab, args.username)
        open_url(session, tab, 'https://x.com/i/account_analytics/content')
        time.sleep(8)
        body = ev(session, tab, 'JSON.stringify(document.body.innerText.slice(0,400))') or ''
        if 'Upgrade to continue' in str(body):
            print('ERROR: still seeing Premium wall. Delegate switch failed.')
            sys.exit(1)

    # Iterate date windows backward from today
    today = datetime.now().date()
    total_days = int(args.max_years * 365)
    all_rows = {}
    seen_ids = set()
    empty_streak = 0
    start_offset = 0
    while start_offset < total_days:
        to_d = today - timedelta(days=start_offset)
        from_d = today - timedelta(days=start_offset + args.window_days)
        wf, wt = from_d.isoformat(), to_d.isoformat()
        print(f'  window {wf} -> {wt} ...', end=' ', flush=True)
        tweets = None
        for jitter in (0, 1, -1, 2):
            # Previously-fetched windows are served from browser HTTP cache
            # and fire no network request; shifting the boundary by a day
            # busts the cache. Dedup by rest_id handles the tiny overlap.
            jf = (from_d - timedelta(days=jitter)).isoformat()
            jt = (to_d - timedelta(days=jitter)).isoformat()
            got = fetch_window(session, tab, jf, jt)
            if got is not None:
                tweets = got
                break
        if tweets is None:
            print('FAILED (skipped)')
            empty_streak += 1
            if empty_streak >= 3:
                print('  too many failures, stopping.')
                break
            continue
        new_rows = [r for r in tweets_to_rows(tweets, args.username)
                    if r['Post id'] and r['Post id'] not in seen_ids]
        for r in new_rows:
            seen_ids.add(r['Post id'])
            all_rows[r['Post id']] = r
        print(f'{len(tweets)} tweets ({len(new_rows)} new)')
        if len(tweets) == 0:
            empty_streak += 1
            if empty_streak >= 2:
                print('  reached end of posting history, stopping.')
                break
        else:
            empty_streak = 0
        start_offset += args.window_days

    rows = sorted(all_rows.values(), key=lambda r: r['Date'], reverse=True)
    print(f'\nTotal unique posts: {len(rows)}')
    write_excel(rows, out_path)
    # also dump raw merged rows as JSON for debugging
    json_path = out_path.replace('.xlsx', '_raw.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f'Excel saved: {out_path}')
    print(f'Raw JSON  : {json_path}')


if __name__ == '__main__':
    main()
