(async () => {
  const html = document.documentElement.outerHTML;
  
  // Search for tofu_unified_table in the full HTML
  const tofuIdx = html.indexOf('tofu_unified_table');
  
  // Search for content_table or unified_table variants
  const searches = {};
  const terms = ['tofu_unified_table', 'unified_table', 'content_table', 
    'BizWebContentTable', 'BizWebPublishedPosts', 'PublishedPostsTable',
    'tofu_content', 'insights_table', 'bizweb_table'];
  for (const t of terms) {
    const idx = html.indexOf(t);
    if (idx !== -1) {
      searches[t] = { pos: idx, ctx: html.slice(idx, idx + 100).replace(/</g, '').slice(0, 100) };
    }
  }
  
  // Search for edges and all_ids (common tofu response fields)
  const edgesIdx = html.indexOf('"edges"');
  const allIdsIdx = html.indexOf('"all_ids"');
  
  // Check for the query doc_id
  const docIdMatch = html.match(/"doc_id"\s*:\s*"?(\d+)"?/);
  
  // Check for the query name
  const queryNameMatch = html.match(/"queryName"\s*:\s*"([^"]+)"/g);
  
  return JSON.stringify({
    htmlLen: html.length,
    searches,
    hasEdges: edgesIdx !== -1 ? edgesIdx : null,
    hasAllIds: allIdsIdx !== -1 ? allIdsIdx : null,
    docId: docIdMatch ? docIdMatch[1] : null,
    queryNames: queryNameMatch ? queryNameMatch.slice(0, 10) : []
  });
})()
