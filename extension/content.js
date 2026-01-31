const goalSentence = "I understand that I am about to shop and I am in a healthy state of mind";

const overlay = document.createElement('div');
overlay.classList.add('stop-shopping-overlay');

// Get the URL for your extension's camera page
const cameraPageUrl = chrome.runtime.getURL("camera.html");

overlay.innerHTML = `
    <div class="lock-box">
        <h1>DO NOT SHOP</h1>
        
        <div class="camera-container">
            <iframe src="${cameraPageUrl}" allow="camera" frameborder="0"></iframe>
        </div>

        <p>Look at yourself. Do you really need this?</p>
        <p>To proceed, type the following:</p>
        <p class="challenge-text">${goalSentence}</p>
        <input type="text" id="unlock-input" placeholder="Type here..." autocomplete="off">
    </div>
`;

document.body.appendChild(overlay);

const inputField = overlay.querySelector('#unlock-input');

inputField.addEventListener('input', (e) => {
    if (e.target.value === goalSentence) {
        overlay.remove();
        stopBeep();
    }
});

// Block pasting
inputField.addEventListener('paste', (e) => {
    e.preventDefault();
    alert("Don't cheat. Look at yourself and type it.");
});

// --- Annoying beep using Web Audio API ---
let audioCtx = null;
let beepInterval = null;

function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function playToneOnce(duration = 220, freq = 880) {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.value = freq;
    gain.gain.value = 0.0;
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.25, now + 0.01);
    osc.start(now);
    gain.gain.linearRampToValueAtTime(0, now + duration / 1000);
    setTimeout(() => {
        try { osc.stop(); } catch (e) {}
    }, duration + 20);
}

function startBeep() {
    if (prefersReducedMotion()) return;
    try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        // Try to play immediately; if context is suspended, resume on first interaction
        playToneOnce();
        beepInterval = setInterval(() => playToneOnce(), 1000);

        // If autoplay is blocked (suspended), resume on click anywhere on overlay
        if (audioCtx.state === 'suspended') {
            const resume = () => {
                audioCtx.resume().then(() => {
                    playToneOnce();
                    if (beepInterval) clearInterval(beepInterval);
                    beepInterval = setInterval(() => playToneOnce(), 1000);
                }).catch(() => {});
                overlay.removeEventListener('click', resume);
            };
            overlay.addEventListener('click', resume, { once: true });
        }
    } catch (err) {
        console.warn('Beep playback failed:', err);
    }
}

function stopBeep() {
    try {
        if (beepInterval) {
            clearInterval(beepInterval);
            beepInterval = null;
        }
        if (audioCtx) {
            audioCtx.close().catch(() => {});
            audioCtx = null;
        }
    } catch (e) {
        console.warn('Error stopping beep', e);
    }
}

// Start the beep when overlay is shown
startBeep();

// Ensure beep stops if overlay is removed by other means
new MutationObserver(() => {
    if (!document.body.contains(overlay)) stopBeep();
}).observe(document.body, { childList: true, subtree: true });