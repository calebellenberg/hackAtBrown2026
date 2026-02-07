/* -------------------- Behavioral Tracking & Logging -------------------- */
(function behavioralTracking() {
    try {
        // Lightweight shim for `chrome.storage.local` when not running as an extension
        if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
            try {
                console.warn('[Tracker] chrome.storage not available — installing local shim for testing');

                // Keep a single JSON object in localStorage under this key
                const SHIM_KEY = 'stop_shopping.chrome_storage_shim_v1';

                function readStore() {
                    try {
                        const raw = localStorage.getItem(SHIM_KEY);
                        return raw ? JSON.parse(raw) : {};
                    } catch (e) { return {}; }
                }

                function writeStore(obj) {
                    try { localStorage.setItem(SHIM_KEY, JSON.stringify(obj)); } catch (e) {}
                }

                window.chrome = window.chrome || {};
                window.chrome.storage = window.chrome.storage || {};
                window.chrome.storage.local = {
                    get: function (keys, callback) {
                        const store = readStore();
                        const out = {};
                        if (typeof keys === 'string') {
                            out[keys] = store[keys];
                        } else if (Array.isArray(keys)) {
                            for (const k of keys) out[k] = store[k];
                        } else if (typeof keys === 'object' && keys !== null) {
                            // keys may be an object of default values
                            for (const k of Object.keys(keys)) out[k] = store[k] === undefined ? keys[k] : store[k];
                        } else if (keys === null || keys === undefined) {
                            // return all
                            for (const k of Object.keys(store)) out[k] = store[k];
                        } else {
                            // unknown type - return all
                            for (const k of Object.keys(store)) out[k] = store[k];
                        }
                        // async-ish callback to match chrome API
                        setTimeout(() => { try { callback(out); } catch (e) {} }, 0);
                    },
                    set: function (items, callback) {
                        const store = readStore();
                        for (const k of Object.keys(items)) store[k] = items[k];
                        writeStore(store);
                        setTimeout(() => { try { if (callback) callback(); } catch (e) {} }, 0);
                    },
                    remove: function (keys, callback) {
                        const store = readStore();
                        if (typeof keys === 'string') delete store[keys];
                        else if (Array.isArray(keys)) keys.forEach(k => delete store[k]);
                        writeStore(store);
                        setTimeout(() => { try { if (callback) callback(); } catch (e) {} }, 0);
                    }
                };
            } catch (shimErr) {
                console.warn('[Tracker] Failed to install chrome.storage shim', shimErr);
            }
        }
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
                // Current Amazon selectors (2024+) - these contain full price
                '.a-price .a-offscreen',
                '#corePrice_feature_div .a-offscreen',
                '#corePriceDisplay_desktop_feature_div .a-offscreen',
                'span.a-price[data-a-color="price"] .a-offscreen',
                '#apex_offerDisplay_desktop .a-offscreen',
                '.priceToPay .a-offscreen',
                '#priceblock_ourprice',
                '#priceblock_dealprice',
                '#priceblock_saleprice',
                '#tp_price_block_total_price_ww .a-offscreen',
                '#price_inside_buybox',
                '#newBuyBoxPrice',
                '.offer-price'
            ];
            for (const selector of selectors) {
                const el = document.querySelector(selector);
                if (el?.textContent) {
                    const raw = el.textContent.trim();
                    const value = parsePrice(raw);
                    if (value && value > 0) {
                        return { raw, value };
                    }
                }
            }
            
            // Try to combine .a-price-whole and .a-price-fraction
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
            
            // Fallback: look for any element with aria-label containing price
            const ariaPrice = document.querySelector('[aria-label*="$"]');
            if (ariaPrice) {
                const ariaLabel = ariaPrice.getAttribute('aria-label');
                const value = parsePrice(ariaLabel);
                if (value && value > 0) {
                    return { raw: ariaLabel, value };
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
            // First try common price selectors used across many sites
            const commonSelectors = [
                '[data-price]',
                '[data-product-price]',
                '.price',
                '.product-price',
                '.current-price',
                '.sale-price',
                '.regular-price',
                '[itemprop="price"]',
                '.price__current',
                '.price-value'
            ];
            
            for (const selector of commonSelectors) {
                const el = document.querySelector(selector);
                if (el) {
                    // Check data-price attribute first
                    const dataPrice = el.getAttribute('data-price') || el.getAttribute('data-product-price');
                    if (dataPrice) {
                        const value = parsePrice(dataPrice);
                        if (value && value > 0) {
                            return { raw: `$${value}`, value };
                        }
                    }
                    // Then check text content
                    const text = el.textContent?.trim() || '';
                    if (text.match(/[$€£]\s?\d+/)) {
                        const value = parsePrice(text);
                        if (value && value > 0) {
                            return { raw: text, value };
                        }
                    }
                }
            }
            
            // Fallback: scan all span/div elements
            const elements = Array.from(document.querySelectorAll('span, div, p'));
            for (const el of elements) {
                const text = el.textContent?.trim() || '';
                // Match price patterns like $19.99, €29, £15.00
                if (text.match(/^[$€£]\s?\d+(\.\d{2})?$/) || text.match(/^\d+(\.\d{2})?\s?[$€£]$/)) {
                    const value = parsePrice(text);
                    if (value && value > 0 && value < 100000) {
                        return { raw: text, value };
                    }
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
        let productNameRecorded = null; // Product name at time of cart click
        let peakScrollVelocity = 0; // pixels per second
        let clickCount = 0;
        let clickTimestamps = [];
        let cartClickCount = 0; // Total cart clicks this session
        
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
                productNameRecorded,
                peakScrollVelocity,
                cartClickCount
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
                if (obj.productNameRecorded) productNameRecorded = obj.productNameRecorded;
                if (typeof obj.peakScrollVelocity === 'number') peakScrollVelocity = Math.max(peakScrollVelocity, obj.peakScrollVelocity);
                if (typeof obj.cartClickCount === 'number') cartClickCount = obj.cartClickCount;
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

            // Input buttons
            if (tag === 'input' && (el.type === 'submit' || el.type === 'button') && addPhrases.some(p => (el.value || '').toLowerCase().includes(p))) return true;

            return false;
        }

        // Capture price with short polling window to catch dynamic updates
        function capturePriceWithPolling(timeoutMs = 2000, intervalMs = 200) {
            return new Promise((resolve) => {
                const start = Date.now();
                let lastSeen = getPagePrice();

                // If we already have a value, resolve quickly but still allow a later update
                if (lastSeen && lastSeen.value) {
                    // Still poll briefly to catch immediate updates
                }

                const iv = setInterval(() => {
                    const now = Date.now();
                    const candidate = getPagePrice();
                    // Prefer non-null numeric values
                    if (candidate && candidate.value) {
                        lastSeen = candidate;
                    }
                    if (now - start >= timeoutMs) {
                        clearInterval(iv);
                        resolve(lastSeen || { raw: null, value: null });
                    }
                }, intervalMs);

                // Also resolve after timeout even if interval didn't run (safety)
                setTimeout(() => {
                    // noop here, actual resolution happens in interval clear
                }, timeoutMs + 50);
            });
        }

        // Track when content.js handles a cart click (to avoid double-counting in click listener)
        let lastCartClickFromContentJs = 0;
        
        // Function to save cart click summary to chrome.storage.local
        function saveCartClickSummary(actionType = 'add_to_cart') {
            try {
                const now = performance.now();
                const elapsed = (now - pageLoadTime) / 1000;
                const cartClickRate = elapsed > 0 ? (cartClickCount / (elapsed / 60)) : 0;
                
                // Build the summary object with all tracked data
                const summary = {
                    // Metadata
                    id: `${actionType}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
                    timestamp: new Date().toISOString(),
                    actionType: actionType, // 'add_to_cart' or 'buy_now'
                    
                    // Site info
                    domain: baseDomain,
                    pageUrl: location.href,
                    
                    // Product info
                    productName: productNameRecorded || null,
                    priceRaw: priceRecorded?.raw || null,
                    priceValue: priceRecorded?.value || null,
                    
                    // Time metrics
                    systemStartTime: systemStartTime,
                    timeToCart: ttcRecorded ? parseFloat(ttcRecorded.toFixed(2)) : null,
                    timeOnSite: parseFloat(elapsed.toFixed(2)),
                    
                    // Interaction metrics
                    clickCount: clickCount,
                    cartClickCount: cartClickCount,
                    cartClickRate: parseFloat(cartClickRate.toFixed(2)),
                    
                    // Scroll behavior  
                    peakScrollVelocity: parseFloat(peakScrollVelocity.toFixed(2)),
                    
                    // Navigation
                    navigationPathLength: navPath.length,
                    navigationPath: navPath.slice(-10) // Last 10 pages to avoid huge data
                };
                
                // Check if chrome.storage is available
                if (typeof chrome === 'undefined' || !chrome.storage || !chrome.storage.local) {
                    console.log('[Tracker] chrome.storage not available, sending to API only');
                    sendToPipelineAPI(summary, []);
                    return summary;
                }
                
                // Determine storage key based on action type
                const storageKey = actionType === 'buy_now' ? 'buy_now_history' : 'add_to_cart_history';
                
                // Save to chrome.storage.local
                chrome.storage.local.get([storageKey, 'all_purchase_attempts'], (result) => {
                    // Save to specific history (add_to_cart or buy_now)
                    const specificHistory = result[storageKey] || [];
                    specificHistory.push(summary);
                    const trimmedSpecific = specificHistory.slice(-100);
                    
                    // Also save to combined history for easy API access
                    const allHistory = result.all_purchase_attempts || [];
                    allHistory.push(summary);
                    const trimmedAll = allHistory.slice(-200);
                    
                    const updateObj = {
                        [storageKey]: trimmedSpecific,
                        all_purchase_attempts: trimmedAll
                    };
                    
                    chrome.storage.local.set(updateObj, () => {
                        console.log(`[Tracker] ${actionType.toUpperCase()} summary saved to storage:`, summary);
                        console.log(`[Tracker] ${storageKey} entries:`, trimmedSpecific.length);
                        console.log(`[Tracker] all_purchase_attempts entries:`, trimmedAll.length);
                        
                        // Send to Pipeline API for Fast Brain + Slow Brain analysis
                        sendToPipelineAPI(summary, trimmedAll.slice(-10));
                    });
                });
                
                return summary;
            } catch (e) {
                console.warn('[Tracker] Failed to save cart click summary:', e);
                return null;
            }
        }
        
        // ===================== PIPELINE API INTEGRATION =====================
        // Use service worker proxy so HTTPS pages can reach HTTP backend (WSL) without mixed-content block.
        async function sendToPipelineAPI(currentPurchase, recentHistory) {
            try {
                console.log('[Tracker] 🚀 Sending purchase data to Pipeline API (Fast Brain + Slow Brain)...');
                
                const systemHour = new Date().getHours();
                const requestBody = {
                    product: currentPurchase.productName || 'Unknown Product',
                    cost: currentPurchase.priceValue || 0,
                    website: currentPurchase.domain || 'unknown',
                    time_to_cart: currentPurchase.timeToCart || null,
                    time_on_site: currentPurchase.timeOnSite || 60,
                    click_count: currentPurchase.clickCount || 0,
                    peak_scroll_velocity: currentPurchase.peakScrollVelocity || 0,
                    system_hour: systemHour
                };
                
                console.log('[Tracker] Pipeline request:', requestBody);
                
                const reply = await new Promise(function (resolve) {
                    chrome.runtime.sendMessage({ type: 'pipeline-analyze', body: requestBody }, resolve);
                });
                
                if (reply && reply.error) {
                    throw new Error(reply.error);
                }
                const result = reply && reply.data;
                if (!result) {
                    throw new Error('No response from backend');
                }
                
                console.log('[Tracker] 🧠 PIPELINE ANALYSIS RESULT:');
                console.log('━'.repeat(50));
                console.log(`Fast Brain Score: ${result.p_impulse_fast.toFixed(3)}`);
                console.log(`Fast Brain Intervention: ${result.fast_brain_intervention}`);
                console.log(`Dominant Trigger: ${result.fast_brain_dominant_trigger}`);
                console.log('---');
                console.log(`Slow Brain Score: ${result.impulse_score.toFixed(3)}`);
                console.log(`Confidence: ${result.confidence.toFixed(2)}`);
                console.log(`Intervention Action: ${result.intervention_action}`);
                console.log(`Reasoning: ${result.reasoning}`);
                if (result.memory_update) {
                    console.log(`Memory Update: ${result.memory_update}`);
                }
                console.log('━'.repeat(50));
                
                // Dispatch event so content.js can show appropriate intervention overlay
                console.log('[Tracker] 📤 Dispatching pipeline-analysis-result event to content.js');
                console.log('[Tracker] Event payload:', JSON.stringify(result, null, 2));
                window.dispatchEvent(new CustomEvent('pipeline-analysis-result', {
                    detail: result
                }));
                console.log('[Tracker] ✅ Event dispatched successfully');
                
                // Also save the analysis result (if chrome.storage is available)
                if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
                    chrome.storage.local.get(['pipeline_analyses'], (data) => {
                        const analyses = data.pipeline_analyses || [];
                        analyses.push({
                            timestamp: new Date().toISOString(),
                            purchase: currentPurchase.productName,
                            result: result
                        });
                        chrome.storage.local.set({ 
                            pipeline_analyses: analyses.slice(-50),
                            last_pipeline_result: result
                        });
                    });
                }
                
                return result;
                
            } catch (error) {
                console.error('[Tracker] ❌ Failed to send to Pipeline API:', error);
                console.log('[Tracker] Make sure the backend is running: cd backend && uvicorn app:app --reload');
                
                // Dispatch a fallback result with MIRROR intervention
                window.dispatchEvent(new CustomEvent('pipeline-analysis-result', {
                    detail: {
                        p_impulse_fast: 0.5,
                        fast_brain_intervention: 'MIRROR',
                        fast_brain_dominant_trigger: 'error',
                        impulse_score: 0.5,
                        confidence: 0.3,
                        reasoning: 'Could not connect to backend. Please take a moment to consider this purchase.',
                        intervention_action: 'MIRROR',
                        memory_update: null,
                        error: error.message
                    }
                }));
                
                return null;
            }
        }
        
        // ===================== END PIPELINE API INTEGRATION =====================
        
        // Listen for cart click events from content.js (this is the primary source of cart click data)
        window.addEventListener('stop-shopping-cart-click', (ev) => {
            try {
                const detail = ev.detail;
                console.log('[Tracker] Received cart click event from content.js:', detail);
                
                // Mark that content.js handled this click
                lastCartClickFromContentJs = Date.now();
                
                // Always increment cart click count
                cartClickCount++;
                console.log('[Tracker] Cart click count updated:', cartClickCount);
                
                // Record price if available
                if (detail && (detail.raw || detail.value)) {
                    priceRecorded = { raw: detail.raw, value: detail.value };
                    console.log('[Tracker] Price recorded:', priceRecorded);
                }
                
                // Record product name if available
                if (detail && detail.productName) {
                    productNameRecorded = detail.productName;
                    console.log('[Tracker] Product name recorded:', productNameRecorded);
                }
                
                // Record time-to-cart if not already recorded
                if (ttcRecorded === null) {
                    const now = performance.now();
                    ttcRecorded = (now - pageLoadTime) / 1000;
                    const timeOnSite = (now - pageLoadTime) / 1000;
                    console.warn(`[Tracker] ⚠️ ADD-TO-CART DETECTED (via content.js)`);
                    console.warn(`[Tracker] Product: ${productNameRecorded || 'N/A'}`);
                    console.warn(`[Tracker] Time-to-Cart (TTC): ${ttcRecorded.toFixed(2)}s`);
                    console.warn(`[Tracker] Time on Site: ${timeOnSite.toFixed(2)}s`);
                    console.warn(`[Tracker] Price (raw): ${priceRecorded?.raw || 'N/A'}`);
                    console.warn(`[Tracker] Price (value): ${priceRecorded?.value ? `$${priceRecorded.value.toFixed(2)}` : 'N/A'}`);
                }
                
                // Determine action type based on button text if available
                const actionType = (detail?.buttonText || '').toLowerCase().includes('buy now') ? 'buy_now' : 'add_to_cart';
                
                // Save the cart click summary to chrome.storage.local
                saveCartClickSummary(actionType);
                
                saveStateDebounced();
            } catch (e) { 
                console.warn('[Tracker] Failed to process cart click event', e); 
            }
        });

        // Click listener (backup detection - content.js event is primary)
        document.addEventListener('click', (ev) => {
            clickCount++;
            const clickTimestamp = Date.now();
            clickTimestamps.push(clickTimestamp);
            
            // Check for Add to Cart (backup detection if content.js didn't catch it)
            const cartEl = findAncestor(ev.target, isAddToCartElement);
            
            // Only process if content.js didn't already handle this click (within 100ms)
            const recentlyHandledByContentJs = (clickTimestamp - lastCartClickFromContentJs) < 100;
            
            if (cartEl && !recentlyHandledByContentJs) {
                cartClickCount++;
                console.log('[Tracker] Cart click detected (backup). Total cart clicks:', cartClickCount);
                
                if (ttcRecorded === null) {
                    const now = performance.now();
                    ttcRecorded = (now - pageLoadTime) / 1000;

                    // Capture price immediately and then poll for updates briefly
                    capturePriceWithPolling(2000, 200).then(priceInfo => {
                        priceRecorded = { raw: priceInfo.raw, value: priceInfo.value };
                        const timeOnSite = (performance.now() - pageLoadTime) / 1000;
                        console.log(`[Tracker] ⚠️ ADD-TO-CART DETECTED (backup)`);
                        console.log(`[Tracker] Time-to-Cart (TTC): ${ttcRecorded.toFixed(2)}s`);
                        console.log(`[Tracker] Time on Site: ${timeOnSite.toFixed(2)}s`);
                        console.log(`[Tracker] Price (raw): ${priceRecorded.raw}`);
                        console.log(`[Tracker] Price (value): ${priceRecorded.value ? `$${priceRecorded.value.toFixed(2)}` : 'N/A'}`);
                        saveStateDebounced();
                    }).catch(() => {
                        // Fallback: capture whatever we can now
                        const priceInfo = getPagePrice();
                        priceRecorded = { raw: priceInfo.raw, value: priceInfo.value };
                        console.warn('[Tracker] Price polling failed, used immediate snapshot');
                        saveStateDebounced();
                    });
                }
            }

            // Save on click interaction
            saveStateDebounced();
        }, { capture: true, passive: true });

        // Submit listener: capture add-to-cart triggered by forms
        document.addEventListener('submit', (ev) => {
            try {
                const form = ev.target;
                // Find submit button used (if any)
                const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                const candidate = submitBtn || form;
                const isCart = candidate && isAddToCartElement(candidate);
                if (isCart && ttcRecorded === null) {
                    const now = performance.now();
                    ttcRecorded = (now - pageLoadTime) / 1000;
                    cartClickDate = new Date().toISOString();
                    capturePriceWithPolling(2000, 200).then(priceInfo => {
                        priceRecorded = { raw: priceInfo.raw, value: priceInfo.value };
                        console.log('[Tracker] ⚠️ ADD-TO-CART VIA FORM DETECTED');
                        console.log('[Tracker] Time-to-Cart (TTC):', ttcRecorded.toFixed(2) + 's');
                        saveStateDebounced();
                    }).catch(() => { saveStateDebounced(); });
                }
            } catch (e) { /* ignore form inspection errors */ }
        }, { capture: true });

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
            console.log('Cart Click Count:', cartClickCount);
            const cartClickRate = elapsed > 0 ? (cartClickCount / (elapsed / 60)) : 0;
            console.log('Cart Click Rate:', cartClickRate.toFixed(2), 'cart clicks/min');
            console.log('Total Timestamps Recorded:', clickTimestamps.length);
            console.log('---');
            
            if (ttcRecorded) {
                console.log('Time-to-Cart (TTC):', ttcRecorded.toFixed(2), 's');
            } else {
                console.log('Time-to-Cart (TTC): Not yet recorded');
            }
            
            if (productNameRecorded) {
                console.log('Product Name:', productNameRecorded);
            } else {
                console.log('Product Name: Not recorded');
            }
            
            if (priceRecorded) {
                console.log('Price (Raw):', priceRecorded.raw || 'N/A');
                console.log('Price (Value):', priceRecorded.value ? `$${priceRecorded.value.toFixed(2)}` : 'N/A');
            } else {
                console.log('Price: Not recorded');
            }
            
            // Format time on site nicely
            function formatTimeOnSite(seconds) {
                const mins = Math.floor(seconds / 60);
                const secs = Math.floor(seconds % 60);
                if (mins === 0) return `${secs}s`;
                if (mins < 60) return `${mins}m ${secs}s`;
                const hours = Math.floor(mins / 60);
                const remainingMins = mins % 60;
                return `${hours}h ${remainingMins}m ${secs}s`;
            }
            console.log('Time on Site:', formatTimeOnSite(elapsed));
            
            console.log('---');
            console.log('Peak Scroll Velocity:', peakScrollVelocity.toFixed(2), 'px/s');
            console.log('Navigation Path Length:', navPath.length);
            console.log('Current Page:', location.href);
            console.log('Base Domain:', baseDomain);
            
            // Print saved cart click history JSON
            console.log('---');
            console.log('📦 SAVED PURCHASE HISTORY (JSON):');
            
            // Check if chrome.storage is available (extension context only)
            if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
                chrome.storage.local.get(['add_to_cart_history', 'buy_now_history', 'all_purchase_attempts'], (result) => {
                    const addToCartHistory = result.add_to_cart_history || [];
                    const buyNowHistory = result.buy_now_history || [];
                    const allHistory = result.all_purchase_attempts || [];
                    
                    console.log('🛒 Add to Cart entries:', addToCartHistory.length);
                    if (addToCartHistory.length > 0) {
                        console.log('ADD_TO_CART_JSON:', JSON.stringify(addToCartHistory, null, 2));
                    }
                    
                    console.log('💳 Buy Now entries:', buyNowHistory.length);
                    if (buyNowHistory.length > 0) {
                        console.log('BUY_NOW_JSON:', JSON.stringify(buyNowHistory, null, 2));
                    }
                    
                    console.log('📊 All Purchase Attempts:', allHistory.length);
                    if (allHistory.length > 0) {
                        console.log('ALL_PURCHASES_JSON:', JSON.stringify(allHistory, null, 2));
                    }
                    
                    if (addToCartHistory.length === 0 && buyNowHistory.length === 0) {
                        console.log('No purchase attempts saved yet.');
                    }
                });
            } else {
                console.log('chrome.storage not available (not in extension context)');
            }
            
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
            getSummary: () => {
                const elapsed = (performance.now() - pageLoadTime) / 1000;
                const cartClickRate = elapsed > 0 ? (cartClickCount / (elapsed / 60)) : 0;
                return {
                    systemStartTime,
                    clicks: clickCount,
                    navPath,
                    ttc: ttcRecorded,
                    price: priceRecorded,
                    productName: productNameRecorded,
                    timeOnSite: parseFloat(elapsed.toFixed(2)),
                    peakScrollVelocity,
                    cartClickCount,
                    cartClickRate: parseFloat(cartClickRate.toFixed(2))
                };
            }
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
                if (msg && msg.type === 'GET_ADD_TO_CART_HISTORY') {
                    chrome.storage.local.get(['add_to_cart_history'], (result) => {
                        sendResponse({ history: result.add_to_cart_history || [] });
                    });
                    return true;
                }
                if (msg && msg.type === 'GET_BUY_NOW_HISTORY') {
                    chrome.storage.local.get(['buy_now_history'], (result) => {
                        sendResponse({ history: result.buy_now_history || [] });
                    });
                    return true;
                }
                if (msg && msg.type === 'GET_ALL_PURCHASE_HISTORY') {
                    chrome.storage.local.get(['all_purchase_attempts'], (result) => {
                        sendResponse({ history: result.all_purchase_attempts || [] });
                    });
                    return true;
                }
                if (msg && msg.type === 'CLEAR_PURCHASE_HISTORY') {
                    chrome.storage.local.remove(['add_to_cart_history', 'buy_now_history', 'all_purchase_attempts'], () => {
                        sendResponse({ success: true });
                    });
                    return true;
                }
            });
        } catch (e) {
            // chrome.runtime may not be available in some contexts
        }

    } catch (err) {
        console.warn('[Tracker] initialization failed', err);
    }
})();