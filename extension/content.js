
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
                console.log('[content.js] Amazon price found with selector:', selector, 'Price:', raw);
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
            console.log('[content.js] Amazon price combined from whole+fraction:', raw);
            return { raw, value };
        }
    }
    
    // Fallback: look for any element with aria-label containing price
    const ariaPrice = document.querySelector('[aria-label*="$"]');
    if (ariaPrice) {
        const ariaLabel = ariaPrice.getAttribute('aria-label');
        const value = parsePrice(ariaLabel);
        if (value && value > 0) {
            console.log('[content.js] Amazon price found via aria-label:', ariaLabel);
            return { raw: ariaLabel, value };
        }
    }

    console.log('[content.js] Amazon price not found with any selector');
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
                    console.log('[content.js] Generic price found via data attribute:', dataPrice);
                    return { raw: `$${value}`, value };
                }
            }
            // Then check text content
            const text = el.textContent?.trim() || '';
            if (text.match(/[$€£]\s?\d+/)) {
                const value = parsePrice(text);
                if (value && value > 0) {
                    console.log('[content.js] Generic price found with selector:', selector, 'Price:', text);
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
            if (value && value > 0 && value < 100000) { // Sanity check
                console.log('[content.js] Generic price found via text scan:', text);
                return { raw: text, value };
            }
        }
    }

    console.log('[content.js] Generic price not found');
    return { raw: null, value: null };
}

function getPagePrice() {
    const site = getSite();
    if (site === 'amazon') return getAmazonPrice();
    if (site === 'shopify') return getShopifyPrice();
    return getGenericPrice();
}

// Product name extraction utilities
function getAmazonProductName() {
    const selectors = [
        '#productTitle',
        '#title',
        'h1#title span',
        '[data-feature-name="title"]',
        'h1.product-title-word-break'
    ];
    for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (el?.textContent) {
            const name = el.textContent.trim();
            if (name.length > 0) {
                console.log('[content.js] Amazon product name found:', name.substring(0, 50) + '...');
                return name;
            }
        }
    }
    return null;
}

function getShopifyProductName() {
    const selectors = [
        'h1.product__title',
        'h1.product-title',
        '.product-single__title',
        '[data-product-title]',
        'h1[itemprop="name"]'
    ];
    for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (el?.textContent) {
            const name = el.textContent.trim();
            if (name.length > 0) return name;
        }
    }
    return null;
}

function getGenericProductName() {
    const selectors = [
        'h1[itemprop="name"]',
        'h1.product-name',
        'h1.product-title',
        '.product-name h1',
        '.product-title h1',
        'h1.pdp-title',
        '[data-testid="product-title"]',
        'h1'
    ];
    for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (el?.textContent) {
            const name = el.textContent.trim();
            // Filter out generic headers
            if (name.length > 0 && name.length < 500 && 
                !name.toLowerCase().includes('shopping cart') &&
                !name.toLowerCase().includes('sign in')) {
                return name;
            }
        }
    }
    // Fallback: try document title
    const docTitle = document.title;
    if (docTitle && docTitle.length > 0) {
        // Remove common suffixes like "| Amazon.com" or "- Best Buy"
        return docTitle.split(/[|\-–—]/)[0].trim();
    }
    return null;
}

function getProductName() {
    const site = getSite();
    if (site === 'amazon') return getAmazonProductName();
    if (site === 'shopify') return getShopifyProductName();
    return getGenericProductName();
}

