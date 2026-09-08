(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  
  // Find BizWebUnifiedTableQueryRefetchable (depth ~33) and BizWebUnifiedTableView (depth ~32)
  while (fiber && depth < 40) {
    const type = fiber.type;
    const typeName = typeof type === 'function' ? (type.displayName || type.name || '') : '';
    
    if (typeName.includes('BizWebUnifiedTableQueryRefetchable')) {
      const props = fiber.memoizedProps || {};
      const result = {
        found: 'QueryRefetchable',
        depth: depth,
        filtersType: typeof props.filters,
        idsType: typeof props.ids,
        idsIsArray: Array.isArray(props.ids),
        idsLen: Array.isArray(props.ids) ? props.ids.length : 0,
        idsSample: Array.isArray(props.ids) ? props.ids.slice(0, 3).map(String) : [],
        filtersKeys: props.filters && typeof props.filters === 'object' ? Object.keys(props.filters) : [],
        dataRefType: typeof props.dataRef,
      };
      
      // Check dataRef structure
      if (props.dataRef && typeof props.dataRef === 'object') {
        result.dataRefKeys = Object.keys(props.dataRef).slice(0, 15);
        // Check if dataRef has the unified_table data
        if (props.dataRef.current) {
          result.dataRefCurrentKeys = Object.keys(props.dataRef.current).slice(0, 15);
        }
        if (props.dataRef.data) {
          result.dataRefDataKeys = Object.keys(props.dataRef.data).slice(0, 15);
        }
      }
      
      // Check filters content
      if (props.filters && typeof props.filters === 'object') {
        try {
          result.filtersStr = JSON.stringify(props.filters).slice(0, 500);
        } catch(e) {
          result.filtersError = e.message;
        }
      }
      
      return JSON.stringify(result);
    }
    
    if (typeName.includes('BizWebUnifiedTableView')) {
      const props = fiber.memoizedProps || {};
      const items = props.items || [];
      const result = {
        found: 'TableView',
        depth: depth,
        itemsLen: items.length,
        itemsSample: [],
        hasNext: props.hasNext,
        label: props.label,
      };
      
      // Get first item structure
      if (items.length > 0 && items[0]) {
        result.item0Keys = Object.keys(items[0]).slice(0, 20);
        // Try to get item data safely
        try {
          const item = items[0];
          const safeItem = {};
          for (const k of Object.keys(item)) {
            const v = item[k];
            if (v === null || v === undefined) { safeItem[k] = v; continue; }
            if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
              safeItem[k] = v;
            } else if (Array.isArray(v)) {
              safeItem[k] = '[array:' + v.length + ']';
            } else if (typeof v === 'object') {
              safeItem[k] = '{obj:' + Object.keys(v).slice(0, 5).join(',') + '}';
            }
          }
          result.item0Safe = safeItem;
        } catch(e) {
          result.item0Error = e.message;
        }
      }
      
      return JSON.stringify(result);
    }
    
    fiber = fiber.return;
    depth++;
  }
  
  return JSON.stringify({error: 'components not found'});
})()
