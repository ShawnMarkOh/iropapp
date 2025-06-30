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
        importStatusEl.style.display = 'none';
        importStatusEl.innerHTML = '';
        if (importProgressContainer) {
            importProgressContainer.style.display = 'none';
        }
        if (importProgressBar) {
            importProgressBar.style.width = '0%';
            importProgressBar.textContent = '0%';
            importProgressBar.classList.remove('bg-success', 'bg-danger');
            importProgressBar.classList.add('progress-bar-animated');
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
        if (importPollingInterval) {
            clearInterval(importPollingInterval);
            importPollingInterval = null;
        }
    }

    async function pollImportStatus(taskId) {
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

                // Update progress bar
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
                        importProgressBar.classList.remove('progress-bar-animated');
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
                        importProgressBar.classList.remove('progress-bar-animated');
                    }
                    if (importStatusEl) {
                        importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> ${data.error}</div>`;
                    }
                    // Don't reset immediately, let user see the error
                    setTimeout(resetImportModal, 8000);
                }
            } catch (error) {
                clearInterval(importPollingInterval);
                if (importStatusEl) {
                    importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> Could not poll for import status. ${error.message}</div>`;
                }
                if (importProgressBar) {
                    importProgressBar.classList.add('bg-danger');
                    importProgressBar.classList.remove('progress-bar-animated');
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
            const formData = new FormData();
            formData.append('db_file', file);

            // Disable form and show progress
            importSubmitBtn.disabled = true;
            dbFileInput.disabled = true;
            importProgressContainer.style.display = 'block';
            importStatusEl.innerHTML = `<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Uploading file... This may take a while for large files.</div>`;
            importStatusEl.style.display = 'block';

            try {
                const response = await fetch('/api/import-weather-db', {
                    method: 'POST',
                    body: formData,
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.error || 'An unknown error occurred during upload.');
                }

                // Start polling for status
                pollImportStatus(result.task_id);

            } catch (error) {
                importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Upload Error:</strong> ${error.message}</div>`;
                setTimeout(resetImportModal, 5000);
            }
        });
    }

    if (importModalEl) {
        importModalEl.addEventListener('hidden.bs.modal', () => {
            resetImportModal();
        });
    }
});
