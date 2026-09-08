(async () => {
  const results = {};
  const videos = document.querySelectorAll('video');
  results.videoCount = videos.length;
  results.videoInfo = [];
  for (const v of videos) {
    results.videoInfo.push({
      src: (v.src || v.currentSrc || '').slice(0, 200),
      duration: v.duration,
      readyState: v.readyState
    });
  }
  const html = document.documentElement.outerHTML;
  const allDurMatches = [];
  const re = /"duration[^"]*":\s*([^\s,}\]]+)/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    allDurMatches.push({
      full: m[0],
      val: m[1],
      ctx: html.slice(Math.max(0, m.index - 50), m.index).replace(/</g, '').slice(-80)
    });
  }
  results.allDurMatches = allDurMatches.slice(0, 15);
  results.totalDurMatches = allDurMatches.length;
  return JSON.stringify(results);
})()
