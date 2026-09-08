(async () => {
  await new Promise(r => setTimeout(r, 2000));
  
  // Look at React fiber tree for the grid data
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  // Find React fiber on the grid element
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$'));
  if (!fiberKey) return JSON.stringify({error: 'no fiber'});
  
  let fiber = grid[fiberKey];
  const fiberInfo = [];
  
  // Walk up the fiber tree to find the data container
  let depth = 0;
  while (fiber && depth < 30) {
    const type = fiber.type;
    const typeName = typeof type === 'function' ? (type.displayName || type.name || '') : (type || '');
    const memoizedProps = fiber.memoizedProps;
    const memoizedState = fiber.memoizedState;
    
    let propsInfo = '';
    if (memoizedProps) {
      const keys = Object.keys(memoizedProps).filter(k => k !== 'children');
      propsInfo = keys.join(',');
    }
    
    if (typeName && typeName.length > 1) {
      fiberInfo.push({
        depth: depth,
        type: typeName.slice(0, 60),
        propsKeys: propsInfo.slice(0, 100)
      });
    }
    
    // Check if this fiber has data we need (look for edges, rows, etc.)
    if (memoizedProps) {
      const propStr = JSON.stringify(memoizedProps).slice(0, 200);
      if (propStr.includes('edges') || propStr.includes('row_id') || propStr.includes('entity_type')) {
        fiberInfo[fiberInfo.length - 1].hasData = true;
        fiberInfo[fiberInfo.length - 1].dataPreview = propStr.slice(0, 300);
      }
    }
    
    fiber = fiber.return;
    depth++;
  }
  
  return JSON.stringify({fiberCount: fiberInfo.length, fibers: fiberInfo.filter(f => f.type.length > 2).slice(0, 20)});
})()
