/**
 * DOM integration tests for content.js price extraction and site detection.
 *
 * Uses jsdom fixtures to simulate real page DOM structures.
 */

// ── Extracted functions (same as content.test.js) ──────────────────────

function parsePrice(text) {
  if (!text) return null;
  const cleaned = text.replace(/[^0-9.]/g, '');
  const value = parseFloat(cleaned);
  return isNaN(value) ? null : value;
}

function getSite() {
  const host = window.location.hostname || '';
  if (host.includes('amazon')) return 'amazon';
  if (host.includes('ebay')) return 'ebay';
  if (host.includes('walmart')) return 'walmart';
  if (host.includes('target.com')) return 'target';
  if (host.includes('bestbuy')) return 'bestbuy';
  if (document.querySelector('meta[name="generator"][content*="Shopify"]')) return 'shopify';
  return 'unknown';
}

// Simplified price extractors for DOM testing
function getAmazonPrice() {
  const selectors = [
    '.a-price .a-offscreen',
    '#corePrice_feature_div .a-offscreen',
    '#priceblock_ourprice',
    '.offer-price'
  ];
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el && el.textContent) {
      const raw = el.textContent.trim();
      const value = parsePrice(raw);
      if (value && value > 0) return { raw, value };
    }
  }
  // Try whole + fraction
  const wholeEl = document.querySelector('.a-price-whole');
  const fractionEl = document.querySelector('.a-price-fraction');
  if (wholeEl && fractionEl) {
    const whole = wholeEl.textContent.replace(/[^0-9]/g, '');
    const fraction = fractionEl.textContent.replace(/[^0-9]/g, '');
    if (whole && fraction) {
      const raw = `$${whole}.${fraction}`;
      const value = parseFloat(`${whole}.${fraction}`);
      return { raw, value };
    }
  }
  return { raw: null, value: null };
}

function getShopifyPrice() {
  const selectors = [
    '[data-product-price]',
    '.product__price',
    '.price-item--sale',
    '.price-item--regular'
  ];
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    if (el && el.textContent) {
      const raw = el.textContent.trim();
      const value = parsePrice(raw);
      return { raw, value };
    }
  }
  return { raw: null, value: null };
}

function getGenericPrice() {
  const commonSelectors = [
    '[data-price]', '[data-product-price]', '.price',
    '.product-price', '[itemprop="price"]'
  ];
  for (const selector of commonSelectors) {
    const el = document.querySelector(selector);
    if (el) {
      const dataPrice = el.getAttribute('data-price') || el.getAttribute('data-product-price');
      if (dataPrice) {
        const value = parsePrice(dataPrice);
        if (value && value > 0) return { raw: `$${value}`, value };
      }
      const text = (el.textContent || '').trim();
      if (text.match(/[$€£]\s?\d+/)) {
        const value = parsePrice(text);
        if (value && value > 0) return { raw: text, value };
      }
    }
  }
  // text scan
  const elements = Array.from(document.querySelectorAll('span, div, p'));
  for (const el of elements) {
    const text = (el.textContent || '').trim();
    if (text.match(/^[$€£]\s?\d+(\.\d{2})?$/) || text.match(/^\d+(\.\d{2})?\s?[$€£]$/)) {
      const value = parsePrice(text);
      if (value && value > 0 && value < 100000) return { raw: text, value };
    }
  }
  return { raw: null, value: null };
}

// isLikelyShoppingPage (simplified for testing)
const KNOWN_SHOPPING_DOMAINS = new Set([
  'amazon.com', 'ebay.com', 'walmart.com', 'target.com', 'bestbuy.com',
  'etsy.com', 'aliexpress.com', 'temu.com', 'costco.com', 'wayfair.com',
]);

function isLikelyShoppingPage() {
  const host = window.location.hostname || '';
  for (const domain of KNOWN_SHOPPING_DOMAINS) {
    if (host === domain || host.endsWith('.' + domain)) return true;
  }
  if (document.querySelector('[itemtype*="schema.org/Product"]')) return true;
  const ogType = document.querySelector('meta[property="og:type"]');
  if (ogType && ogType.content && ogType.content.toLowerCase().includes('product')) return true;
  if (document.querySelector('[itemprop="price"], [data-price], .price, .product-price')) return true;
  return false;
}

// showInterventionOverlay (simplified for DOM test)
function showInterventionOverlay(interventionAction, opts = {}) {
  switch (interventionAction) {
    case 'NONE':
      return false;
    case 'MIRROR':
      const mirrorOverlay = document.createElement('div');
      mirrorOverlay.id = 'impulse-mirror-overlay';
      document.body.appendChild(mirrorOverlay);
      return true;
    case 'COOLDOWN':
      const cooldownOverlay = document.createElement('div');
      cooldownOverlay.id = 'impulse-cooldown-overlay';
      document.body.appendChild(cooldownOverlay);
      return true;
    case 'PHRASE':
      const phraseOverlay = document.createElement('div');
      phraseOverlay.id = 'impulse-phrase-overlay';
      document.body.appendChild(phraseOverlay);
      return true;
    default:
      // Default to MIRROR
      const defaultOverlay = document.createElement('div');
      defaultOverlay.id = 'impulse-mirror-overlay';
      document.body.appendChild(defaultOverlay);
      return true;
  }
}


