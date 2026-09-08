(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  const rows = grid.querySelectorAll('[role=row]');
  const results = [];
  
  for (let i = 0; i < Math.min(3, rows.length); i++) {
    const row = rows[i];
    const rowInfo = {
      tagName: row.tagName,
      ariaLabel: row.getAttribute('aria-label') || '',
      childCount: row.children.length,
      children: []
    };
    
    for (const child of row.children) {
      const childInfo = {
        tag: child.tagName,
        role: child.getAttribute('role') || '',
        text: (child.innerText || '').slice(0, 80),
        childCount: child.children.length
      };
      // Check for nested children
      if (child.children.length > 0 && child.children.length < 10) {
        childInfo.nested = [];
        for (const nc of child.children) {
          childInfo.nested.push({
            tag: nc.tagName,
            role: nc.getAttribute('role') || '',
            text: (nc.innerText || '').slice(0, 60)
          });
        }
      }
      rowInfo.children.push(childInfo);
    }
    results.push(rowInfo);
  }
  
  return JSON.stringify({rowCount: rows.length, rows: results});
})()
