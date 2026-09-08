(async () => {
  // Search for duration data in the page's internal HTML/scripts
  const html = document.body.innerHTML;
  const matches = [];
  const re = /duration[^\"]*":\s*(\d+)/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    matches.push({
      val: m[1],
      ctx: html.slice(Math.max(0, m.index - 80), m.index + m[0].length + 30).replace(/<[^>]+>/g, '').slice(0, 200)
    });
  }

  // Also search for video_duration, video_length, length_in_seconds etc.
  const re2 = /(?:video_duration|video_length|length_in|clip_length|media_duration)[^\"]*":\s*(\d+)/gi;
  while ((m = re2.exec(html)) !== null) {
    matches.push({
      val: m[1],
      ctx: html.slice(Math.max(0, m.index - 80), m.index + m[0].length + 30).replace(/<[^>]+>/g, '').slice(0, 200)
    });
  }

  // Also search for "26" near "second" or "sec"
  const re3 = /26\s*(?:seconds?|secs?)/gi;
  while ((m = re3.exec(html)) !== null) {
    matches.push({
      val: '26sec',
      ctx: html.slice(Math.max(0, m.index - 80), m.index + m[0].length + 30).replace(/<[^>]+>/g, '').slice(0, 200)
    });
  }

  return JSON.stringify({ count: matches.length, items: matches.slice(0, 15) });
})()
