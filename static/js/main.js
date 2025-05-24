/**
 * Main JavaScript file for Photobooth application
 */
document.addEventListener('DOMContentLoaded', function() {
    // Setup drop zone for file uploads
    const dropZone = document.getElementById('drop-zone');
    const fileSelector = document.getElementById('file-selector');
    const selectFilesBtn = document.getElementById('select-files-btn');
    
    if (dropZone && fileSelector) {
        // File selector button
        if (selectFilesBtn) {
            selectFilesBtn.addEventListener('click', function(e) {
                e.preventDefault();
                fileSelector.click();
            });
        }
        
        // Handle file selection
        fileSelector.addEventListener('change', function() {
            handleFiles(this.files);
        });
        
        // Drag and drop events
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });
        
        function highlight() {
            dropZone.classList.add('highlight');
        }
        
        function unhighlight() {
            dropZone.classList.remove('highlight');
        }
        
        // Handle dropped files
        dropZone.addEventListener('drop', function(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles(files);
        });
    }
    
    // Handle file uploads
    function handleFiles(files) {
        if (!files.length) return;
        
        // Convert FileList to array and filter for images
        const imageFiles = Array.from(files).filter(file => file.type.startsWith('image/'));
        
        if (imageFiles.length === 0) {
            showToast('Please select image files only.', 'warning');
            return;
        }
        
        // Upload each file
        imageFiles.forEach(file => {
            uploadFile(file);
        });
        
        // Reset file input
        if (fileSelector) {
            fileSelector.value = '';
        }
    }
    
    // Upload a file
    function uploadFile(file) {
        const progressBar = document.getElementById('upload-progress-bar');
        const progressContainer = document.getElementById('upload-progress-container');
        const uploadFileName = document.getElementById('upload-file-name');
        const resultContainer = document.getElementById('result-container');
        const fileDetails = document.getElementById('file-details');
        const viewFileLink = document.getElementById('view-file-link');
        const successMessage = document.getElementById('success-message');
        const folderId = document.getElementById('folder-id');
        
        if (!folderId) {
            showToast('Folder ID is missing.', 'danger');
            return;
        }
        
        const folderIdValue = folderId.value;
        
        // Show progress
        if (progressContainer && uploadFileName) {
            progressContainer.style.display = 'block';
            uploadFileName.textContent = file.name;
        }
        
        // Reset progress bar
        if (progressBar) {
            progressBar.style.width = '0%';
            progressBar.setAttribute('aria-valuenow', 0);
        }
        
        // Create FormData
        const formData = new FormData();
        formData.append('file', file);
        formData.append('folder_id', folderIdValue);
        
        // Create and send request
        const xhr = new XMLHttpRequest();
        
        xhr.open('POST', '/upload', true);
        
        // Update progress bar
        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable && progressBar) {
                const percent = (e.loaded / e.total) * 100;
                progressBar.style.width = percent + '%';
                progressBar.setAttribute('aria-valuenow', percent);
            }
        });
        
        // Handle response
        xhr.onload = function() {
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    
                    // Hide progress
                    if (progressContainer) {
                        progressContainer.style.display = 'none';
                    }
                    
                    // Show result
                    if (resultContainer) {
                        resultContainer.style.display = 'block';
                    }
                    
                    // Update file details
                    if (fileDetails) {
                        fileDetails.textContent = `${file.name} (${formatFileSize(file.size)})`;
                    }
                    
                    // Update view link
                    if (viewFileLink && response.file_url) {
                        viewFileLink.href = response.file_url;
                    }
                    
                    // Update success message
                    if (successMessage) {
                        successMessage.textContent = 'Your photo has been uploaded successfully.';
                    }
                    
                    // Show toast notification
                    showToast('Upload successful!', 'success');
                    
                } catch (error) {
                    showToast('Error parsing response: ' + error.message, 'danger');
                }
            } else {
                showToast('Upload failed. Please try again.', 'danger');
                
                // Hide progress
                if (progressContainer) {
                    progressContainer.style.display = 'none';
                }
            }
        };
        
        // Handle errors
        xhr.onerror = function() {
            showToast('Upload failed. Please check your connection.', 'danger');
            
            // Hide progress
            if (progressContainer) {
                progressContainer.style.display = 'none';
            }
        };
        
        // Send the form data
        xhr.send(formData);
    }
    
    // Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // New upload button
    const newUploadBtn = document.getElementById('new-upload-btn');
    if (newUploadBtn) {
        newUploadBtn.addEventListener('click', function() {
            const resultContainer = document.getElementById('result-container');
            if (resultContainer) {
                resultContainer.style.display = 'none';
            }
        });
    }

    // Setup delete handlers
    setupPhotoDeleteHandlers();
    setupFolderDeleteHandlers();
});

/**
 * Set up event handlers for photo delete buttons
 */
function setupPhotoDeleteHandlers() {
    document.querySelectorAll('.delete-photo-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const photoId = this.dataset.photoId;
            const photoName = this.dataset.photoName;
            
            if (confirm(`Are you sure you want to delete the photo "${photoName}"? This action cannot be undone.`)) {
                deletePhoto(photoId);
            }
        });
    });
}

/**
 * Set up event handlers for folder delete buttons
 */
function setupFolderDeleteHandlers() {
    document.querySelectorAll('.delete-folder-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const folderId = this.dataset.folderId;
            const folderName = this.dataset.folderName;
            
            if (confirm(`Are you sure you want to delete the folder "${folderName}" and all its photos? This action cannot be undone.`)) {
                deleteFolder(folderId);
            }
        });
    });
}

/**
 * Delete a photo with the given ID
 */
function deletePhoto(photoId) {
    fetch(`/photo/delete/${photoId}`, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove the photo element from the DOM
            const photoElement = document.querySelector(`.photo-item[data-photo-id="${photoId}"]`);
            if (photoElement) {
                photoElement.remove();
            }
            
            // Show success message
            showToast('Photo deleted successfully.', 'success');
        } else {
            // Show error message
            showToast(data.message || 'Error deleting photo.', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error deleting photo.', 'danger');
    });
}

/**
 * Delete a folder with the given ID
 */
function deleteFolder(folderId) {
    fetch(`/folder/delete/${folderId}`, {
        method: 'GET',
        headers: {
            'Accept': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Remove the folder element from the DOM
            const folderElement = document.querySelector(`.folder-item[data-folder-id="${folderId}"]`);
            if (folderElement) {
                folderElement.remove();
            }
            
            // Show success message
            showToast('Folder and all its photos deleted successfully.', 'success');
            
            // Redirect if we're on the folder view page
            if (window.location.pathname.includes('/folder/view/')) {
                window.location.href = '/folders';
            }
        } else {
            // Show error message
            showToast(data.message || 'Error deleting folder.', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Error deleting folder.', 'danger');
    });
}

/**
 * Show a toast notification
 */
function showToast(message, type = 'info') {
    const toastContainer = document.querySelector('.toast-container');
    
    if (!toastContainer) return;
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    const toastContent = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toast.innerHTML = toastContent;
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 5000
    });
    
    bsToast.show();
    
    // Remove toast after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}