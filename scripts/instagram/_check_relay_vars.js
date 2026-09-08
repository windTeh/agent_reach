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
      
      const keys = ds.getRenderKeys();
      const firstItem = ds.getItemForKey(keys[0]);
      const fields = firstItem.fields || {};
      
      // Get the __fragmentOwner which has the query variables
      const fragmentOwner = fields.__fragmentOwner;
      if (!fragmentOwner) return JSON.stringify({error: 'no fragmentOwner'});
      
      const result = {};
      result.identifier = (fragmentOwner.identifier || '').slice(0, 200);
      
      // Get variables safely
      const vars = fragmentOwner.variables;
      if (vars && typeof vars === 'object') {
        const varsSafe = {};
        for (const k of Object.keys(vars)) {
          const v = vars[k];
          if (v === null || v === undefined) { varsSafe[k] = v; continue; }
          if (typeof v === 'string') { varsSafe[k] = v.slice(0, 100); continue; }
          if (typeof v === 'number' || typeof v === 'boolean') { varsSafe[k] = v; continue; }
          if (Array.isArray(v)) {
            varsSafe[k] = v.map(item => {
              if (typeof item === 'string' || typeof item === 'number') return item;
              if (typeof item === 'object' && item) {
                const s = {};
                for (const ik of Object.keys(item)) {
                  const iv = item[ik];
                  if (typeof iv === 'string' || typeof iv === 'number' || typeof iv === 'boolean' || iv === null) s[ik] = iv;
                  else s[ik] = typeof iv;
                }
                return s;
              }
              return String(item);
            });
          } else {
            varsSafe[k] = typeof v;
          }
        }
        result.variables = varsSafe;
      }
      
      // Also check node for query info
      const node = fragmentOwner.node;
      if (node && typeof node === 'object') {
        result.nodeKeys = Object.keys(node).slice(0, 10);
        if (node.params) {
          result.paramsKeys = Object.keys(node.params).slice(0, 10);
          result.docId = node.params.docID || node.params.id || '';
          result.name = node.params.name || '';
        }
      }
      
      return JSON.stringify(result);
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
