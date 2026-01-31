/* -------------------- Behavioral Tracking & Logging -------------------- */
(function behavioralTracking() {
    try {
        // --- Configuration & State ---
        const pageLoadTime = performance.now();
        const pageLoadTimestamp = Date.now();
        let ttcRecorded = null; // Time-to-Cart (seconds)
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
            clickTimestamps.push(Date.now());
            
            // Check for Add to Cart
            const cartEl = findAncestor(ev.target, isAddToCartElement);
            if (cartEl && ttcRecorded === null) {
                const now = performance.now();
                ttcRecorded = (now - pageLoadTime) / 1000;
                console.warn(`[Tracker] Time-to-Cart (TTC): ${ttcRecorded.toFixed(2)}s`);
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
            // Only log if console is open/active to reduce noise
            // console.groupCollapsed('[Tracker] Periodic Summary');
            // ... (logging logic preserved) ...
            // console.groupEnd();
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
                peakScrollVelocity
            })
        };

    } catch (err) {
        console.warn('[Tracker] initialization failed', err);
    }
})();