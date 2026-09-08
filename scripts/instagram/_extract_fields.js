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
      
      // Extract fields structure
      const fields = firstItem.fields || {};
      const fieldsSafe = {};
      for (const k of Object.keys(fields)) {
        const v = fields[k];
        if (v === null || v === undefined) { fieldsSafe[k] = v; continue; }
        if (typeof v === 'string') { fieldsSafe[k] = v.slice(0, 80); continue; }
        if (typeof v === 'number' || typeof v === 'boolean') { fieldsSafe[k] = v; continue; }
        if (typeof v === 'object') {
          const vKeys = Object.keys(v);
          const vSafe = {};
          for (const vk of vKeys) {
            const vv = v[vk];
            if (vv === null || vv === undefined) vSafe[vk] = vv;
            else if (typeof vv === 'string') vSafe[vk] = vv.slice(0, 60);
            else if (typeof vv === 'number' || typeof vv === 'boolean') vSafe[vk] = vv;
            else vSafe[vk] = typeof vv;
          }
          fieldsSafe[k] = vSafe;
        }
      }
      
      // Extract header structure
      const header = firstItem.header || {};
      const headerSafe = {};
      for (const k of Object.keys(header)) {
        const v = header[k];
        if (v === null || v === undefined) { headerSafe[k] = v; continue; }
        if (typeof v === 'string') { headerSafe[k] = v.slice(0, 80); continue; }
        if (typeof v === 'number' || typeof v === 'boolean') { headerSafe[k] = v; continue; }
        if (typeof v === 'object') {
          const vKeys = Object.keys(v);
          const vSafe = {};
          for (const vk of vKeys) {
            const vv = v[vk];
            if (vv === null || vv === undefined) vSafe[vk] = vv;
            else if (typeof vv === 'string') vSafe[vk] = vv.slice(0, 60);
            else if (typeof vv === 'number' || typeof vv === 'boolean') vSafe[vk] = vv;
            else vSafe[vk] = typeof vv;
          }
          headerSafe[k] = vSafe;
        }
      }
      
      return JSON.stringify({
        id: firstItem.id,
        entityType: firstItem.entityType,
        fieldsKeys: Object.keys(fields),
        fields: fieldsSafe,
        headerKeys: Object.keys(header),
        header: headerSafe
      });
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
