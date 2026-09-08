(async () => {
  // Hook fetch and XHR to capture all GraphQL responses
  window.__capturedResponses = [];
  
  const origFetch = window.fetch;
  window.fetch = async function(...args) {
    const resp = await origFetch.apply(this, args);
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (url.includes('graphql') || url.includes('bnzai')) {
      try {
        const clone = resp.clone();
        const text = await clone.text();
        // Search for duration in the response
        const durMatches = [];
        const re = /"duration[^"]*":\s*(\d+)/g;
        let m;
        while ((m = re.exec(text)) !== null) {
          durMatches.push({ key: m[0], val: m[1], ctx: text.slice(Math.max(0, m.index - 40), m.index + m[0].length + 10).slice(0, 100) });
        }
        window.__capturedResponses.push({
          type: 'fetch',
          url: url.slice(0, 200),
          size: text.length,
          durationMatches: durMatches.slice(0, 10),
          hasContentId: text.includes('18117072050489215'),
          hasStory: text.includes('STORY') || text.includes('story'),
          snippet: text.slice(0, 500)
        });
      } catch(e) {}
    }
    return resp;
  };

  // Also hook XMLHttpRequest
  const origXHOpen = XMLHttpRequest.prototype.open;
  const origXhSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__url = url;
    return origXHOpen.apply(this, [method, url, ...rest]);
  };
  XMLHttpRequest.prototype.send = function(body) {
    this.addEventListener('load', function() {
      const url = this.__url || '';
      if (url.includes('graphql') || url.includes('bnzai')) {
        const text = this.responseText || '';
        const durMatches = [];
        const re = /"duration[^"]*":\s*(\d+)/g;
        let m;
        while ((m = re.exec(text)) !== null) {
          durMatches.push({ key: m[0], val: m[1], ctx: text.slice(Math.max(0, m.index - 40), m.index + m[0].length + 10).slice(0, 100) });
        }
        window.__capturedResponses.push({
          type: 'xhr',
          url: url.slice(0, 200),
          size: text.length,
          durationMatches: durMatches.slice(0, 10),
          hasContentId: text.includes('18117072050489215'),
          hasStory: text.includes('STORY') || text.includes('story')
        });
      }
    });
    return origXhSend.apply(this, arguments);
  };

  return 'Hooks installed. Now reload the page to capture responses.';
})()
