document.addEventListener('DOMContentLoaded', () => {
    // --- Import Data Modal Logic ---
    const importForm = document.getElementById('import-data-form');
    const importStatusEl = document.getElementById('import-status');
    const dbFileInput = document.getElementById('db-file-input');
    const importModalEl = document.getElementById('importDataModal');
    const importProgressContainer = document.getElementById('import-progress-container');
    const importProgressBar = document.getElementById('import-progress-bar');
    const importSubmitBtn = importForm ? importForm.querySelector('button[type="submit"]') : null;

    let importPollingInterval = null;
    let currentXhr = null; // To hold the upload request

    function resetImportModal() {
        if (currentXhr) {
            currentXhr.abort();
            currentXhr = null;
        }
        if (importPollingInterval) {
            clearInterval(importPollingInterval);
            importPollingInterval = null;
        }

        importStatusEl.style.display = 'none';
        importStatusEl.innerHTML = '';
        if (importProgressContainer) {
            importProgressContainer.style.display = 'none';
        }
        if (importProgressBar) {
            importProgressBar.style.width = '0%';
            importProgressBar.textContent = '0%';
            importProgressBar.classList.remove('bg-success', 'bg-danger');
            importProgressBar.classList.add('progress-bar-animated', 'progress-bar-striped');
            importProgressBar.setAttribute('aria-valuenow', 0);
        }
        if (importForm) {
            importForm.reset();
        }
        if (importSubmitBtn) {
            importSubmitBtn.disabled = false;
        }
        if (dbFileInput) {
            dbFileInput.disabled = false;
        }
    }

    async function pollImportStatus(taskId) {
        // Set up UI for processing phase
        importStatusEl.innerHTML = `<div class="alert alert-info">File uploaded. Now processing data on server...</div>`;
        importProgressBar.style.width = '0%';
        importProgressBar.textContent = '0%';
        importProgressBar.setAttribute('aria-valuenow', 0);

        importPollingInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/import-status/${taskId}`);
                if (!response.ok) {
                    // Stop polling on 404 or other fatal errors
                    clearInterval(importPollingInterval);
                    const errData = await response.json().catch(() => null);
                    const errorMsg = errData ? errData.error : 'Failed to get import status.';
                    throw new Error(errorMsg);
                }
                const data = await response.json();

                // Update progress bar for processing
                if (importProgressBar) {
                    const progress = Math.round(data.progress || 0);
                    importProgressBar.style.width = `${progress}%`;
                    importProgressBar.textContent = `${progress}%`;
                    importProgressBar.setAttribute('aria-valuenow', progress);
                }

                // Update status message
                if (data.message && importStatusEl) {
                    importStatusEl.innerHTML = `<div class="alert alert-info">${data.message}</div>`;
                    importStatusEl.style.display = 'block';
                }

                if (data.status === 'complete') {
                    clearInterval(importPollingInterval);
                    if (importProgressBar) {
                        importProgressBar.classList.add('bg-success');
                        importProgressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                    }
                    const stats = data.stats;
                    if (importStatusEl) {
                        importStatusEl.innerHTML = `
                            <div class="alert alert-success">
                                <strong>Import Complete!</strong><br>
                                New Hourly Weather records: ${stats.hourly_weather}<br>
                                New Hourly Snapshots: ${stats.hourly_snapshot}<br>
                                The page will now reload to reflect the new data.
                            </div>`;
                    }
                    setTimeout(() => {
                        window.location.reload();
                    }, 4000);
                } else if (data.status === 'error') {
                    clearInterval(importPollingInterval);
                    if (importProgressBar) {
                        importProgressBar.classList.add('bg-danger');
                        importProgressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                    }
                    if (importStatusEl) {
                        importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> ${data.error}</div>`;
                    }
                    setTimeout(resetImportModal, 8000);
                }
            } catch (error) {
                clearInterval(importPollingInterval);
                if (importStatusEl) {
                    importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> Could not poll for import status. ${error.message}</div>`;
                }
                if (importProgressBar) {
                    importProgressBar.classList.add('bg-danger');
                    importProgressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                }
                setTimeout(resetImportModal, 8000);
            }
        }, 2000); // Poll every 2 seconds
    }

    if (importForm) {
        importForm.addEventListener('submit', (e) => {
            e.preventDefault();
            if (!dbFileInput.files || dbFileInput.files.length === 0) {
                importStatusEl.innerHTML = `<div class="alert alert-warning">Please select a file first.</div>`;
                importStatusEl.style.display = 'block';
                return;
            }

            const file = dbFileInput.files[0];
            const formData = new FormData();
            formData.append('db_file', file);

            // Reset UI for new upload
            resetImportModal();
            importSubmitBtn.disabled = true;
            dbFileInput.disabled = true;
            importProgressContainer.style.display = 'block';
            importStatusEl.style.display = 'block';
            importStatusEl.innerHTML = `<div class="alert alert-info">Starting upload...</div>`;

            currentXhr = new XMLHttpRequest();
            currentXhr.open('POST', '/api/import-weather-db', true);

            // Upload progress
            currentXhr.upload.addEventListener('progress', (event) => {
                if (event.lengthComputable) {
                    const percentComplete = Math.round((event.loaded / event.total) * 100);
                    importProgressBar.style.width = percentComplete + '%';
                    importProgressBar.textContent = percentComplete + '%';
                    importProgressBar.setAttribute('aria-valuenow', percentComplete);
                    importStatusEl.innerHTML = `<div class="alert alert-info">Uploading file...</div>`;
                }
            });

            // Upload finished
            currentXhr.addEventListener('load', () => {
                const xhr = currentXhr;
                currentXhr = null;
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const result = JSON.parse(xhr.responseText);
                        if (result.task_id) {
                            pollImportStatus(result.task_id);
                        } else {
                            throw new Error('Server did not return a task ID.');
                        }
                    } catch (parseError) {
                        importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> Failed to parse server response.</div>`;
                        setTimeout(resetImportModal, 5000);
                    }
                } else {
                    let errorMsg = `Upload failed with status: ${xhr.status} ${xhr.statusText}`;
                    try {
                        const errJson = JSON.parse(xhr.responseText);
                        if (errJson.error) errorMsg = errJson.error;
                    } catch (e) { /* ignore if response is not json */ }
                    
                    if (xhr.status === 413) {
                        errorMsg = 'File is too large. The server rejected the upload. Please check the web server configuration (e.g., Nginx client_max_body_size).';
                    }

                    importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Upload Error:</strong> ${errorMsg}</div>`;
                    importProgressBar.classList.add('bg-danger');
                    importProgressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                    setTimeout(resetImportModal, 8000);
                }
            });

            // Upload error
            currentXhr.addEventListener('error', () => {
                currentXhr = null;
                importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Network Error:</strong> The upload could not be completed.</div>`;
                importProgressBar.classList.add('bg-danger');
                importProgressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                setTimeout(resetImportModal, 5000);
            });

            // Upload aborted
            currentXhr.addEventListener('abort', () => {
                currentXhr = null;
                console.log('Upload aborted.');
            });

            currentXhr.send(formData);
        });
    }

    if (importModalEl) {
        importModalEl.addEventListener('hidden.bs.modal', () => {
            resetImportModal();
        });
    }
});
