// Service worker proxies backend requests so HTTPS pages can reach HTTP backend (WSL).
// Content scripts are subject to mixed content; extension context is not.
// If your WSL IP changes (e.g. after reboot), run "hostname -I" in WSL and update below.
const BACKEND_URL = 'http://172.26.57.128:8000';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== 'pipeline-analyze') {
    sendResponse({ error: 'Unknown request type' });
    return true;
  }
  fetch(`${BACKEND_URL}/pipeline-analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(msg.body || {})
  })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
    .then(data => sendResponse({ data }))
    .catch(err => sendResponse({ error: err.message || 'Could not connect to backend' }));
  return true; // keep channel open for async sendResponse
});
