"""Find the export download button via 'Open export options' or notification bell."""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Find "Open export options" button
out, _, _ = browser_eval(S, """
(() => {
  // Find all buttons/links with export-related text
  const btns = Array.from(document.querySelectorAll('[role=button], button, a'));
  const exportBtns = btns.filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '').trim();
    return t.includes('Export') || t.includes('export') || t.includes('Open export');
  }).map(el => ({
    text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 80),
    tag: el.tagName,
    ariaLabel: el.getAttribute('aria-label') || '',
  }));
  
  // Find notification bell
  const allBtns = Array.from(document.querySelectorAll('[role=button]'));
  const notifBtn = allBtns.find(el => {
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    return al.includes('notif') || al.includes('alert') || al.includes('bell');
  });
  
  // Find the "1 exports ready" text anywhere
  const allEls = Array.from(document.querySelectorAll('*'));
  const exportReadyEls = allEls.filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return t.includes('exports ready') && el.children.length <= 3;
  }).map(el => ({
    tag: el.tagName,
    text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 100),
    role: el.getAttribute('role'),
    visible: el.offsetHeight > 0,
  }));
  
  return JSON.stringify({
    exportButtons: exportBtns.slice(0, 5),
    notifBell: notifBtn ? {ariaLabel: notifBtn.getAttribute('aria-label'), text: (notifBtn.textContent||'').slice(0, 30)} : null,
    exportReadyElements: exportReadyEls.slice(0, 5),
  });
})()
""", timeout=15)

path = os.path.join(SCRIPT_DIR, '_export_btns.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Export buttons written to {path}')