// Generic overlay builder used for both shopping and gambling messages
const pageLoadTime = Date.now();
function createOverlay(opts = {}) {
    const {
        title = 'STOP AND THINK',
        message = 'Look at yourself. Do you really need this?',
        challenge = "I understand that I am about to shop and I am in a healthy state of mind",
        onUnlock = null
    } = opts;

    const overlay = document.createElement('div');
    overlay.classList.add('stop-shopping-overlay');

    const cameraPageUrl = chrome.runtime.getURL('camera.html');

    // If a price was provided, include it in the overlay content
    const priceHtml = opts.price ? `<p style="font-size:18px;margin:10px 0;color:#d9534f">Price: <strong>${opts.price}</strong></p>` : '';
    
    // If a product name was provided, include it
    const productNameHtml = opts.productName ? `<p style="font-size:14px;margin:10px 0;color:#fff;max-width:500px;word-wrap:break-word;"><strong>${opts.productName}</strong></p>` : '';

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
            <p style="font-size:14px;margin:5px 0;color:#666;">${dateString} | ${timeString} | Time on site: <strong style="color:#d9534f;">${formatDuration(timeSpentMs)}</strong></p>
            ${priceHtml}
            <div class="camera-container">
                <iframe src="${cameraPageUrl}" allow="camera" frameborder="0"></iframe>
            </div>
            <p>${message} To proceed, type the following:</p>
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
            console.log('Purchase button clicked - intercepting');
            const result = getPagePrice();
            const productName = getProductName();
            const priceDisplay = result.raw || (result.value ? `$${result.value}` : 'Price not found');
            const clickTime = Date.now();
            
            // Get button text to distinguish Add to Cart vs Buy Now
            const buttonText = (button.innerText || button.value || button.getAttribute('aria-label') || '').trim();

            // Dispatch custom event with price AND cart click data for tracker.js
            const cartEvent = new CustomEvent('stop-shopping-cart-click', {
                detail: { 
                    raw: result.raw, 
                    value: result.value,
                    productName: productName,
                    buttonText: buttonText,
                    timestamp: clickTime,
                    cartClickDate: new Date(clickTime).toISOString()
                }
            });
            window.dispatchEvent(cartEvent);
            console.log('[content.js] Dispatched cart click event with price:', result, 'product:', productName);

            const overlayOpts = isGambling ? {
                title: 'DO NOT GAMBLE',
                message: 'Gambling can be addictive — pause and think before you wager.',
                challenge: 'I understand that I am about to gamble and I will make a rational decision',
                price: priceDisplay,
                productName: productName
            } : {
                price: priceDisplay,
                productName: productName
            };

            createOverlay(overlayOpts);

            // Prevent the actual add-to-cart action
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            
            // For form-based add-to-cart buttons, also disable the form temporarily
            const form = button.closest('form');
            if (form) {
                const originalAction = form.action;
                form.action = 'javascript:void(0)';
                setTimeout(() => { form.action = originalAction; }, 100);
            }
            
            return false;
        }, true);
    }

    // Expose find/attach logic (re-implemented from dist)
    function findAndInterceptPurchaseButtons() {
        const selectors = [
            // Add to Cart selectors
            '#add-to-cart-button',
            '#addToCart',
            '#submit.add-to-cart-button',
            '[name="submit.add-to-cart"]',
            'input[name="submit.add-to-cart"]',
            '[data-feature-name="add-to-cart"]',
            'input[value="Add to Cart"]',
            'input[value="Add to cart"]',
            'button[aria-label*="Add to Cart"]',
            'button[aria-label*="Add to cart"]',
            '.add-to-cart-button',
            '[data-action="add-to-cart"]',
            '.add-to-cart',
            '[data-testid="add-to-cart"]',
            
            // Buy Now selectors
            '#buy-now-button',
            '#buyNow',
            '#submit.buy-now-button',
            '[name="submit.buy-now"]',
            'input[name="submit.buy-now"]',
            '[data-feature-name="buy-now"]',
            'input[value="Buy Now"]',
            'input[value="Buy now"]',
            'button[aria-label*="Buy Now"]',
            'button[aria-label*="Buy now"]',
            '.buy-now-button',
            '[data-action="buy-now"]',
            '.buy-now',
            '[data-testid="buy-now"]',
            '#one-click-button',
            '#turbo-checkout-pyo-button',
            '[data-feature-name="turbo-checkout"]',
            '#submitOrderButtonId',
            '.instant-buy',
            '[data-action="checkout"]'
        ];

        const findAllButtons = () => {
            const buttons = [];
            for (const sel of selectors) {
                const matches = document.querySelectorAll(sel);
                matches.forEach(btn => {
                    if (!btn.dataset.intercepted) {
                        console.log('[content.js] Found purchase button with selector:', sel);
                        buttons.push(btn);
                    }
                });
            }
            return buttons;
        };

        const interceptAll = () => {
            const buttons = findAllButtons();
            buttons.forEach(btn => attachClickListener(btn));
            return buttons.length;
        };

        const count = interceptAll();
        if (count === 0) {
            console.log('[content.js] No purchase buttons found yet, setting up observer');
        }
        
        // Always set up observer to catch dynamically added buttons
        const observer = new MutationObserver(() => {
            interceptAll();
        });
        observer.observe(document.body, { childList: true, subtree: true });
        
        // Also intercept form submissions for add-to-cart and buy-now forms
        document.addEventListener('submit', (e) => {
            const form = e.target;
            const isCartForm = form.id === 'addToCart' || 
                               form.querySelector('#add-to-cart-button') ||
                               form.querySelector('[name="submit.add-to-cart"]');
            const isBuyNowForm = form.id === 'buyNow' ||
                                 form.querySelector('#buy-now-button') ||
                                 form.querySelector('[name="submit.buy-now"]') ||
                                 form.querySelector('#one-click-button');
            
            if ((isCartForm || isBuyNowForm) && !form.dataset.overlayShown) {
                console.log('[content.js] Intercepting purchase form submission');
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                
                form.dataset.overlayShown = 'true';
                
                const result = getPagePrice();
                const productName = getProductName();
                const priceDisplay = result.raw || (result.value ? `$${result.value}` : 'Price not found');
                
                // Determine button text for action type
                const buttonText = isBuyNowForm ? 'Buy Now' : 'Add to Cart';
                
                // Dispatch event for tracker.js
                const cartEvent = new CustomEvent('stop-shopping-cart-click', {
                    detail: { 
                        raw: result.raw, 
                        value: result.value,
                        productName: productName,
                        buttonText: buttonText,
                        timestamp: Date.now(),
                        cartClickDate: new Date().toISOString()
                    }
                });
                window.dispatchEvent(cartEvent);
                
                createOverlay({ price: priceDisplay, productName: productName });
                
                // Reset after a delay so they can try again after overlay
                setTimeout(() => { form.dataset.overlayShown = ''; }, 1000);
                
                return false;
            }
        }, true);
    }

    try { findAndInterceptPurchaseButtons(); } catch (e) { console.warn('Purchase button interception failed', e); }

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



