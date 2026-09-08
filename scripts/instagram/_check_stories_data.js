(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  
  while (fiber && depth < 10) {
    const typeName = typeof fiber.type === 'function' ? (fiber.type.displayName || fiber.type.name || '') : '';
    if (typeName.includes('WebTable.react]') && !typeName.includes('use')) {
      const ds = (fiber.memoizedProps || {}).dataSource;
      if (!ds) return JSON.stringify({error: 'no ds'});
      const keys = ds.getRenderKeys();
      if (!keys || !keys.length) return JSON.stringify({error: 'no rows'});
      const firstItem = ds.getItemForKey(keys[0]);
      
      // Extract key fields safely
      const safe = {};
      const importantKeys = ['id', 'storyID', 'mediaType', 'creationTime', 'postType', 
        'privacyScope', 'expirationTime', 'indexInResults', 'title', 'imageUri', 'uri'];
      for (const k of importantKeys) {
        const v = firstItem[k];
        if (v === null || v === undefined) safe[k] = v;
        else if (typeof v === 'string') safe[k] = v.slice(0, 100);
        else if (typeof v === 'number' || typeof v === 'boolean') safe[k] = v;
        else safe[k] = typeof v;
      }
      
      // Extract metrics
      const metrics = firstItem.metrics;
      let metricsSafe = {};
      if (metrics && typeof metrics === 'object') {
        for (const k of Object.keys(metrics)) {
          const v = metrics[k];
          if (v === null || v === undefined) metricsSafe[k] = v;
          else if (typeof v === 'string') metricsSafe[k] = v.slice(0, 60);
          else if (typeof v === 'number' || typeof v === 'boolean') metricsSafe[k] = v;
          else if (typeof v === 'object') {
            const vKeys = Object.keys(v);
            const vSafe = {};
            for (const vk of vKeys.slice(0, 10)) {
              const vv = v[vk];
              if (vv === null || vv === undefined) vSafe[vk] = vv;
              else if (typeof vv === 'string') vSafe[vk] = vv.slice(0, 60);
              else if (typeof vv === 'number' || typeof vv === 'boolean') vSafe[vk] = vv;
              else vSafe[vk] = typeof vv;
            }
            metricsSafe[k] = vSafe;
          }
        }
      }
      
      // Extract owners
      const owners = firstItem.owners;
      let ownersSafe = null;
      if (Array.isArray(owners)) {
        ownersSafe = owners.slice(0, 2).map(o => {
          if (typeof o === 'object' && o) {
            const oSafe = {};
            for (const k of Object.keys(o).slice(0, 10)) {
              const v = o[k];
              if (v === null || v === undefined) oSafe[k] = v;
              else if (typeof v === 'string') oSafe[k] = v.slice(0, 60);
              else if (typeof v === 'number' || typeof v === 'boolean') oSafe[k] = v;
              else oSafe[k] = typeof v;
            }
            return oSafe;
          }
          return String(o);
        });
      }
      
      // Extract creator
      const creator = firstItem.creator;
      let creatorSafe = null;
      if (creator && typeof creator === 'object') {
        creatorSafe = {};
        for (const k of Object.keys(creator).slice(0, 10)) {
          const v = creator[k];
          if (v === null || v === undefined) creatorSafe[k] = v;
          else if (typeof v === 'string') creatorSafe[k] = v.slice(0, 60);
          else if (typeof v === 'number' || typeof v === 'boolean') creatorSafe[k] = v;
          else creatorSafe[k] = typeof v;
        }
      }
      
      // Extract maxMetricValues (might have duration)
      const maxMetrics = firstItem.maxMetricValues;
      let maxMetricsSafe = null;
      if (maxMetrics && typeof maxMetrics === 'object') {
        maxMetricsSafe = {};
        for (const k of Object.keys(maxMetrics).slice(0, 15)) {
          const v = maxMetrics[k];
          if (v === null || v === undefined) maxMetricsSafe[k] = v;
          else if (typeof v === 'string') maxMetricsSafe[k] = v.slice(0, 60);
          else if (typeof v === 'number' || typeof v === 'boolean') maxMetricsSafe[k] = v;
          else maxMetricsSafe[k] = typeof v;
        }
      }
      
      return JSON.stringify({
        item: safe,
        metrics: metricsSafe,
        owners: ownersSafe,
        creator: creatorSafe,
        maxMetricValues: maxMetricsSafe
      });
    }
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
