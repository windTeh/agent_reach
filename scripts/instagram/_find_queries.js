(async () => {
  // Install hook BEFORE reload by using window.onbeforeunload
  // Actually, let's just capture the initial HTML preloader data instead
  
  // The page data is embedded in the HTML as preloader data
  // Let's find the GraphQL query info from the preloader
  const html = document.documentElement.outerHTML;
  
  // Search for query names and doc_ids
  const results = {};
  
  // Find all query names
  const queryNameRe = /"params":\{"name":"([^"]+)"/g;
  const queryNames = [];
  let m;
  while ((m = queryNameRe.exec(html)) !== null) {
    queryNames.push(m[1]);
  }
  results.queryNames = [...new Set(queryNames)];
  
  // Find doc_ids near published_posts or content_management
  const docIdRe = /"doc_id":"(\d+)"/g;
  const docIds = [];
  while ((m = docIdRe.exec(html)) !== null) {
    const ctx = html.slice(Math.max(0, m.index - 200), m.index + 50);
    docIds.push({doc_id: m[1], ctx: ctx.slice(-100)});
  }
  results.docIds = docIds.slice(0, 10);
  
  // Search for specific published_posts related queries
  const ppIdx = html.indexOf('PublishedPosts');
  if (ppIdx !== -1) {
    results.publishedPostsCtx = html.slice(Math.max(0, ppIdx - 100), ppIdx + 200).replace(/</g, '');
  }
  
  // Search for ContentManagement queries
  const cmMatches = [];
  const cmRe = /ContentManagement\w+/g;
  while ((m = cmRe.exec(html)) !== null) {
    cmMatches.push(m[0]);
  }
  results.contentManagementQueries = [...new Set(cmMatches)];
  
  return JSON.stringify(results);
})()
