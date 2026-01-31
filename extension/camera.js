navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
        document.getElementById('cam').srcObject = stream;
    })
    .catch(err => {
        console.error("Camera denied:", err);
    });