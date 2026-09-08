"""Click 'Open export options' and check for download."""
import sys, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Click "Open export options"
out, _, _ = browser_eval(S, """
(() => {
  const btn = Array.from(document.querySelectorAll('[role=button]')).find(el => (el.textContent||'').replace(/[\\u200b]/g,'').trim() === 'Open export options');
  if (btn) { btn.click(); return 'clicked'; }
  return 'not found';
})()
""", timeout=10)
print('Click:', out)

time.sleep(2)

# Check what appeared
out, _, _ = browser_eval(S, """
(() => {
  const result = {};
  
  // Check for any new panels/popovers
  const panels = document.querySelectorAll('[class*=popover], [class*=Popover], [class*=dropdown], [class*=Dropdown], [class*=panel], [class*=Panel]');
  result.panelCount = panels.length;
  
  // Check for download links
  const links = Array.from(document.querySelectorAll('a[href]')).filter(a => {
    const h = (a.href || '').toLowerCase();
    return h.includes('download') || h.includes('export') || h.endsWith('.csv') || h.endsWith('.xlsx');
  }).map(a => ({href: a.href.slice(0, 300), text: (a.textContent || '').trim().slice(0, 80), download: a.download || ''}));
  result.downloadLinks = links;
  
  // Check for new dialogs
  const dialogs = document.querySelectorAll('[role=dialog]');
  result.dialogCount = dialogs.length;
  result.dialogTexts = Array.from(dialogs).map(d => (d.textContent || '').replace(/[\\u200b]/g, '').slice(0, 800));
  
  // Check for any download buttons
  const dlBtns = Array.from(document.querySelectorAll('[role=button], button, a')).filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '').trim().toLowerCase();
    return t.includes('download');
  }).map(el => ({
    text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 80),
    tag: el.tagName,
    href: (el.href || '').slice(0, 200),
  }));
  result.downloadButtons = dlBtns.slice(0, 10);
  
  // Check for any visible text about "ready" or "export"
  const readyTexts = Array.from(document.querySelectorAll('*')).filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return (t.includes('ready') || t.includes('Ready')) && el.children.length === 0 && t.length < 100 && t.length > 3;
  }).map(el => (el.textContent || '').replace(/[\\u200b]/g, '').trim());
  result.readyTexts = [...new Set(readyTexts)].slice(0, 10);
  
  return JSON.stringify(result);
})()
""", timeout=15)

path = os.path.join(SCRIPT_DIR, '_export_panel_result.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Result written to {path}')
