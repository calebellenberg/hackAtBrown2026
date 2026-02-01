// ==================== Preferences Management ====================
const PREFS_KEY = 'stop_shopping_preferences';
const BACKEND_URL = 'http://localhost:8000';

// DOM elements for preferences
const prefsSetup = document.getElementById('prefs-setup');
const prefsDisplay = document.getElementById('prefs-display');
const mainContent = document.getElementById('main-content');
const dangerZone = document.getElementById('danger-zone');
const statusMsg = document.getElementById('status-msg');

const budgetInput = document.getElementById('budget');
const thresholdInput = document.getElementById('threshold');
const sensitivitySelect = document.getElementById('sensitivity');
const financialGoalsInput = document.getElementById('financial-goals');
const savePrefsBtn = document.getElementById('save-prefs-btn');
const editPrefsBtn = document.getElementById('edit-prefs-btn');
const resetMemoryBtn = document.getElementById('reset-memory-btn');

const displayBudget = document.getElementById('display-budget');
const displayThreshold = document.getElementById('display-threshold');
const displaySensitivity = document.getElementById('display-sensitivity');
const displayGoals = document.getElementById('display-goals');
const displayGoalsContainer = document.getElementById('display-goals-container');

// ==================== Status Message Helpers ====================
function showStatus(message, type = 'loading') {
  if (statusMsg) {
    statusMsg.textContent = message;
    statusMsg.className = `status-msg ${type}`;
  }
}

function hideStatus() {
  if (statusMsg) {
    statusMsg.className = 'status-msg';
    statusMsg.textContent = '';
  }
}

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
  if (dangerZone) dangerZone.classList.add('hidden');
  hideStatus();
  
  // Pre-fill with existing values if editing
  if (prefs) {
    budgetInput.value = prefs.budget || '';
    thresholdInput.value = prefs.threshold || '';
    sensitivitySelect.value = prefs.sensitivity || 'medium';
    financialGoalsInput.value = prefs.financialGoals || '';
  }
}

