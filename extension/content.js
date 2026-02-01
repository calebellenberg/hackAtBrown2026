
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

// ===================== INTERVENTION OVERLAY FUNCTIONS =====================

// Helper function to format time duration
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

// Remove any existing intervention overlays
function removeExistingOverlays() {
    const selectors = [
        '.stop-shopping-overlay',
        '.intervention-overlay',
        '#loading-overlay',
        '#impulse-mirror-overlay',
        '#impulse-cooldown-overlay',
        '#impulse-phrase-overlay'
    ];
    const existing = document.querySelectorAll(selectors.join(', '));
    console.log('[content.js] Removing', existing.length, 'existing overlays');
    existing.forEach(el => el.remove());
}

// MIRROR intervention: Camera-focused overlay with reasoning, simple continue button
function createMirrorOverlay(opts = {}) {
    removeExistingOverlays();
    
    const { reasoning = '', price = '', productName = '', impulseScore = 0, onContinue = null } = opts;
    
    const overlay = document.createElement('div');
    overlay.id = 'impulse-mirror-overlay';
    
    const cameraPageUrl = chrome.runtime.getURL('camera.html');
    const timeSpentMs = Date.now() - pageLoadTime;
    const scorePercent = Math.round(impulseScore * 100);
    
    // Inline styles for guaranteed visibility
    overlay.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        background: linear-gradient(135deg, rgba(0,0,0,0.95) 0%, rgba(20,20,40,0.98) 100%) !important;
        z-index: 2147483647 !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    `;
    
    overlay.innerHTML = `
        <div style="background: linear-gradient(145deg, #1e1e2e, #2a2a4a); padding: 40px; border-radius: 20px; max-width: 500px; width: 90%; text-align: center; color: white; box-shadow: 0 25px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.1);">
            <div style="margin-bottom: 20px;">
                <span style="font-size: 48px;">🪞</span>
                <h1 style="margin: 10px 0 0; font-size: 28px; color: #4ecdc4;">Take a Moment to Reflect</h1>
            </div>
            
            <div style="margin: 20px 0;">
                <div style="background: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #4ecdc4, #44cf6c); height: 100%; width: ${scorePercent}%; border-radius: 10px; transition: width 0.5s;"></div>
                </div>
                <span style="color: rgba(255,255,255,0.7); font-size: 14px; margin-top: 8px; display: block;">Impulse Score: ${scorePercent}%</span>
            </div>
            
            <div style="margin: 20px 0; border-radius: 12px; overflow: hidden; background: #000;">
                <iframe src="${cameraPageUrl}" allow="camera" frameborder="0" style="width: 100%; height: 200px; border: none;"></iframe>
            </div>
            
            <div style="margin: 15px 0; color: rgba(255,255,255,0.8);">
                ${productName ? `<p style="margin: 5px 0; font-size: 16px; font-weight: 600;">${productName}</p>` : ''}
                ${price ? `<p style="margin: 5px 0; color: #ff6b6b; font-size: 20px; font-weight: bold;">${price}</p>` : ''}
                <p style="margin: 5px 0; color: rgba(255,255,255,0.5); font-size: 13px;">Time on site: ${formatDuration(timeSpentMs)}</p>
            </div>
            
            <div style="background: rgba(78,205,196,0.15); border-left: 4px solid #4ecdc4; padding: 15px; margin: 20px 0; text-align: left; border-radius: 0 8px 8px 0;">
                <p style="margin: 0 0 8px; font-weight: 600; color: #4ecdc4; font-size: 14px;">Why we're asking you to pause:</p>
                <p style="margin: 0; color: rgba(255,255,255,0.9); line-height: 1.5; font-size: 14px;">${reasoning}</p>
            </div>
            
            <button id="mirror-continue-btn" style="background: linear-gradient(135deg, #4ecdc4, #44cf6c); color: #000; border: none; padding: 15px 30px; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer; width: 100%; transition: transform 0.2s, box-shadow 0.2s;">
                I've reflected. Continue with purchase.
            </button>
        </div>
    `;
    
    document.body.appendChild(overlay);
    console.log('[content.js] MIRROR overlay created and appended');
    
    document.getElementById('mirror-continue-btn').addEventListener('click', () => {
        overlay.remove();
        if (typeof onContinue === 'function') onContinue();
    });
}

// COOLDOWN intervention: Timer overlay, must wait before proceeding
function createCooldownOverlay(opts = {}) {
    removeExistingOverlays();
    
    const { reasoning = '', price = '', productName = '', impulseScore = 0, cooldownSeconds = 30, onComplete = null } = opts;
    
    const overlay = document.createElement('div');
    overlay.id = 'impulse-cooldown-overlay';
    
    const cameraPageUrl = chrome.runtime.getURL('camera.html');
    const timeSpentMs = Date.now() - pageLoadTime;
    const scorePercent = Math.round(impulseScore * 100);
    
    // Inline styles for guaranteed visibility
    overlay.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        background: linear-gradient(135deg, rgba(20,0,0,0.98) 0%, rgba(40,10,10,0.98) 100%) !important;
        z-index: 2147483647 !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    `;
    
    overlay.innerHTML = `
        <div style="background: linear-gradient(145deg, #2e1e1e, #4a2a2a); padding: 40px; border-radius: 20px; max-width: 500px; width: 90%; text-align: center; color: white; box-shadow: 0 25px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,100,100,0.2);">
            <div style="margin-bottom: 20px;">
                <span style="font-size: 48px;">⏱️</span>
                <h1 style="margin: 10px 0 0; font-size: 28px; color: #ff6b6b;">Cool Down Period</h1>
            </div>
            
            <div style="margin: 20px 0;">
                <div style="background: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #ff6b6b, #ffa500); height: 100%; width: ${scorePercent}%; border-radius: 10px;"></div>
                </div>
                <span style="color: #ff6b6b; font-size: 14px; margin-top: 8px; display: block; font-weight: 600;">Impulse Score: ${scorePercent}% (High Risk)</span>
            </div>
            
            <div id="timer-container" style="margin: 25px 0;">
                <div id="timer-circle" style="width: 120px; height: 120px; border-radius: 50%; background: linear-gradient(145deg, #3a2020, #5a3030); display: flex; flex-direction: column; justify-content: center; align-items: center; margin: 0 auto; box-shadow: 0 10px 30px rgba(0,0,0,0.4), inset 0 2px 10px rgba(255,255,255,0.05);">
                    <span id="timer-value" style="font-size: 48px; font-weight: bold; color: #ff6b6b;">${cooldownSeconds}</span>
                    <span style="font-size: 12px; color: rgba(255,255,255,0.5); text-transform: uppercase; letter-spacing: 1px;">seconds</span>
                </div>
            </div>
            
            <div style="margin: 20px 0; border-radius: 12px; overflow: hidden; background: #000; max-height: 150px;">
                <iframe src="${cameraPageUrl}" allow="camera" frameborder="0" style="width: 100%; height: 150px; border: none;"></iframe>
            </div>
            
            <div style="margin: 15px 0; color: rgba(255,255,255,0.8);">
                ${productName ? `<p style="margin: 5px 0; font-size: 16px; font-weight: 600;">${productName}</p>` : ''}
                ${price ? `<p style="margin: 5px 0; color: #ff6b6b; font-size: 20px; font-weight: bold;">${price}</p>` : ''}
                <p style="margin: 5px 0; color: rgba(255,255,255,0.5); font-size: 13px;">Time on site: ${formatDuration(timeSpentMs)}</p>
            </div>
            
            <div style="background: rgba(255,107,107,0.15); border-left: 4px solid #ff6b6b; padding: 15px; margin: 20px 0; text-align: left; border-radius: 0 8px 8px 0;">
                <p style="margin: 0 0 8px; font-weight: 600; color: #ff6b6b; font-size: 14px;">This purchase was flagged because:</p>
                <p style="margin: 0; color: rgba(255,255,255,0.9); line-height: 1.5; font-size: 14px;">${reasoning}</p>
            </div>
            
            <button id="cooldown-continue-btn" disabled style="background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.4); border: none; padding: 15px 30px; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: not-allowed; width: 100%;">
                Please wait...
            </button>
        </div>
    `;
    
    document.body.appendChild(overlay);
    console.log('[content.js] COOLDOWN overlay created and appended');
    
    const timerValue = document.getElementById('timer-value');
    const continueBtn = document.getElementById('cooldown-continue-btn');
    const timerCircle = document.getElementById('timer-circle');
    let remaining = cooldownSeconds;
    
    const countdown = setInterval(() => {
        remaining--;
        timerValue.textContent = remaining;
        
        if (remaining <= 0) {
            clearInterval(countdown);
            continueBtn.disabled = false;
            continueBtn.textContent = 'Continue with purchase';
            continueBtn.style.cssText = 'background: linear-gradient(135deg, #ff6b6b, #ffa500); color: #000; border: none; padding: 15px 30px; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer; width: 100%;';
            timerCircle.style.background = 'linear-gradient(145deg, #2a4a2a, #3a6a3a)';
            timerValue.style.color = '#44cf6c';
        }
    }, 1000);
    
    continueBtn.addEventListener('click', () => {
        if (!continueBtn.disabled) {
            clearInterval(countdown);
            overlay.remove();
            if (typeof onComplete === 'function') onComplete();
        }
    });
}

