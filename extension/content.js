const goalSentence = "I understand that I am about to shop and I am in a healthy state of mind";

// Create the overlay
const overlay = document.createElement('div');
overlay.classList.add('stop-shopping-overlay');

overlay.innerHTML = `
    <div class="lock-box">
        <h1>DO NOT SHOP</h1>
        
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
const videoElement = document.getElementById('self-reflection-cam');

// Request camera access
navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
        videoElement.srcObject = stream;
    })
    .catch(err => {
        console.error("Camera access denied or not supported:", err);
        // Fallback if they say no to the camera
        videoElement.style.display = 'none'; 
    });

// --- Unlock Logic ---
const inputField = overlay.querySelector('#unlock-input');

inputField.addEventListener('input', (e) => {
    if (e.target.value === goalSentence) {
        // 1. Stop the camera (turn off the hardware light)
        if (videoElement.srcObject) {
            const stream = videoElement.srcObject;
            const tracks = stream.getTracks();
            tracks.forEach(track => track.stop());
        }
        
        // 2. Remove the overlay
        overlay.remove();
    }
});

inputField.addEventListener('paste', (e) => {
    e.preventDefault();
    alert("Don't cheat. Look at yourself and type it.");
});