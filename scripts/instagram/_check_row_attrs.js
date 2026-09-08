(async () => {
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  const rows = grid.querySelectorAll('tr[role=row]');
  const results = [];
  
  for (let i = 1; i < Math.min(4, rows.length); i++) {
    const row = rows[i];
    const rowAttrs = {};
    for (const attr of row.attributes) {
      if (attr.name.startsWith('data-') || attr.name === 'id') {
        rowAttrs[attr.name] = attr.value.slice(0, 100);
      }
    }
    
    // Check for links in the row that might contain post ID
    const links = row.querySelectorAll('a[href]');
    const linkHrefs = [];
    for (const a of links) {
      linkHrefs.push(a.href.slice(0, 200));
    }
    
    // Check for any element with data-item-id or similar
    const dataEls = row.querySelectorAll('[data-item-id], [data-id], [data-row-id], [data-content-id], [data-entity-id]');
    const dataIds = [];
    for (const el of dataEls) {
      for (const attr of el.attributes) {
        if (attr.name.startsWith('data-') && attr.value.match(/^\d{5,}$/)) {
          dataIds.push({attr: attr.name, val: attr.value});
        }
      }
    }
    
    // Get all attributes of all elements in the row
    const allDataAttrs = [];
    row.querySelectorAll('*').forEach(el => {
      for (const attr of el.attributes) {
        if (attr.name.startsWith('data-') && attr.value.length > 3 && attr.value.length < 50) {
          allDataAttrs.push({tag: el.tagName, attr: attr.name, val: attr.value.slice(0, 60)});
        }
      }
    });
    
    results.push({
      rowIdx: i,
      rowAttrs,
      linkHrefs: linkHrefs.slice(0, 5),
      dataIds: dataIds.slice(0, 5),
      allDataAttrs: allDataAttrs.slice(0, 15)
    });
  }
  
  return JSON.stringify({rowCount: rows.length, rows: results});
})()
