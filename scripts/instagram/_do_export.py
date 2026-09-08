"""Click Export data, set date range, generate and capture the export request."""
import sys, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from scripts.tmp.content_version.fetch_fb_insights import browser_eval, install_capture_hook

S = 'dqg7tk9s'

# Install hook to capture the export request
install_capture_hook(S)
browser_eval(S, "window.__fbReqBodies = []; 'cleared'", timeout=10)

# Close any existing dialog first
browser_eval(S, """
(() => {
  const closeBtn = Array.from(document.querySelectorAll('[role=dialog] [role=button]')).find(el => (el.textContent||'').trim().startsWith('Close'));
  if (closeBtn) closeBtn.click();
  return 'closed';
})()
""", timeout=10)
time.sleep(1)

# Click Export data again
browser_eval(S, """
(() => {
  const btn = Array.from(document.querySelectorAll('[role=button], button')).find(el => (el.textContent||'').trim() === 'Export data');
  if (btn) { btn.click(); return 'clicked'; }
  return 'not found';
})()
""", timeout=10)
time.sleep(2)

# Try to set date range to a wider range
# First check the date range button text
out, _, _ = browser_eval(S, """
(() => {
  const dialog = document.querySelector('[role=dialog]');
  if (!dialog) return JSON.stringify({error: 'no dialog'});
  
  // Find the date range button
  const dateBtn = Array.from(dialog.querySelectorAll('[role=button]')).find(el => {
    const t = (el.textContent || '').trim();
    return t.includes('2026') || t.includes('2025') || t.includes('Date range');
  });
  
  if (dateBtn) {
    return JSON.stringify({found: true, text: dateBtn.textContent.trim()});
  }
  return JSON.stringify({found: false});
})()
""", timeout=10)
print('Date range button:', out)

# Instead of trying to change the date range via UI (complex),
# let's just click Generate with the current settings and see what request is made
js_generate = """
(() => {
  const dialog = document.querySelector('[role=dialog]');
  if (!dialog) return 'no dialog';
  const genBtn = Array.from(dialog.querySelectorAll('[role=button], button')).find(el => (el.textContent||'').trim() === 'Generate');
  if (genBtn) {
    genBtn.click();
    return 'clicked Generate';
  }
  return 'Generate not found';
})()
"""
out, _, _ = browser_eval(S, js_generate, timeout=10)
print('Generate:', out)

# Wait for the export request to be made
time.sleep(5)

# Check captured requests
out, _, _ = browser_eval(S, """
JSON.stringify({
  count: (window.__fbReqBodies || []).length,
  bodies: (window.__fbReqBodies || []).map(b => {
    const friendlyMatch = b.body.match(/fb_api_req_friendly_name=([^&]+)/);
    const friendly = friendlyMatch ? decodeURIComponent(friendlyMatch[1]) : '';
    const docId = (b.body.match(/doc_id=([^&]+)/) || [])[1];
    return {type: b.t, len: b.len, docId, friendly};
  })
})
""", timeout=10)
print('Captured requests:', out)

# Also check if a download was triggered
# Check for any new downloads or export status
time.sleep(3)
out, _, _ = browser_eval(S, """
(() => {
  // Check if there's an export progress/status dialog
  const dialogs = document.querySelectorAll('[role=dialog]');
  const result = {dialogCount: dialogs.length};
  if (dialogs.length) {
    result.dialogTexts = Array.from(dialogs).map(d => (d.textContent || '').slice(0, 500));
  }
  
  // Check for any notification/toast
  const toasts = document.querySelectorAll('[class*=toast], [class*=Toast], [class*=notification], [class*=Notification]');
  result.toastCount = toasts.length;
  if (toasts.length) {
    result.toastTexts = Array.from(toasts).map(t => (t.textContent || '').slice(0, 200));
  }
  
  return JSON.stringify(result);
})()
""", timeout=10)
print('Status:', out)
