"""Deep inspect the export notification element."""
import sys, os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

out, _, _ = browser_eval(S, """
(() => {
  // Find the leaf element with "exports ready"
  const allEls = Array.from(document.querySelectorAll('*'));
  const leaf = allEls.find(el => {
    const t = (el.textContent || '').replace(/[\\u200b]/g, '');
    return t.includes('exports ready') && el.children.length === 0;
  });
  if (!leaf) return JSON.stringify({error: 'not found'});
  
  // Walk up the tree and inspect each level
  const levels = [];
  let el = leaf;
  for (let i = 0; i < 15; i++) {
    if (!el) break;
    const info = {
      level: i,
      tag: el.tagName,
      role: el.getAttribute('role'),
      className: (el.className || '').toString().slice(0, 100),
      childCount: el.children.length,
      innerHTML: (el.innerHTML || '').slice(0, 300),
      hasHref: !!el.href,
      href: (el.href || '').slice(0, 200),
      onclick: typeof el.onclick === 'function',
      cursor: getComputedStyle(el).cursor,
    };
    levels.push(info);
    el = el.parentElement;
  }
  
  // Also check for any sibling elements
  const parent = leaf.parentElement;
  const siblings = parent ? Array.from(parent.children).map(c => ({
    tag: c.tagName,
    text: (c.textContent || '').replace(/[\\u200b]/g, '').trim().slice(0, 100),
    role: c.getAttribute('role'),
    childCount: c.children.length,
  })) : [];
  
  return JSON.stringify({levels: levels.slice(0, 8), siblings});
})()
""", timeout=15)

path = os.path.join(SCRIPT_DIR, '_notif_structure.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Notification structure written to {path}')
