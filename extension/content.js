
// Price extraction utilities (from dist)
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

// Generic overlay builder used for both shopping and gambling messages
const pageLoadTime = Date.now();
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

    // If a price was provided, include it in the overlay content
    const priceHtml = opts.price ? `<p style="font-size:18px;margin:10px 0;color:#d9534f">Price: <strong>${opts.price}</strong></p>` : '';

    // Get current system time and time spent
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    const dateString = now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
    const timeSpentMs = Date.now() - pageLoadTime;
    function formatDuration(milliseconds) {
        const totalSeconds = Math.floor(milliseconds / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        if (minutes === 0) return `${seconds}s`;
        if (minutes < 60) return `${minutes}m ${seconds}s`;
        const hours = Math.floor(minutes / 60);
        const remainingMinutes = minutes % 60;
        return `${hours}h ${remainingMinutes}m ${seconds}s`;
    }

    overlay.innerHTML = `
        <div class="lock-box">
            <h1>${title}</h1>
            <p style="font-size:14px;margin:5px 0;color:#666;">📅 ${dateString} | 🕐 ${timeString}</p>
            <p style="font-size:14px;margin:5px 0;color:#666;">⏱️ Time on site: <strong style="color:#d9534f;">${formatDuration(timeSpentMs)}</strong></p>
            ${priceHtml}
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

// Initialization: load gambling list and attach Add-to-Cart interception
(async function init() {
    const host = window.location.hostname;
    const baseDomain = getBaseDomain(host);
    const disableKey = DISABLE_KEY_PREFIX + baseDomain;

    // Load gambling list (best-effort)
    let isGambling = false;
    try {
        const url = chrome.runtime.getURL('gambling_sites.json');
        const res = await fetch(url);
        const list = await res.json();
        if (Array.isArray(list)) {
            isGambling = list.some(d => hostMatchesDomain(host, d));
        }
    } catch (e) {
        console.warn('Failed to load gambling_sites.json', e);
    }

    // Find and intercept add-to-cart. If user has dismissed overlay for site, skip interception.
    function attachClickListener(button) {
        if (button.dataset.intercepted) return;
        button.dataset.intercepted = 'true';

        button.addEventListener('click', (e) => {
            try {
                // If user disabled overlay for this base domain in this session, allow default behavior
                if (sessionStorage.getItem(disableKey) === '1') return;
            } catch (err) {}

            console.log('Add to Cart clicked - intercepting');
            const result = getPagePrice();
            const priceDisplay = result.raw || (result.value ? `$${result.value}` : 'Price not found');

            const overlayOpts = isGambling ? {
                title: 'DO NOT GAMBLE',
                message: 'Gambling can be addictive — pause and think before you wager.',
                challenge: 'I understand that I am about to gamble and I will make a rational decision',
                price: priceDisplay,
                onUnlock: () => { try { sessionStorage.setItem(disableKey, '1'); } catch (e) {} }
            } : {
                price: priceDisplay,
                onUnlock: () => { try { sessionStorage.setItem(disableKey, '1'); } catch (e) {} }
            };

            createOverlay(overlayOpts);

            // Prevent the actual add-to-cart action temporarily while overlay is visible
            e.preventDefault();
            e.stopPropagation();
        }, true);
    }

    // Expose find/attach logic (re-implemented from dist)
    function findAndInterceptAddToCartButton() {
        const selectors = [
            '#add-to-cart-button',
            '#addToCart',
            '[data-feature-name="add-to-cart"]',
            'input[value="Add to Cart"]',
            'button[aria-label*="Add to Cart"]'
        ];

        const findButton = () => {
            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn) return btn;
            }
            return null;
        };

        let button = findButton();
        if (!button) {
            const observer = new MutationObserver(() => {
                button = findButton();
                if (button && !button.dataset.intercepted) {
                    attachClickListener(button);
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        } else if (!button.dataset.intercepted) {
            attachClickListener(button);
        }
    }

    try { findAndInterceptAddToCartButton(); } catch (e) { console.warn('Add-to-cart interception failed', e); }

    // Backwards-compatible message API for GET_PRICE
    try {
        chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
            if (msg && msg.type === 'GET_PRICE') {
                const result = getPagePrice();
                sendResponse({ price: result.raw, value: result.value });
            }
        });
    } catch (e) {
        // chrome.runtime may not be available in some contexts
    }
})();



