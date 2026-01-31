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
    }
});

// Block pasting
inputField.addEventListener('paste', (e) => {
    e.preventDefault();
    alert("Don't cheat. Look at yourself and type it.");
});