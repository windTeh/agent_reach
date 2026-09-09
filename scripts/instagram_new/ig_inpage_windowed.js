// Meta Business Suite 帖子表格：按自定义日期窗口递归拆分，避免每页 50 条截断。
// 仅过滤非 Instagram 帖子；保留页面结果中的所有 IG_POST，不按 owner_id 过滤。
// 这样可完整保留 Published posts 表格返回的 Instagram 记录，并仍排除 Facebook 节点。
(() => {
  const CONFIG = { from: __START_DATE__, to: __END_DATE__, assetId: __ASSET_ID__, count: 50, maxDepth: 16 };
  const day = 86400000;
  const millis = s => new Date(s + 'T00:00:00Z').getTime();
  const iso = value => new Date(value).toISOString().slice(0, 10);
  const splitObjects = text => {
    const result = []; let depth = 0, start = -1, quoted = false, escaped = false;
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (quoted) { if (escaped) escaped = false; else if (char === '\\') escaped = true; else if (char === '"') quoted = false; continue; }
      if (char === '"') { quoted = true; continue; }
      if (char === '{') { if (!depth) start = i; depth++; }
      else if (char === '}') { depth--; if (!depth && start >= 0) { result.push(text.slice(start, i + 1)); start = -1; } }
    }
    return result;
  };
  const cell = value => {
    const renderer = value && value.renderer;
    if (!renderer || String(renderer.__typename || '').includes('Noop')) return null;
    if (renderer.date_time != null) return renderer.date_time;
    const result = renderer.result || {};
    return result.value != null ? result.value : ((result.singleValueFormatter || {}).full_formatted_result ?? null);
  };
  const extract = node => {
    const header = node.header || {}, entity = header.entity || {}, info = entity.entity_info || {}, fields = node.fields || {};
    const ownerInfo = (((info.owner || {}).entity_info) || {});
    const ownerId = String(ownerInfo.id || '').replace(/^GraphQLTofuIGAccountEntityInfo:/, '');
    // 账号用户名以接口返回值为准，而非脚本配置里的账号名。
    const ownerUsername = ownerInfo.username || ownerInfo.name || ownerInfo.title || '';
    const keys = ['views', 'reach', 'interactions', 'net_reactions', 'net_comments', 'shares', 'net_saves', 'link_clicks', 'replies', 'new_follows', 'video_play_time', 'video_average_play_time', 'video_three_second_views', 'instream_ads_estimated_earnings'];
    const metrics = {}; keys.forEach(key => metrics[key] = cell(fields[key]));
    // Published posts 的跨发布关系在不同 Meta 页面版本可能挂在 node/header/entity/
    // entity_info 的任一层级，因此递归扫描所有 cross_post* 字段，而非只读固定路径。
    const crossPosts = [];
    const seenCross = new Set();
    const scanCross = (value, depth = 0) => {
      if (!value || typeof value !== 'object' || depth > 8) return;
      if (Array.isArray(value)) { value.forEach(item => scanCross(item, depth + 1)); return; }
      Object.entries(value).forEach(([key, item]) => {
        if (/cross[_-]?post/i.test(key)) {
          const items = Array.isArray(item) ? item : [item];
          items.forEach(candidate => {
            const detail = candidate || {};
            const id = String(detail.id || ((detail.entity_info || {}).id) || '');
            const marker = key + ':' + id + ':' + String((detail.entity_info || {}).title || '');
            if (!seenCross.has(marker)) {
              seenCross.add(marker);
              crossPosts.push({field: key, entity_type: detail.entity_type || '', id, title: ((detail.entity_info || {}).title) || ''});
            }
          });
        }
        scanCross(item, depth + 1);
      });
    };
    scanCross(node);
    return {
      row_id: node.row_id, entity_type: entity.entity_type, owner_id: ownerId, owner_username: ownerUsername,
      title: info.title || '', created_at: info.created_at || null,
      cross_posts: crossPosts,
      // 仅当关系中出现 FB Page Post 等另一平台的实际对象时，才是真正的交叉发布。
      // __isTofuCrossPostedContentInfo 是 Meta 通用接口标记，不能单独作为判定条件。
      is_cross_post: crossPosts.some(item => item.entity_type && item.entity_type !== 'IG_POST'),
      entity_keys: Object.keys(entity), entity_info_keys: Object.keys(info), owner_info_keys: Object.keys(ownerInfo), owner_title: ownerInfo.title || '', metrics
    };
  };
  const query = async (from, to) => {
    const body = window.__igPostsQueryTemplate;
    const parts = {}, order = [];
    body.split('&').forEach(item => { const pivot = item.indexOf('='); if (pivot > 0) { const key = item.slice(0, pivot); order.push(key); parts[key] = item.slice(pivot + 1); } });
    const variables = JSON.parse(decodeURIComponent(parts.variables));
    variables.count = CONFIG.count;
    variables.initialFilters = [];
    variables.timeRange = { type: 'CUSTOM', start_iso_date: from, end_iso_date: to };
    parts.variables = encodeURIComponent(JSON.stringify(variables));
    const payload = order.map(key => key + '=' + parts[key]).join('&');
    let responseText, lastError;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const control = new AbortController(), timer = setTimeout(() => control.abort(), 90000);
        const response = await window.__igPostsNativeFetch('/api/graphql/', { method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: payload, credentials: 'include', signal: control.signal });
        responseText = await response.text(); clearTimeout(timer); break;
      } catch (error) { lastError = error; await new Promise(resolve => setTimeout(resolve, 1500)); }
    }
    if (responseText == null) return {edges: [], total: 0, error: 'fetch failed: ' + String(lastError)};
    const edges = []; let total = 0, error = null;
    splitObjects(responseText).forEach(item => {
      try {
        const parsed = JSON.parse(item), content = (((parsed.data || {}).tofu_unified_table || {}).content || {});
        if (Array.isArray(content.edges)) { edges.push(...content.edges); total = Math.max(total, Array.isArray(content.all_ids) ? content.all_ids.length : 0); }
        if (parsed.errors && !error) error = JSON.stringify(parsed.errors).slice(0, 300);
      } catch (_) {}
    });
    return {edges, total: total || edges.length, error};
  };
  const rows = [], seen = new Set(), report = {requests: 0, rejected: 0, windows: [], errors: []};
  window.__igPostsProgress = {phase: 'starting', requests: 0, rows: 0, rejected: 0};
  const collect = async (from, to, depth) => {
    window.__igPostsProgress.phase = 'fetching ' + from + '~' + to;
    const result = await query(from, to); report.requests++; window.__igPostsProgress.requests = report.requests;
    if (result.error) { report.errors.push(from + '~' + to + ': ' + result.error); return; }
    const truncated = result.edges.length < result.total && result.total > 0;
    if (truncated && millis(to) - millis(from) >= day && depth < CONFIG.maxDepth) {
      const mid = millis(from) + Math.floor((millis(to) - millis(from)) / 2);
      await collect(from, iso(mid), depth + 1); await collect(iso(mid + day), to, depth + 1);
    } else {
      if (truncated) report.errors.push('窗口仍截断: ' + from + '~' + to + ' (' + result.edges.length + '/' + result.total + ')');
      result.edges.forEach(edge => {
        const row = extract(edge.node || {});
        if (row.entity_type !== 'IG_POST') { report.rejected++; return; }
        if (row.row_id && !seen.has(row.row_id)) { seen.add(row.row_id); rows.push(row); }
      });
      window.__igPostsProgress.rows = rows.length; window.__igPostsProgress.rejected = report.rejected;
    }
    report.windows.push({from, to, edges: result.edges.length, total: result.total, truncated});
  };
  window.__igPostsRun = (async () => {
    try {
      await collect(CONFIG.from, CONFIG.to, 0);
      rows.sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0));
      window.__igPostsRows = rows;
      window.__igPostsReport = {...report, totalRows: rows.length, uniqueRows: seen.size};
      window.__igPostsProgress.phase = 'done';
    } catch (error) { window.__igPostsProgress.phase = 'error: ' + String(error && error.message || error); }
  })();
  return 'Instagram-only windowed fetch started';
})()
