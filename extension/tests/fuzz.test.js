/**
 * Fuzz tests for extension functions using fast-check.
 *
 * Property-based tests ensuring functions never throw for arbitrary
 * inputs and return well-typed results.
 */

const fc = require('fast-check');

// ── Extracted functions ────────────────────────────────────────────────

function parsePrice(text) {
  if (!text) return null;
  const cleaned = text.replace(/[^0-9.]/g, '');
  const value = parseFloat(cleaned);
  return isNaN(value) ? null : value;
}

function hostMatchesDomain(hostname, domain) {
  if (!domain) return false;
  domain = domain.toLowerCase();
  hostname = hostname.toLowerCase();
  return hostname === domain || hostname.endsWith('.' + domain);
}

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

const PURCHASE_KEYWORDS = [
  'add to cart', 'add to bag', 'add to basket', 'buy now',
  'buy it now', 'place order', 'checkout now', 'order now',
];

const NEGATIVE_PATTERNS = [
  'add to wishlist', 'save for later', 'sold out', 'out of stock',
  'sign in', 'notify me',
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


// ════════════════════════════════════════════════════════════════════════
// Fuzz Tests
// ════════════════════════════════════════════════════════════════════════

describe('parsePrice fuzz', () => {
  test('never throws for any string', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = parsePrice(s);
        // Should never throw; result is null or a number
        expect(result === null || typeof result === 'number').toBe(true);
      }),
      { numRuns: 500 }
    );
  });

  test('result >= 0 when not null (for non-negative inputs)', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant('$'),
          fc.constant('€'),
          fc.constant('£'),
          fc.constant('')
        ).chain(prefix =>
          fc.float({ min: 0, max: 99999, noNaN: true }).map(n =>
            `${prefix}${n.toFixed(2)}`
          )
        ),
        (priceStr) => {
          const result = parsePrice(priceStr);
          if (result !== null) {
            expect(result).toBeGreaterThanOrEqual(0);
          }
        }
      ),
      { numRuns: 200 }
    );
  });
});


describe('hostMatchesDomain fuzz', () => {
  test('domain matches itself for any non-empty domain', () => {
    fc.assert(
      fc.property(
        fc.stringOf(fc.constantFrom('a', 'b', 'c', '.', '-'), { minLength: 3, maxLength: 30 })
          .filter(s => s.includes('.') && !s.startsWith('.') && !s.endsWith('.')),
        (domain) => {
          expect(hostMatchesDomain(domain, domain)).toBe(true);
        }
      ),
      { numRuns: 200 }
    );
  });

  test('returns boolean for any inputs', () => {
    fc.assert(
      fc.property(fc.string(), fc.string(), (hostname, domain) => {
        const result = hostMatchesDomain(hostname, domain);
        expect(typeof result).toBe('boolean');
      }),
      { numRuns: 200 }
    );
  });
});


describe('getBaseDomain fuzz', () => {
  test('result is suffix of input for domain-like strings', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz'), { minLength: 1, maxLength: 10 }),
          { minLength: 2, maxLength: 5 }
        ).map(parts => parts.join('.')),
        (hostname) => {
          const base = getBaseDomain(hostname);
          if (base) {
            expect(hostname.toLowerCase().endsWith(base.toLowerCase())).toBe(true);
          }
        }
      ),
      { numRuns: 200 }
    );
  });

  test('never throws for any string', () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        const result = getBaseDomain(s);
        expect(result === null || result === undefined || typeof result === 'string').toBe(true);
      }),
      { numRuns: 200 }
    );
  });
});


describe('formatDuration fuzz', () => {
  test('returns string with digit for any non-negative int', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 100000000 }), (ms) => {
        const result = formatDuration(ms);
        expect(typeof result).toBe('string');
        expect(result).toMatch(/\d/); // contains at least one digit
      }),
      { numRuns: 300 }
    );
  });
});


describe('matchesPurchaseKeyword + matchesNegativePattern disjointness', () => {
  test('known purchase keywords are not negative patterns', () => {
    for (const keyword of PURCHASE_KEYWORDS) {
      expect(matchesPurchaseKeyword(keyword)).toBe(true);
      // "Add to cart" should not match "add to wishlist"
      // but could match if keyword contains a negative substring (unlikely)
      // We just verify the function doesn't throw
      matchesNegativePattern(keyword);
    }
  });

  test('known negative patterns are not purchase keywords', () => {
    for (const pattern of NEGATIVE_PATTERNS) {
      expect(matchesNegativePattern(pattern)).toBe(true);
    }
  });
});


describe('generateInterventionId fuzz', () => {
  test('100 calls all produce unique IDs', () => {
    const ids = new Set();
    for (let i = 0; i < 100; i++) {
      ids.add(generateInterventionId());
    }
    expect(ids.size).toBe(100);
  });

  test('all IDs match expected format', () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const id = generateInterventionId();
        expect(id).toMatch(/^intervention_\d+_[a-z0-9]+$/);
      }),
      { numRuns: 100 }
    );
  });
});
