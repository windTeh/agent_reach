(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  
  while (fiber && depth < 50) {
    const typeName = typeof fiber.type === 'function' ? (fiber.type.displayName || fiber.type.name || '') : '';
    
    // Find TofuUnifiedTablePaginationInner (depth ~32) which has 'query' prop
    if (typeName.includes('TofuUnifiedTablePaginationInner')) {
      const props = fiber.memoizedProps || {};
      const result = {found: 'PaginationInner', depth};
      
      // Check query prop
      const query = props.query;
      if (query && typeof query === 'object') {
        result.queryKeys = Object.keys(query).slice(0, 15);
        if (query.params) {
          result.queryParamsKeys = Object.keys(query.params).slice(0, 10);
          result.docId = query.params.docID || query.params.id || '';
          result.queryName = query.params.name || '';
          result.operationKind = query.params.operationKind || '';
        }
        if (query.variables) {
          const vars = query.variables;
          const varsSafe = {};
          for (const k of Object.keys(vars)) {
            const v = vars[k];
            if (v === null || v === undefined) varsSafe[k] = v;
            else if (typeof v === 'string') varsSafe[k] = v.slice(0, 100);
            else if (typeof v === 'number' || typeof v === 'boolean') varsSafe[k] = v;
            else if (Array.isArray(v)) varsSafe[k] = v.slice(0, 5).map(x => typeof x === 'object' && x ? '{obj}' : x);
            else varsSafe[k] = typeof v;
          }
          result.variables = varsSafe;
        }
      }
      
      // Check filters
      const filters = props.filters;
      if (filters) {
        result.filtersType = typeof filters;
        if (Array.isArray(filters)) {
          result.filtersLen = filters.length;
        }
      }
      
      result.hasNext = props.hasNext;
      result.accountIDs = props.accountIDs;
      
      return JSON.stringify(result);
    }
    
    // Also check TofuUnifiedTableQueryRoot
    if (typeName.includes('TofuUnifiedTableQueryRoot') && !typeName.includes('Placeholder')) {
      const props = fiber.memoizedProps || {};
      const result = {found: 'QueryRoot', depth};
      
      result.accountIDs = props.accountIDs;
      result.businessID = props.businessID;
      result.adAccountID = props.adAccountID;
      result.contentQualifier = props.contentQualifier;
      result.pageSize = props.pageSize;
      result.maxRowCount = props.maxRowCount;
      
      // Check filters
      if (props.filters) {
        result.filtersType = typeof props.filters;
        if (typeof props.filters === 'object' && !Array.isArray(props.filters)) {
          result.filtersKeys = Object.keys(props.filters).slice(0, 15);
        }
      }
      
      // Check fixedFilters
      if (props.fixedFilters) {
        result.fixedFiltersType = typeof props.fixedFilters;
        if (typeof props.fixedFilters === 'object') {
          try {
            result.fixedFiltersStr = JSON.stringify(props.fixedFilters).slice(0, 500);
          } catch(e) {
            result.fixedFiltersKeys = Object.keys(props.fixedFilters).slice(0, 10);
          }
        }
      }
      
      return JSON.stringify(result);
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
