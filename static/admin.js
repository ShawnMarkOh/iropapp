document.addEventListener('DOMContentLoaded', () => {
    // --- Import Data Modal Logic ---
    const importForm = document.getElementById('import-data-form');
    const importStatusEl = document.getElementById('import-status');
    const dbFileInput = document.getElementById('db-file-input');
    const importModalEl = document.getElementById('importDataModal');

    if (importForm && importStatusEl && dbFileInput && importModalEl) {
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

            importStatusEl.innerHTML = `<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Uploading and processing... This may take a moment.</div>`;
            importStatusEl.style.display = 'block';

            try {
                const response = await fetch('/api/import-weather-db', {
                    method: 'POST',
                    body: formData,
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.error || 'An unknown error occurred.');
                }

                const stats = result.stats;
                importStatusEl.innerHTML = `
                    <div class="alert alert-success">
                        <strong>Import Complete!</strong><br>
                        New Hourly Weather records: ${stats.hourly_weather}<br>
                        New Hourly Snapshots: ${stats.hourly_snapshot}<br>
                        The page will now reload to reflect the new data.
                    </div>`;
                
                setTimeout(() => {
                    window.location.reload();
                }, 3000);

            } catch (error) {
                importStatusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> ${error.message}</div>`;
            }
        });

        importModalEl.addEventListener('hidden.bs.modal', () => {
            importStatusEl.style.display = 'none';
            importStatusEl.innerHTML = '';
            importForm.reset();
        });
    }
});