// Show the main UI with preferences display
function showMainUI(prefs) {
  prefsSetup.classList.add('hidden');
  prefsDisplay.classList.remove('hidden');
  mainContent.classList.remove('hidden');
  if (dangerZone) dangerZone.classList.remove('hidden');
  hideStatus();
  
  // Update display values
  displayBudget.textContent = prefs.budget ? `$${prefs.budget}` : 'Not set';
  displayThreshold.textContent = prefs.threshold ? `$${prefs.threshold}` : 'Not set';
  displaySensitivity.textContent = formatSensitivity(prefs.sensitivity);
  
  // Display financial goals if provided
  if (prefs.financialGoals && prefs.financialGoals.trim()) {
    displayGoals.textContent = prefs.financialGoals;
    displayGoalsContainer.style.display = 'block';
  } else {
    displayGoalsContainer.style.display = 'none';
  }
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
  savePrefsBtn.addEventListener('click', async () => {
    const budget = parseFloat(budgetInput.value) || 0;
    const threshold = parseFloat(thresholdInput.value) || 0;
    const sensitivity = sensitivitySelect.value;
    const financialGoals = financialGoalsInput.value.trim();
    
    if (budget <= 0 && threshold <= 0) {
      alert('Please enter at least a budget or a large purchase threshold.');
      return;
    }
    
    const prefs = { budget, threshold, sensitivity, financialGoals };
    
    // Disable button during save
    savePrefsBtn.disabled = true;
    savePrefsBtn.textContent = 'Saving...';
    
    try {
      // Save to localStorage first
      if (savePreferences(prefs)) {
        // Show main UI immediately
        showMainUI(prefs);
        
        // Then sync to backend (non-blocking for UI)
        await syncPreferencesToBackend(prefs);
      } else {
        alert('Failed to save preferences. Please try again.');
      }
    } finally {
      savePrefsBtn.disabled = false;
      savePrefsBtn.textContent = 'Save Preferences';
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

// ==================== Backend API Integration ====================

// Sync preferences to backend memory files
async function syncPreferencesToBackend(prefs) {
  try {
    showStatus('Syncing to memory...', 'loading');
    
    const response = await fetch(`${BACKEND_URL}/update-preferences`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        budget: prefs.budget,
        threshold: prefs.threshold,
        sensitivity: prefs.sensitivity,
        financial_goals: prefs.financialGoals || ''
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const result = await response.json();
    console.log('[Popup] Preferences synced to backend:', result);
    showStatus('Preferences saved to memory!', 'success');
    
    // Hide success message after 2 seconds
    setTimeout(hideStatus, 2000);
    
    return true;
  } catch (error) {
    console.error('[Popup] Failed to sync preferences to backend:', error);
    showStatus('Saved locally (backend unavailable)', 'error');
    
    // Hide error message after 3 seconds
    setTimeout(hideStatus, 3000);
    
    return false;
  }
}

// Reset all memory files to template state
async function resetMemoryOnBackend() {
  try {
    showStatus('Resetting memory...', 'loading');
    
    const response = await fetch(`${BACKEND_URL}/reset-memory`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const result = await response.json();
    console.log('[Popup] Memory reset on backend:', result);
    
    return true;
  } catch (error) {
    console.error('[Popup] Failed to reset memory on backend:', error);
    showStatus('Failed to reset memory. Is the backend running?', 'error');
    
    return false;
  }
}

// Reset Memory button handler
if (resetMemoryBtn) {
  resetMemoryBtn.addEventListener('click', async () => {
    // First confirmation
    const firstConfirm = confirm(
      'Are you sure you want to reset all memory?\n\n' +
      'This will erase:\n' +
      '• All your preferences\n' +
      '• Spending history\n' +
      '• Behavioral patterns\n' +
      '• Goals and budget limits\n\n' +
      'This action cannot be undone.'
    );
    
    if (!firstConfirm) {
      return;
    }
    
    // Second confirmation for extra safety
    const secondConfirm = confirm(
      '⚠️ FINAL WARNING ⚠️\n\n' +
      'Are you ABSOLUTELY sure?\n\n' +
      'All your data will be permanently erased.'
    );
    
    if (!secondConfirm) {
      return;
    }
    
    // Disable button during reset
    resetMemoryBtn.disabled = true;
    resetMemoryBtn.textContent = 'Resetting...';
    
    try {
      // Reset backend memory
      const backendSuccess = await resetMemoryOnBackend();
      
      // Clear localStorage preferences
      localStorage.removeItem(PREFS_KEY);
      
      // Clear any other extension storage
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        chrome.storage.local.clear(() => {
          console.log('[Popup] Chrome storage cleared');
        });
      }
      
      if (backendSuccess) {
        showStatus('Memory reset successfully!', 'success');
      }
      
      // Show setup form after a brief delay
      setTimeout(() => {
        hideStatus();
        showSetupForm();
        resetMemoryBtn.disabled = false;
        resetMemoryBtn.textContent = 'Reset All Memory';
      }, 1500);
      
    } catch (error) {
      console.error('[Popup] Error during reset:', error);
      showStatus('Error during reset. Please try again.', 'error');
      resetMemoryBtn.disabled = false;
      resetMemoryBtn.textContent = 'Reset All Memory';
    }
  });
}

// Initialize on load
initPreferences();

// ==================== Persage vitals (from broker) ====================
const VITALS_URL = 'http://localhost:8766/vitals';
const POLL_MS = 1500;

const popupHeart = document.getElementById('popup-heart');
const popupBreath = document.getElementById('popup-breath');
const vitalsStatus = document.getElementById('vitals-status');

var vitalsPollTimer = null;
function pollVitals() {
  if (!popupHeart || !popupBreath || !vitalsStatus) return;
  fetch(VITALS_URL)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var hr = data.heart_rate;
      var br = data.respiration_rate;
      popupHeart.textContent = (hr != null && hr > 0) ? Math.round(hr) : '--';
      popupBreath.textContent = (br != null && br > 0) ? Math.round(br) : '--';
      vitalsStatus.textContent = 'Vitals: live';
      vitalsStatus.className = 'vitals-status connected';
    })
    .catch(function () {
      popupHeart.textContent = '--';
      popupBreath.textContent = '--';
      vitalsStatus.textContent = 'Vitals: start broker (port 8766) for live data';
      vitalsStatus.className = 'vitals-status disconnected';
    });
}

pollVitals();
vitalsPollTimer = setInterval(pollVitals, POLL_MS);

document.addEventListener('visibilitychange', function () {
  if (document.hidden && vitalsPollTimer) clearInterval(vitalsPollTimer);
});

