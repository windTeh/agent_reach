(async () => {
  const html = document.documentElement.outerHTML;
  
  // Check the context around "edges" at position 1727441
  const edgesPos = html.indexOf('"edges"');
  if (edgesPos === -1) return JSON.stringify({error: 'no edges found'});
  
  const ctx = html.slice(Math.max(0, edgesPos - 500), edgesPos + 2000);
  
  // Look for the data structure around edges
  const hasAllIds = ctx.includes('"all_ids"');
  const hasContent = ctx.includes('"content"');
  const hasRowId = ctx.includes('"row_id"');
  const hasEntityType = ctx.includes('"entity_type"');
  const hasTofu = ctx.includes('tofu_unified_table');
  
  // Extract the JSON structure around edges
  // Find the parent object that contains edges
  let braceStart = edgesPos;
  let depth = 0;
  for (let i = edgesPos; i >= Math.max(0, edgesPos - 1000); i--) {
    if (html[i] === '}') depth++;
    if (html[i] === '{') {
      if (depth === 0) { braceStart = i; break; }
      depth--;
    }
  }
  
  const parentCtx = html.slice(braceStart, braceStart + 500).replace(/</g, '');
  
  // Also check for renderer/cellValue pattern (tofu response format)
  const hasRenderer = ctx.includes('"renderer"');
  const hasCellValue = ctx.includes('"cellValue"');
  
  return JSON.stringify({
    edgesPos,
    hasAllIds,
    hasContent,
    hasRowId,
    hasEntityType,
    hasTofu,
    hasRenderer,
    parentCtx: parentCtx.slice(0, 400),
    edgesCtx: ctx.slice(0, 500).replace(/</g, '')
  });
})()
