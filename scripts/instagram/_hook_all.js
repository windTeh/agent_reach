(async () => {
  // Install a comprehensive fetch/XHR hook to capture GraphQL requests
  window.__capturedReqs = [];
  
  // Hook the native fetch if available, otherwise regular fetch
  const origFetch = window.__nativeFetch || window.fetch;
  const hookedFetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const opts = args[1] || {};
    const body = opts.body || '';
    
    const resp = await origFetch.apply(this, args);
    
    if (url.includes('/api/graphql') || url.includes('bnzai')) {
      try {
        const clone = resp.clone();
        const text = await clone.text();
        window.__capturedReqs.push({
          type: 'fetch',
          url: url.slice(0, 150),
          bodyLen: body.length,
          bodyKeys: body.slice(0, 300),
          respLen: text.length,
          hasTofu: text.includes('tofu_unified_table'),
          hasEdges: text.includes('"edges"'),
          hasAllIds: text.includes('"all_ids"'),
          respStart: text.slice(0, 300)
        });
      } catch(e) {}
    }
    return resp;
  };
  
  if (window.__nativeFetch) window.__nativeFetch = hookedFetch;
  else window.fetch = hookedFetch;
  
  // Also hook XHR
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__url = url;
    this.__method = method;
    return origOpen.apply(this, [method, url, ...rest]);
  };
  XMLHttpRequest.prototype.send = function(body) {
    this.addEventListener('load', function() {
      const url = this.__url || '';
      if (url.includes('/api/graphql') || url.includes('bnzai')) {
        const text = this.responseText || '';
        window.__capturedReqs.push({
          type: 'xhr',
          url: url.slice(0, 150),
          bodyLen: (body || '').length,
          bodyKeys: (body || '').slice(0, 300),
          respLen: text.length,
          hasTofu: text.includes('tofu_unified_table'),
          hasEdges: text.includes('"edges"'),
          hasAllIds: text.includes('"all_ids"'),
          respStart: text.slice(0, 300)
        });
      }
    });
    return origSend.apply(this, arguments);
  };
  
  return 'Hooks installed. Trigger a table refresh now.';
})()
