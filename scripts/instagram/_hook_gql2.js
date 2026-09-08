(async () => {
  // Hook fetch + XHR to capture ALL GraphQL request bodies
  if (window.__gqlHook2) return 'already hooked';
  window.__gqlReqs = [];
  
  const origFetch = window.fetch;
  window.fetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const opts = args[1] || {};
    const body = opts.body || '';
    
    if (url.includes('/api/graphql') || url.includes('bnzai')) {
      const entry = {type: 'fetch', url: url.slice(0, 150), bodyLen: body.length, body: body.slice(0, 2000), ts: Date.now()};
      window.__gqlReqs.push(entry);
    }
    return origFetch.apply(this, args);
  };
  
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__url = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if (this.__url && (this.__url.includes('/api/graphql') || this.__url.includes('bnzai'))) {
      window.__gqlReqs.push({type: 'xhr', url: (this.__url || '').slice(0, 150), bodyLen: (body || '').length, body: (body || '').slice(0, 2000), ts: Date.now()});
    }
    return origSend.apply(this, arguments);
  };
  
  window.__gqlHook2 = true;
  return 'hook installed';
})()
