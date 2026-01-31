/* -------------------- Behavioral Tracking & Logging -------------------- */
(function behavioralTracking() {
    try {
        // --- Price Extraction Utilities ---
        function parsePrice(text) {
            if (!text) return null;
            const cleaned = text.replace(/[^0-9.]/g, "");
            const value = parseFloat(cleaned);
            return isNaN(value) ? null : value;
        }

        function getSite() {
            const host = window.location.hostname || '';
            if (host.includes('amazon')) return 'amazon';
            if (document.querySelector('meta[name="generator"][content*="Shopify"]')) return 'shopify';
            return 'unknown';
        }

        function getAmazonPrice() {
            const selectors = [
                '#priceblock_ourprice',
                '#priceblock_dealprice',
                '#priceblock_saleprice',
                '.a-price .a-offscreen'
            ];
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (el?.textContent) {
                    const raw = el.textContent.trim();
                    const value = parsePrice(raw);
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
                if (el?.textContent) {
                    const raw = el.textContent.trim();
                    const value = parsePrice(raw);
                    return { raw, value };
                }
            }
            return { raw: null, value: null };
        }

        function getGenericPrice() {
            const elements = Array.from(document.querySelectorAll('span, div'));
            for (const el of elements) {
                const text = el.textContent?.trim() || '';
                if (text.match(/[$€£]\s?\d+/)) {
                    const value = parsePrice(text);
                    if (value && value > 0) return { raw: text, value };
                }
            }
            return { raw: null, value: null };
        }

        function getPagePrice() {
            const site = getSite();
            if (site === 'amazon') return getAmazonPrice();
            if (site === 'shopify') return getShopifyPrice();
            return getGenericPrice();
        }

        // --- Configuration & State ---
        const pageLoadTime = performance.now();
        const pageLoadTimestamp = Date.now();
        let ttcRecorded = null; // Time-to-Cart (seconds)
        let priceRecorded = null; // Price info at time of cart click
        let cartClickDate = null; // Date/time of cart click
        let peakScrollVelocity = 0; // pixels per second
        let clickCount = 0;
        let clickTimestamps = [];
        
        // Navigation path: Start with current page
        let navPath = [{ url: location.href, ts: Date.now() }];
        
        // Scroll tracking variables
        let lastScrollY = window.scrollY;
        let lastScrollTime = performance.now();

        // Derive base domain for storage key
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

        const host = window.location.hostname;
        const baseDomain = getBaseDomain(host);
        const STATE_KEY = 'stop_shopping.tracker:' + baseDomain;
        
        // Default system start; may be overridden by restoreState
        let systemStartTime = new Date(pageLoadTimestamp).toISOString();

        // --- Persistence Logic ---

        function getState() {
            return {
                systemStartTime,
                clickCount,
                clickTimestamps,
                navPath,
                ttcRecorded,
                priceRecorded,
                cartClickDate,
                peakScrollVelocity
            };
        }

        function saveState() {
            try {
                sessionStorage.setItem(STATE_KEY, JSON.stringify(getState()));
            } catch (e) { /* Quota exceeded or security error */ }
        }

        let saveTimeout = null;
        function saveStateDebounced() {
            if (saveTimeout) clearTimeout(saveTimeout);
            saveTimeout = setTimeout(() => { saveState(); saveTimeout = null; }, 500);
        }

        function restoreState(obj) {
            try {
                if (!obj) return;
                if (obj.systemStartTime) systemStartTime = obj.systemStartTime;
                if (typeof obj.clickCount === 'number') clickCount = obj.clickCount;
                if (Array.isArray(obj.clickTimestamps)) {
                    // Merge unique timestamps
                    obj.clickTimestamps.forEach(ts => { 
                        if (!clickTimestamps.includes(ts)) clickTimestamps.push(ts); 
                    });
                }
                if (Array.isArray(obj.navPath)) {
                    // Fix: Prepend old history to current history
                    const currentEntry = navPath[0]; 
                    // Filter duplicates from old history based on URL+TS
                    const oldUnique = obj.navPath.filter(n => n.url !== currentEntry.url || Math.abs(n.ts - currentEntry.ts) > 1000);
                    navPath = [...oldUnique, ...navPath];
                }
                if (typeof obj.ttcRecorded === 'number') ttcRecorded = obj.ttcRecorded;
                if (obj.priceRecorded) priceRecorded = obj.priceRecorded;
                if (obj.cartClickDate) cartClickDate = obj.cartClickDate;
                if (typeof obj.peakScrollVelocity === 'number') peakScrollVelocity = Math.max(peakScrollVelocity, obj.peakScrollVelocity);
            } catch (e) { console.warn('[Tracker] restoreState failed', e); }
        }

        // Try to restore immediately
        try {
            const raw = sessionStorage.getItem(STATE_KEY);
            if (raw) {
                restoreState(JSON.parse(raw));
                console.info('[Tracker] Restored state for', baseDomain);
            }
        } catch (e) { /* ignore */ }

        // Initialization confirmation
        console.log('[Tracker] Initialized for domain:', baseDomain);
        console.log('[Tracker] State key:', STATE_KEY);
        console.log('[Tracker] Page load time:', new Date(pageLoadTimestamp).toISOString());

        // --- History Monkey-Patching (Defensive) ---
        // We wrap this carefully to ensure Amazon's router is not disrupted.
        (function hookHistory() {
            const _push = history.pushState;
            const _replace = history.replaceState;
            
            function trackUrlChange(methodName, url) {
                try {
                    const resolved = url ? new URL(url, location.href).href : location.href;
                    navPath.push({ url: resolved, ts: Date.now() });
                    // Save state on navigation
                    saveStateDebounced();
                } catch (err) {
                    console.warn(`[Tracker] ${methodName} url parse failed`, err);
                }
            }

            history.pushState = function (state, title, url) {
                // 1. Execute original immediately
                const res = _push.apply(this, arguments);
                // 2. Track side effect safely
                trackUrlChange('pushState', url);
                return res;
            };

            history.replaceState = function (state, title, url) {
                const res = _replace.apply(this, arguments);
                trackUrlChange('replaceState', url);
                return res;
            };

            window.addEventListener('popstate', () => {
                navPath.push({ url: location.href, ts: Date.now() });
                saveStateDebounced();
            });
        })();

        // --- Interaction Tracking ---

        // Utility: Find ancestor safely
        function findAncestor(el, predicate) {
            let current = el;
            while (current) {
                // Safety check to prevent errors accessing properties on restricted nodes
                try { 
                    if (predicate(current)) return current; 
                } catch (e) {}
                current = current.parentElement;
            }
            return null;
        }

        // Detect add-to-cart clicks
        function isAddToCartElement(el) {
            // FIX: Ensure it is an Element node (nodeType 1) to avoid getAttribute errors on text nodes
            if (!el || el.nodeType !== 1) return false;
            
            const tag = el.tagName.toLowerCase();
            const text = (el.innerText || el.value || '').trim().toLowerCase();
            const id = el.getAttribute('id') || '';
            const cls = el.getAttribute('class') || '';
            const attrStr = (id + ' ' + cls).toLowerCase();

            const addPhrases = ['add to cart', 'add to bag', 'add to basket', 'add to trolley', 'buy now', 'add to order'];
            
            if (addPhrases.some(p => text.includes(p))) return true;
            if (/(add_to_cart|addtocart|add-to-cart|btn-add|add-to-basket|add-to-bag)/i.test(attrStr)) return true;
            
            // Input buttons
            if (tag === 'input' && (el.type === 'submit' || el.type === 'button') && addPhrases.some(p => (el.value || '').toLowerCase().includes(p))) return true;
            
            return false;
        }

        // Click listener
        document.addEventListener('click', (ev) => {
            clickCount++;
            const clickTimestamp = Date.now();
            clickTimestamps.push(clickTimestamp);
            
            // Check for Add to Cart
            const cartEl = findAncestor(ev.target, isAddToCartElement);
            if (cartEl && ttcRecorded === null) {
                const now = performance.now();
                ttcRecorded = (now - pageLoadTime) / 1000;
                
                // Capture price and date/time
                const priceInfo = getPagePrice();
                priceRecorded = { raw: priceInfo.raw, value: priceInfo.value };
                cartClickDate = new Date().toISOString();
                
                console.warn(`[Tracker] ⚠️ ADD-TO-CART DETECTED`);
                console.warn(`[Tracker] Time-to-Cart (TTC): ${ttcRecorded.toFixed(2)}s`);
                console.warn(`[Tracker] Price (raw): ${priceRecorded.raw}`);
                console.warn(`[Tracker] Price (value): ${priceRecorded.value ? `$${priceRecorded.value.toFixed(2)}` : 'N/A'}`);
                console.warn(`[Tracker] Cart clicked at: ${cartClickDate}`);
            }

            // Save on click interaction
            saveStateDebounced();
        }, { capture: true, passive: true });

        // Scroll listener
        window.addEventListener('scroll', () => {
            const now = performance.now();
            const dt = now - lastScrollTime;
            
            // Throttle calculations to ~60fps (16ms)
            if (dt < 16) return; 

            const y = window.scrollY;
            const dy = Math.abs(y - lastScrollY);
            const v = (dy / dt) * 1000; // px/s
            
            if (v > peakScrollVelocity) {
                peakScrollVelocity = v;
                // Note: We do NOT saveState here to improve scrolling performance
            }
            
            lastScrollY = y;
            lastScrollTime = now;
        }, { passive: true });

        // --- Reporting ---

        // Periodic summary log & Save
        const summaryInterval = setInterval(() => {
            saveState(); // Periodic save instead of on-scroll save
            
            const elapsed = (performance.now() - pageLoadTime) / 1000;
            const clickRate = elapsed > 0 ? (clickCount / elapsed) : 0;
            
            console.group('[Tracker] Periodic Summary');
            console.log('Timestamp:', new Date().toISOString());
            console.log('System Start Time:', systemStartTime);
            console.log('---');
            console.log('Elapsed Time:', elapsed.toFixed(2), 's');
            console.log('Click Count:', clickCount);
            console.log('Click Rate:', clickRate.toFixed(2), 'clicks/sec');
            console.log('Total Timestamps Recorded:', clickTimestamps.length);
            console.log('---');
            
            if (ttcRecorded) {
                console.log('Time-to-Cart (TTC):', ttcRecorded.toFixed(2), 's');
            } else {
                console.log('Time-to-Cart (TTC): Not yet recorded');
            }
            
            if (priceRecorded) {
                console.log('Price (Raw):', priceRecorded.raw || 'N/A');
                console.log('Price (Value):', priceRecorded.value ? `$${priceRecorded.value.toFixed(2)}` : 'N/A');
            } else {
                console.log('Price: Not recorded');
            }
            
            if (cartClickDate) {
                console.log('Cart Click Time:', cartClickDate);
            } else {
                console.log('Cart Click Time: Not recorded');
            }
            
            console.log('---');
            console.log('Peak Scroll Velocity:', peakScrollVelocity.toFixed(2), 'px/s');
            console.log('Navigation Path Length:', navPath.length);
            console.log('Current Page:', location.href);
            console.log('Base Domain:', baseDomain);
            console.groupEnd();
        }, 10000);

        // Final Report
        window.addEventListener('beforeunload', () => {
            saveState(); // Ensure final state is saved
        });

        // Visibility change (tab switch)
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') {
                saveState();
            }
        });

        // Expose debug handle
        window.__shoppingTracker = {
            getSummary: () => ({
                systemStartTime,
                clicks: clickCount,
                navPath,
                ttc: ttcRecorded,
                price: priceRecorded,
                cartClickDate,
                peakScrollVelocity
            })
        };

        // --- Message Listener (for popup.js requests) ---
        try {
            chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
                if (msg && msg.type === 'GET_PRICE') {
                    const result = getPagePrice();
                    sendResponse({ price: result.raw, value: result.value });
                }
                if (msg && msg.type === 'GET_TRACKER_SUMMARY') {
                    sendResponse(window.__shoppingTracker.getSummary());
                }
            });
        } catch (e) {
            // chrome.runtime may not be available in some contexts
        }

    } catch (err) {
        console.warn('[Tracker] initialization failed', err);
    }
})();