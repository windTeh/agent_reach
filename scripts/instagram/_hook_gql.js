(async () => {
  // Hook fetch to capture GraphQL requests
  window.__capturedGQL = [];
  const origFetch = window.__nativeFetch || window.fetch;
  const hookFetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (url.includes('/api/graphql/') || url.includes('bnzai')) {
      const body = args[1] && args[1].body;
      try {
        const resp = await origFetch.apply(this, args);
        const clone = resp.clone();
        const text = await clone.text();
        window.__capturedGQL.push({
          url: url.slice(0, 100),
          bodyLen: body ? body.length : 0,
          bodySnippet: body ? body.slice(0, 500) : '',
          respLen: text.length,
          respSnippet: text.slice(0, 500)
        });
        return resp;
      } catch(e) {
        window.__capturedGQL.push({error: e.message});
        throw e;
      }
    }
    return origFetch.apply(this, args);
  };
  
  if (window.__nativeFetch) {
    window.__nativeFetch = hookFetch;
  } else {
    window.fetch = hookFetch;
  }
  
  return 'Hook installed. Now trigger a table refresh or filter change.';
})()
