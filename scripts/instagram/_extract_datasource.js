(async () => {
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  const fiberKey = Object.keys(grid).find(k => k.startsWith('__reactFiber$'));
  let fiber = grid[fiberKey];
  let depth = 0;
  
  while (fiber && depth < 10) {
    const typeName = typeof fiber.type === 'function' ? (fiber.type.displayName || fiber.type.name || '') : '';
    
    if (typeName.includes('WebTable.react]') && !typeName.includes('use')) {
      const props = fiber.memoizedProps || {};
      const ds = props.dataSource;
      if (!ds) return JSON.stringify({error: 'no dataSource'});
      
      // Try to get data using the dataSource methods
      const result = {};
      
      // getSize - how many rows
      if (typeof ds.getSize === 'function') {
        result.size = ds.getSize();
      }
      
      // getRenderItems
      if (typeof ds.getRenderItems === 'function') {
        const items = ds.getRenderItems();
        result.renderItemsType = typeof items;
        result.renderItemsIsArray = Array.isArray(items);
        if (Array.isArray(items)) {
          result.renderItemsLen = items.length;
          if (items[0]) {
            result.item0Type = typeof items[0];
            if (typeof items[0] === 'object' && items[0] !== null) {
              result.item0Keys = Object.keys(items[0]).slice(0, 20);
            }
          }
        }
      }
      
      // getRenderKeys
      if (typeof ds.getRenderKeys === 'function') {
        const keys = ds.getRenderKeys();
        result.renderKeysIsArray = Array.isArray(keys);
        if (Array.isArray(keys)) {
          result.renderKeysLen = keys.length;
          result.renderKeysSample = keys.slice(0, 5).map(String);
        }
      }
      
      // getItemForKey with first key
      if (typeof ds.getItemForKey === 'function' && result.renderKeysSample && result.renderKeysSample[0]) {
        const item = ds.getItemForKey(result.renderKeysSample[0]);
        if (item && typeof item === 'object') {
          result.itemForKeyKeys = Object.keys(item).slice(0, 20);
          // Safely extract values
          const safeItem = {};
          for (const k of Object.keys(item).slice(0, 20)) {
            const v = item[k];
            if (v === null || v === undefined) safeItem[k] = v;
            else if (typeof v === 'string') safeItem[k] = v.slice(0, 80);
            else if (typeof v === 'number' || typeof v === 'boolean') safeItem[k] = v;
            else safeItem[k] = typeof v;
          }
          result.itemForKeySafe = safeItem;
        }
      }
      
      return JSON.stringify(result);
    }
    
    fiber = fiber.return;
    depth++;
  }
  return JSON.stringify({error: 'WebTable not found'});
})()
