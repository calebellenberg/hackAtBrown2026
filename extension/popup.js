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

// ==================== Camera (browser getUserMedia) + Persage vitals ====================
const VITALS_URL = 'http://localhost:8766/vitals';
const POLL_MS = 1500;

const popupCam = document.getElementById('popup-cam');
const popupHeart = document.getElementById('popup-heart');
const popupBreath = document.getElementById('popup-breath');
const vitalsStatus = document.getElementById('vitals-status');

if (popupCam) {
  navigator.mediaDevices.getUserMedia({ video: true })
    .then(function (stream) {
      popupCam.srcObject = stream;
    })
    .catch(function (err) {
      console.error('Popup camera:', err);
      if (vitalsStatus) vitalsStatus.textContent = 'Camera: allow access when prompted';
    });
}

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
  if (document.hidden) {
    if (vitalsPollTimer) clearInterval(vitalsPollTimer);
    if (popupCam && popupCam.srcObject) {
      popupCam.srcObject.getTracks().forEach(function (t) { t.stop(); });
    }
  }
});

