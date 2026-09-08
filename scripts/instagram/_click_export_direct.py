"""Find and click the '1 exports ready for download' element directly."""
import sys, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Find the exact element with "exports ready" text and click it
out, _, _ = browser_eval(S, """
(() => {
  // Find all elements that contain "exports ready" text (leaf nodes)
  const allEls = Array.from(document.querySelectorAll('*'));
  const leafEls = allEls.filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return t.includes('exports ready') && el.children.length === 0;
  });
  
  const candidates = leafEls.map(el => {
    // Walk up to find the nearest clickable ancestor
    let clickable = el;
    for (let i = 0; i < 10; i++) {
      if (!clickable.parentElement) break;
      const role = clickable.getAttribute('role');
      const isBtn = clickable.tagName === 'BUTTON' || clickable.tagName === 'A';
      if (role === 'button' || isBtn) break;
      clickable = clickable.parentElement;
    }
    return {
      text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 100),
      tag: el.tagName,
      clickableTag: clickable.tagName,
      clickableRole: clickable.getAttribute('role'),
      clickableAriaLabel: clickable.getAttribute('aria-label'),
      visible: el.offsetHeight > 0,
      rect: el.getBoundingClientRect ? {x: el.getBoundingClientRect().x, y: el.getBoundingClientRect().y} : null,
    };
  });
  
  // Click the nearest clickable ancestor of the first visible leaf
  for (const c of candidates) {
    if (c.visible && c.rect && c.rect.y > 0) {
      // Find the actual element and click it
      const leaf = leafEls.find(el => (el.textContent || '').replace(/[\\u200b]/g, '').includes('exports ready') && el.offsetHeight > 0);
      if (leaf) {
        // Walk up to find clickable parent
        let target = leaf;
        for (let i = 0; i < 15; i++) {
          if (!target.parentElement) break;
          const r = target.getAttribute('role');
          if (r === 'button' || target.tagName === 'BUTTON' || target.tagName === 'A') break;
          target = target.parentElement;
        }
        target.click();
        return JSON.stringify({clicked: true, candidates: candidates.slice(0, 3), clickedTag: target.tagName, clickedRole: target.getAttribute('role')});
      }
    }
  }
  
  return JSON.stringify({clicked: false, candidates: candidates.slice(0, 3)});
})()
""", timeout=15)
print('Click result:', out)

time.sleep(3)

# Check what appeared
out, _, _ = browser_eval(S, """
(() => {
  const result = {};
  
  // Check for new dialogs/panels
  const dialogs = document.querySelectorAll('[role=dialog]');
  result.dialogCount = dialogs.length;
  if (dialogs.length) {
    result.dialogTexts = Array.from(dialogs).map(d => (d.textContent || '').replace(/[\\u200b]/g, '').slice(0, 1000));
  }
  
  // Check for download links
  const links = Array.from(document.querySelectorAll('a[href]')).filter(a => {
    const h = (a.href || '').toLowerCase();
    return h.includes('download') || h.includes('export') || h.endsWith('.csv') || h.endsWith('.xlsx');
  }).map(a => ({href: a.href.slice(0, 300), text: (a.textContent || '').trim().slice(0, 80)}));
  result.downloadLinks = links;
  
  // Check for download buttons
  const dlBtns = Array.from(document.querySelectorAll('[role=button], button')).filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '').trim().toLowerCase();
    return t.includes('download');
  }).map(el => ({text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 80)}));
  result.downloadButtons = dlBtns.slice(0, 5);
  
  return JSON.stringify(result);
})()
""", timeout=15)

path = os.path.join(SCRIPT_DIR, '_after_click_export.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'After click result written to {path}')
