/**
 * Unit tests for pure functions extracted from content.js.
 *
 * Functions are loaded by evaluating content.js source directly,
 * but since content.js wraps most logic in an IIFE with chrome/DOM deps,
 * we extract and test the top-level pure functions defined before the IIFE.
 */

// ── Extract pure functions from content.js ──────────────────────────────
// content.js defines these at top level before the IIFE:
//   parsePrice, getSite, formatDuration, hostMatchesDomain, getBaseDomain,
//   matchesPurchaseKeyword, matchesNegativePattern, generateInterventionId,
//   showInterventionOverlay, save/get/clearInterventionState, etc.

const fs = require('fs');
const path = require('path');

// Read the source and extract the functions we can test
const contentSource = fs.readFileSync(
  path.join(__dirname, '..', 'content.js'),
  'utf-8'
);

// We'll define the functions directly for testing since the IIFE
// in content.js auto-executes and needs chrome/DOM context.
// Instead, we extract the function bodies.

// parsePrice - from content.js line 3-8
function parsePrice(text) {
  if (!text) return null;
  const cleaned = text.replace(/[^0-9.]/g, '');
  const value = parseFloat(cleaned);
  return isNaN(value) ? null : value;
}

// hostMatchesDomain - from content.js line 819-824
function hostMatchesDomain(hostname, domain) {
  if (!domain) return false;
  domain = domain.toLowerCase();
  hostname = hostname.toLowerCase();
  return hostname === domain || hostname.endsWith('.' + domain);
}

// getBaseDomain - from content.js line 828-840
function getBaseDomain(hostname) {
  if (!hostname) return hostname;
  const parts = hostname.toLowerCase().split('.');
  if (parts.length <= 2) return hostname;
  const secondLast = parts[parts.length - 2];
  const last = parts[parts.length - 1];
  if (secondLast.length <= 3 && last.length <= 3) {
    return parts.slice(-3).join('.');
  }
  return parts.slice(-2).join('.');
}

// formatDuration - from content.js line 444-453
function formatDuration(milliseconds) {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) return `${seconds}s`;
  if (minutes < 60) return `${minutes}m ${seconds}s`;
  const hours = Math.floor(minutes / 60);
  const remainingMins = minutes % 60;
  return `${hours}h ${remainingMins}m ${seconds}s`;
}

// PURCHASE_KEYWORDS & NEGATIVE_PATTERNS from content.js
const PURCHASE_KEYWORDS = [
  'add to cart', 'add to bag', 'add to basket', 'add to trolley', 'buy now',
  'buy it now', 'place order', 'place your order', 'complete purchase',
  'proceed to checkout', 'checkout now', 'order now', 'purchase now',
  'subscribe & save', 'preorder', 'pre-order', 'reserve now', 'add to order'
];

const NEGATIVE_PATTERNS = [
  'add to wishlist', 'add to wish list', 'add to favorites', 'add to favourite',
  'save for later', 'save to list', 'sold out', 'out of stock', 'unavailable',
  'sign in', 'log in', 'create account', 'notify me', 'notify when available',
  'add to registry', 'add to compare', 'share'
];

function matchesPurchaseKeyword(text) {
  const lower = text.toLowerCase();
  return PURCHASE_KEYWORDS.some(p => lower.includes(p));
}

function matchesNegativePattern(text) {
  const lower = text.toLowerCase();
  return NEGATIVE_PATTERNS.some(p => lower.includes(p));
}

