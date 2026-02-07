/**
 * Unit tests for tracker.js functions.
 *
 * Since tracker.js wraps everything in an IIFE, we extract the key
 * functions for testing.
 */

// ── Extracted functions from tracker.js ────────────────────────────────

function isAddToCartElement(el) {
  if (!el || el.nodeType !== 1) return false;

  const tag = el.tagName.toLowerCase();
  const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
  const id = el.getAttribute('id') || '';
  const cls = el.getAttribute('class') || '';
  const attrStr = (id + ' ' + cls).toLowerCase();

  const addPhrases = [
    'add to cart', 'add to bag', 'add to basket', 'add to trolley', 'buy now',
    'buy it now', 'place order', 'place your order', 'complete purchase',
    'proceed to checkout', 'checkout now', 'order now', 'purchase now',
    'subscribe & save', 'preorder', 'pre-order', 'reserve now', 'add to order'
  ];

  if (addPhrases.some(p => text.includes(p))) return true;
  if (/(add_to_cart|addtocart|add-to-cart|btn-add|add-to-basket|add-to-bag|buy-now|buynow|buy_now|checkout|place-order|place_order)/i.test(attrStr)) return true;

  if (tag === 'input' && (el.type === 'submit' || el.type === 'button') && addPhrases.some(p => (el.value || '').toLowerCase().includes(p))) return true;

  return false;
}

// Chrome storage shim (from tracker.js)
function createStorageShim() {
  const SHIM_KEY = 'test_chrome_storage_shim';
  function readStore() {
    try {
      const raw = localStorage.getItem(SHIM_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }
  function writeStore(obj) {
    try { localStorage.setItem(SHIM_KEY, JSON.stringify(obj)); } catch (e) {}
  }

  return {
    get: function(keys, callback) {
      const store = readStore();
      const out = {};
      if (typeof keys === 'string') {
        out[keys] = store[keys];
      } else if (Array.isArray(keys)) {
        for (const k of keys) out[k] = store[k];
      }
      setTimeout(() => callback(out), 0);
    },
    set: function(items, callback) {
      const store = readStore();
      for (const k of Object.keys(items)) store[k] = items[k];
      writeStore(store);
      setTimeout(() => { if (callback) callback(); }, 0);
    },
    remove: function(keys, callback) {
      const store = readStore();
      if (typeof keys === 'string') delete store[keys];
      else if (Array.isArray(keys)) keys.forEach(k => delete store[k]);
      writeStore(store);
      setTimeout(() => { if (callback) callback(); }, 0);
    },
    _readStore: readStore,
    _SHIM_KEY: SHIM_KEY,
  };
}

// State save/restore (simplified from tracker.js)
function createStateManager() {
  const STATE_KEY = 'test_tracker_state';

  let state = {
    clickCount: 0,
    peakScrollVelocity: 0,
    cartClickCount: 0,
  };

  return {
    getState: () => ({ ...state }),
    saveState: () => {
      sessionStorage.setItem(STATE_KEY, JSON.stringify(state));
    },
    restoreState: () => {
      const raw = sessionStorage.getItem(STATE_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        Object.assign(state, saved);
      }
    },
    update: (updates) => {
      Object.assign(state, updates);
    },
  };
}


// ════════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════════

describe('isAddToCartElement', () => {
  test('matches button with "Add to Cart" text', () => {
    const btn = document.createElement('button');
    btn.innerText = 'Add to Cart';
    expect(isAddToCartElement(btn)).toBe(true);
  });

  test('matches button with cart class', () => {
    const btn = document.createElement('button');
    btn.className = 'add-to-cart-button primary';
    btn.innerText = 'Continue';
    expect(isAddToCartElement(btn)).toBe(true);
  });

  test('does not match generic button', () => {
    const btn = document.createElement('button');
    btn.innerText = 'Learn More';
    expect(isAddToCartElement(btn)).toBe(false);
  });

  test('does not match null', () => {
    expect(isAddToCartElement(null)).toBe(false);
  });

  test('does not match text node (nodeType 3)', () => {
    const textNode = document.createTextNode('Add to Cart');
    expect(isAddToCartElement(textNode)).toBe(false);
  });

  test('matches input with matching value', () => {
    const input = document.createElement('input');
    input.type = 'submit';
    input.value = 'Add to Cart';
    expect(isAddToCartElement(input)).toBe(true);
  });

  test('matches Buy Now button', () => {
    const btn = document.createElement('button');
    btn.innerText = 'Buy Now';
    expect(isAddToCartElement(btn)).toBe(true);
  });

  test('matches checkout button via class', () => {
    const btn = document.createElement('button');
    btn.id = 'checkout-btn';
    btn.innerText = 'Submit';
    expect(isAddToCartElement(btn)).toBe(true);
  });
});


describe('Chrome storage shim', () => {
  let shim;

  beforeEach(() => {
    localStorage.clear();
    shim = createStorageShim();
  });

  test('set and get roundtrip', (done) => {
    shim.set({ testKey: 'testValue' }, () => {
      shim.get('testKey', (result) => {
        expect(result.testKey).toBe('testValue');
        done();
      });
    });
  });

  test('remove deletes key', (done) => {
    shim.set({ toRemove: 'value' }, () => {
      shim.remove('toRemove', () => {
        shim.get('toRemove', (result) => {
          expect(result.toRemove).toBeUndefined();
          done();
        });
      });
    });
  });

  test('array keys in get', (done) => {
    shim.set({ a: 1, b: 2, c: 3 }, () => {
      shim.get(['a', 'b'], (result) => {
        expect(result.a).toBe(1);
        expect(result.b).toBe(2);
        expect(result.c).toBeUndefined();
        done();
      });
    });
  });
});


describe('Tracker state save/restore', () => {
  let manager;

  beforeEach(() => {
    sessionStorage.clear();
    manager = createStateManager();
  });

  test('save and restore roundtrip', () => {
    manager.update({ clickCount: 42, peakScrollVelocity: 1500.5 });
    manager.saveState();

    // Create new manager to simulate page reload
    const manager2 = createStateManager();
    manager2.restoreState();
    const state = manager2.getState();
    expect(state.clickCount).toBe(42);
    expect(state.peakScrollVelocity).toBe(1500.5);
  });

  test('restore with no saved state keeps defaults', () => {
    manager.restoreState();
    const state = manager.getState();
    expect(state.clickCount).toBe(0);
    expect(state.peakScrollVelocity).toBe(0);
  });
});
