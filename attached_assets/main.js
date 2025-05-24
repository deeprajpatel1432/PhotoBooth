/**
 * Main JavaScript file for Photobooth application
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Auto-dismiss alerts after 5 seconds
    setTimeout(() => {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(alert => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Toggle between storage types on the generate page
    const storageRadios = document.querySelectorAll('input[name="storage_type"]');
    if (storageRadios.length) {
        const localFolderDiv = document.getElementById('local_folder_div');
        
        storageRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'local') {
                    localFolderDiv.style.display = 'block';
                    document.getElementById('folder_name').setAttribute('required', '');
                } else {
                    localFolderDiv.style.display = 'none';
                    document.getElementById('folder_name').removeAttribute('required');
                }
            });
        });
    }

    // File upload handling for drop zone
    const dropZone = document.getElementById('drop-zone');
    const fileSelector = document.getElementById('file-selector');
    const selectFilesBtn = document.getElementById('select-files-btn');

    if (dropZone && fileSelector) {
        // Drag and drop handlers
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('highlight');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('highlight');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('highlight');
            
            if (e.dataTransfer.files.length) {
                handleFiles(e.dataTransfer.files);
            }
        });

        // Click to select files
        if (selectFilesBtn) {
            selectFilesBtn.addEventListener('click', () => {
                fileSelector.click();
            });
        }

        // Handle selected files
        fileSelector.addEventListener('change', () => {
            if (fileSelector.files.length) {
                handleFiles(fileSelector.files);
            }
        });
    }

    // Handle the selected files
    function handleFiles(files) {
        for (let i = 0; i < files.length; i++) {
            uploadFile(files[i]);
        }
    }

    // Upload a file to the server
    function uploadFile(file) {
        const folderId = document.getElementById('folder-id').value;
        const token = document.getElementById('token').value;
        const progressContainer = document.getElementById('upload-progress-container');
        const progressBar = document.getElementById('upload-progress-bar');
        const fileName = document.getElementById('upload-file-name');
        const resultContainer = document.getElementById('result-container');
        
        // Check if file is an image
        if (!file.type.match('image.*')) {
            alert('Please select an image file (JPEG, PNG, GIF)');
            return;
        }

        // Create form data
        const formData = new FormData();
        formData.append('file', file);
        formData.append('folder_id', folderId);
        formData.append('token', token);

        // Display progress
        progressContainer.style.display = 'block';
        fileName.textContent = file.name;
        progressBar.style.width = '0%';
        resultContainer.style.display = 'none';

        // Upload
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload', true);

        // Track progress
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progressBar.style.width = percentComplete + '%';
                progressBar.setAttribute('aria-valuenow', percentComplete);
            }
        };

        // Handle response
        xhr.onload = function() {
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                
                if (response.success) {
                    // Show success
                    progressContainer.style.display = 'none';
                    resultContainer.style.display = 'block';
                    
                    // Update result container
                    document.getElementById('file-details').textContent = `${response.file_name} (${formatFileSize(response.file_size)})`;
                    
                    const viewLink = document.getElementById('view-file-link');
                    if (viewLink) {
                        viewLink.href = response.file_url;
                    }
                    
                    // Reset file selector
                    if (fileSelector) {
                        fileSelector.value = '';
                    }
                } else {
                    alert('Upload failed: ' + response.error);
                    progressContainer.style.display = 'none';
                }
            } else {
                alert('Upload failed. Server returned: ' + xhr.status);
                progressContainer.style.display = 'none';
            }
        };

        xhr.onerror = function() {
            alert('Upload failed. Check your connection.');
            progressContainer.style.display = 'none';
        };

        xhr.send(formData);
    }

    // Format file size
    function formatFileSize(bytes) {
        if (bytes < 1024) {
            return bytes + ' bytes';
        } else if (bytes < 1048576) {
            return (bytes / 1024).toFixed(1) + ' KB';
        } else {
            return (bytes / 1048576).toFixed(1) + ' MB';
        }
    }

    // New Upload Button
    const newUploadBtn = document.getElementById('new-upload-btn');
    if (newUploadBtn) {
        newUploadBtn.addEventListener('click', () => {
            // Hide result and reset progress
            const resultContainer = document.getElementById('result-container');
            const progressContainer = document.getElementById('upload-progress-container');
            
            if (resultContainer) {
                resultContainer.style.display = 'none';
            }
            
            if (progressContainer) {
                progressContainer.style.display = 'none';
            }
            
            // Reset file selector
            if (fileSelector) {
                fileSelector.value = '';
            }
        });
    }
});