// PHRASE intervention: Must type a phrase to proceed (strongest intervention)
function createPhraseOverlay(opts = {}) {
    removeExistingOverlays();
    
    const { 
        reasoning = '', 
        price = '', 
        productName = '', 
        impulseScore = 0,
        challenge = "I understand this may be an impulse purchase and I choose to proceed",
        onUnlock = null 
    } = opts;
    
    const overlay = document.createElement('div');
    overlay.id = 'impulse-phrase-overlay';
    
    const cameraPageUrl = chrome.runtime.getURL('camera.html');
    const timeSpentMs = Date.now() - pageLoadTime;
    const scorePercent = Math.round(impulseScore * 100);
    
    // Inline styles for guaranteed visibility
    overlay.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        background: linear-gradient(135deg, rgba(40,0,0,0.98) 0%, rgba(60,10,10,0.98) 100%) !important;
        z-index: 2147483647 !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    `;
    
    overlay.innerHTML = `
        <div style="background: linear-gradient(145deg, #3e1e1e, #5a2a2a); padding: 40px; border-radius: 20px; max-width: 550px; width: 90%; text-align: center; color: white; box-shadow: 0 25px 80px rgba(0,0,0,0.6), 0 0 0 2px rgba(255,50,50,0.3);">
            <div style="margin-bottom: 20px;">
                <span style="font-size: 48px;">⚠️</span>
                <h1 style="margin: 10px 0 0; font-size: 28px; color: #ff4444;">High Impulse Alert</h1>
            </div>
            
            <div style="margin: 20px 0;">
                <div style="background: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #ff4444, #ff0000); height: 100%; width: ${scorePercent}%; border-radius: 10px;"></div>
                </div>
                <span style="color: #ff4444; font-size: 14px; margin-top: 8px; display: block; font-weight: 700;">⚠️ Impulse Score: ${scorePercent}% (CRITICAL)</span>
            </div>
            
            <div style="margin: 20px 0; border-radius: 12px; overflow: hidden; background: #000;">
                <iframe src="${cameraPageUrl}" allow="camera" frameborder="0" style="width: 100%; height: 180px; border: none;"></iframe>
            </div>
            
            <div style="margin: 15px 0; color: rgba(255,255,255,0.8);">
                ${productName ? `<p style="margin: 5px 0; font-size: 16px; font-weight: 600;">${productName}</p>` : ''}
                ${price ? `<p style="margin: 5px 0; color: #ff4444; font-size: 22px; font-weight: bold;">${price}</p>` : ''}
                <p style="margin: 5px 0; color: rgba(255,255,255,0.5); font-size: 13px;">Time on site: ${formatDuration(timeSpentMs)}</p>
            </div>
            
            <div style="background: rgba(255,68,68,0.2); border: 2px solid #ff4444; padding: 15px; margin: 20px 0; text-align: left; border-radius: 8px;">
                <p style="margin: 0 0 8px; font-weight: 700; color: #ff4444; font-size: 14px;">⚠️ Strong Warning:</p>
                <p style="margin: 0; color: rgba(255,255,255,0.95); line-height: 1.5; font-size: 14px;">${reasoning}</p>
            </div>
            
            <div style="background: rgba(0,0,0,0.3); padding: 20px; border-radius: 12px; margin-top: 20px;">
                <p style="margin: 0 0 10px; color: rgba(255,255,255,0.8); font-size: 14px;">To proceed, type the following phrase exactly:</p>
                <p style="margin: 0 0 15px; color: #ff6b6b; font-size: 15px; font-style: italic; background: rgba(255,107,107,0.1); padding: 12px; border-radius: 8px; word-break: break-word;">"${challenge}"</p>
                <input id="phrase-input" type="text" placeholder="Type the phrase here..." autocomplete="off" 
                    style="width: 100%; padding: 15px; font-size: 16px; border: 2px solid rgba(255,255,255,0.2); border-radius: 10px; background: rgba(0,0,0,0.4); color: white; box-sizing: border-box; outline: none; transition: border-color 0.2s;"
                    onfocus="this.style.borderColor='#ff6b6b'" onblur="this.style.borderColor='rgba(255,255,255,0.2)'">
            </div>
        </div>
    `;
    
    document.body.appendChild(overlay);
    console.log('[content.js] PHRASE overlay created and appended');
    
    const inputField = document.getElementById('phrase-input');
    
    inputField.addEventListener('input', (e) => {
        if (e.target.value === challenge) {
            console.log('[content.js] Phrase matched! Removing overlay.');
            overlay.remove();
            if (typeof onUnlock === 'function') onUnlock();
        }
    });
    
    // Block pasting
    inputField.addEventListener('paste', (e) => {
        e.preventDefault();
        alert("Please type the phrase manually to confirm you've read it.");
    });
    
    // Focus the input after a short delay
    setTimeout(() => inputField.focus(), 100);
}

// Show the appropriate intervention based on the analysis result
function showInterventionOverlay(interventionAction, opts = {}) {
    console.log('[content.js] 🎯 showInterventionOverlay called');
    console.log('[content.js] Intervention action:', interventionAction);
    console.log('[content.js] Options:', JSON.stringify(opts, null, 2));
    
    try {
        switch (interventionAction) {
            case 'NONE':
                // No intervention needed - allow purchase
                console.log('[content.js] ✅ No intervention needed');
                return false;
                
            case 'MIRROR':
                console.log('[content.js] 🪞 Creating MIRROR overlay...');
                createMirrorOverlay(opts);
                return true;
                
            case 'COOLDOWN':
                console.log('[content.js] ⏱️ Creating COOLDOWN overlay...');
                createCooldownOverlay({ ...opts, cooldownSeconds: 30 });
                return true;
                
            case 'PHRASE':
                console.log('[content.js] ⚠️ Creating PHRASE overlay...');
                createPhraseOverlay(opts);
                return true;
                
            default:
                // Default to MIRROR for unknown intervention types
                console.log('[content.js] ❓ Unknown intervention type "' + interventionAction + '", defaulting to MIRROR');
                createMirrorOverlay(opts);
                return true;
        }
    } catch (error) {
        console.error('[content.js] ❌ Error creating intervention overlay:', error);
        alert('Error creating intervention: ' + error.message);
        return false;
    }
}

// ===================== END INTERVENTION OVERLAY FUNCTIONS =====================

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

    // Store pending purchase data for the pipeline result handler
    let pendingPurchaseData = null;
    
    // Flag to prevent double-triggering of analysis
    let isProcessingPurchase = false;
    let lastProcessedProduct = null;
    
    // Create a loading overlay while waiting for pipeline analysis
    function createLoadingOverlay(productName, price) {
        console.log('[content.js] createLoadingOverlay called with:', productName, price);
        
        removeExistingOverlays();
        
        const overlay = document.createElement('div');
        overlay.classList.add('intervention-overlay', 'intervention-loading');
        overlay.id = 'loading-overlay';
        
        // Add inline styles to guarantee visibility
        overlay.style.cssText = `
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            background-color: rgba(0, 0, 0, 0.95) !important;
            z-index: 2147483647 !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        `;
        
        overlay.innerHTML = `
            <div style="background: #1a1a1a; padding: 40px 60px; border-radius: 16px; text-align: center; color: white; box-shadow: 0 20px 60px rgba(0,0,0,0.5);">
                <div style="width: 50px; height: 50px; border: 4px solid rgba(255,255,255,0.2); border-top-color: #4ecdc4; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 20px;"></div>
                <h2 style="margin: 0 0 10px; font-size: 24px; color: #fff;">Analyzing Purchase...</h2>
                <p style="margin: 0 0 5px; color: rgba(255,255,255,0.8);">${productName || 'Your purchase'}</p>
                ${price ? `<p style="margin: 0 0 10px; color: #ff6b6b; font-size: 18px;">${price}</p>` : ''}
                <p style="margin: 0; color: rgba(255,255,255,0.5); font-size: 14px;">Running behavioral analysis...</p>
            </div>
            <style>
                @keyframes spin { to { transform: rotate(360deg); } }
            </style>
        `;
        
        document.body.appendChild(overlay);
        console.log('[content.js] Loading overlay appended to body. Overlay element:', overlay);
        console.log('[content.js] Body children count:', document.body.children.length);
        
        return overlay;
    }
    
    // Listen for pipeline analysis results from tracker.js
    console.log('[content.js] 📡 Registering pipeline-analysis-result event listener');
    window.addEventListener('pipeline-analysis-result', (ev) => {
        console.log('[content.js] 🎯 Pipeline analysis result received');
        try {
            const result = ev.detail;
            console.log('[content.js] Result:', result);
            console.log('[content.js] Intervention action:', result.intervention_action);
            
            // Remove loading overlay if present
            const loadingOverlay = document.getElementById('loading-overlay');
            if (loadingOverlay) {
                console.log('[content.js] Removing loading overlay');
                loadingOverlay.remove();
            }
            
            // Get pending purchase data
            const purchaseData = pendingPurchaseData || {};
            const productKey = purchaseData.productKey || null;
            pendingPurchaseData = null; // Clear pending data
            
            // Build intervention options with callbacks to reset state
            const onInterventionComplete = () => {
                console.log('[content.js] 🔓 Intervention complete, resetting state');
                isProcessingPurchase = false;
                if (productKey) {
                    lastProcessedProduct = { key: productKey, timestamp: Date.now() };
                }
            };
            
            const interventionOpts = {
                reasoning: result.reasoning || 'Analysis complete.',
                price: purchaseData.priceDisplay || '',
                productName: purchaseData.productName || '',
                impulseScore: result.impulse_score || 0.5,
                onContinue: onInterventionComplete,
                onComplete: onInterventionComplete,
                onUnlock: onInterventionComplete
            };
            
            console.log('[content.js] Calling showInterventionOverlay with:', result.intervention_action, interventionOpts);
            
            // Show the appropriate intervention overlay
            const interventionShown = showInterventionOverlay(result.intervention_action, interventionOpts);
            
            if (!interventionShown) {
                console.log('[content.js] ✅ No intervention needed - purchase can proceed');
                // Reset state immediately for NONE interventions
                isProcessingPurchase = false;
                if (productKey) {
                    lastProcessedProduct = { key: productKey, timestamp: Date.now() };
                }
                // Show a brief "Approved" toast for feedback
                showApprovedToast();
            } else {
                console.log('[content.js] 🛑 Intervention overlay shown');
            }
        } catch (error) {
            console.error('[content.js] ❌ Error handling pipeline result:', error);
            // Reset state on error
            isProcessingPurchase = false;
        }
    });
    
    // Show a brief "approved" toast when no intervention is needed
    function showApprovedToast() {
        const toast = document.createElement('div');
        toast.className = 'impulse-toast approved-toast';
        toast.innerHTML = `
            <span class="toast-icon">✅</span>
            <span class="toast-text">Purchase looks good!</span>
        `;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #44cf6c, #4ecdc4);
            color: #000;
            padding: 12px 20px;
            border-radius: 8px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 14px;
            font-weight: 600;
            z-index: 2147483647;
            display: flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
            animation: slideIn 0.3s ease-out;
        `;
        document.body.appendChild(toast);
        
        // Remove after 2 seconds
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => toast.remove(), 300);
        }, 2000);
    }

    // Find and intercept add-to-cart. If user has dismissed overlay for site, skip interception.
    function attachClickListener(button) {
        if (button.dataset.intercepted) return;
        button.dataset.intercepted = 'true';

        button.addEventListener('click', (e) => {
            console.log('[content.js] 🛒 Purchase button clicked - intercepting');
            
            const result = getPagePrice();
            const productName = getProductName();
            const priceDisplay = result.raw || (result.value ? `$${result.value}` : 'Price not found');
            const clickTime = Date.now();
            
            // Create a unique key for this product to prevent double-analysis
            const productKey = `${productName}-${result.value || 'unknown'}`;
            
            // Check if we're already processing this purchase or just processed it
            if (isProcessingPurchase) {
                console.log('[content.js] ⚠️ Already processing a purchase, ignoring click');
                e.preventDefault();
                e.stopPropagation();
                return false;
            }
            
            // Check if we just processed this same product (within 30 seconds)
            if (lastProcessedProduct && lastProcessedProduct.key === productKey) {
                const timeSinceLastProcess = Date.now() - lastProcessedProduct.timestamp;
                if (timeSinceLastProcess < 30000) { // 30 second cooldown
                    console.log('[content.js] ⚠️ Already processed this product recently, allowing click through');
                    // Allow the actual purchase to proceed
                    return true;
                }
            }
            
            // Set processing flag
            isProcessingPurchase = true;
            console.log('[content.js] 🔒 Setting isProcessingPurchase = true');
            
            // Safety timeout: reset flag after 60 seconds in case something goes wrong
            setTimeout(() => {
                if (isProcessingPurchase) {
                    console.log('[content.js] ⚠️ Safety timeout: resetting isProcessingPurchase');
                    isProcessingPurchase = false;
                }
            }, 60000);
            
            // Get button text to distinguish Add to Cart vs Buy Now
            const buttonText = (button.innerText || button.value || button.getAttribute('aria-label') || '').trim();

            // Store pending purchase data for when pipeline result arrives
            pendingPurchaseData = {
                raw: result.raw,
                value: result.value,
                productName: productName,
                priceDisplay: priceDisplay,
                buttonText: buttonText,
                productKey: productKey
            };

            // Dispatch custom event with price AND cart click data for tracker.js
            // This triggers the pipeline API call
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

            // Show loading overlay while waiting for pipeline analysis
            // For gambling sites, show immediate intervention
            if (isGambling) {
                console.log('[content.js] 🎰 Gambling site detected - showing phrase overlay');
                createPhraseOverlay({
                    reasoning: 'This appears to be a gambling site. Gambling can be addictive.',
                    price: priceDisplay,
                    productName: productName,
                    impulseScore: 1.0,
                    challenge: 'I understand that I am about to gamble and I will make a rational decision'
                });
            } else {
                // Show loading overlay while waiting for pipeline result
                console.log('[content.js] ⏳ Showing loading overlay while analyzing...');
                try {
                    createLoadingOverlay(productName, priceDisplay);
                    console.log('[content.js] Loading overlay created successfully');
                } catch (err) {
                    console.error('[content.js] Error creating loading overlay:', err);
                    alert('Error creating overlay: ' + err.message);
                }
            }

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
        }, true); // capture phase so we run before the site's handler
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

        // Capture-phase fallback: catch Add to Cart / Buy Now by text when button wasn't in our selectors
        document.addEventListener('click', (e) => {
            const buttonLike = e.target.closest('button, input[type="submit"], input[type="button"], [role="button"], [data-action="add-to-cart"], [data-action="buy-now"]');
            if (!buttonLike) return;
            const text = (buttonLike.value || buttonLike.textContent || buttonLike.getAttribute('aria-label') || '').toLowerCase();
            const isAddCart = text.includes('add to cart') || text.includes('add to basket');
            const isBuyNow = text.includes('buy now') || text.includes('proceed to checkout') || text.includes('buy with');
            if (!isAddCart && !isBuyNow) return;
            if (buttonLike.dataset.intercepted) return; // already handled by attachClickListener
            if (isProcessingPurchase) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                return false;
            }
            buttonLike.dataset.intercepted = 'true';
            isProcessingPurchase = true;
            setTimeout(() => {
                if (isProcessingPurchase) {
                    isProcessingPurchase = false;
                }
            }, 60000);
            const result = getPagePrice();
            const productName = getProductName();
            const priceDisplay = result.raw || (result.value ? `$${result.value}` : 'Price not found');
            const productKey = productName + '-' + (result.value || 'unknown');
            pendingPurchaseData = { raw: result.raw, value: result.value, productName: productName, priceDisplay: priceDisplay, productKey: productKey, buttonText: isBuyNow ? 'Buy Now' : 'Add to Cart' };
            window.dispatchEvent(new CustomEvent('stop-shopping-cart-click', {
                detail: { raw: result.raw, value: result.value, productName: productName, buttonText: pendingPurchaseData.buttonText, timestamp: Date.now(), cartClickDate: new Date().toISOString() }
            }));
            try {
                createLoadingOverlay(productName, priceDisplay);
            } catch (err) {
                console.error('[content.js] Error creating loading overlay:', err);
            }
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            return false;
        }, true);

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



