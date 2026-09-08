"""Check what happened after clicking Generate."""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Check for dialogs, downloads, new pages
js = """
(() => {
  const result = {};
  
  // Check all dialogs
  const dialogs = document.querySelectorAll('[role=dialog]');
  result.dialogCount = dialogs.length;
  result.dialogTexts = Array.from(dialogs).map(d => {
    const text = (d.textContent || '').replace(/[\\u200b\\u200c\\u200d\\uFEFF]/g, '');
    return text.slice(0, 600);
  });
  
  // Check for any download links
  const downloadLinks = Array.from(document.querySelectorAll('a[download], a[href*="download"]'));
  result.downloadLinks = downloadLinks.map(a => ({href: (a.href || '').slice(0, 200), download: a.download || ''}));
  
  // Check for iframes (sometimes used for downloads)
  const iframes = document.querySelectorAll('iframe');
  result.iframeCount = iframes.length;
  result.iframeSrcs = Array.from(iframes).map(f => (f.src || '').slice(0, 200));
  
  // Check browser tabs/windows (can't really do this from JS)
  result.url = location.href;
  
  // Check for any export-related elements
  const exportEls = Array.from(document.querySelectorAll('*')).filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return (t.includes('export') || t.includes('Export') || t.includes('download') || t.includes('Download') || t.includes('generating') || t.includes('Generating') || t.includes('preparing') || t.includes('Preparing'))
      && el.children.length === 0
      && t.length < 200
      && t.length > 3;
  }).map(el => (el.textContent || '').replace(/[\\u200b]/g, '').trim()).filter((v, i, a) => a.indexOf(v) === i);
  result.exportRelatedTexts = exportEls.slice(0, 10);
  
  return JSON.stringify(result);
})()
"""
out, _, _ = browser_eval(S, js, timeout=15)
path = os.path.join(SCRIPT_DIR, '_export_status.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Status written to {path}')
