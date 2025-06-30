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
            const CHUNK_SIZE = 1 * 1024 * 1024; // 1MB
            const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
            const uploadId = `upload-${Date.now()}-${Math.random().toString(36).substring(2)}`;

            importStatusEl.style.display = 'block';
            importStatusEl.innerHTML = `<div class="alert alert-info">Preparing to upload...</div>`;
            
            try {
                for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                    const start = chunkIndex * CHUNK_SIZE;
                    const end = Math.min(start + CHUNK_SIZE, file.size);
                    const chunk = file.slice(start, end);

                    const formData = new FormData();
                    formData.append('chunk', chunk, file.name);
                    formData.append('upload_id', uploadId);
                    formData.append('chunk_index', chunkIndex);
                    
                    const response = await fetch('/api/import-weather-db-chunk', {
                        method: 'POST',
                        body: formData,
                    });

                    if (!response.ok) {
                        const result = await response.json();
                        throw new Error(result.error || `Chunk ${chunkIndex + 1} upload failed.`);
                    }
                    
                    const progress = Math.round(((chunkIndex + 1) / totalChunks) * 100);
                    importStatusEl.innerHTML = `<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Uploading file... (${progress}%)</div>`;
                }

                importStatusEl.innerHTML = `<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Upload complete. Processing data... This may take a moment.</div>`;

                const completeResponse = await fetch('/api/import-weather-db-complete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        upload_id: uploadId,
                        filename: file.name,
                        total_chunks: totalChunks
                    })
                });

                const result = await completeResponse.json();
                if (!completeResponse.ok) {
                    throw new Error(result.error || 'An unknown error occurred during processing.');
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
