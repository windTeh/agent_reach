(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  
  while (fiber && depth < 50) {
    const typeName = typeof fiber.type === 'function' ? (fiber.type.displayName || fiber.type.name || '') : '';
    
    if (typeName.includes('TofuUnifiedTablePaginationInner')) {
      const props = fiber.memoizedProps || {};
      const query = props.query || {};
      const fo = query.__fragmentOwner;
      
      if (!fo) return JSON.stringify({error: 'no fragmentOwner'});
      
      const result = {};
      result.identifier = (fo.identifier || '').slice(0, 300);
      
      // Extract variables safely
      const vars = fo.variables;
      if (vars && typeof vars === 'object') {
        const varsSafe = {};
        for (const k of Object.keys(vars)) {
          const v = vars[k];
          if (v === null || v === undefined) { varsSafe[k] = v; continue; }
          if (typeof v === 'string') { varsSafe[k] = v.slice(0, 100); continue; }
          if (typeof v === 'number' || typeof v === 'boolean') { varsSafe[k] = v; continue; }
          if (Array.isArray(v)) {
            varsSafe[k] = v.slice(0, 5).map(x => {
              if (typeof x === 'string' || typeof x === 'number') return x;
              if (typeof x === 'object' && x) return '{' + Object.keys(x).slice(0, 8).join(',') + '}';
              return String(x);
            });
          } else {
            varsSafe[k] = typeof v;
          }
        }
        result.variables = varsSafe;
      }
      
      // Check node for doc_id
      const node = fo.node;
      if (node && typeof node === 'object') {
        if (node.params) {
          result.docId = node.params.docID || node.params.id || '';
          result.queryName = node.params.name || '';
          result.operationKind = node.params.operationKind || '';
        }
      }
      
      return JSON.stringify(result);
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
