// 页面内全量抓取: 重放表格查询 + 流式解析 + 提取行数据
// 依赖: localStorage.__fbQBody 模板; 页面已登录
// 输出: window.__fbAllRows (行数组), window.__fbFetchReport
(() => {
  const CONFIG = {
    from: '2016-01-01',
    to: '2026-08-24',
    count: 50,
    maxPages: 20,
  };
  const t0 = Date.now();

  // 大括号配对: 把流式文本切成完整 JSON 对象数组
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

  const cellValue = (cell) => {
    if (!cell || typeof cell !== 'object') return null;
    const r = cell.renderer;
    if (!r || typeof r !== 'object') return null;
    if ((r.__typename || '').includes('Noop')) return null;
    if ('date_time' in r) return r.date_time;
    const res = r.result;
    if (res && typeof res === 'object') {
      if (res.value !== undefined && res.value !== null) return res.value;
      const fmt = res.singleValueFormatter;
      if (fmt && typeof fmt === 'object') return fmt.full_formatted_result;
    }
    return null;
  };

  const extractRow = (node) => {
    const header = node.header || {};
    const entity = header.entity || {};
    const info = entity.entity_info || {};
    const f = node.fields || {};
    const owner = (info.owner && info.owner.entity_info) ? (info.owner.entity_info.title || info.owner.entity_info.id) : null;
    const cp = (entity.cross_posted_entities || []).map(c => ({
      type: c.entity_type,
      title: ((c.entity_info || {}).title) || '',
      owner: ((c.entity_info || {}).owner || {}).entity_info ? ((c.entity_info.owner.entity_info).title) : null,
    }));
    const keys = ['views', 'reach', 'viewers', 'interactions', 'net_reactions', 'net_comments', 'shares',
      'net_saves', 'link_clicks', 'replies', 'new_follows', 'video_play_time', 'video_average_play_time',
      'video_three_second_views', 'instream_ads_estimated_earnings'];
    const metrics = {};
    keys.forEach(k => metrics[k] = cellValue(f[k]));
    return {
      row_id: node.row_id, entity_type: entity.entity_type, title: info.title || '',
      created_at: info.created_at,
      image_uri: info.image_source && info.image_source.uri,
      owner, cross_posts: cp, metrics,
    };
  };

  const fetchPage = async (varsExtra) => {
    const body = window.__fbQBodyVar;
    const parts = {}; const order = [];
    body.split('&').forEach(p => { const i = p.indexOf('='); if (i > 0) { order.push(p.slice(0, i)); parts[p.slice(0, i)] = p.slice(i + 1); } });
    const vars = JSON.parse(decodeURIComponent(parts.variables));
    vars.count = CONFIG.count;
    vars.initialFilters = [];
    vars.timeRange = { type: 'CUSTOM', start_iso_date: CONFIG.from, end_iso_date: CONFIG.to };
    if (varsExtra) Object.assign(vars, varsExtra);
    parts.variables = encodeURIComponent(JSON.stringify(vars));
    const newBody = order.map(k => k + '=' + parts[k]).join('&');
    const r = await fetch('/api/graphql/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: newBody,
      credentials: 'include',
    });
    return await r.text();
  };

  const parseContent = (text) => {
    const objs = splitJsonObjects(text);
    let edges = [], pageInfo = null, err = null;
    for (const s of objs) {
      let o; try { o = JSON.parse(s); } catch (e) { continue; }
      const t = (o.data || {}).tofu_unified_table || {};
      if (t.content && typeof t.content === 'object' && Array.isArray(t.content.edges)) {
        edges = edges.concat(t.content.edges);
        if (t.content.page_info) pageInfo = t.content.page_info;
      }
      if (o.errors && !err) err = JSON.stringify(o.errors).slice(0, 200);
    }
    return { edges, pageInfo, err };
  };

  window.__fbRun2 = (async () => {
    const allRows = [];
    let cursor = null;
    const report = { pages: 0, perPage: [], errors: [], totalBytes: 0 };
    for (let pg = 0; pg < CONFIG.maxPages; pg++) {
      const extra = cursor ? { after: cursor } : null;
      const text = await fetchPage(extra);
      report.totalBytes += text.length;
      const { edges, pageInfo, err } = parseContent(text);
      if (err) report.errors.push('pg' + pg + ': ' + err);
      if (!edges.length) {
        report.errors.push('pg' + pg + ': no edges, bytes=' + text.length);
        break;
      }
      const rows = edges.map(e => extractRow(e.node));
      allRows.push(...rows);
      report.perPage.push(rows.length);
      report.pages = pg + 1;
      const pi = pageInfo || {};
      if (pi.has_next_page && pi.end_cursor) {
        cursor = pi.end_cursor;
      } else {
        break;
      }
    }
    window.__fbAllRows = allRows;
    window.__fbFetchReport = {
      totalRows: allRows.length,
      pages: report.pages,
      perPage: report.perPage,
      totalBytes: report.totalBytes,
      errors: report.errors,
      elapsedMs: Date.now() - t0,
      cursorUsed: !!cursor,
      firstDate: allRows.length ? allRows[0].created_at : null,
      lastDate: allRows.length ? allRows[allRows.length - 1].created_at : null,
    };
    return window.__fbFetchReport;
  })();
  return 'full fetch started';
})()
