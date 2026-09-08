(async () => {
  await new Promise(r => setTimeout(r, 2000));
  const grid = document.querySelector('[role=grid]');
  if (!grid) return JSON.stringify({error: 'no grid'});
  
  // Get column headers
  const headerRow = grid.querySelector('tr[role=row]');
  const headers = [];
  if (headerRow) {
    const ths = headerRow.querySelectorAll('th[role=columnheader]');
    for (const th of ths) headers.push((th.innerText || '').trim().slice(0, 40));
  }
  
  // Get first 3 data rows with all cells
  const allRows = grid.querySelectorAll('tr[role=row]');
  const dataRows = [];
  for (let i = 1; i < Math.min(4, allRows.length); i++) {
    const row = allRows[i];
    const cells = row.querySelectorAll('td[role=gridcell]');
    const cellData = [];
    for (let j = 0; j < cells.length; j++) {
      const cell = cells[j];
      const text = (cell.innerText || '').trim().slice(0, 100);
      // Check for images/thumbnails
      const imgs = cell.querySelectorAll('img');
      const imgSrcs = Array.from(imgs).map(img => img.src.slice(0, 100));
      // Check for links
      const links = cell.querySelectorAll('a[href]');
      const linkData = Array.from(links).map(a => ({href: a.href.slice(0, 150), text: (a.innerText||'').slice(0, 50)}));
      cellData.push({
        col: headers[j] || ('col' + j),
        text: text,
        imgs: imgSrcs.slice(0, 2),
        links: linkData.slice(0, 2)
      });
    }
    dataRows.push({rowIdx: i, cellCount: cells.length, cells: cellData});
  }
  
  return JSON.stringify({
    headers: headers,
    headerCount: headers.length,
    totalDataRows: allRows.length - 1,
    dataRows: dataRows
  });
})()
