(async () => {
  // Find the tofu_unified_table query template from preloader data
  const html = document.documentElement.outerHTML;
  
  // Search for tofu_unified_table or BizWebPublishedPosts query
  const patterns = [
    'tofu_unified_table',
    'BizWebPublishedPosts',
    'BizWebContentTable',
    'published_posts',
    'content_table'
  ];
  
  const found = {};
  for (const p of patterns) {
    const idx = html.indexOf(p);
    if (idx !== -1) {
      found[p] = {
        pos: idx,
        ctx: html.slice(Math.max(0, idx - 100), idx + 200).replace(/</g, '').slice(0, 300)
      };
    }
  }
  
  // Also check for __fbQBodyVar or similar template variable
  const hasQBodyVar = html.includes('__fbQBodyVar');
  
  // Check for the table data structure
  const tableData = [];
  const re = /"tofu_unified_table"/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    tableData.push({
      pos: m.index,
      ctx: html.slice(Math.max(0, m.index - 50), m.index + 100).slice(0, 200)
    });
  }
  
  // Look for the query variables in the preloader
  const queryVars = [];
  const re2 = /"variables":\s*(\{[^}]{50,500}\})/g;
  while ((m = re2.exec(html)) !== null) {
    queryVars.push(m[1].slice(0, 300));
  }
  
  return JSON.stringify({
    found,
    hasQBodyVar,
    tableData: tableData.slice(0, 3),
    queryVars: queryVars.slice(0, 3)
  });
})()
