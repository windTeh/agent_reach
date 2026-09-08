(async () => {
  const html = document.documentElement.outerHTML;
  
  // Find the preloader data for the object insights query
  // The preloader data contains the actual response data
  const preloaderName = 'BizWebInsightsObjectInsightsDeepLinkContainerQuery';
  
  // Search for the preloader data section
  // It's typically in a <script> tag with the preloader name
  const scripts = document.querySelectorAll('script');
  let preloaderScript = null;
  for (const s of scripts) {
    const text = s.textContent || '';
    if (text.includes(preloaderName) && text.length > 1000) {
      preloaderScript = text;
      break;
    }
  }
  
  if (!preloaderScript) {
    // Try to find it in the full HTML
    const idx = html.indexOf('"' + preloaderName + '"');
    if (idx === -1) {
      return JSON.stringify({ found: false, msg: 'preloader not found' });
    }
    // Extract a large window
    const start = Math.max(0, idx - 500);
    const end = Math.min(html.length, idx + 50000);
    preloaderScript = html.slice(start, end);
  }
  
  // Search for duration in the preloader data
  const durMatches = [];
  const re = /"(duration[^"]*|video_duration|video_length|clip_length|media_duration|original_audio_duration)":\s*([^\s,}\]]+)/g;
  let m;
  while ((m = re.exec(preloaderScript)) !== null) {
    durMatches.push({
      key: m[1],
      val: m[2],
      ctx: preloaderScript.slice(Math.max(0, m.index - 60), m.index + m[0].length + 30).slice(0, 200)
    });
  }
  
  // Also search for "26" as a standalone value (the user said duration is 26)
  const val26Matches = [];
  const re2 = /"(\w+)":\s*26[,\s}]/g;
  while ((m = re2.exec(preloaderScript)) !== null) {
    val26Matches.push({
      key: m[1],
      ctx: preloaderScript.slice(Math.max(0, m.index - 40), m.index + m[0].length + 20).slice(0, 150)
    });
  }
  
  // Search for "26000" (26 seconds in ms)
  const val26000Matches = [];
  const re3 = /"(\w+)":\s*26000[,\s}]/g;
  while ((m = re3.exec(preloaderScript)) !== null) {
    val26000Matches.push({
      key: m[1],
      ctx: preloaderScript.slice(Math.max(0, m.index - 40), m.index + m[0].length + 20).slice(0, 150)
    });
  }
  
  return JSON.stringify({
    scriptLen: preloaderScript.length,
    durationMatches: durMatches.slice(0, 10),
    val26Matches: val26Matches.slice(0, 10),
    val26000Matches: val26000Matches.slice(0, 10)
  });
})()
