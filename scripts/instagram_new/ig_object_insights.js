// ig_object_insights.js — 在任意 business.facebook.com 页面调用
// Meta 的 TofuObjectInsightsV2EntityQuery，取跨发布帖的 Instagram 单独指标。
//
// 实现要点
//   - 会话参数（fb_dtsg/lsd/rev/c_user）从当前页面提取，payload 完全手工拼装，
//     无需页面导航，也不依赖预先捕获的请求模板。
//   - entity_insights 命名规则：无 foa_ 前缀 = Instagram 单独；带 foa_ 前缀 = FB+IG 合并。
//   - 老跨发帖（Meta 后端数据缺失时）`view` 字段会显式返回 TofuErrorQueryResult：
//     这是 Meta 端的真实数据缺失，不是请求失败。这种情况下，只要其他 IG 单值字段
//     能取到数据（reach/impression/interaction/reaction/save/share/comment），就视
//     为成功，仅标记 views_unavailable=true 并把 views 留空。绝不能用 Content 表格
//     的合并值兜底——那是 FB+IG 混合数，写进 Doris 会污染所有老跨发帖。
//   - useBizWebInsightsSingleValueQuery 用于补 IG 端 Follows（实体查询不含该字段）。
(() => {
  const POST_ID = __POST_ID__;
  const ENTITY_FN = 'TofuObjectInsightsV2EntityQuery';
  const ENTITY_DOC = __ENTITY_DOC__;
  const SINGLE_FN = 'useBizWebInsightsSingleValueQuery';
  const SINGLE_DOC = __SINGLE_DOC__;
  const CALLER = 'BIZWEB_OBJECT_INSIGHTS';

  const IG_FIELDS = {
    views: 'view', reach: 'reach', viewers: 'viewers',
    interactions: 'interaction', net_reactions: 'reaction',
    net_comments: 'comment', shares: 'share', net_saves: 'save',
    link_clicks: 'link_clicks', replies: 'replies', impressions: 'impression',
  };
  const FOA_FIELDS = {
    views: 'foa_views', interactions: 'foa_interaction',
    net_reactions: 'foa_reactions', net_comments: 'foa_comments',
    shares: 'foa_shares', net_saves: 'foa_saves',
    link_clicks: 'foa_link_click', new_follows: 'foa_follow',
  };

  const html = document.documentElement.innerHTML;
  const cookie = document.cookie || '';
  const first = (text, patterns) => {
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) return match[1];
    }
    return '';
  };
  const dtsg = first(html, [/name="fb_dtsg" value="([^"]+)"/, /"DTSGInitialData",\[\],\{"token":"([^"]+)"/]);
  const lsd  = first(html, [/"LSD",\[\],\{"token":"([^"]+)"/, /name="lsd" value="([^"]+)"/]);
  const rev  = first(html, [/"server_revision":(\d+)/]);
  const user = first(cookie, [/(?:^|;\s*)c_user=(\d+)/]);
  if (!dtsg || !lsd || !user) {
    return JSON.stringify({ok: false, error: 'missing session tokens (fb_dtsg/lsd/c_user)', post_id: POST_ID});
  }
  // jazoest 是 fb_dtsg 各字符码之和再前置 2，Meta 前端固定算法。
  const jazoest = '2' + Array.from(dtsg).reduce((sum, char) => sum + char.charCodeAt(0), 0);

  const build = (friendlyName, docId, variables) => [
    'av=0', '__aaid=0', '__user=' + user, '__a=1',
    '__req=' + Math.random().toString(36).slice(2, 8), '__ccg=MODERATE', '__rev=' + rev,
    '__spin_r=' + rev, '__spin_b=trunk', '__spin_t=' + Math.floor(Date.now() / 1000), '__comet_req=11',
    'fb_dtsg=' + encodeURIComponent(dtsg), 'jazoest=' + jazoest, 'lsd=' + encodeURIComponent(lsd),
    'fb_api_caller_class=RelayModern', 'fb_api_req_friendly_name=' + friendlyName,
    'server_timestamps=true', 'variables=' + encodeURIComponent(JSON.stringify(variables)),
    'doc_id=' + docId,
  ].join('&');

  // 响应可能带 for (;;); 前缀或由多个 JSON 对象拼接，统一取出所有顶层对象。
  const parseObjects = text => {
    const cleaned = String(text).replace(/^for\s*\(;;\);/, '');
    const out = [];
    let depth = 0, start = -1, quoted = false, escaped = false;
    for (let i = 0; i < cleaned.length; i++) {
      const char = cleaned[i];
      if (quoted) { if (escaped) escaped = false; else if (char === '\\') escaped = true; else if (char === '"') quoted = false; continue; }
      if (char === '"') { quoted = true; continue; }
      if (char === '{') { if (!depth) start = i; depth++; }
      else if (char === '}') { depth--; if (!depth && start >= 0) { try { out.push(JSON.parse(cleaned.slice(start, i + 1))); } catch (_) {} start = -1; } }
    }
    return out;
  };

  const send = async (payload) => {
    const control = new AbortController();
    const timer = setTimeout(() => control.abort(), 60000);
    try {
      const response = await fetch('/api/graphql/', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: payload,
        credentials: 'include',
        signal: control.signal,
      });
      return await response.text();
    } finally {
      clearTimeout(timer);
    }
  };

  const toNumber = raw => {
    if (raw == null) return null;
    if (typeof raw === 'number') return raw;
    const text = String(raw).replace(/,/g, '').trim();
    const match = text.match(/^(-?[0-9]+(?:\.[0-9]+)?)([KMB])?$/i);
    if (!match) return null;
    const base = Number(match[1]);
    const unit = (match[2] || '').toUpperCase();
    if (unit === 'K') return Math.round(base * 1000);
    if (unit === 'M') return Math.round(base * 1000000);
    if (unit === 'B') return Math.round(base * 1000000000);
    return base;
  };

  // 把 entity_insights 单个 cell 转为数值。区分"成功取值"与"业务无数据"——
  // TofuErrorQueryResult 是 Meta 主动告知该指标不存在（老跨发帖常见），与请求
  // 抛错完全不同，绝不能误判为失败。
  const valueOf = cell => {
    if (!cell || typeof cell !== 'object') return null;
    if (cell.__typename === 'TofuErrorQueryResult') return null;
    if (typeof cell.value === 'number') return cell.value;
    const f = cell.singleValueFormatter || cell.formatter;
    return f ? toNumber(f.full_formatted_result) : null;
  };
  const hasField = cell => valueOf(cell) != null;

  return (async () => {
    const result = {ok: false, post_id: POST_ID, ig: {}, cross_entities: [], error: null};
    try {
      const entityPayload = build(ENTITY_FN, ENTITY_DOC, {
        entityID: POST_ID, callerID: CALLER,
        shouldShowCrossPosting: true, shouldEnablePostQualityPillExpansion: true,
      });
      let entityJson = null, lastError = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const objects = parseObjects(await send(entityPayload));
          const found = objects.find(item => item && item.data && item.data.tofu_entity);
          if (found) { entityJson = found; break; }
          const failure = objects.find(item => item && item.errors);
          lastError = failure ? JSON.stringify(failure.errors).slice(0, 300) : 'no tofu_entity in response';
        } catch (error) { lastError = String(error); }
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      if (!entityJson) throw new Error('实体查询失败: ' + lastError);

      const entity = entityJson.data.tofu_entity || {};
      const insights = entity.entity_insights || {};

      const igOut = {};
      for (const [outKey, cellKey] of Object.entries(IG_FIELDS)) igOut[outKey] = valueOf(insights[cellKey]);
      const foaOut = {};
      for (const [outKey, cellKey] of Object.entries(FOA_FIELDS)) foaOut[outKey] = valueOf(insights[cellKey]);
      result.ig = igOut;
      result.foa = foaOut;
      result.entity_type = entity.entity_type || '';

      const crossPosted = ((entity.entity_info || {}).cross_posted_entities) || [];
      result.cross_entities = crossPosted.map(item => ({
        entity_type: item.entity_type || '',
        entity_id: item.entity_id || '',
        ig_view: valueOf((item.entity_insights || {}).view),
      }));

      // IG 端 Follows 不在实体查询里，单独查一次。
      try {
        const followPayload = build(SINGLE_FN, SINGLE_DOC, {
          arg: {
            breakdowns: [], compare_time_range: null,
            delta_formats: ['DELTA_RAW_VALUE'], event: 'FOLLOW',
            id: POST_ID, time_range: {type: 'LIFETIME'}, tofu_metric: 'COUNT',
          },
          callerID: CALLER, shouldQueryDefinition: false,
        });
        const followObjects = parseObjects(await send(followPayload));
        const found = followObjects.find(item => item && item.data && item.data.tofu_metrics_query);
        if (found && found.data.tofu_metrics_query.__typename !== 'TofuErrorQueryResult') {
          igOut.new_follows = toNumber(found.data.tofu_metrics_query.value);
        }
      } catch (error) { /* 单指标 Follows 失败不影响主流程 */ }

      // 成功判定：跨发布帖 IG 端能取到的非 null 字段数量。老跨发帖 view 字段业务
      // 缺失很常见，所以不强制要求 view；reach/impression/interaction 三者至少
      // 一个有值即视为能覆盖 Content 合并值。
      const igSingleKeys = ['view','reach','impression','interaction','reaction','share','save','comment'];
      const igKeyCell = k => insights[{
        view: 'view', reach: 'reach', impression: 'impression', interaction: 'interaction',
        reaction: 'reaction', share: 'share', save: 'save', comment: 'comment'
      }[k]];
      result.views_unavailable = !hasField(insights.view);
      result.got_keys = igSingleKeys.filter(k => hasField(igKeyCell(k)));
      result.got_count = result.got_keys.length;
      const coreHit = ['reach','impression','interaction'].some(k => hasField(igKeyCell(k)));
      result.ok = result.got_count >= 1 && coreHit;
      if (!result.ok) result.error = '实体查询未返回任何可用的 Instagram 字段: got=' + result.got_keys.join(',');
    } catch (error) {
      result.error = String((error && error.message) || error);
    }
    window.__igOiResult = result;
    return JSON.stringify(result);
  })();
})()
