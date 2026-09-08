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
      
      // creationTime.$1 structure
      const ct1 = firstItem.creationTime && firstItem.creationTime.$1;
      let ct1Safe = {};
      if (ct1 && typeof ct1 === 'object') {
        for (const k of Object.keys(ct1).slice(0, 15)) {
          const v = ct1[k];
          if (v === null || v === undefined) ct1Safe[k] = v;
          else if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') ct1Safe[k] = v;
          else ct1Safe[k] = typeof v;
        }
      }
      
      // video structure
      const vid = firstItem.video;
      let vidSafe = {};
      if (vid && typeof vid === 'object') {
        for (const k of Object.keys(vid).slice(0, 15)) {
          const v = vid[k];
          if (v === null || v === undefined) vidSafe[k] = v;
          else if (typeof v === 'string') vidSafe[k] = v.slice(0, 80);
          else if (typeof v === 'number' || typeof v === 'boolean') vidSafe[k] = v;
          else vidSafe[k] = typeof v;
        }
      }
      
      // Check second item (might be video story)
      let secondItemInfo = null;
      if (keys.length > 1) {
        const second = ds.getItemForKey(keys[1]);
        secondItemInfo = {
          id: second.id,
          mediaType: second.mediaType,
          videoType: typeof second.video,
          hasVideolist: !!second.videolist
        };
        if (second.video && typeof second.video === 'object') {
          secondItemInfo.videoKeys = Object.keys(second.video).slice(0, 10);
          // Check for duration
          for (const k of Object.keys(second.video)) {
            if (k.toLowerCase().includes('dur') || k.toLowerCase().includes('length') || k.toLowerCase().includes('time')) {
              const v = second.video[k];
              if (typeof v === 'string' || typeof v === 'number') secondItemInfo['video_' + k] = v;
            }
          }
        }
      }
      
      // Check all items for mediaType distribution
      const mediaTypes = {};
      for (const key of keys) {
        const item = ds.getItemForKey(key);
        const mt = item.mediaType || 'unknown';
        mediaTypes[mt] = (mediaTypes[mt] || 0) + 1;
      }
      
      // Check BizWebUnifiedTableQueryRefetchable for pagination
      let fiber3 = fiber;
      let depth3 = 0;
      let queryRefInfo = null;
      while (fiber3 && depth3 < 40) {
        const tn3 = typeof fiber3.type === 'function' ? (fiber3.type.displayName || fiber3.type.name || '') : '';
        if (tn3.includes('BizWebUnifiedTableQueryRefetchable')) {
          const props3 = fiber3.memoizedProps || {};
          queryRefInfo = {
            label: props3.label,
            hasLoadNext: typeof props3.loadNext === 'function'
          };
          break;
        }
        fiber3 = fiber3.return;
        depth3++;
      }
      
      return JSON.stringify({
        creationTime$1: ct1Safe,
        video: vidSafe,
        secondItem: secondItemInfo,
        mediaTypeDistribution: mediaTypes,
        queryRef: queryRefInfo
      });
    }
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'not found'});
})()
