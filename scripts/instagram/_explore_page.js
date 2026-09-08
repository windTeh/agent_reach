(async () => {
  await new Promise(r => setTimeout(r, 10000));
  const results = {};
  results.url = location.href.slice(0, 200);
  results.title = document.title;
  results.bodyLen = document.body.innerText.length;
  
  // Check for grid/table
  const grids = document.querySelectorAll('[role=grid]');
  results.gridCount = grids.length;
  
  // Check for table
  const tables = document.querySelectorAll('table');
  results.tableCount = tables.length;
  
  // Check for list/card structures
  const cards = document.querySelectorAll('[data-visualcompletion]');
  results.cardCount = cards.length;
  
  // Check for any data rows
  const rows = document.querySelectorAll('[role=row]');
  results.rowCount = rows.length;
  
  // Get first 500 chars of text
  results.firstText = document.body.innerText.slice(0, 800);
  
  // Check for any GraphQL-related elements
  const scripts = document.querySelectorAll('script');
  let gqlQueries = [];
  for (const s of scripts) {
    const text = s.textContent || '';
    const matches = text.match(/queryName["\s:]+([^"]{10,80})/g);
    if (matches) gqlQueries.push(...matches);
  }
  results.gqlQueries = gqlQueries.slice(0, 5);
  
  return JSON.stringify(results);
})()
