// Setup button - opens camera page
const setupBtn = document.getElementById('setup-btn');
if (setupBtn) {
  setupBtn.addEventListener('click', () => {
    chrome.tabs.create({ url: 'camera.html' });
  });
}

// Price display functionality
const getPriceButton = document.getElementById('get-price');
const priceDisplay = document.getElementById('price');

// Tracker stats functionality
const getStatsButton = document.getElementById('get-stats');
const statsDisplay = document.getElementById('stats');
const timeOnSiteDisplay = document.getElementById('time-on-site');
const cartClicksDisplay = document.getElementById('cart-clicks');
const cartRateDisplay = document.getElementById('cart-rate');
const ttcDisplay = document.getElementById('ttc');
const lastPriceDisplay = document.getElementById('last-price');

if (getStatsButton && statsDisplay) {
  getStatsButton.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      statsDisplay.style.display = 'block';
      cartClicksDisplay.textContent = 'No active tab';
      return;
    }

    chrome.tabs.sendMessage(tab.id, { type: 'GET_TRACKER_SUMMARY' }, (resp) => {
      if (chrome.runtime.lastError || !resp) {
        statsDisplay.style.display = 'block';
        timeOnSiteDisplay.textContent = 'Not available';
        cartClicksDisplay.textContent = 'Not available';
        cartRateDisplay.textContent = '—';
        ttcDisplay.textContent = '—';
        lastPriceDisplay.textContent = '—';
        return;
      }

      // Format time on site nicely
      function formatTime(seconds) {
        if (seconds == null) return '—';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (mins === 0) return `${secs}s`;
        if (mins < 60) return `${mins}m ${secs}s`;
        const hours = Math.floor(mins / 60);
        const remainingMins = mins % 60;
        return `${hours}h ${remainingMins}m ${secs}s`;
      }

      statsDisplay.style.display = 'block';
      timeOnSiteDisplay.textContent = formatTime(resp.timeOnSite);
      cartClicksDisplay.textContent = resp.cartClickCount ?? 0;
      cartRateDisplay.textContent = resp.cartClickRate != null ? resp.cartClickRate.toFixed(2) : '0.00';
      ttcDisplay.textContent = resp.ttc != null ? `${resp.ttc.toFixed(2)}s` : 'Not recorded';
      
      if (resp.price && resp.price.value) {
        lastPriceDisplay.textContent = `$${resp.price.value.toFixed(2)}`;
      } else if (resp.price && resp.price.raw) {
        lastPriceDisplay.textContent = resp.price.raw;
      } else {
        lastPriceDisplay.textContent = 'Not recorded';
      }
    });
  });
}

if (getPriceButton && priceDisplay) {
  getPriceButton.addEventListener('click', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      priceDisplay.textContent = 'No active tab';
      return;
    }

    const tabId = tab.id;

    function showResult(resp) {
      const display = resp?.price ?? 'Not found';
      const value = resp?.value;
      priceDisplay.textContent = value != null ? `$${value.toFixed(2)}` : display;
    }

    chrome.tabs.sendMessage(tabId, { type: 'GET_PRICE' }, async (resp) => {
      if (chrome.runtime.lastError) {
        // Try to inject the content script, then retry
        priceDisplay.textContent = 'Injecting helper script...';
        try {
          await chrome.scripting.executeScript({
            target: { tabId: tabId },
            files: ['content.js']
          });
        } catch (err) {
          const msg = err?.message || (chrome.runtime.lastError && chrome.runtime.lastError.message) || 'unknown error';
          console.error('scripting.executeScript failed:', err, chrome.runtime.lastError);
          priceDisplay.textContent = `Failed to inject: ${msg}`;
          return;
        }

        // Small delay to allow content script to register its listener
        setTimeout(() => {
          chrome.tabs.sendMessage(tabId, { type: 'GET_PRICE' }, (resp2) => {
            if (chrome.runtime.lastError) {
              const msg = chrome.runtime.lastError.message || 'Content script still not responding';
              console.error('sendMessage after inject error:', chrome.runtime.lastError);
              priceDisplay.textContent = msg;
              return;
            }
            showResult(resp2);
          });
        }, 300);
        return;
      }
      showResult(resp);
    });
  });
}