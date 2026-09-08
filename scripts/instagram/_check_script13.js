(async () => {
  const scripts = document.querySelectorAll('script[type="application/json"]');
  const s13 = scripts[13];
  if (!s13) return JSON.stringify({error: 'no script 13'});
  const text = s13.textContent || '';
  
  // Search for post-related fields
  const searches = {};
  const terms = ['row_id', 'entity_type', 'IG_POST', 'IG_STORY', 'created_at', 
    'post_id', 'owner_username', 'tofu', 'unified_table', 'bizweb',
    'metrics', 'impressions', 'engagement', 'reach'];
  for (const t of terms) {
    const idx = text.indexOf(t);
    if (idx !== -1) {
      searches[t] = {pos: idx, ctx: text.slice(idx, idx + 80)};
    }
  }
  
  // Search for the RelayPrefetchedStreamCache entries
  const relayIdx = text.indexOf('RelayPrefetchedStreamCache');
  let relayEntries = [];
  if (relayIdx !== -1) {
    // Find all query names near RelayPrefetchedStreamCache
    const re = /RelayPrefetchedStreamCache[^"]*","next",\[\],\["([^"]+)"/g;
    let m;
    let searchFrom = 0;
    while ((m = re.exec(text)) !== null) {
      relayEntries.push(m[1].slice(0, 120));
      if (relayEntries.length >= 10) break;
    }
  }
  
  // Also look for "result" keys that contain data
  const resultMatches = [];
  const re2 = /"result":\{"data":\{([^}]{0,200})/g;
  let m2;
  while ((m2 = re2.exec(text)) !== null) {
    resultMatches.push(m2[0].slice(0, 200));
    if (resultMatches.length >= 5) break;
  }
  
  return JSON.stringify({
    scriptLen: text.length,
    searches: searches,
    relayEntries: relayEntries.slice(0, 10),
    resultMatches: resultMatches.slice(0, 5)
  });
})()
