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

    function resetImportModal() {
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
        importProgressBar.style.width = '100%'; // Progress bar is for upload, now we are processing
        importProgressBar.textContent = 'Processing...';
        importProgressBar.setAttribute('aria-valuenow', 100);

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
        importForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!dbFileInput.files || dbFileInput.files.length === 0) {
                importStatusEl.innerHTML = `<div class="alert alert-warning">Please select a file first.</div>`;
                importStatusEl.style.display = 'block';
                return;
            }

            const file = dbFileInput.files[0];
            const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
            const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
            const uploadId = crypto.randomUUID();

            // Reset UI for new upload
            resetImportModal();
            importSubmitBtn.disabled = true;
            dbFileInput.disabled = true;
            importProgressContainer.style.display = 'block';
            importStatusEl.style.display = 'block';
            importStatusEl.innerHTML = `<div class="alert alert-info">Starting upload...</div>`;

            try {
                for (let i = 0; i < totalChunks; i++) {
                    const start = i * CHUNK_SIZE;
                    const end = Math.min(start + CHUNK_SIZE, file.size);
                    const chunk = file.slice(start, end);

                    const formData = new FormData();
                    formData.append('file', chunk, file.name);
                    formData.append('upload_id', uploadId);
                    
                    const percentComplete = Math.round(((i + 1) / totalChunks) * 100);
                    importStatusEl.innerHTML = `<div class="alert alert-info">Uploading chunk ${i + 1} of ${totalChunks}...</div>`;

                    const response = await fetch('/api/upload-chunk', {
                        method: 'POST',
                        body: formData,
                    });

                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({ error: 'Unknown upload error.' }));
                        throw new Error(`Chunk upload failed: ${errorData.error}`);
                    }
                    
                    importProgressBar.style.width = percentComplete + '%';
                    importProgressBar.textContent = percentComplete + '%';
                    importProgressBar.setAttribute('aria-valuenow', percentComplete);
                }

                // All chunks uploaded, now assemble the file on the server
                importStatusEl.innerHTML = `<div class="alert alert-info">File upload complete. Assembling file on server...</div>`;

                const assembleResponse = await fetch('/api/assemble-file', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        upload_id: uploadId,
                        filename: file.name,
                    }),
                });

                if (!assembleResponse.ok) {
                    const errorData = await assembleResponse.json().catch(() => ({ error: 'Unknown assembly error.' }));
                    throw new Error(`File assembly failed: ${errorData.error}`);
                }

                const result = await assembleResponse.json();
                if (result.task_id) {
                    pollImportStatus(result.task_id);
                } else {
                    throw new Error('Server did not return a task ID for processing.');
                }

            } catch (error) {
                importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Upload Error:</strong> ${error.message}</div>`;
                importProgressBar.classList.add('bg-danger');
                importProgressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                setTimeout(resetImportModal, 8000);
            }
        });
    }

    if (importModalEl) {
        importModalEl.addEventListener('hidden.bs.modal', () => {
            resetImportModal();
        });
    }
});
