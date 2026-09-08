(async () => {
  // Try multiple approaches to get story duration from Instagram web API
  
  // Approach 1: Try i.instagram.com API (might not work due to CORS)
  const approaches = {};
  
  // Approach 2: Try Business Suite internal GraphQL with known query patterns
  try {
    // First, get the fb_dtsg token from the page
    const dtsgEl = document.querySelector('input[name="fb_dtsg"]');
    const fb_dtsg = dtsgEl ? dtsgEl.value : null;
    
    if (!fb_dtsg) {
      // Try to find it in the page scripts
      const scripts = document.querySelectorAll('script');
      for (const s of scripts) {
        const m = (s.textContent || '').match(/"DTSGInitialData".*?token:"([^"]+)"/);
        if (m) { approaches.fb_dtsg = m[1]; break; }
      }
    } else {
      approaches.fb_dtsg = fb_dtsg;
    }
  } catch(e) { approaches.dtsgError = e.message; }

  // Approach 3: Try to find the story data in the page's React tree
  try {
    const rootEl = document.getElementById('mount_0_0') || document.getElementById('mount_0') || document.body.firstElementChild;
    if (rootEl && rootEl._reactRootContainer) {
      approaches.hasReactRoot = true;
    }
    // Try React 18+ style root
    const allEls = document.querySelectorAll('*');
    for (const el of allEls) {
      const keys = Object.keys(el);
      const fiberKey = keys.find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
      if (fiberKey) {
        approaches.fiberKey = fiberKey;
        break;
      }
    }
  } catch(e) { approaches.reactError = e.message; }

  // Approach 4: Check for __relay_store__ or similar data stores
  try {
    const storeKeys = Object.keys(window).filter(k => 
      k.toLowerCase().includes('store') || k.toLowerCase().includes('relay') || 
      k.toLowerCase().includes('graphql') || k.toLowerCase().includes('data')
    );
    approaches.storeKeys = storeKeys.slice(0, 20);
  } catch(e) {}

  // Approach 5: Try to use the Business Suite's internal API to get story metadata
  // The content_id from the URL is 18117072050489215
  // Try to fetch the story's media info
  try {
    const r = await fetch('https://business.facebook.com/api/graphql/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      credentials: 'include',
      body: new URLSearchParams({
        doc_id: 'BizWebIGStoryObjectInsightsQuery',
        variables: JSON.stringify({
          contentID: '18117072050489215',
          assetID: '213562039049926',
          businessID: '800253393765350'
        })
      }).toString()
    });
    const text = await r.text();
    approaches.storyQueryResult = text.slice(0, 2000);
    approaches.storyQueryStatus = r.status;
  } catch(e) { approaches.storyQueryError = e.message; }

  return JSON.stringify(approaches);
})()
