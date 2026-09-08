(async () => {
  await new Promise(r => setTimeout(r, 2000));
  
  // Look for dropdown options
  const menus = document.querySelectorAll('[role=menu], [role=listbox], [role=menuitem], [role=option]');
  const menuItems = [];
  menus.forEach(el => {
    const t = (el.innerText || '').trim();
    if (t && t.length < 100) menuItems.push({
      role: el.getAttribute('role'),
      text: t,
      tag: el.tagName
    });
  });
  
  // Also check for any new overlay/popover
  const overlays = document.querySelectorAll('[data-visualcompletion*="root"], [role=dialog]');
  const overlayTexts = [];
  overlays.forEach(el => {
    const t = (el.innerText || '').slice(0, 200);
    if (t.includes('days') || t.includes('Last') || t.includes('month')) {
      overlayTexts.push(t);
    }
  });
  
  return JSON.stringify({
    menuItems: menuItems.slice(0, 15),
    overlayTexts: overlayTexts.slice(0, 3),
    capturedReqs: window.__capturedReqs || []
  });
})()
