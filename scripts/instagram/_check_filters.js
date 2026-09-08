(async () => {
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  
  while (fiber && depth < 40) {
    const typeName = typeof fiber.type === 'function' ? (fiber.type.displayName || fiber.type.name || '') : '';
    
    if (typeName.includes('BizWebUnifiedTableQueryRefetchable')) {
      const props = fiber.memoizedProps || {};
      const filters = props.filters;
      let filtersInfo = 'null';
      if (filters) {
        // Manually extract known filter keys
        const fKeys = Object.keys(filters);
        filtersInfo = {};
        for (const k of fKeys) {
          const v = filters[k];
          if (v === null || v === undefined) filtersInfo[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') filtersInfo[k] = v;
          else if (Array.isArray(v)) filtersInfo[k] = v.slice(0, 5).map(String);
          else filtersInfo[k] = typeof v;
        }
      }
      
      const ids = props.ids;
      let idsInfo = {type: typeof ids, isArray: Array.isArray(ids)};
      if (Array.isArray(ids)) {
        idsInfo.len = ids.length;
        idsInfo.sample = ids.slice(0, 3).map(id => String(id).slice(0, 50));
      }
      
      return JSON.stringify({
        found: 'QueryRefetchable',
        depth: depth,
        filters: filtersInfo,
        ids: idsInfo,
        label: props.label
      });
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found', maxDepth: depth});
})()
