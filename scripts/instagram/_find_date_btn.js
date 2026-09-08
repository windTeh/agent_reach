(async () => {
  await new Promise(r => setTimeout(r, 2000));
  
  // Find all buttons and their text
  const buttons = Array.from(document.querySelectorAll('div[role=button]'));
  const btnTexts = buttons.map(b => ({
    text: (b.innerText || '').trim().slice(0, 80),
    ariaLabel: b.getAttribute('aria-label') || ''
  })).filter(b => b.text.length > 0 && b.text.length < 80);
  
  // Look for date-related buttons
  const dateButtons = btnTexts.filter(b => 
    b.text.includes('days') || b.text.includes('Last') || 
    b.text.includes('date') || b.text.includes('Date') ||
    b.text.includes('202') || b.text.includes('Custom') ||
    b.text.includes('week') || b.text.includes('month')
  );
  
  // Also check for select elements or combobox
  const selects = document.querySelectorAll('[role=combobox], [role=listbox], select');
  const selectInfo = Array.from(selects).map(s => ({
    role: s.getAttribute('role'),
    text: (s.innerText || '').slice(0, 100),
    ariaLabel: s.getAttribute('aria-label') || ''
  }));
  
  return JSON.stringify({
    totalButtons: buttons.length,
    dateButtons: dateButtons.slice(0, 10),
    selects: selectInfo.slice(0, 5),
    allBtnTexts: btnTexts.slice(0, 30)
  });
})()
