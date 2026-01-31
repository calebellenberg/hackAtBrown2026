
// Generic overlay builder used for both shopping and gambling messages
function createOverlay(opts = {}) {
    const {
        title = 'DO NOT SHOP',
        message = 'Look at yourself. Do you really need this?',
        challenge = "I understand that I am about to shop and I am in a healthy state of mind",
        onUnlock = null
    } = opts;

    const overlay = document.createElement('div');
    overlay.classList.add('stop-shopping-overlay');

    const cameraPageUrl = chrome.runtime.getURL('camera.html');

    overlay.innerHTML = `
        <div class="lock-box">
            <h1>${title}</h1>
            
            <div class="camera-container">
                <iframe src="${cameraPageUrl}" allow="camera" frameborder="0"></iframe>
            </div>

            <p>${message}</p>
            <p>To proceed, type the following:</p>
            <p class="challenge-text">${challenge}</p>
            <input type="text" id="unlock-input" placeholder="Type here..." autocomplete="off">
        </div>
    `;

    document.body.appendChild(overlay);

    const inputField = overlay.querySelector('#unlock-input');

    inputField.addEventListener('input', (e) => {
        if (e.target.value === challenge) {
            overlay.remove();
            try { if (typeof onUnlock === 'function') onUnlock(); } catch (err) { console.warn('onUnlock handler failed', err); }
        }
    });

    // Block pasting
    inputField.addEventListener('paste', (e) => {
        e.preventDefault();
        alert("Don't cheat. Look at yourself and type it.");
    });
}

// Basic hostname matcher: checks exact match or subdomain match
function hostMatchesDomain(hostname, domain) {
    if (!domain) return false;
    domain = domain.toLowerCase();
    hostname = hostname.toLowerCase();
    return hostname === domain || hostname.endsWith('.' + domain);
}

// Derive a simple base domain (eTLD+1 approximation) for session-wide keys.
// This is a heuristic: for common hosts like 'www.amazon.com' -> 'amazon.com'.
function getBaseDomain(hostname) {
    if (!hostname) return hostname;
    const parts = hostname.toLowerCase().split('.');
    if (parts.length <= 2) return hostname;
    // Handle common second-level TLDs like co.uk, com.au by keeping last 3 if second last is length <= 3
    const secondLast = parts[parts.length - 2];
    const last = parts[parts.length - 1];
    // crude check for country-code TLDs with short second-level labels
    if (secondLast.length <= 3 && last.length <= 3) {
        return parts.slice(-3).join('.');
    }
    return parts.slice(-2).join('.');
}

// Decide which overlay to show by checking gambling list; shopping is default
const DISABLE_KEY_PREFIX = 'stop_shopping.disabled:';

(async function decideOverlay() {
    const host = window.location.hostname;
    const baseDomain = getBaseDomain(host);
    const disableKey = DISABLE_KEY_PREFIX + baseDomain;

    // If the user already disabled the overlay for this site (base domain) in this session, do nothing
    try {
        if (sessionStorage.getItem(disableKey) === '1') {
            console.info('[Overlay] previously dismissed for', baseDomain);
            return;
        }
    } catch (e) {
        // sessionStorage may be unavailable in some contexts; ignore
    }
    let isGambling = false;
    try {
        const url = chrome.runtime.getURL('gambling_sites.json');
        const res = await fetch(url);
        const list = await res.json();
        if (Array.isArray(list)) {
            isGambling = list.some(d => hostMatchesDomain(host, d));
        }
    } catch (e) {
        // If fetch fails, fall back to not gambling
        console.warn('Failed to load gambling_sites.json', e);
    }

    if (isGambling) {
        createOverlay({
            title: 'DO NOT GAMBLE',
            message: 'Gambling can be addictive — pause and think before you wager.',
            challenge: 'I understand that I am about to gamble and I will make a rational decision',
            onUnlock: () => {
                try { sessionStorage.setItem(disableKey, '1'); } catch (e) {}
            }
        });
    } else {
        createOverlay({
            onUnlock: () => {
                try { sessionStorage.setItem(disableKey, '1'); } catch (e) {}
            }
        });
    }
})();
/* -------------------- Behavioral Tracking & Logging -------------------- */
(function behavioralTracking() {
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
            navPath.push({ url: new URL(url, location.href).href, ts: Date.now() });
            console.info('[Tracker] pushState ->', url);
            return res;
        };
        history.replaceState = function (state, title, url) {
            const res = _replace.apply(this, arguments);
            navPath.push({ url: new URL(url, location.href).href, ts: Date.now() });
            console.info('[Tracker] replaceState ->', url);
            return res;
        };
        window.addEventListener('popstate', () => {
            navPath.push({ url: location.href, ts: Date.now() });
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
})();


