<<<<<<< HEAD
document.addEventListener('DOMContentLoaded', () => {
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
});
=======
// ==================== Preferences Management ====================
const PREFS_KEY = 'stop_shopping_preferences';

// DOM elements for preferences
const prefsSetup = document.getElementById('prefs-setup');
const prefsDisplay = document.getElementById('prefs-display');
const mainContent = document.getElementById('main-content');

const budgetInput = document.getElementById('budget');
const thresholdInput = document.getElementById('threshold');
const sensitivitySelect = document.getElementById('sensitivity');
const savePrefsBtn = document.getElementById('save-prefs-btn');
const editPrefsBtn = document.getElementById('edit-prefs-btn');

const displayBudget = document.getElementById('display-budget');
const displayThreshold = document.getElementById('display-threshold');
const displaySensitivity = document.getElementById('display-sensitivity');

// Load preferences from localStorage
function loadPreferences() {
  try {
    const saved = localStorage.getItem(PREFS_KEY);
    return saved ? JSON.parse(saved) : null;
  } catch (e) {
    console.error('Failed to load preferences:', e);
    return null;
  }
}

// Save preferences to localStorage
function savePreferences(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    return true;
  } catch (e) {
    console.error('Failed to save preferences:', e);
    return false;
  }
}

// Format sensitivity for display
function formatSensitivity(value) {
  const labels = {
    'low': 'Low',
    'medium': 'Medium',
    'high': 'High'
  };
  return labels[value] || value;
}

// Show the setup form (for first-time or editing)
function showSetupForm(prefs = null) {
  prefsSetup.classList.remove('hidden');
  prefsDisplay.classList.add('hidden');
  mainContent.classList.add('hidden');
  
  // Pre-fill with existing values if editing
  if (prefs) {
    budgetInput.value = prefs.budget || '';
    thresholdInput.value = prefs.threshold || '';
    sensitivitySelect.value = prefs.sensitivity || 'medium';
  }
}

// Show the main UI with preferences display
function showMainUI(prefs) {
  prefsSetup.classList.add('hidden');
  prefsDisplay.classList.remove('hidden');
  mainContent.classList.remove('hidden');
  
  // Update display values
  displayBudget.textContent = prefs.budget ? `$${prefs.budget}` : 'Not set';
  displayThreshold.textContent = prefs.threshold ? `$${prefs.threshold}` : 'Not set';
  displaySensitivity.textContent = formatSensitivity(prefs.sensitivity);
}

// Initialize preferences UI
function initPreferences() {
  const prefs = loadPreferences();
  
  if (!prefs) {
    // First-time user - show setup form
    showSetupForm();
  } else {
    // Returning user - show main UI
    showMainUI(prefs);
  }
}

// Save button handler
if (savePrefsBtn) {
  savePrefsBtn.addEventListener('click', () => {
    const budget = parseFloat(budgetInput.value) || 0;
    const threshold = parseFloat(thresholdInput.value) || 0;
    const sensitivity = sensitivitySelect.value;
    
    if (budget <= 0 && threshold <= 0) {
      alert('Please enter at least a budget or a large purchase threshold.');
      return;
    }
    
    const prefs = { budget, threshold, sensitivity };
    
    if (savePreferences(prefs)) {
      showMainUI(prefs);
    } else {
      alert('Failed to save preferences. Please try again.');
    }
  });
}

// Edit button handler
if (editPrefsBtn) {
  editPrefsBtn.addEventListener('click', () => {
    const prefs = loadPreferences();
    showSetupForm(prefs);
  });
}

// Initialize on load
initPreferences();

>>>>>>> 4dd1cdc (data json)
