// Price extraction utilities (from webscrapping)
function parsePrice(text: string): number | null {
  if (!text) return null;
  const cleaned = text.replace(/[^0-9.]/g, "");
  const value = parseFloat(cleaned);
  return isNaN(value) ? null : value;
}

function getSite(): 'amazon' | 'shopify' | 'unknown' {
  const host = window.location.hostname || '';
  if (host.includes('amazon')) return 'amazon';
  if (document.querySelector('meta[name="generator"][content*="Shopify"]')) return 'shopify';
  return 'unknown';
}

interface PriceResult {
  raw: string | null;
  value: number | null;
}

function getAmazonPrice(): PriceResult {
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

function getShopifyPrice(): PriceResult {
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

function getGenericPrice(): PriceResult {
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

function getPagePrice(): PriceResult {
  const site = getSite();
  if (site === 'amazon') return getAmazonPrice();
  if (site === 'shopify') return getShopifyPrice();
  return getGenericPrice();
}

// Overlay and camera logic
const goalSentence = "I understand that I am about to shop and I am in a healthy state of mind";

// Track page load time
const pageLoadTime = Date.now();

let overlay: HTMLDivElement | null = null;
let videoElement: HTMLVideoElement | null = null;

function formatDuration(milliseconds: number): string {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    
    if (minutes === 0) {
        return `${seconds}s`;
    } else if (minutes < 60) {
        return `${minutes}m ${seconds}s`;
    } else {
        const hours = Math.floor(minutes / 60);
        const remainingMinutes = minutes % 60;
        return `${hours}h ${remainingMinutes}m ${seconds}s`;
    }
}

function createAndShowOverlay(priceInfo: string): void {
    if (overlay) overlay.remove();

    // Get current system time
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit', 
        second: '2-digit',
        hour12: true 
    });
    const dateString = now.toLocaleDateString('en-US', {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });

    // Calculate time spent on page
    const timeSpent = formatDuration(Date.now() - pageLoadTime);

    // Create the overlay
    overlay = document.createElement('div');
    overlay.classList.add('stop-shopping-overlay');

    overlay.innerHTML = `
        <div class="lock-box">
            <h1>DO NOT SHOP</h1>
            <p style="font-size: 14px; margin: 5px 0; color: #666;">📅 ${dateString} | 🕐 ${timeString}</p>
            <p style="font-size: 14px; margin: 5px 0; color: #666;">⏱️ Time on site: <strong style="color: #d9534f;">${timeSpent}</strong></p>
            <p style="font-size: 18px; margin: 10px 0; color: #d9534f;">Price: <strong>${priceInfo}</strong></p>
            
            <div class="camera-container">
                <video id="self-reflection-cam" autoplay muted></video>
            </div>

            <p>Look at yourself. Do you really need this?</p>
            <p>To proceed, type the following:</p>
            <p class="challenge-text">${goalSentence}</p>
            <input type="text" id="unlock-input" placeholder="Type here..." autocomplete="off">
        </div>
    `;

    document.body.appendChild(overlay);

    // --- Camera Logic ---
    videoElement = document.getElementById('self-reflection-cam') as HTMLVideoElement;

    // Request camera access
    navigator.mediaDevices.getUserMedia({ video: true })
        .then((stream: MediaStream) => {
            if (videoElement) videoElement.srcObject = stream;
        })
        .catch((err: Error) => {
            console.error("Camera access denied or not supported:", err);
            // Fallback if they say no to the camera
            if (videoElement) videoElement.style.display = 'none';
        });

    // --- Unlock Logic ---
    const inputField = overlay.querySelector('#unlock-input') as HTMLInputElement;

    inputField.addEventListener('input', (e: Event) => {
        const target = e.target as HTMLInputElement;
        if (target.value === goalSentence) {
            // 1. Stop the camera (turn off the hardware light)
            if (videoElement && videoElement.srcObject) {
                const stream = videoElement.srcObject as MediaStream;
                const tracks = stream.getTracks();
                tracks.forEach(track => track.stop());
            }
            
            // 2. Remove the overlay
            if (overlay) overlay.remove();
            overlay = null;
        }
    });

    inputField.addEventListener('paste', (e: ClipboardEvent) => {
        e.preventDefault();
        alert("Don't cheat. Look at yourself and type it.");
    });
}

// Detect and intercept "Add to Cart" button clicks on Amazon
function findAndInterceptAddToCartButton(): void {
    // Common Amazon "Add to Cart" selectors
    const selectors = [
        '#add-to-cart-button',
        '#addToCart',
        '[data-feature-name="add-to-cart"]',
        'input[value="Add to Cart"]',
        'button[aria-label*="Add to Cart"]'
    ];

    const findButton = (): HTMLElement | null => {
        for (const sel of selectors) {
            const btn = document.querySelector(sel) as HTMLElement;
            if (btn) return btn;
        }
        return null;
    };

    let button = findButton();

    // If button not found, wait for it to appear (dynamic content)
    if (!button) {
        const observer = new MutationObserver(() => {
            button = findButton();
            if (button && !button.dataset.intercepted) {
                attachClickListener(button);
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    } else if (!button.dataset.intercepted) {
        attachClickListener(button);
    }
}

function attachClickListener(button: HTMLElement): void {
    if (button.dataset.intercepted) return;
    button.dataset.intercepted = 'true';

    button.addEventListener('click', (e: Event) => {
        console.log('Add to Cart clicked!');
        const result = getPagePrice();
        const priceDisplay = result.raw || `$${result.value}` || 'Price not found';
        
        // Show the overlay with price
        createAndShowOverlay(priceDisplay);
        
        // Prevent the actual add-to-cart action temporarily while overlay is visible
        e.preventDefault();
        e.stopPropagation();
    }, true);
}

// Start listening for Add to Cart button on page load
findAndInterceptAddToCartButton();

// Listen for popup messages asking for price
chrome.runtime.onMessage.addListener(
    (msg: any, sender: chrome.runtime.MessageSender, sendResponse: (response?: any) => void) => {
        if (msg && msg.type === 'GET_PRICE') {
            const result = getPagePrice();
            // Keep backward-compatible fields: price = raw string, value = numeric
            sendResponse({ price: result.raw, value: result.value });
        }
    }
);


