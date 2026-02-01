// Use the browser's camera (no Python server needed)
(function () {
    var cam = document.getElementById('cam');
    if (!cam) return;
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(function (stream) {
            cam.srcObject = stream;
        })
        .catch(function (err) {
            console.error('Camera denied or unavailable:', err);
        });
})();
