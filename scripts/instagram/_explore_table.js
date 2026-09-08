(async () => {
  await new Promise(r => setTimeout(r, 3000));
  const results = {};
  
  // Check grid/row structure
  const grid = document.querySelector('[role=grid]');
  if (grid) {
    results.gridExists = true;
    const rows = grid.querySelectorAll('[role=row]');
    results.rowCount = rows.length;
    
    // Extract first row data
    if (rows.length > 0) {
      const firstRow = rows[0];
      const cells = firstRow.querySelectorAll('[role=gridcell]');
      results.cellCount = cells.length;
      results.firstRowCells = [];
      for (const cell of cells) {
        results.firstRowCells.push(cell.innerText.slice(0, 100));
      }
    }
    
    // Extract column headers
    const headers = grid.querySelectorAll('[role=columnheader]');
    results.headers = [];
    for (const h of headers) {
      results.headers.push(h.innerText.slice(0, 50));
    }
  }
  
  // Check for time range selector
  const timeBtns = [];
  document.querySelectorAll('div[role=button]').forEach(el => {
    const t = el.innerText || '';
    if (t.includes('days') || t.includes('Last') || t.includes('month')) {
      timeBtns.push(t.slice(0, 80));
    }
  });
  results.timeButtons = timeBtns.slice(0, 5);
  
  // Check for tofu_unified_table in the initial HTML data
  const html = document.documentElement.outerHTML;
  const tofuIdx = html.indexOf('tofu_unified_table');
  results.hasTofuTable = tofuIdx !== -1;
  
  // Check for BizWebContentManagement query
  const cmIdx = html.indexOf('ContentManagement');
  results.hasContentMgmt = cmIdx !== -1;
  if (cmIdx !== -1) {
    results.cmCtx = html.slice(cmIdx, cmIdx + 200).replace(/</g, '').slice(0, 200);
  }
  
  return JSON.stringify(results);
})()
