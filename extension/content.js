
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

    try {
        if (isGambling) {
        createOverlay({
            title: 'DO NOT GAMBLE',
            message: 'Gambling can be addictive — pause and think before you wager.',
            challenge: 'I understand that I am about to gamble and I will make a rational decision',
            onUnlock: () => {
                try { sessionStorage.setItem(disableKey, '1'); } catch (e) {}
            }
        });
        return;
    }
    // show shopping overlay
    createOverlay({
        onUnlock: () => {
            try { sessionStorage.setItem(disableKey, '1'); } catch (e) {}
        }
    });
    } catch (err) {
        console.warn('[Overlay] decideOverlay failed, skipping overlay to avoid interfering with page', err);
    }
})();



