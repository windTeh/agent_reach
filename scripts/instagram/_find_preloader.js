(async () => {
  const html = document.documentElement.outerHTML;
  
  // Find all script tags with preloader data
  const scripts = document.querySelectorAll('script[type="application/json"]');
  const results = [];
  
  for (let i = 0; i < scripts.length; i++) {
    const text = scripts[i].textContent || '';
    if (text.length < 100) continue;
    
    // Check if it contains relevant keywords
    if (text.includes('PublishedPosts') || text.includes('ContentManagement') || 
        text.includes('published_posts') || text.includes('edges') ||
        text.includes('tofu_unified_table') || text.includes('unified_table')) {
      
      // Find query names and doc_ids
      const queryNames = [];
      const re1 = /"name":"([^"]*(?:Published|Content|Unified|Table)[^"]*)"/g;
      let m;
      while ((m = re1.exec(text)) !== null) {
        queryNames.push(m[1]);
      }
      
      const docIds = [];
      const re2 = /"doc_id":"(\d+)"/g;
      while ((m = re2.exec(text)) !== null) {
        const ctx = text.slice(Math.max(0, m.index - 150), m.index + 30);
        docIds.push({doc_id: m[1], nearby: ctx.slice(-120)});
      }
      
      results.push({
        scriptIdx: i,
        len: text.length,
        queryNames: [...new Set(queryNames)],
        docIds: docIds.slice(0, 5),
        hasEdges: text.includes('"edges"'),
        hasTofu: text.includes('tofu_unified_table'),
        hasUnifiedTable: text.includes('unified_table'),
        preview: text.slice(0, 200)
      });
    }
  }
  
  return JSON.stringify({scriptCount: scripts.length, relevant: results.slice(0, 5)});
})()
