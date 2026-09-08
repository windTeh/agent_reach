// 页面内全量抓取 v2: 时间窗口二分法绕过单页 50 行上限
// 原理: 每次请求返回 edges(<=50) + all_ids(该窗口真实总数);
//       若 edges < all_ids 说明被截断 -> 窗口对半分递归, 直到每窗完整
// 依赖: window.__fbQBodyVar 请求模板; 页面已登录
// 输出: window.__fbAllRows (去重行数组), window.__fbFetchReport
(() => {
  const CONFIG = {
    from: '2016-01-01',
    to: '2026-08-24',
    count: 50,
    maxDepth: 14,
  };
  const t0 = Date.now();
  const dayMs = 86400000;
  const toDate = (s) => new Date(s + 'T00:00:00Z').getTime();
  const toIso = (t) => new Date(t).toISOString().slice(0, 10);

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
    // 支持两种数据格式：
    // 1. published_posts (tofu_unified_table): node.header.entity + node.fields + node.row_id
    // 2. archive_stories (entity_list): node.entity_info + node.entity_insights + node.entity_id
    const isEntityList = !!node.entity_id && !node.row_id;

    if (isEntityList) {
      // archive_stories 格式
      const info = node.entity_info || {};
      const insights = node.entity_insights || {};
      const insightKeys = [
        ['views', 'views_count'], ['reach', 'reach'], ['viewers', 'viewers'],
        ['interactions', 'interactions'], ['net_reactions', 'likes_and_reactions'],
        ['net_comments', 'comments'], ['shares', 'share'], ['net_saves', 'saves'],
        ['link_clicks', 'link_clicks'], ['replies', 'replies'],
        ['new_follows', 'new_follows'], ['video_play_time', 'video_total_time_watched'],
        ['video_average_play_time', 'video_average_time_watched'],
        ['video_three_second_views', 'video_views_3s'],
        ['instream_ads_estimated_earnings', 'instream_ads_earnings'],
        ['sticker_taps', 'sticker_taps'],
      ];
      const metrics = {};
      insightKeys.forEach(([outKey, inKey]) => {
        const v = insights[inKey];
        metrics[outKey] = (v && typeof v === 'object' && 'value' in v) ? v.value : null;
      });
      // story_duration_in_sec -> duration (ms)
      const durSec = info.story_duration_in_sec || info.video_duration_in_sec;
      return {
        row_id: node.entity_id, entity_type: node.entity_type,
        title: info.title || '', created_at: info.created_at,
        image_uri: info.image_source && info.image_source.uri,
        owner: null, cross_posts: [], metrics,
        _owner_id: '', account_name: null,
        duration: durSec != null ? Math.round(durSec * 1000) : null,
        account_id: null, media_type: null,
        content_format: info.content_format || null,
        story_status: info.story_status || null,
      };
    }

    // published_posts 格式（原有逻辑）
    const header = node.header || {};
    const entity = header.entity || {};
    const info = entity.entity_info || {};
    const f = node.fields || {};
    const ownerInfo = (info.owner && info.owner.entity_info) ? info.owner.entity_info : null;
    const account_username = ownerInfo ? (ownerInfo.title || ownerInfo.id) : null;
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
      owner: account_username, cross_posts: cp, metrics,
      _owner_id: ownerInfo ? String(ownerInfo.id || '').replace(/^GraphQLTofuIGAccountEntityInfo:/, '') : '',
      account_name: info.full_name || (ownerInfo && ownerInfo.full_name) || null,
      duration: (info.duration_in_ms != null) ? info.duration_in_ms
              : ((info.video_duration != null) ? info.video_duration : null),
      account_id: info.fbid_v2 || (ownerInfo && ownerInfo.fbid_v2) || null,
      media_type: (info.media_type != null) ? info.media_type : null,
    };
  };

  const fetchWindow = async (fromIso, toIso) => {
    const body = window.__fbQBodyVar;
    const parts = {}; const order = [];
    body.split('&').forEach(p => { const i = p.indexOf('='); if (i > 0) { order.push(p.slice(0, i)); parts[p.slice(0, i)] = p.slice(i + 1); } });
    const vars = JSON.parse(decodeURIComponent(parts.variables));
    vars.count = CONFIG.count;
    vars.initialFilters = [];
    vars.timeRange = { type: 'CUSTOM', start_iso_date: fromIso, end_iso_date: toIso };
    // archive_stories 使用 contentArgs.time_range 而非顶层 timeRange
    if (vars.contentArgs && vars.contentArgs.time_range) {
      vars.contentArgs.time_range = { type: 'CUSTOM', start_iso_date: fromIso, end_iso_date: toIso };
    }
    // archive_stories 页面默认关闭了很多指标查询，需要开启关键指标
    const metricsToEnable = [
      'queryViewsCount', 'queryReach', 'queryViewers', 'queryInteraction',
      'queryReaction', 'queryComment', 'queryShare', 'querySaves',
      'queryLinkClicks', 'queryReplies', 'queryNewFollowers', 'queryViewTime',
      'queryAvgViewTime', 'queryViews3s', 'queryInstreamAdsEarnings',
    ];
    for (const flag of metricsToEnable) {
      if (flag in vars) vars[flag] = true;
    }
    parts.variables = encodeURIComponent(JSON.stringify(vars));
    const newBody = order.map(k => k + '=' + parts[k]).join('&');
    // 使用干净的 native fetch (绕开被 hook 污染的 window.fetch), 带超时与重试
    const doFetch = async () => {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 90000);
      try {
        const r = await window.__nativeFetch('/api/graphql/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: newBody,
          credentials: 'include',
          signal: ctrl.signal,
        });
        return await r.text();
      } finally { clearTimeout(timer); }
    };
    let text = null, lastErr = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try { text = await doFetch(); break; }
      catch (e) { lastErr = e; await new Promise(rs => setTimeout(rs, 2000)); }
    }
    if (text === null) return { edges: [], allIds: 0, err: 'fetch failed: ' + String(lastErr), bytes: 0 };
    const objs = splitJsonObjects(text);
    let edges = [], allIds = 0, err = null;
    for (const s of objs) {
      let o; try { o = JSON.parse(s); } catch (e) { continue; }
      const data = o.data || {};
      // published_posts 用 tofu_unified_table，archive_stories 用 entity_list
      const t = data.tofu_unified_table || data.entity_list || {};
      if (t.content && typeof t.content === 'object' && Array.isArray(t.content.edges)) {
        edges = edges.concat(t.content.edges);
        if (Array.isArray(t.content.all_ids)) allIds = Math.max(allIds, t.content.all_ids.length);
      }
      if (o.errors && !err) err = JSON.stringify(o.errors).slice(0, 150);
    }
    return { edges, allIds, err, bytes: text.length };
  };

  const results = [];
  const seen = new Set();
  const report = { windows: [], bytes: 0, errors: [], requests: 0 };
  window.__fbWinProgress = { phase: 'starting', requests: 0, rows: 0, currentWindow: null, splits: 0, startedAt: Date.now() };

  const processWindow = async (winFrom, winTo, depth) => {
    window.__fbWinProgress.currentWindow = winFrom + '~' + winTo;
    const r = await fetchWindow(winFrom, winTo);
    report.requests++; report.bytes += r.bytes;
    window.__fbWinProgress.requests = report.requests;
    window.__fbWinProgress.phase = 'fetched ' + winFrom + '~' + winTo;
    if (r.err) { report.errors.push(winFrom + '~' + winTo + ': ' + r.err); return; }
    const total = r.allIds || r.edges.length;
    const truncated = r.edges.length < total && total > 0;
    const oneDay = toDate(winTo) - toDate(winFrom) < dayMs;
    if (truncated && !oneDay && depth < CONFIG.maxDepth) {
      // 截断 -> 对半分
      window.__fbWinProgress.splits++;
      const mid = toDate(winFrom) + Math.floor((toDate(winTo) - toDate(winFrom)) / 2);
      await processWindow(winFrom, toIso(mid), depth + 1);
      await processWindow(toIso(mid + dayMs), winTo, depth + 1);
    } else {
      if (truncated) report.errors.push('WARN window still truncated: ' + winFrom + '~' + winTo + ' edges=' + r.edges.length + '/total=' + total);
      r.edges.forEach(e => {
        const row = extractRow(e.node);
        if (row.row_id && !seen.has(row.row_id)) { seen.add(row.row_id); results.push(row); }
      });
      window.__fbWinProgress.rows = results.length;
    }
    report.windows.push({ from: winFrom, to: winTo, edges: r.edges.length, allIds: total, split: truncated });
  };

  window.__fbWinRun = (async () => {
    try {
      await processWindow(CONFIG.from, CONFIG.to, 0);
      results.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
      window.__fbAllRows = results;
      window.__fbFetchReport = {
        totalRows: results.length,
        uniqueIds: seen.size,
        requests: report.requests,
        totalBytes: report.bytes,
        errors: report.errors,
        windows: report.windows,
        elapsedMs: Date.now() - t0,
        firstDate: results.length ? results[0].created_at : null,
        lastDate: results.length ? results[results.length - 1].created_at : null,
      };
      window.__fbWinProgress.phase = 'done';
    } catch (e) {
      window.__fbWinProgress.phase = 'error: ' + String(e && e.message || e);
    }
    return 'done';
  })();
  return 'windowed fetch started v2';
})()
