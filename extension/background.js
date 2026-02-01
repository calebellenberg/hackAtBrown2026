// Service worker proxies backend requests so HTTPS pages can reach HTTP backend.
// Content scripts are subject to mixed content; extension context is not.
// For macOS/Linux: use localhost. For WSL: use the WSL IP address (run "hostname -I" in WSL).
const BACKEND_URL = 'http://localhost:8000';

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
