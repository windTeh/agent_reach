(async () => {
  // Find and click the time range selector
  const buttons = Array.from(document.querySelectorAll('div[role=button]'));
  const timeBtn = buttons.find(b => {
    const t = b.innerText || '';
    return t.includes('Last') && t.includes('days');
  });
  
  if (!timeBtn) {
    // Try other patterns
    const timeBtn2 = buttons.find(b => {
      const t = b.innerText || '';
      return t.includes('days') || t.includes('month') || t.includes('90');
    });
    if (timeBtn2) {
      timeBtn2.click();
      return JSON.stringify({clicked: true, text: timeBtn2.innerText.slice(0, 80)});
    }
    return JSON.stringify({clicked: false, msg: 'no time button found', 
      buttons: buttons.map(b => b.innerText.slice(0, 40)).filter(t => t.length > 0).slice(0, 20)});
  }
  
  timeBtn.click();
  return JSON.stringify({clicked: true, text: timeBtn.innerText.slice(0, 80)});
})()
