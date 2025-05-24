/**
 * QR code scanning functionality using jsQR library
 */

// This file would be used if we implement QR code scanning within the app
// Currently we're using direct URL handling, but this would be useful for
// a feature where users can scan a QR code within the app to navigate to
// the upload page.

document.addEventListener('DOMContentLoaded', function() {
    // We'll use the jsQR library for QR code detection
    // This script assumes the jsQR library is loaded
    
    // Check if jsQR scanner page is active
    const scannerContainer = document.getElementById('qr-scanner-container');
    if (!scannerContainer) return;
    
    // DOM Elements
    const videoElement = document.getElementById('qr-video');
    const canvasElement = document.getElementById('qr-canvas');
    const scanResultElement = document.getElementById('qr-result');
    const startScanButton = document.getElementById('start-scan');
    const stopScanButton = document.getElementById('stop-scan');
    
    let scanning = false;
    let videoStream = null;
    
    // Start QR scanning
    function startScanning() {
        if (scanning) return;
        
        // Get user media
        navigator.mediaDevices.getUserMedia({ 
            video: { 
                facingMode: 'environment',
                width: { ideal: 1280 },
                height: { ideal: 720 }
            } 
        })
        .then(function(stream) {
            videoStream = stream;
            videoElement.srcObject = stream;
            videoElement.play();
            scanning = true;
            
            startScanButton.style.display = 'none';
            stopScanButton.style.display = 'inline-block';
            
            // Start processing frames
            requestAnimationFrame(scanFrame);
        })
        .catch(function(error) {
            console.error('Error accessing camera:', error);
            alert('Could not access camera. Please ensure you have granted camera permissions.');
        });
    }
    
    // Stop QR scanning
    function stopScanning() {
        if (!scanning) return;
        
        // Stop all video tracks
        if (videoStream) {
            videoStream.getTracks().forEach(track => track.stop());
            videoStream = null;
        }
        
        videoElement.srcObject = null;
        scanning = false;
        
        startScanButton.style.display = 'inline-block';
        stopScanButton.style.display = 'none';
    }
    
    // Process video frame to detect QR code
    function scanFrame() {
        if (!scanning) return;
        
        // Ensure video is playing and has dimensions
        if (videoElement.readyState === videoElement.HAVE_ENOUGH_DATA) {
            // Set canvas dimensions to match video
            canvasElement.height = videoElement.videoHeight;
            canvasElement.width = videoElement.videoWidth;
            
            // Get canvas context and draw current video frame
            const context = canvasElement.getContext('2d');
            context.drawImage(videoElement, 0, 0, canvasElement.width, canvasElement.height);
            
            // Get image data for QR processing
            const imageData = context.getImageData(0, 0, canvasElement.width, canvasElement.height);
            
            // Process with jsQR
            if (typeof jsQR === 'function') {
                const code = jsQR(imageData.data, imageData.width, imageData.height, {
                    inversionAttempts: 'dontInvert',
                });
                
                if (code) {
                    // QR code detected!
                    stopScanning();
                    
                    // Check if the QR code contains a valid Drive QR Upload URL
                    const qrData = code.data;
                    if (qrData.includes('/scan') && qrData.includes('token=') && qrData.includes('folder=')) {
                        // Valid QR code for our app
                        window.location.href = qrData;
                    } else {
                        // Invalid QR code
                        scanResultElement.innerHTML = `
                            <div class="alert alert-warning">
                                <h5>Invalid QR Code</h5>
                                <p>The scanned QR code is not a valid Drive QR Upload code.</p>
                                <p>Scanned content: ${qrData}</p>
                                <button class="btn btn-primary mt-2" onclick="startScanning()">
                                    Scan Again
                                </button>
                            </div>
                        `;
                    }
                }
            }
        }
        
        // Continue scanning if active
        if (scanning) {
            requestAnimationFrame(scanFrame);
        }
    }
    
    // Event listeners
    if (startScanButton) {
        startScanButton.addEventListener('click', startScanning);
    }
    
    if (stopScanButton) {
        stopScanButton.addEventListener('click', stopScanning);
    }
    
    // Check browser support
    function checkScannerSupport() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            scannerContainer.innerHTML = `
                <div class="alert alert-danger mb-0">
                    <h5><i class="fas fa-exclamation-circle me-2"></i>Browser Not Supported</h5>
                    <p>Your browser doesn't support camera access needed for QR scanning.</p>
                    <p>Please use a modern browser like Chrome, Firefox, or Safari.</p>
                </div>
            `;
            return false;
        }
        
        if (typeof jsQR !== 'function') {
            scannerContainer.innerHTML = `
                <div class="alert alert-warning mb-0">
                    <h5><i class="fas fa-exclamation-triangle me-2"></i>QR Scanner Library Missing</h5>
                    <p>The jsQR library required for QR code scanning couldn't be loaded.</p>
                </div>
            `;
            return false;
        }
        
        return true;
    }
    
    // Initialize if the page contains scanner elements
    if (videoElement && canvasElement && scanResultElement) {
        if (checkScannerSupport()) {
            // Auto-start scanning if supported
            if (startScanButton.dataset.autostart === 'true') {
                startScanning();
            }
        }
    }
});
