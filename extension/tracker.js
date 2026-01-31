/* -------------------- Behavioral Tracking & Logging -------------------- */
(function behavioralTracking() {
    try {
    const pageLoadTime = performance.now();
    const pageLoadTimestamp = Date.now();
    const systemStartTime = new Date(pageLoadTimestamp).toISOString();

    // Click rate
    let clickCount = 0;
    const clickTimestamps = [];

    // Navigation path
    const navPath = [{ url: location.href, ts: Date.now() }];
    // Monkey-patch history API to capture SPA navigations
    (function hookHistory() {
        const _push = history.pushState;
        const _replace = history.replaceState;
        history.pushState = function (state, title, url) {
            const res = _push.apply(this, arguments);
            try {
                const resolved = url ? new URL(url, location.href).href : location.href;
                navPath.push({ url: resolved, ts: Date.now() });
                console.info('[Tracker] pushState ->', resolved);
            } catch (err) {
                try { navPath.push({ url: location.href, ts: Date.now() }); } catch (e) {}
                console.warn('[Tracker] pushState url parse failed', err);
            }
            return res;
        };
        history.replaceState = function (state, title, url) {
            const res = _replace.apply(this, arguments);
            try {
                const resolved = url ? new URL(url, location.href).href : location.href;
                navPath.push({ url: resolved, ts: Date.now() });
                console.info('[Tracker] replaceState ->', resolved);
            } catch (err) {
                try { navPath.push({ url: location.href, ts: Date.now() }); } catch (e) {}
                console.warn('[Tracker] replaceState url parse failed', err);
            }
            return res;
        };
        window.addEventListener('popstate', () => {
            try { navPath.push({ url: location.href, ts: Date.now() }); } catch (e) {}
            console.info('[Tracker] popstate ->', location.href);
        });
    })();

    // Time-to-Cart
    let ttcRecorded = null; // seconds

    // Scroll velocity peak
    let lastScrollY = window.scrollY;
    let lastScrollTime = performance.now();
    let peakScrollVelocity = 0; // pixels per second

    // Utility: find ancestor matching predicate
    function findAncestor(el, predicate) {
        while (el) {
            try { if (predicate(el)) return el; } catch (e) {}
            el = el.parentElement;
        }
        return null;
    }

    // Detect add-to-cart clicks (text-based heuristics + common attrs)
    function isAddToCartElement(el) {
        if (!el) return false;
        const tag = el.tagName && el.tagName.toLowerCase();
        const text = (el.innerText || el.value || '').trim().toLowerCase();
        const attrs = '' + (el.getAttribute && el.getAttribute('id') || '') + ' ' + (el.getAttribute && el.getAttribute('class') || '');
        const attrStr = attrs.toLowerCase();

        const addPhrases = ['add to cart', 'add to bag', 'add to basket', 'add to cart', 'add to trolley', 'buy now', 'add to order', 'add to cart +'];
        if (addPhrases.some(p => text.includes(p))) return true;
        if (/(add_to_cart|addtocart|add-to-cart|btn-add|add-to-basket|add-to-bag)/i.test(attrStr)) return true;
        // input[type=submit] with value
        if (tag === 'input' && (el.type === 'submit' || el.type === 'button') && addPhrases.some(p => (el.value||'').toLowerCase().includes(p))) return true;
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
    }, { capture: true, passive: true });

    // Scroll listener to compute velocity
    window.addEventListener('scroll', () => {
        const now = performance.now();
        const y = window.scrollY;
        const dy = Math.abs(y - lastScrollY);
        const dt = Math.max(6, now - lastScrollTime); // ms
        const v = (dy / dt) * 1000; // px/s
        if (v > peakScrollVelocity) peakScrollVelocity = v;
        lastScrollY = y;
        lastScrollTime = now;
    }, { passive: true });

    // Periodic summary log
    const summaryInterval = setInterval(() => {
        const elapsed = (performance.now() - pageLoadTime) / 1000;
        const clickRate = elapsed > 0 ? (clickCount / elapsed) : 0; // clicks per second
        console.groupCollapsed('[Tracker] Periodic Summary');
        console.log('System time:', new Date().toISOString());
        console.log('Elapsed (s):', elapsed.toFixed(2));
        console.log('Click count:', clickCount, 'Click rate (clicks/sec):', clickRate.toFixed(3));
        console.log('Navigation path:', navPath.map(i => i.url));
        console.log('TTC (s):', ttcRecorded === null ? 'not yet' : ttcRecorded.toFixed(2));
        console.log('Peak scroll velocity (px/s):', Math.round(peakScrollVelocity));
        console.groupEnd();
    }, 10000);

    // Before unload: final report
    window.addEventListener('beforeunload', () => {
        try {
            const elapsed = (performance.now() - pageLoadTime) / 1000;
            const clickRate = elapsed > 0 ? (clickCount / elapsed) : 0;
            console.group('[Tracker] Final Report');
            console.log('System time (end):', new Date().toISOString());
            console.log('Time on site (s):', elapsed.toFixed(2));
            console.log('Click count:', clickCount);
            console.log('Click rate (clicks/sec):', clickRate.toFixed(3));
            console.log('Navigation path:', navPath);
            console.log('TTC (s):', ttcRecorded === null ? 'not recorded' : ttcRecorded.toFixed(2));
            console.log('Peak scroll velocity (px/s):', Math.round(peakScrollVelocity));
            console.groupEnd();
        } catch (e) {
            console.error('Tracker final report failed', e);
        }
        clearInterval(summaryInterval);
    });

    // Also log visibility change (user leaves tab)
    document.addEventListener('visibilitychange', () => {
        console.log('[Tracker] visibilitychange:', document.visibilityState, new Date().toISOString());
    });

    // Expose a debug handle
    window.__shoppingTracker = {
        getSummary: () => ({
            systemStartTime,
            clicks: clickCount,
            clickTimestamps,
            navPath,
            ttc: ttcRecorded,
            peakScrollVelocity
        })
    };
    } catch (err) {
        console.warn('[Tracker] initialization failed, tracker disabled to avoid page errors', err);
    }
})();
