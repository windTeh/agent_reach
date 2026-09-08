// 页面内重放 /api/graphql/ 表格查询并提取行数据(浏览器会话内执行)
// 依赖: localStorage.__fbQBody 已保存请求模板; 页面已登录 business.facebook.com
(() => {
  window.__fbRun = (async () => {
    const body = localStorage.getItem('__fbQBody');
    if (!body) return {error: 'no template in localStorage'};
    const parts = {};
    const order = [];
    body.split('&').forEach(p => { const i = p.indexOf('='); if (i > 0) { order.push(p.slice(0, i)); parts[p.slice(0, i)] = p.slice(i + 1); } });
    const vars = JSON.parse(decodeURIComponent(parts.variables || '{}'));
    // ---- 可调参数 ----
    vars.count = 500;                      // 每页行数(上限待测)
    vars.initialFilters = [];              // 关键: 去掉列过滤, 拿全字段
    vars.timeRange = { type: 'LAST_365D' }; // 时间范围
    // ------------------
    parts.variables = encodeURIComponent(JSON.stringify(vars));
    const newBody = order.map(k => k + '=' + parts[k]).join('&');

    let resp;
    try {
      resp = await fetch('/api/graphql/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: newBody,
        credentials: 'include',
      });
    } catch (e) { return { error: 'fetch failed: ' + e.message }; }
    const text = await resp.text();

    // 解析 Relay 流式响应(\n\n 分隔多 JSON)
    const blocks = text.split('\n\n').map(b => b.trim()).filter(Boolean);
    let content = null, pageInfo = null, reqErr = null;
    for (const b of blocks) {
      let o; try { o = JSON.parse(b); } catch (e) { continue; }
      const t = (o.data || {}).tofu_unified_table || {};
      if (t.content && Array.isArray(t.content.edges)) { content = t.content; pageInfo = t.content.page_info; break; }
      if (o.errors) reqErr = JSON.stringify(o.errors).slice(0, 300);
    }
    if (!content) return { error: reqErr || 'no content found', len: text.length, blocks: blocks.length };

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
    const rows = content.edges.map(e => extractRow(e.node));
    window.__fbAllRows = rows;
    window.__fbPageInfo = pageInfo;
    window.__fbLastRun = {
      ok: true, count: rows.length, bytes: text.length,
      pageInfo: pageInfo ? { hasNext: !!pageInfo.has_next_page, endCursor: (pageInfo.end_cursor || '').slice(0, 24) } : null,
      firstDate: rows.length ? rows[0].created_at : null,
      lastDate: rows.length ? rows[rows.length - 1].created_at : null,
    };
    return window.__fbLastRun;
  })();
  return 'started';
})()