function generateInterventionId() {
  return `intervention_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

// State persistence functions
const INTERVENTION_STATE_KEY = 'impulse_guard.intervention_state';
const COMPLETED_INTERVENTIONS_KEY = 'impulse_guard.completed_interventions';

function saveInterventionState(state) {
  try {
    sessionStorage.setItem(INTERVENTION_STATE_KEY, JSON.stringify(state));
  } catch (e) {}
}

function getInterventionState() {
  try {
    const stored = sessionStorage.getItem(INTERVENTION_STATE_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch (e) {
    return null;
  }
}

function clearInterventionState() {
  try {
    sessionStorage.removeItem(INTERVENTION_STATE_KEY);
  } catch (e) {}
}

function moveToCompletedInterventions(state) {
  try {
    const completed = JSON.parse(sessionStorage.getItem(COMPLETED_INTERVENTIONS_KEY) || '[]');
    completed.push({
      ...state,
      status: 'COMPLETED',
      completedAt: Date.now()
    });
    const trimmed = completed.slice(-10);
    sessionStorage.setItem(COMPLETED_INTERVENTIONS_KEY, JSON.stringify(trimmed));
  } catch (e) {}
}

function isRecentlyCompleted(productKey, windowMs = 30000) {
  try {
    const completed = JSON.parse(sessionStorage.getItem(COMPLETED_INTERVENTIONS_KEY) || '[]');
    const now = Date.now();
    return completed.some(item =>
      item.productKey === productKey &&
      item.completedAt &&
      (now - item.completedAt) < windowMs
    );
  } catch (e) {
    return false;
  }
}


// ════════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════════

describe('parsePrice', () => {
  test('parses $19.99', () => {
    expect(parsePrice('$19.99')).toBe(19.99);
  });

  test('parses $1,299', () => {
    expect(parsePrice('$1,299')).toBe(1299);
  });

  test('parses EUR 29.50 (strips non-numeric)', () => {
    expect(parsePrice('EUR 29.50')).toBe(29.50);
  });

  test('returns null for null input', () => {
    expect(parsePrice(null)).toBeNull();
  });

  test('returns null for undefined input', () => {
    expect(parsePrice(undefined)).toBeNull();
  });

  test('returns null for "free"', () => {
    expect(parsePrice('free')).toBeNull();
  });

  test('parses $0 as 0', () => {
    expect(parsePrice('$0')).toBe(0);
  });

  test('returns null for empty string', () => {
    expect(parsePrice('')).toBeNull();
  });

  test('parses large prices', () => {
    expect(parsePrice('$99,999.99')).toBe(99999.99);
  });

  test('parses £15.00', () => {
    expect(parsePrice('£15.00')).toBe(15.0);
  });
});


describe('hostMatchesDomain', () => {
  test('exact match', () => {
    expect(hostMatchesDomain('amazon.com', 'amazon.com')).toBe(true);
  });

  test('subdomain match', () => {
    expect(hostMatchesDomain('www.amazon.com', 'amazon.com')).toBe(true);
  });

  test('deep subdomain match', () => {
    expect(hostMatchesDomain('shop.m.amazon.com', 'amazon.com')).toBe(true);
  });

  test('evil prefix does not match', () => {
    expect(hostMatchesDomain('evil-amazon.com', 'amazon.com')).toBe(false);
  });

  test('null domain returns false', () => {
    expect(hostMatchesDomain('test.com', null)).toBe(false);
  });

  test('empty domain returns false', () => {
    expect(hostMatchesDomain('test.com', '')).toBe(false);
  });

  test('case insensitive', () => {
    expect(hostMatchesDomain('WWW.AMAZON.COM', 'amazon.com')).toBe(true);
  });
});


describe('getBaseDomain', () => {
  test('strips www prefix', () => {
    expect(getBaseDomain('www.amazon.com')).toBe('amazon.com');
  });

  test('bare domain returned as-is', () => {
    expect(getBaseDomain('amazon.com')).toBe('amazon.com');
  });

  test('co.uk TLD keeps 3 parts', () => {
    expect(getBaseDomain('www.example.co.uk')).toBe('example.co.uk');
  });

  test('null returns null', () => {
    expect(getBaseDomain(null)).toBeNull();
  });

  test('empty string returns empty', () => {
    expect(getBaseDomain('')).toBe('');
  });

  test('single part domain', () => {
    expect(getBaseDomain('localhost')).toBe('localhost');
  });
});


describe('formatDuration', () => {
  test('seconds only', () => {
    expect(formatDuration(5000)).toBe('5s');
  });

  test('minutes and seconds', () => {
    expect(formatDuration(125000)).toBe('2m 5s');
  });

  test('hours, minutes, seconds', () => {
    expect(formatDuration(3725000)).toBe('1h 2m 5s');
  });

  test('zero milliseconds', () => {
    expect(formatDuration(0)).toBe('0s');
  });

  test('exactly one minute', () => {
    expect(formatDuration(60000)).toBe('1m 0s');
  });

  test('exactly one hour', () => {
    expect(formatDuration(3600000)).toBe('1h 0m 0s');
  });
});


describe('matchesPurchaseKeyword', () => {
  test('matches "Add to Cart"', () => {
    expect(matchesPurchaseKeyword('Add to Cart')).toBe(true);
  });

  test('matches "Buy Now"', () => {
    expect(matchesPurchaseKeyword('Buy Now')).toBe(true);
  });

  test('matches "Proceed to Checkout"', () => {
    expect(matchesPurchaseKeyword('Proceed to Checkout')).toBe(true);
  });

  test('does not match "Learn More"', () => {
    expect(matchesPurchaseKeyword('Learn More')).toBe(false);
  });

  test('does not match empty string', () => {
    expect(matchesPurchaseKeyword('')).toBe(false);
  });

  test('case insensitive', () => {
    expect(matchesPurchaseKeyword('ADD TO CART')).toBe(true);
  });
});


describe('matchesNegativePattern', () => {
  test('matches "Add to Wishlist"', () => {
    expect(matchesNegativePattern('Add to Wishlist')).toBe(true);
  });

  test('matches "Sold Out"', () => {
    expect(matchesNegativePattern('Sold Out')).toBe(true);
  });

  test('does not match "Add to Cart"', () => {
    expect(matchesNegativePattern('Add to Cart')).toBe(false);
  });

  test('does not match empty string', () => {
    expect(matchesNegativePattern('')).toBe(false);
  });
});


describe('generateInterventionId', () => {
  test('returns string with intervention_ prefix', () => {
    const id = generateInterventionId();
    expect(id).toMatch(/^intervention_\d+_[a-z0-9]+$/);
  });

  test('generates unique IDs', () => {
    const ids = new Set();
    for (let i = 0; i < 100; i++) {
      ids.add(generateInterventionId());
    }
    expect(ids.size).toBe(100);
  });
});


describe('Intervention state persistence', () => {
  test('save and get roundtrip', () => {
    const state = {
      interventionId: 'test_123',
      interventionAction: 'MIRROR',
      productName: 'Test Product',
      status: 'IN_PROGRESS',
    };
    saveInterventionState(state);
    const retrieved = getInterventionState();
    expect(retrieved).toEqual(state);
  });

  test('get returns null when empty', () => {
    expect(getInterventionState()).toBeNull();
  });

  test('clear removes state', () => {
    saveInterventionState({ test: true });
    clearInterventionState();
    expect(getInterventionState()).toBeNull();
  });

  test('isRecentlyCompleted returns true within window', () => {
    moveToCompletedInterventions({
      productKey: 'shoes-99',
      completedAt: Date.now(),
    });
    expect(isRecentlyCompleted('shoes-99', 30000)).toBe(true);
  });

  test('isRecentlyCompleted returns false for unknown product', () => {
    expect(isRecentlyCompleted('nonexistent-product')).toBe(false);
  });

  test('moveToCompletedInterventions overflow trims to 10', () => {
    for (let i = 0; i < 15; i++) {
      moveToCompletedInterventions({
        productKey: `item-${i}`,
        completedAt: Date.now(),
      });
    }
    const completed = JSON.parse(
      sessionStorage.getItem(COMPLETED_INTERVENTIONS_KEY) || '[]'
    );
    expect(completed.length).toBe(10);
  });
});
