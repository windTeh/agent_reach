(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
  if (!fiberKey) return JSON.stringify({error: 'no fiber'});
  
  let fiber = grid[fiberKey];
  const fiberInfo = [];
  let depth = 0;
  
  while (fiber && depth < 40) {
    const type = fiber.type;
    const typeName = typeof type === 'function' ? (type.displayName || type.name || '') : (type || '');
    
    if (typeName && typeName.length > 1) {
      const info = {depth, type: typeName.slice(0, 60)};
      
      // Safely check props without full serialization
      const props = fiber.memoizedProps;
      if (props && typeof props === 'object') {
        const keys = Object.keys(props).filter(k => k !== 'children');
        info.propsKeys = keys.slice(0, 10);
        
        // Check for data-related props
        for (const k of keys) {
          const v = props[k];
          if (v && typeof v === 'object' && !Array.isArray(v)) {
            const vKeys = Object.keys(v);
            if (vKeys.includes('edges') || vKeys.includes('row_id') || vKeys.includes('entity_type') || vKeys.includes('all_ids')) {
              info.dataKey = k;
              info.dataKeys = vKeys.slice(0, 15);
            }
          }
          // Check for arrays of data objects
          if (Array.isArray(v) && v.length > 0 && v[0] && typeof v[0] === 'object') {
            const firstKeys = Object.keys(v[0]);
            if (firstKeys.includes('row_id') || firstKeys.includes('entity_type') || firstKeys.includes('node')) {
              info.arrayKey = k;
              info.arrayLen = v.length;
              info.arrayFirstKeys = firstKeys.slice(0, 15);
            }
          }
        }
      }
      
      fiberInfo.push(info);
    }
    
    fiber = fiber.return;
    depth++;
  }
  
  return JSON.stringify({fiberCount: fiberInfo.length, fibers: fiberInfo.filter(f => f.type.length > 2).slice(0, 25)});
})()
