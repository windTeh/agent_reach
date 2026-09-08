"""Find and click the export download notification, then capture the download."""
import sys, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Close the export dialog first
browser_eval(S, """
(() => {
  const closeBtn = Array.from(document.querySelectorAll('[role=dialog] [role=button]')).find(el => (el.textContent||'').trim().startsWith('Close'));
  if (closeBtn) closeBtn.click();
  return 'closed';
})()
""", timeout=10)
time.sleep(1)

# Find the "exports ready for download" notification
out, _, _ = browser_eval(S, """
(() => {
  // Look for notification/bell icon with export ready text
  const allEls = Array.from(document.querySelectorAll('*'));
  const exportNotifs = allEls.filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return t.includes('export') && t.includes('download') && el.children.length <= 2;
  });
  
  const result = [];
  for (const el of exportNotifs) {
    result.push({
      tag: el.tagName,
      text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 100),
      role: el.getAttribute('role'),
      isButton: el.tagName === 'BUTTON' || el.getAttribute('role') === 'button',
      hasClick: typeof el.onclick === 'function',
      parentTag: el.parentElement ? el.parentElement.tagName : null,
      parentRole: el.parentElement ? el.parentElement.getAttribute('role') : null,
    });
  }
  
  // Also look for bell/notification icon
  const bellBtn = Array.from(document.querySelectorAll('[role=button]')).find(el => {
    const ariaLabel = el.getAttribute('aria-label') || '';
    return ariaLabel.includes('notification') || ariaLabel.includes('Notification') || ariaLabel.includes('bell');
  });
  
  return JSON.stringify({
    exportNotifs: result.slice(0, 5),
    hasBellButton: !!bellBtn,
    bellLabel: bellBtn ? bellBtn.getAttribute('aria-label') : null,
  });
})()
""", timeout=15)
print('Export notifications:', out)

# Try to find and click the notification
out, _, _ = browser_eval(S, """
(() => {
  // Look for clickable element with "exports ready for download"
  const allEls = Array.from(document.querySelectorAll('[role=button], button, a, [class*=notification], [class*=Notification]'));
  const notif = allEls.find(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return t.includes('export') && t.includes('download');
  });
  
  if (notif) {
    notif.click();
    return JSON.stringify({clicked: true, text: (notif.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 100)});
  }
  
  // Try broader search - any element with the text
  const allEls2 = Array.from(document.querySelectorAll('*'));
  const notif2 = allEls2.find(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return t.includes('exports ready') && el.children.length <= 3 && el.tagName !== 'BODY' && el.tagName !== 'HTML';
  });
  
  if (notif2) {
    notif2.click();
    return JSON.stringify({clicked: true, text: (notif2.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 100), tag: notif2.tagName});
  }
  
  return JSON.stringify({clicked: false});
})()
""", timeout=10)
print('Click notification:', out)

time.sleep(3)

# Check what appeared after clicking
out, _, _ = browser_eval(S, """
(() => {
  const result = {};
  
  // Check for download panel/dropdown
  const panels = document.querySelectorAll('[class*=panel], [class*=Panel], [class*=dropdown], [class*=Dropdown], [class*=menu], [class*=Menu]');
  result.panelCount = panels.length;
  
  // Check for download links
  const links = Array.from(document.querySelectorAll('a[href]')).filter(a => {
    const h = a.href || '';
    return h.includes('download') || h.includes('export') || h.includes('csv') || h.includes('xlsx');
  }).map(a => ({href: a.href.slice(0, 200), text: (a.textContent || '').trim().slice(0, 50)}));
  result.downloadLinks = links;
  
  // Check for new dialogs
  const dialogs = document.querySelectorAll('[role=dialog]');
  result.dialogCount = dialogs.length;
  result.dialogTexts = Array.from(dialogs).map(d => (d.textContent || '').replace(/[\\u200b]/g, '').slice(0, 500));
  
  // Check for any visible text about downloading
  const dlTexts = Array.from(document.querySelectorAll('*')).filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return (t.includes('Download') || t.includes('download')) && el.children.length === 0 && t.length < 100 && t.length > 3;
  }).map(el => (el.textContent || '').replace(/[\\u200b]/g, '').trim());
  result.downloadTexts = [...new Set(dlTexts)].slice(0, 10);
  
  return JSON.stringify(result);
})()
""", timeout=15)

path = os.path.join(SCRIPT_DIR, '_download_panel.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Download panel info written to {path}')
