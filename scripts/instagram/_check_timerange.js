(async () => {
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
      const firstItem = ds.getItemForKey(ds.getRenderKeys()[0]);
      const vars = (firstItem.fields || {}).__fragmentOwner.variables;
      
      // Extract timeRange
      const tr = vars.timeRange;
      let trSafe = {};
      if (tr && typeof tr === 'object') {
        for (const k of Object.keys(tr)) {
          const v = tr[k];
          if (v === null || v === undefined) trSafe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') trSafe[k] = v;
          else trSafe[k] = typeof v;
        }
      }
      
      // Extract filters[0].values
      const f0 = vars.filters[0];
      let f0ValuesSafe = {};
      if (f0 && f0.values && typeof f0.values === 'object') {
        for (const k of Object.keys(f0.values)) {
          const v = f0.values[k];
          if (v === null || v === undefined) f0ValuesSafe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') f0ValuesSafe[k] = v;
          else if (Array.isArray(v)) f0ValuesSafe[k] = v.slice(0, 5);
          else f0ValuesSafe[k] = typeof v;
        }
      }
      
      // Extract initialFilters[0].values
      const if0 = vars.initialFilters[0];
      let if0ValuesSafe = {};
      if (if0 && if0.values && typeof if0.values === 'object') {
        for (const k of Object.keys(if0.values)) {
          const v = if0.values[k];
          if (v === null || v === undefined) if0ValuesSafe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') if0ValuesSafe[k] = v;
          else if (Array.isArray(v)) if0ValuesSafe[k] = v.slice(0, 5);
          else if0ValuesSafe[k] = typeof v;
        }
      }
      
      return JSON.stringify({
        timeRange: trSafe,
        filters0Values: f0ValuesSafe,
        initialFilters0Values: if0ValuesSafe,
        visibleColumnKeys: vars.visibleColumnKeys
      });
    }
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