// ════════════════════════════════════════════════════════════════════════
// Tests
// ════════════════════════════════════════════════════════════════════════

describe('Amazon price extraction', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  test('extracts from .a-offscreen', () => {
    document.body.innerHTML = `
      <div class="a-price"><span class="a-offscreen">$29.99</span></div>
    `;
    const result = getAmazonPrice();
    expect(result.value).toBe(29.99);
    expect(result.raw).toBe('$29.99');
  });

  test('extracts from whole + fraction', () => {
    document.body.innerHTML = `
      <span class="a-price-whole">149.</span>
      <span class="a-price-fraction">95</span>
    `;
    const result = getAmazonPrice();
    expect(result.value).toBe(149.95);
  });

  test('returns null when no price elements', () => {
    document.body.innerHTML = '<div>No price here</div>';
    const result = getAmazonPrice();
    expect(result.value).toBeNull();
  });
});


describe('Shopify price extraction', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  test('extracts from [data-product-price]', () => {
    document.body.innerHTML = `
      <span data-product-price>$49.99</span>
    `;
    const result = getShopifyPrice();
    expect(result.value).toBe(49.99);
  });

  test('extracts from .product__price', () => {
    document.body.innerHTML = `
      <div class="product__price">$35.00</div>
    `;
    const result = getShopifyPrice();
    expect(result.value).toBe(35.0);
  });

  test('returns null when no Shopify elements', () => {
    document.body.innerHTML = '<div>Not a Shopify page</div>';
    const result = getShopifyPrice();
    expect(result.value).toBeNull();
  });
});


describe('Generic price extraction', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  test('extracts from data-price attribute', () => {
    document.body.innerHTML = `
      <div data-price="79.99"></div>
    `;
    const result = getGenericPrice();
    expect(result.value).toBe(79.99);
  });

  test('extracts from text scan', () => {
    document.body.innerHTML = `
      <span>$24.99</span>
    `;
    const result = getGenericPrice();
    expect(result.value).toBe(24.99);
  });

  test('extracts from .price class', () => {
    document.body.innerHTML = `
      <span class="price">$19.99</span>
    `;
    const result = getGenericPrice();
    expect(result.value).toBe(19.99);
  });

  test('returns null for non-price page', () => {
    document.body.innerHTML = '<div>No prices at all</div>';
    const result = getGenericPrice();
    expect(result.value).toBeNull();
  });
});


describe('getSite', () => {
  test('returns unknown for non-shopping domain', () => {
    // jsdom defaults to about:blank / localhost
    expect(getSite()).toBe('unknown');
  });

  test('detects Shopify via meta tag', () => {
    document.head.innerHTML = `
      <meta name="generator" content="Shopify">
    `;
    expect(getSite()).toBe('shopify');
    document.head.innerHTML = '';
  });
});


describe('isLikelyShoppingPage', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    document.head.innerHTML = '';
  });

  test('detects via schema.org Product', () => {
    document.body.innerHTML = `
      <div itemtype="http://schema.org/Product"></div>
    `;
    expect(isLikelyShoppingPage()).toBe(true);
  });

  test('detects via og:type product', () => {
    document.head.innerHTML = `
      <meta property="og:type" content="product">
    `;
    expect(isLikelyShoppingPage()).toBe(true);
  });

  test('detects via price element', () => {
    document.body.innerHTML = `
      <span itemprop="price">$29.99</span>
    `;
    expect(isLikelyShoppingPage()).toBe(true);
  });

  test('returns false for non-shopping page', () => {
    document.body.innerHTML = '<div>Just a blog post</div>';
    expect(isLikelyShoppingPage()).toBe(false);
  });
});


describe('showInterventionOverlay', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  test('NONE returns false and creates no overlay', () => {
    const result = showInterventionOverlay('NONE');
    expect(result).toBe(false);
    expect(document.body.children.length).toBe(0);
  });

  test('MIRROR creates overlay', () => {
    const result = showInterventionOverlay('MIRROR', {});
    expect(result).toBe(true);
    expect(document.getElementById('impulse-mirror-overlay')).not.toBeNull();
  });

  test('COOLDOWN creates overlay', () => {
    const result = showInterventionOverlay('COOLDOWN', {});
    expect(result).toBe(true);
    expect(document.getElementById('impulse-cooldown-overlay')).not.toBeNull();
  });

  test('PHRASE creates overlay', () => {
    const result = showInterventionOverlay('PHRASE', {});
    expect(result).toBe(true);
    expect(document.getElementById('impulse-phrase-overlay')).not.toBeNull();
  });

  test('unknown type defaults to MIRROR', () => {
    const result = showInterventionOverlay('UNKNOWN_TYPE', {});
    expect(result).toBe(true);
    expect(document.getElementById('impulse-mirror-overlay')).not.toBeNull();
  });
});
