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
      
      // Get the dataRef which should have the Relay query data
      const dr = props.dataRef;
      let result = {};
      
      if (dr && dr.current) {
        const cur = dr.current;
        result.currentKeys = Object.keys(cur).slice(0, 20);
        
        // Look for tofu_unified_table data
        for (const k of Object.keys(cur)) {
          if (k.includes('tofu') || k.includes('unified') || k.includes('table') || k.includes('content')) {
            const v = cur[k];
            if (v && typeof v === 'object') {
              result[k + '_keys'] = Object.keys(v).slice(0, 15);
            }
          }
        }
      }
      
      // Check the fragmentOwner variables from an item
      const ds = null; // We need to find the WebTable separately
      
      // Check filters more carefully
      const filters = props.filters;
      if (filters) {
        result.filtersIsArray = Array.isArray(filters);
        if (Array.isArray(filters)) {
          result.filtersLen = filters.length;
          const f0 = filters[0];
          if (f0 && typeof f0 === 'object') {
            // Extract all keys and their types/values
            const f0Safe = {};
            for (const k of Object.keys(f0)) {
              const v = f0[k];
              if (v === null || v === undefined) { f0Safe[k] = v; continue; }
              if (typeof v === 'string') { f0Safe[k] = v.slice(0, 100); continue; }
              if (typeof v === 'number' || typeof v === 'boolean') { f0Safe[k] = v; continue; }
              if (Array.isArray(v)) {
                f0Safe[k] = v.map(item => {
                  if (typeof item === 'string' || typeof item === 'number') return item;
                  if (typeof item === 'object' && item) {
                    const itemSafe = {};
                    for (const ik of Object.keys(item)) {
                      const iv = item[ik];
                      if (iv === null || iv === undefined) itemSafe[ik] = iv;
                      else if (typeof iv === 'string') itemSafe[ik] = iv.slice(0, 60);
                      else if (typeof iv === 'number' || typeof iv === 'boolean') itemSafe[ik] = iv;
                      else itemSafe[ik] = typeof iv;
                    }
                    return itemSafe;
                  }
                  return String(item);
                });
              } else {
                f0Safe[k] = typeof v;
              }
            }
            result.filters0 = f0Safe;
          }
        } else if (typeof filters === 'object') {
          result.filtersKeys = Object.keys(filters);
        }
      }
      
      return JSON.stringify(result);
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
