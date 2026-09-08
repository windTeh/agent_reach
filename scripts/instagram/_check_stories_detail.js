(async () => {
  await new Promise(r => setTimeout(r, 2000));
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
      
      // creationTime structure
      const ct = firstItem.creationTime;
      let ctSafe = {};
      if (ct && typeof ct === 'object') {
        for (const k of Object.keys(ct)) {
          const v = ct[k];
          if (v === null || v === undefined) ctSafe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') ctSafe[k] = v;
          else ctSafe[k] = typeof v;
        }
      }
      
      // expirationTime structure
      const et = firstItem.expirationTime;
      let etSafe = {};
      if (et && typeof et === 'object') {
        for (const k of Object.keys(et)) {
          const v = et[k];
          if (v === null || v === undefined) etSafe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') etSafe[k] = v;
          else etSafe[k] = typeof v;
        }
      }
      
      // Check for pagination - look at BizWebUnifiedTableView props
      let fiber2 = fiber;
      let depth2 = 0;
      let paginationInfo = null;
      while (fiber2 && depth2 < 30) {
        const tn2 = typeof fiber2.type === 'function' ? (fiber2.type.displayName || fiber2.type.name || '') : '';
        if (tn2.includes('BizWebUnifiedTableView')) {
          const props2 = fiber2.memoizedProps || {};
          paginationInfo = {
            hasNext: props2.hasNext,
            hasLoadNext: typeof props2.loadNext === 'function',
            label: props2.label
          };
          break;
        }
        fiber2 = fiber2.return;
        depth2++;
      }
      
      // Also check all items' creationTime to see date range
      const allDates = [];
      for (const key of keys) {
        const item = ds.getItemForKey(key);
        const ct2 = item.creationTime;
        if (ct2 && typeof ct2 === 'object') {
          allDates.push(ct2.timestamp || ct2.value || ct2.time || '');
        } else if (typeof ct2 === 'number') {
          allDates.push(ct2);
        }
      }
      
      // Check FOA_INTERACTIONS value structure
      const foa = firstItem.metrics && firstItem.metrics.FOA_INTERACTIONS;
      let foaSafe = {};
      if (foa && typeof foa === 'object') {
        for (const k of Object.keys(foa)) {
          const v = foa[k];
          if (v === null || v === undefined) foaSafe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') foaSafe[k] = v;
          else foaSafe[k] = typeof v;
        }
      }
      
      return JSON.stringify({
        creationTime: ctSafe,
        expirationTime: etSafe,
        pagination: paginationInfo,
        allDates: allDates,
        totalRows: keys.length,
        foaInteractions: foaSafe,
        // Check video field for duration
        videoType: typeof firstItem.video,
        hasVideolist: !!firstItem.videolist
      });
    }
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
