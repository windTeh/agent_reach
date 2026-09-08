(async () => {
  await new Promise(r => setTimeout(r, 3000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  // Get column headers
  const headers = [];
  const headerRow = grid.querySelector('tr[role=row]');
  if (headerRow) {
    const ths = headerRow.querySelectorAll('th[role=columnheader]');
    for (const th of ths) {
      headers.push((th.innerText || '').trim().slice(0, 50));
    }
  }
  
  // Get data rows (skip header)
  const allRows = grid.querySelectorAll('tr[role=row]');
  const dataRows = [];
  for (let i = 1; i < Math.min(5, allRows.length); i++) {
    const row = allRows[i];
    const cells = row.querySelectorAll('td[role=gridcell]');
    const cellTexts = [];
    for (const cell of cells) {
      cellTexts.push((cell.innerText || '').trim().slice(0, 120));
    }
    
    // Also check for links
    const links = row.querySelectorAll('a[href]');
    const linkHrefs = [];
    for (const a of links) {
      linkHrefs.push(a.href.slice(0, 200));
    }
    
    dataRows.push({
      cellCount: cells.length,
      cells: cellTexts,
      links: linkHrefs.slice(0, 5),
      ariaLabel: (row.getAttribute('aria-label') || '').slice(0, 100)
    });
  }
  
  return JSON.stringify({
    headers: headers,
    headerCount: headers.length,
    totalRows: allRows.length - 1,
    dataRows: dataRows
  });
})()
