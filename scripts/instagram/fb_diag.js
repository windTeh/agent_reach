// 页面内诊断：重放一次请求并暴露原始响应/结构到 window
(async () => {
  if (!window.__fbQBodyVar) { window.__fbDiag = {error: 'no template'}; return; }
  const body = window.__fbQBodyVar;
  const parts = {};
  const order = [];
  body.split('&').forEach(p => {
    const i = p.indexOf('=');
    if (i > 0) { order.push(p.slice(0, i)); parts[p.slice(0, i)] = p.slice(i + 1); }
  });
  const vars = JSON.parse(decodeURIComponent(parts.variables));
  vars.count = 50;
  vars.initialFilters = [];
  vars.timeRange = { type: 'CUSTOM', start_iso_date: '2016-01-01', end_iso_date: '2026-08-24' };
  parts.variables = encodeURIComponent(JSON.stringify(vars));
  const newBody = order.map(k => k + '=' + parts[k]).join('&');

  const splitJsonObjects = (text) => {
    const objs = [];
    let depth = 0, start = -1, inStr = false, esc = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === '\\') esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') { inStr = true; continue; }
      if (ch === '{') { if (depth === 0) start = i; depth++; }
      else if (ch === '}') { depth--; if (depth === 0 && start >= 0) { objs.push(text.slice(start, i + 1)); start = -1; } }
    }
    return objs;
  };

  const r = await fetch('/api/graphql/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: newBody,
    credentials: 'include',
  });
  const text = await r.text();
  window.__fbRawResponse = text;

  const objs = splitJsonObjects(text);
  let content = null;
  for (const s of objs) {
    let o;
    try { o = JSON.parse(s); } catch (e) { continue; }
    const t = (o.data || {}).tofu_unified_table;
    if (t && t.content) { content = t.content; break; }
  }
  window.__fbDiagContent = content;
  window.__fbDiag = {
    bytes: text.length,
    keys: content ? Object.keys(content) : null,
    edgesLen: content && content.edges ? content.edges.length : null,
    allIdsLen: content && content.all_ids ? content.all_ids.length : null,
    pageInfo: content && content.page_info ? content.page_info : null,
    firstIds: content && content.edges ? content.edges.slice(0, 3).map(e => e.node && e.node.row_id) : null,
    lastIds: content && content.edges ? content.edges.slice(-3).map(e => e.node && e.node.row_id) : null,
    allIdsSample: content && content.all_ids ? content.all_ids.slice(0, 5) : null,
  };
})();
