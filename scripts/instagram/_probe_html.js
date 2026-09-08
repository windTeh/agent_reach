(async () => {
  // Search for the content_id in the page's HTML to find the embedded data
  const html = document.documentElement.outerHTML;
  const contentId = '18117072050489215';
  const idx = html.indexOf(contentId);
  
  if (idx === -1) {
    return JSON.stringify({ found: false, htmlLen: html.length });
  }
  
  // Extract a large window around the content_id
  const start = Math.max(0, idx - 2000);
  const end = Math.min(html.length, idx + 5000);
  const context = html.slice(start, end);
  
  // Search for duration-related fields in this context
  const durFields = [];
  const re = /"(duration[^"]*|video_duration|video_length|length_in_seconds|clip_duration|media_duration|original_duration)":\s*([^\s,}]+)/g;
  let m;
  while ((m = re.exec(context)) !== null) {
    durFields.push({ key: m[1], val: m[2], pos: m.index });
  }
  
  // Also look for any numeric fields near the content_id
  const numFields = [];
  const re2 = /"(\w+)":\s*(\d{1,6})/g;
  while ((m = re2.exec(context)) !== null) {
    if (parseInt(m[2]) > 0 && parseInt(m[2]) < 100000) {
      numFields.push({ key: m[1], val: m[2], pos: m.index });
    }
  }
  
  return JSON.stringify({
    found: true,
    htmlLen: html.length,
    contentIdPos: idx,
    durationFields: durFields,
    numericFields: numFields.slice(0, 30),
    contextAroundContentId: context.slice(idx - start - 200, idx - start + 500).replace(/</g, '&lt;').slice(0, 2000)
  });
})()
