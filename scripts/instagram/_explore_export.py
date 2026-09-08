"""Explore the Export data functionality on archive_stories page."""
import sys, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval

S = 'dqg7tk9s'

# Check current URL
out, _, _ = browser_eval(S, "location.href", timeout=15)
print('Current URL:', out)

# Check if we're on archive_stories
if 'archive_stories' not in out:
    print('Not on archive_stories page!')
    sys.exit(1)

# Step 1: Find and click the "Export data" button
js_find = """
(() => {
  const btns = Array.from(document.querySelectorAll('[role=button], button'));
  const exportBtn = btns.find(el => {
    const t = (el.textContent || '').trim();
    return t === 'Export data' || t.startsWith('Export data');
  });
  if (exportBtn) {
    return JSON.stringify({found: true, text: exportBtn.textContent.trim().slice(0, 50)});
  }
  // Try broader search
  const allBtns = btns.map(el => (el.textContent || '').trim()).filter(t => t.length > 0 && t.length < 50);
  return JSON.stringify({found: false, availableButtons: allBtns.slice(0, 20)});
})()
"""
out, _, _ = browser_eval(S, js_find, timeout=10)
print('Export button:', out)

# Step 2: Click the Export data button
js_click = """
(() => {
  const btns = Array.from(document.querySelectorAll('[role=button], button'));
  const exportBtn = btns.find(el => {
    const t = (el.textContent || '').trim();
    return t === 'Export data' || t.startsWith('Export data');
  });
  if (exportBtn) {
    exportBtn.click();
    return 'clicked';
  }
  return 'not found';
})()
"""
out, _, _ = browser_eval(S, js_click, timeout=10)
print('Click export:', out)

# Step 3: Wait for dialog/modal to appear
time.sleep(3)

# Step 4: Check what dialog/options appeared
js_dialog = """
(() => {
  // Look for modal/dialog
  const dialogs = document.querySelectorAll('[role=dialog], [role=alertdialog], [class*=modal], [class*=Modal], [class*=dialog], [class*=Dialog]');
  const result = {dialogCount: dialogs.length};
  
  if (dialogs.length) {
    const d = dialogs[0];
    result.dialogText = (d.textContent || '').slice(0, 1000);
    // Find buttons in dialog
    const btns = Array.from(d.querySelectorAll('[role=button], button, a')).map(el => ({
      text: (el.textContent || '').trim().slice(0, 50),
      role: el.getAttribute('role'),
    })).filter(b => b.text);
    result.dialogButtons = btns.slice(0, 10);
    // Find select/dropdown options
    const selects = Array.from(d.querySelectorAll('select, [role=listbox], [role=combobox]'));
    result.selectCount = selects.length;
    // Find radio/checkbox
    const radios = Array.from(d.querySelectorAll('input[type=radio], [role=radio]')).map(el => ({
      name: el.name || '',
      value: el.value || '',
      checked: el.checked || el.getAttribute('aria-checked') === 'true',
      label: (el.parentElement || {}).textContent || '',
    })).slice(0, 10);
    result.radios = radios;
  }
  
  // Also check for any new overlay/popover
  const overlays = document.querySelectorAll('[class*=overlay], [class*=Overlay], [class*=popover], [class*=Popover]');
  result.overlayCount = overlays.length;
  if (overlays.length) {
    result.overlayText = (overlays[0].textContent || '').slice(0, 500);
  }
  
  return JSON.stringify(result);
})()
"""
out, _, _ = browser_eval(S, js_dialog, timeout=15)
# Write to file for readability
path = os.path.join(SCRIPT_DIR, '_export_dialog.json')
with open(path, 'w', encoding='utf-8') as f:
    f.write(out)
print(f'Dialog info written to {path}')
