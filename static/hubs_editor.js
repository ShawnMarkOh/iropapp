document.addEventListener('DOMContentLoaded', () => {
    const activeHubsContainer = document.getElementById('active-hubs-container');
    const inactiveHubsContainer = document.getElementById('inactive-hubs-container');

    function renderHub(hub) {
        return `
            <div class="card mb-3">
                <div class="card-body">
                    <h5 class="card-title">${hub.name} (${hub.iata})</h5>
                    <p class="card-text">${hub.city}</p>
                </div>
            </div>
        `;
    }

    async function loadHubs() {
        try {
            const [activeRes, inactiveRes] = await Promise.all([
                fetch('/api/hubs'),
                fetch('/api/hubs/inactive')
            ]);

            if (!activeRes.ok || !inactiveRes.ok) {
                throw new Error('Failed to fetch hub data');
            }

            const activeHubs = await activeRes.json();
            const inactiveHubs = await inactiveRes.json();

            activeHubsContainer.innerHTML = activeHubs.map(renderHub).join('');
            inactiveHubsContainer.innerHTML = inactiveHubs.map(renderHub).join('');

            if (inactiveHubs.length === 0) {
                inactiveHubsContainer.innerHTML = '<p>No inactive hubs.</p>';
            }

        } catch (error) {
            console.error(error);
            activeHubsContainer.innerHTML = '<div class="alert alert-danger">Could not load active hubs.</div>';
            inactiveHubsContainer.innerHTML = '<div class="alert alert-danger">Could not load inactive hubs.</div>';
        }
    }

    loadHubs();
});
