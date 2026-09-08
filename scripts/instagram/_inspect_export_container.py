"""Explore the mediaManagerExportInsightsButton element for download options."""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Inspect the export button area
out, _, _ = browser_eval(S, """
(() => {
  const container = document.getElementById('mediaManagerExportInsightsButton');
  if (!container) return JSON.stringify({error: 'no container'});
  
  const result = {};
  
  // Get all child elements with text
  const allChildren = Array.from(container.querySelectorAll('*'));
  const textEls = allChildren.filter(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '').trim();
    return t.length > 0 && t.length < 200 && el.children.length === 0;
  }).map(el => ({
    tag: el.tagName,
    text: (el.textContent || '').replace(/[\\u200b]/g, '').trim(),
    role: el.getAttribute('role'),
    cursor: getComputedStyle(el).cursor,
    ariaLabel: el.getAttribute('aria-label') || '',
  }));
  result.textElements = textEls;
  
  // Get all role=button elements
  const buttons = Array.from(container.querySelectorAll('[role=button], button')).map(el => ({
    text: (el.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 80),
    ariaLabel: el.getAttribute('aria-label') || '',
  }));
  result.buttons = buttons;
  
  // Get all links
  const links = Array.from(container.querySelectorAll('a[href]')).map(el => ({
    href: el.href.slice(0, 200),
    text: (el.textContent || '').trim().slice(0, 50),
    download: el.download || '',
  }));
  result.links = links;
  
  // Check for the "Open export options" button specifically
  const openBtn = Array.from(container.querySelectorAll('[role=button]')).find(el => {
    const al = el.getAttribute('aria-label') || '';
    return al.includes('export') || al.includes('Export');
  });
  if (openBtn) {
    result.openExportBtn = {
      ariaLabel: openBtn.getAttribute('aria-label'),
      text: (openBtn.textContent || '').trim().slice(0, 50),
    };
  }
  
  // Full inner text
  result.fullText = (container.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 500);
  
  return JSON.stringify(result);
})()
""", timeout=15)

path = os.path.join(SCRIPT_DIR, '_export_container.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Export container written to {path}')
