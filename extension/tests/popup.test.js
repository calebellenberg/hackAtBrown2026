/**
 * Unit tests for popup.js functions.
 *
 * Tests loadPreferences, savePreferences, formatSensitivity,
 * and DOM state toggling (showSetupForm/showMainUI).
 */

// ── Extracted functions from popup.js ──────────────────────────────────

const PREFS_KEY = 'stop_shopping_preferences';

function loadPreferences() {
  try {
    const saved = localStorage.getItem(PREFS_KEY);
    return saved ? JSON.parse(saved) : null;
  } catch (e) {
    return null;
  }
}

function savePreferences(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    return true;
  } catch (e) {
    return false;
  }
}

function formatSensitivity(value) {
  const labels = {
    'low': 'Low',
    'medium': 'Medium',
    'high': 'High'
  };
  return labels[value] || value;
}


// ════════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════════

describe('loadPreferences', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('returns null when no preferences saved', () => {
    expect(loadPreferences()).toBeNull();
  });

  test('returns saved preferences', () => {
    const prefs = { budget: 500, threshold: 100, sensitivity: 'high' };
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    expect(loadPreferences()).toEqual(prefs);
  });

  test('returns null for corrupt JSON', () => {
    localStorage.setItem(PREFS_KEY, 'not valid json{{{');
    expect(loadPreferences()).toBeNull();
  });
});


describe('savePreferences', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test('saves and retrieves roundtrip', () => {
    const prefs = { budget: 300, threshold: 50, sensitivity: 'medium' };
    expect(savePreferences(prefs)).toBe(true);
    expect(loadPreferences()).toEqual(prefs);
  });

  test('overwrites existing preferences', () => {
    savePreferences({ budget: 100 });
    savePreferences({ budget: 200 });
    expect(loadPreferences().budget).toBe(200);
  });
});


describe('formatSensitivity', () => {
  test('formats low', () => {
    expect(formatSensitivity('low')).toBe('Low');
  });

  test('formats medium', () => {
    expect(formatSensitivity('medium')).toBe('Medium');
  });

  test('formats high', () => {
    expect(formatSensitivity('high')).toBe('High');
  });

  test('returns raw value for unknown', () => {
    expect(formatSensitivity('extreme')).toBe('extreme');
  });

  test('returns undefined for undefined', () => {
    expect(formatSensitivity(undefined)).toBeUndefined();
  });
});


describe('DOM state: showSetupForm / showMainUI', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="prefs-setup" class="hidden"></div>
      <div id="prefs-display"></div>
      <div id="main-content"></div>
      <div id="danger-zone"></div>
      <div id="status-msg"></div>
      <span id="display-budget"></span>
      <span id="display-threshold"></span>
      <span id="display-sensitivity"></span>
      <span id="display-goals"></span>
      <div id="display-goals-container"></div>
    `;
  });

  function showSetupForm(prefs = null) {
    document.getElementById('prefs-setup').classList.remove('hidden');
    document.getElementById('prefs-display').classList.add('hidden');
    document.getElementById('main-content').classList.add('hidden');
    const dz = document.getElementById('danger-zone');
    if (dz) dz.classList.add('hidden');
  }

  function showMainUI(prefs) {
    document.getElementById('prefs-setup').classList.add('hidden');
    document.getElementById('prefs-display').classList.remove('hidden');
    document.getElementById('main-content').classList.remove('hidden');
    const dz = document.getElementById('danger-zone');
    if (dz) dz.classList.remove('hidden');

    document.getElementById('display-budget').textContent = prefs.budget ? `$${prefs.budget}` : 'Not set';
    document.getElementById('display-threshold').textContent = prefs.threshold ? `$${prefs.threshold}` : 'Not set';
    document.getElementById('display-sensitivity').textContent = formatSensitivity(prefs.sensitivity);
  }

  test('showSetupForm makes setup visible and hides main', () => {
    showSetupForm();
    expect(document.getElementById('prefs-setup').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('prefs-display').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('main-content').classList.contains('hidden')).toBe(true);
  });

  test('showMainUI hides setup and shows main with values', () => {
    showMainUI({ budget: 500, threshold: 100, sensitivity: 'high' });
    expect(document.getElementById('prefs-setup').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('prefs-display').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('display-budget').textContent).toBe('$500');
    expect(document.getElementById('display-threshold').textContent).toBe('$100');
    expect(document.getElementById('display-sensitivity').textContent).toBe('High');
  });

  test('showSetupForm → showMainUI toggle works', () => {
    showSetupForm();
    expect(document.getElementById('prefs-setup').classList.contains('hidden')).toBe(false);

    showMainUI({ budget: 300, threshold: 50, sensitivity: 'low' });
    expect(document.getElementById('prefs-setup').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('main-content').classList.contains('hidden')).toBe(false);
  });
});


describe('initPreferences logic', () => {
  beforeEach(() => {
    localStorage.clear();
    document.body.innerHTML = `
      <div id="prefs-setup" class="hidden"></div>
      <div id="prefs-display"></div>
      <div id="main-content"></div>
      <div id="danger-zone"></div>
      <span id="display-budget"></span>
      <span id="display-threshold"></span>
      <span id="display-sensitivity"></span>
      <span id="display-goals"></span>
      <div id="display-goals-container"></div>
    `;
  });

  test('no stored prefs shows setup form', () => {
    // Simulate initPreferences logic
    const prefs = loadPreferences();
    if (!prefs) {
      document.getElementById('prefs-setup').classList.remove('hidden');
      document.getElementById('prefs-display').classList.add('hidden');
    }
    expect(document.getElementById('prefs-setup').classList.contains('hidden')).toBe(false);
  });

  test('stored prefs shows main UI', () => {
    savePreferences({ budget: 500, threshold: 100, sensitivity: 'medium' });
    const prefs = loadPreferences();
    if (prefs) {
      document.getElementById('prefs-setup').classList.add('hidden');
      document.getElementById('main-content').classList.remove('hidden');
    }
    expect(document.getElementById('prefs-setup').classList.contains('hidden')).toBe(true);
  });
});
