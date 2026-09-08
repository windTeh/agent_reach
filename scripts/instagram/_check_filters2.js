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
      
      // Deep dive into filters[0]
      let filtersDeep = 'null';
      if (filters && filters[0]) {
        const f0 = filters[0];
        const f0Keys = Object.keys(f0);
        filtersDeep = {keys: f0Keys};
        for (const k of f0Keys) {
          const v = f0[k];
          if (v === null || v === undefined) filtersDeep[k] = v;
          else if (typeof v === 'string') filtersDeep[k] = v.slice(0, 100);
          else if (typeof v === 'number' || typeof v === 'boolean') filtersDeep[k] = v;
          else if (Array.isArray(v)) {
            filtersDeep[k] = v.slice(0, 5).map(item => {
              if (typeof item === 'string' || typeof item === 'number') return item;
              if (typeof item === 'object' && item) return '{' + Object.keys(item).slice(0, 8).join(',') + '}';
              return String(item);
            });
          }
          else if (typeof v === 'object') {
            filtersDeep[k] = '{keys:' + Object.keys(v).slice(0, 10).join(',') + '}';
          }
        }
      }
      
      // Also check the dataRef
      let dataRefInfo = 'none';
      if (props.dataRef) {
        const dr = props.dataRef;
        if (dr.current) {
          const cur = dr.current;
          dataRefInfo = {currentKeys: Object.keys(cur).slice(0, 15)};
          // Check for unified_table data
          if (cur.tofu_unified_table) {
            const tut = cur.tofu_unified_table;
            dataRefInfo.tofuKeys = Object.keys(tut).slice(0, 15);
          }
          // Check for other data keys
          for (const k of Object.keys(cur)) {
            if (k.includes('table') || k.includes('unified') || k.includes('content')) {
              dataRefInfo[k + '_keys'] = Object.keys(cur[k]).slice(0, 10);
            }
          }
        }
      }
      
      return JSON.stringify({filters: filtersDeep, dataRef: dataRefInfo});
    }
    
    // Also check WebTable dataSource
    if (typeName.includes('WebTable.react]') && !typeName.includes('use')) {
      const props = fiber.memoizedProps || {};
      const ds = props.dataSource;
      if (ds) {
        let dsInfo = {type: typeof ds};
        if (typeof ds === 'object') {
          dsInfo.keys = Object.keys(ds).slice(0, 15);
          // Check for rows/items
          for (const k of Object.keys(ds)) {
            const v = ds[k];
            if (Array.isArray(v)) {
              dsInfo[k + '_len'] = v.length;
              if (v.length > 0 && v[0] && typeof v[0] === 'object') {
                dsInfo[k + '_0_keys'] = Object.keys(v[0]).slice(0, 15);
              }
            }
          }
        }
        return JSON.stringify({webTableDataSource: dsInfo});
      }
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
