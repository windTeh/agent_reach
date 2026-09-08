(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  const found = [];
  
  while (fiber && depth < 50) {
    const typeName = typeof fiber.type === 'function' ? (fiber.type.displayName || fiber.type.name || '') : '';
    if (typeName.length > 1) {
      const info = {depth, type: typeName.slice(0, 80)};
      const props = fiber.memoizedProps;
      if (props && typeof props === 'object') {
        const keys = Object.keys(props).filter(k => k !== 'children');
        // Check for interesting props
        if (keys.includes('ids') || keys.includes('filters') || keys.includes('dataRef') || 
            keys.includes('loadNext') || keys.includes('hasNext') || keys.includes('variables')) {
          info.interestingKeys = keys.slice(0, 15);
        }
      }
      found.push(info);
    }
    fiber = fiber.return;
    depth++;
  }
  
  return JSON.stringify({totalDepth: depth, components: found.filter(f => f.interestingKeys || f.type.includes('Query') || f.type.includes('Refetch') || f.type.includes('Unified') || f.type.includes('Story') || f.type.includes('Archive')).slice(0, 15)});
})()
