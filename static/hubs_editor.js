// Cookie helpers
function setCookie(name, value, days) {
    let expires = "";
    if (days) {
        let date = new Date();
        date.setTime(date.getTime() + (days*24*60*60*1000));
        expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + (value || "")  + expires + "; path=/; SameSite=Lax";
}

function getCookie(name) {
    let nameEQ = name + "=";
    let ca = document.cookie.split(';');
    for(let i=0;i < ca.length;i++) {
        let c = ca[i];
        while (c.charAt(0)==' ') c = c.substring(1,c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
    }
    return null;
}

document.addEventListener('DOMContentLoaded', () => {
    const activeHubsContainer = document.getElementById('active-hubs-container');
    const inactiveHubsContainer = document.getElementById('inactive-hubs-container');
    const socket = typeof io !== 'undefined' ? io() : null;

    // If the editor elements aren't on the page, don't initialize.
    if (!activeHubsContainer || !inactiveHubsContainer) {
        return;
    }

    const hubPresets = {
        'default': ['CLT', 'PHL', 'DCA', 'DAY', 'DFW'],
        'preset2': ['ORD', 'DFW', 'MIA', 'PHX'],
        'preset3': ['CLT', 'MDT', 'PHL']
    };

    function renderHub(hub) {
        return `
            <div class="card mb-3" data-iata="${hub.iata}">
                <div class="card-body p-3">
                    <h5 class="card-title mb-1">${hub.name} (${hub.iata})</h5>
                    <p class="card-text text-muted small">${hub.city}</p>
                </div>
            </div>
        `;
    }

    function saveHubOrder() {
        const activeHubElements = Array.from(activeHubsContainer.querySelectorAll('.card'));
        const activeHubsOrder = activeHubElements.map(el => el.dataset.iata);
        
        if (getCookie("cookie_consent") === "true") {
            setCookie('card_order', activeHubsOrder.join(','), 365);
        }

        if (socket) {
            socket.emit('hub_order_change', { order: activeHubsOrder });
        }

        // Manage placeholder text for active hubs
        const activePlaceholder = activeHubsContainer.querySelector('p.text-muted');
        if (activeHubElements.length === 0) {
            if (!activePlaceholder) {
                const p = document.createElement('p');
                p.className = 'text-muted';
                p.textContent = 'Drag hubs here to activate them.';
                activeHubsContainer.appendChild(p);
            }
        } else {
            if (activePlaceholder) {
                activePlaceholder.remove();
            }
        }

        // Manage placeholder text for inactive hubs
        const inactiveElements = inactiveHubsContainer.querySelectorAll('.card');
        const inactivePlaceholder = inactiveHubsContainer.querySelector('p.text-muted');
        if (inactiveElements.length === 0) {
            if (!inactivePlaceholder) {
                const p = document.createElement('p');
                p.className = 'text-muted';
                p.textContent = 'All hubs are active.';
                inactiveHubsContainer.appendChild(p);
            }
        } else {
            if (inactivePlaceholder) {
                inactivePlaceholder.remove();
            }
        }
    }

    function applyHubPreset(presetName, allHubsMap) {
        const presetOrder = hubPresets[presetName];
        if (!presetOrder) return;
    
        const activeHubs = presetOrder.map(iata => allHubsMap.get(iata)).filter(Boolean);
        const activeIataSet = new Set(presetOrder);
        const inactiveHubs = [...allHubsMap.values()].filter(hub => !activeIataSet.has(hub.iata));
    
        activeHubsContainer.innerHTML = activeHubs.map(renderHub).join('');
        inactiveHubsContainer.innerHTML = inactiveHubs.map(renderHub).join('');
        
        saveHubOrder();
    }

    function loadHubs(defaultActiveHubs, defaultInactiveHubs) {
        const allHubs = [...defaultActiveHubs, ...defaultInactiveHubs];
        const allHubsMap = new Map(allHubs.map(h => [h.iata, h]));

        let activeHubs = [];
        let inactiveHubs = [];

        const savedOrderCookie = getCookie('card_order');
        if (getCookie("cookie_consent") === "true" && savedOrderCookie) {
            const savedOrder = savedOrderCookie.split(',');
            activeHubs = savedOrder.map(iata => allHubsMap.get(iata)).filter(Boolean);
            const activeIataSet = new Set(savedOrder);
            inactiveHubs = allHubs.filter(hub => !activeIataSet.has(hub.iata));
        } else {
            activeHubs = defaultActiveHubs;
            inactiveHubs = defaultInactiveHubs;
        }

        activeHubsContainer.innerHTML = activeHubs.map(renderHub).join('');
        inactiveHubsContainer.innerHTML = inactiveHubs.map(renderHub).join('');

        if (activeHubs.length === 0) {
            activeHubsContainer.innerHTML = '<p class="text-muted">Drag hubs here to activate them.</p>';
        }
        if (inactiveHubs.length === 0) {
            inactiveHubsContainer.innerHTML = '<p class="text-muted">All hubs are active.</p>';
        }
    }

    async function init() {
        let defaultActiveHubs, defaultInactiveHubs;
        try {
            const [defaultActiveRes, defaultInactiveRes] = await Promise.all([
                fetch('/api/hubs'),
                fetch('/api/hubs/inactive')
            ]);

            if (!defaultActiveRes.ok || !defaultInactiveRes.ok) {
                throw new Error('Failed to fetch hub data');
            }

            defaultActiveHubs = await defaultActiveRes.json();
            defaultInactiveHubs = await defaultInactiveRes.json();
        } catch (error) {
            console.error(error);
            activeHubsContainer.innerHTML = '<div class="alert alert-danger">Could not load active hubs.</div>';
            inactiveHubsContainer.innerHTML = '<div class="alert alert-danger">Could not load inactive hubs.</div>';
            return;
        }

        loadHubs(defaultActiveHubs, defaultInactiveHubs);

        const allHubs = [...defaultActiveHubs, ...defaultInactiveHubs];
        const allHubsMap = new Map(allHubs.map(h => [h.iata, h]));

        document.querySelectorAll('.hub-presets-dropdown').forEach(dropdown => {
            dropdown.addEventListener('click', (event) => {
                if (event.target.matches('.dropdown-item')) {
                    event.preventDefault();
                    const presetName = event.target.dataset.preset;
                    applyHubPreset(presetName, allHubsMap);
                }
            });
        });

        new Sortable(activeHubsContainer, {
            group: 'shared-hubs',
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: saveHubOrder
        });

        new Sortable(inactiveHubsContainer, {
            group: 'shared-hubs',
            animation: 150,
            ghostClass: 'sortable-ghost',
            onEnd: saveHubOrder
        });
    }

    init();
});
