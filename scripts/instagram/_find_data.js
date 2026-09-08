(async () => {
  const scripts = document.querySelectorAll('script[type="application/json"]');
  
  // Script #21 has edges - let's examine it
  const s21 = scripts[21];
  const text21 = s21 ? s21.textContent : '';
  
  // Find the edges data and surrounding context
  const edgesIdx = text21.indexOf('"edges"');
  let edgesCtx = '';
  if (edgesIdx !== -1) {
    edgesCtx = text21.slice(Math.max(0, edgesIdx - 300), edgesIdx + 1000);
  }
  
  // Also search for the query name / doc_id in the full HTML
  const html = document.documentElement.outerHTML;
  
  // Search for "BusinessCometContentManagement" near doc_id
  const bcmMatches = [];
  let searchFrom = 0;
  while (true) {
    const idx = html.indexOf('BusinessCometContentManagement', searchFrom);
    if (idx === -1) break;
    const ctx = html.slice(idx, idx + 200);
    bcmMatches.push(ctx.slice(0, 120));
    searchFrom = idx + 1;
    if (bcmMatches.length >= 10) break;
  }
  
  // Search for "tofu_unified_table" in ALL script tags
  const tofuScripts = [];
  for (let i = 0; i < scripts.length; i++) {
    const t = scripts[i].textContent || '';
    if (t.includes('tofu_unified_table')) {
      tofuScripts.push({idx: i, len: t.length});
    }
  }
  
  // Search for "unified_table" variant
  const utMatches = [];
  let utSearch = 0;
  while (true) {
    const idx = html.indexOf('unified_table', utSearch);
    if (idx === -1) break;
    utMatches.push(html.slice(idx, idx + 80));
    utSearch = idx + 1;
    if (utMatches.length >= 5) break;
  }
  
  return JSON.stringify({
    script21Len: text21.length,
    edgesContext: edgesCtx.slice(0, 1500),
    bcmMatches: [...new Set(bcmMatches)].slice(0, 5),
    tofuScripts: tofuScripts,
    unifiedTableMatches: utMatches.slice(0, 3)
  });
})()
