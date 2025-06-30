document.addEventListener('DOMContentLoaded', () => {

    async function fetchData(url, previewId) {
        const previewEl = document.querySelector(`#${previewId} pre code`);
        if (!previewEl) return;

        previewEl.textContent = 'Loading...';
        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            previewEl.textContent = JSON.stringify(data, null, 2);
        } catch (error) {
            console.error('Error fetching API ', error);
            previewEl.textContent = `Error loading  ${error.message}`;
        }
    }

    document.getElementById('fetch-hubs')?.addEventListener('click', () => {
        fetchData('/api/hubs', 'hubs-preview');
    });

    document.getElementById('fetch-airport-info')?.addEventListener('click', () => {
        fetchData('/api/airport-info/KPIA', 'airport-info-preview');
    });

    document.getElementById('fetch-weather')?.addEventListener('click', () => {
        fetchData('/api/weather/CLT', 'weather-preview');
    });

    document.getElementById('fetch-snapshots')?.addEventListener('click', async () => {
        const previewEl = document.querySelector('#snapshots-preview pre code');
        if (!previewEl) return;

        previewEl.textContent = 'Loading... (step 1: fetching archive dates)';
        try {
            const datesResponse = await fetch('/api/archive-dates');
            if (!datesResponse.ok) throw new Error('Could not fetch archive dates.');
            const dates = await datesResponse.json();

            if (dates.length === 0) {
                previewEl.textContent = 'No archive dates available to fetch snapshots.';
                return;
            }
            
            const latestDate = dates[0];
            previewEl.textContent = `Loading... (step 2: fetching snapshots for CLT on ${latestDate})`;
            await fetchData(`/api/hourly-snapshots/CLT/${latestDate}`, 'snapshots-preview');

        } catch (error) {
            console.error('Error fetching snapshot ', error);
            previewEl.textContent = `Error loading  ${error.message}`;
        }
    });

    document.getElementById('fetch-groundstops')?.addEventListener('click', () => {
        fetchData('/api/groundstops', 'groundstops-preview');
    });

    document.getElementById('fetch-archive-dates')?.addEventListener('click', () => {
        fetchData('/api/archive-dates', 'archive-dates-preview');
    });

});
