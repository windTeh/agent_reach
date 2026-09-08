(async () => {
  const results = {};

  // 1. Check all script tags for duration data
  const scripts = document.querySelectorAll('script');
  let scriptDurationMatches = [];
  for (const s of scripts) {
    const text = s.textContent || '';
    const re = /"duration":\s*(\d+)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      scriptDurationMatches.push({
        val: m[1],
        ctx: text.slice(Math.max(0, m.index - 60), m.index + m[0].length + 20).slice(0, 200)
      });
    }
  }
  results.scriptMatches = scriptDurationMatches.slice(0, 10);

  // 2. Check window-level variables for story data
  const windowKeys = ['__STORE__', '__store__', '__RELAY_STORE__', '__relay_store__',
    '__initial_data__', '__data__', '__preloader_data__'];
  results.windowVars = {};
  for (const k of windowKeys) {
    if (window[k] !== undefined) {
      results.windowVars[k] = typeof window[k];
    }
  }

  // 3. Try to find React fiber with story data
  // Look for elements with data-visualcompletion or data-sigil
  const reactRoots = document.querySelectorAll('[data-visualcompletion="root"]');
  results.reactRootCount = reactRoots.length;

  // 4. Check for any element with aria-label containing "26" or "duration"
  const ariaEls = [];
  document.querySelectorAll('[aria-label]').forEach(el => {
    const label = el.getAttribute('aria-label');
    if (label && (label.includes('26') || label.toLowerCase().includes('duration') || label.toLowerCase().includes('second'))) {
      ariaEls.push(label.slice(0, 200));
    }
  });
  results.ariaLabels = ariaEls.slice(0, 10);

  // 5. Check for tooltip or title attributes with duration
  const titleEls = [];
  document.querySelectorAll('[title]').forEach(el => {
    const t = el.getAttribute('title');
    if (t && (t.includes('26') || t.toLowerCase().includes('duration') || t.toLowerCase().includes('second'))) {
      titleEls.push(t.slice(0, 200));
    }
  });
  results.titleAttrs = titleEls.slice(0, 10);

  // 6. Look for "26" in all text nodes
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
  const text26 = [];
  while (walker.nextNode()) {
    const t = walker.currentNode.textContent;
    if (t.includes('26') && t.trim().length < 50) {
      text26.push(t.trim());
    }
  }
  results.text26 = text26.slice(0, 20);

  return JSON.stringify(results);
})()
