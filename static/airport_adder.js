document.addEventListener('DOMContentLoaded', () => {
    const addAirportForm = document.getElementById('add-airport-form');
    const icaoInput = document.getElementById('icao-input');
    const statusEl = document.getElementById('add-airport-status');
    const addAirportModalEl = document.getElementById('addAirportModal');
    const addAirportModal = addAirportModalEl ? new bootstrap.Modal(addAirportModalEl) : null;
    const editHubsModalEl = document.getElementById('editHubsModal');
    const editHubsModal = editHubsModalEl ? new bootstrap.Modal(editHubsModalEl) : null;

    if (!addAirportForm || !addAirportModal) return;

    addAirportForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const icao = icaoInput.value.toUpperCase();
        
        statusEl.style.display = 'block';
        statusEl.innerHTML = `<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Fetching data for ${icao}...</div>`;

        try {
            // 1. Fetch from our own backend proxy
            const airportResp = await fetch(`/api/airport-info/${icao}`);
            if (!airportResp.ok) {
                let errorMsg = `Could not fetch airport data (status: ${airportResp.status})`;
                try {
                    const errJson = await airportResp.json();
                    if (errJson.error) errorMsg = errJson.error;
                } catch (e) { /* ignore if response is not json */ }
                throw new Error(errorMsg);
            }
            const airportRespText = await airportResp.text();
            let airportJson;

            try {
                // First, try to parse the whole response as JSON. This handles the direct JSON case.
                airportJson = JSON.parse(airportRespText);
            } catch (e) {
                // If that fails, it might be HTML with a <pre> tag.
                const preMatch = airportRespText.match(/<pre[^>]*>([\s\S]*?)<\/pre>/);
                if (preMatch && preMatch[1]) {
                    try {
                        airportJson = JSON.parse(preMatch[1]);
                    } catch (e2) {
                        throw new Error('Found a <pre> tag, but its content is not valid JSON.');
                    }
                } else {
                    // If no JSON and no <pre> tag, then we can't handle it.
                    throw new Error('No valid data found for that ICAO code. The airport may not exist or the API is unavailable.');
                }
            }

            const airportData = airportJson[0];

            if (!airportData || !airportData.iataId) {
                throw new Error('No valid data found for that ICAO code.');
            }

            // Check if IATA already exists
            if (window.allHubsMap && window.allHubsMap.has(airportData.iataId)) {
                throw new Error(`Airport ${airportData.iataId} (${airportData.name}) already exists in the hub list.`);
            }

            statusEl.innerHTML = `<div class="alert alert-info"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Fetching timezone for ${airportData.iataId}...</div>`;

            // 2. Fetch timezone
            const tzResp = await fetch(`https://timeapi.io/api/TimeZone/coordinate?latitude=${airportData.lat}&longitude=${airportData.lon}`);
            if (!tzResp.ok) {
                throw new Error('Could not fetch timezone data.');
            }
            const tzData = await tzResp.json();
            const timezone = tzData.timeZone;

            if (!timezone) {
                throw new Error('Could not determine timezone for the airport.');
            }

            // 3. Format into hub object
            const newHub = {
                name: (airportData.name.split('/')[1] || airportData.name).trim().replace(/\s\s+/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                iata: airportData.iataId,
                city: `${(airportData.name.split('/')[0] || '').trim().replace(/\b\w/g, l => l.toUpperCase())}, ${airportData.state}`,
                tz: timezone,
                lat: parseFloat(airportData.lat),
                lon: parseFloat(airportData.lon),
                runways: (airportData.runways || []).map(r => {
                    const parts = r.id.split('/');
                    const heading = parseInt(parts[0], 10) * 10;
                    const len = parseInt((r.dimension || '0x0').split('x')[0], 10);
                    return {
                        label: r.id.replace(/^0+/, ''),
                        heading: heading,
                        len: len
                    };
                }).filter(r => r.len > 0)
            };

            // 4. Dispatch event to notify other parts of the app
            document.dispatchEvent(new CustomEvent('newHubAdded', { detail: newHub }));

            // 5. Show success and manage modals
            statusEl.innerHTML = `<div class="alert alert-success">Successfully added ${newHub.name} (${newHub.iata}). It is now available in the 'Inactive Hubs' list in the editor.</div>`;
            
            setTimeout(() => {
                addAirportModal.hide();
                if (editHubsModal) {
                    editHubsModal.show();
                }
            }, 2500);

        } catch (error) {
            statusEl.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> ${error.message}</div>`;
        }
    });

    addAirportModalEl.addEventListener('hidden.bs.modal', () => {
        statusEl.style.display = 'none';
        statusEl.innerHTML = '';
        addAirportForm.reset();
    });
});
