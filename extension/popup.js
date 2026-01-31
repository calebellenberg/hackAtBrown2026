document.getElementById('setup-btn').addEventListener('click', () => {
  // Opens the camera page in a new tab
  chrome.tabs.create({ url: 'camera.html' });
});