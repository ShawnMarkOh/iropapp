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
    let allHubsMap; // Will be populated in init()
    const isMobile = window.matchMedia('(max-width: 767.98px)').matches;

    // If the editor elements aren't on the page, don't initialize.
    if (!activeHubsContainer || !inactiveHubsContainer) {
        return;
    }

    // Listen for newly added hubs from the other modal
    document.addEventListener('newHubAdded', (e) => {
        const newHub = e.detail;
        if (newHub && inactiveHubsContainer) {
            // Check if it's already in the DOM to prevent duplicates
            if (document.querySelector(`.hub-card[data-iata="${newHub.iata}"]`)) {
                return;
            }
            if (allHubsMap) {
                allHubsMap.set(newHub.iata, newHub);
            }
            
            // Add the new hub card to the inactive list
            const inactivePlaceholder = inactiveHubsContainer.querySelector('p.text-muted');
            if (inactivePlaceholder) {
                inactivePlaceholder.remove();
            }
            inactiveHubsContainer.insertAdjacentHTML('beforeend', renderHub(newHub, false));
        }
    });

    const hubPresets = {
        'default': ['CLT', 'PHL', 'DCA', 'DAY', 'DFW'],
        'preset2': ['ORD', 'DFW', 'MIA', 'PHX'],
        'preset3': ['CLT', 'MDT', 'PHL']
    };

    function renderHub(hub, isActive) {
        let buttons = '';
        if (isMobile) {
            if (isActive) {
                buttons = `
                    <div class="hub-actions">
                        <button class="btn btn-sm btn-outline-secondary hub-action-btn" data-action="move-up" aria-label="Move Up">▲</button>
                        <button class="btn btn-sm btn-outline-secondary hub-action-btn" data-action="move-down" aria-label="Move Down">▼</button>
                        <button class="btn btn-sm btn-outline-warning hub-action-btn" data-action="deactivate" aria-label="Deactivate">✖</button>
                    </div>
                `;
            } else {
                buttons = `
                    <div class="hub-actions">
                        <button class="btn btn-sm btn-outline-success hub-action-btn" data-action="activate" aria-label="Activate">✔</button>
                    </div>
                `;
            }
        }

        return `
            <div class="card mb-3 hub-card" data-iata="${hub.iata}">
                <div class="card-body">
                    <div>
                        <h5 class="card-title">${hub.name} (${hub.iata})</h5>
                        <p class="card-text text-muted small">${hub.city}</p>
                    </div>
                    ${buttons}
                </div>
            </div>
        `;
    }

    function updateMobileButtonStates() {
        if (!isMobile) return;

        const activeCards = activeHubsContainer.querySelectorAll('.hub-card');
        activeCards.forEach((card, index) => {
            const upButton = card.querySelector('[data-action="move-up"]');
            const downButton = card.querySelector('[data-action="move-down"]');
            if (upButton) upButton.disabled = (index === 0);
            if (downButton) downButton.disabled = (index === activeCards.length - 1);
        });
    }

    function handleHubAction(e) {
        const button = e.target.closest('button[data-action]');
        if (!button) return;

        const card = button.closest('.hub-card');
        if (!card) return;

        const action = button.dataset.action;
        const iata = card.dataset.iata;
        const hubData = allHubsMap.get(iata);

        switch (action) {
            case 'activate':
                card.remove();
                activeHubsContainer.insertAdjacentHTML('beforeend', renderHub(hubData, true));
                break;
            case 'deactivate':
                card.remove();
                inactiveHubsContainer.insertAdjacentHTML('afterbegin', renderHub(hubData, false));
                break;
            case 'move-up':
                const prev = card.previousElementSibling;
                if (prev) {
                    card.parentElement.insertBefore(card, prev);
                }
                break;
            case 'move-down':
                const next = card.nextElementSibling;
                if (next) {
                    card.parentElement.insertBefore(next, card);
                }
                break;
        }
        
        saveHubOrder();
        updateMobileButtonStates();
    }

    function saveHubOrder() {
        const activeHubElements = Array.from(activeHubsContainer.querySelectorAll('.card'));
        const activeHubsOrder = activeHubElements.map(el => el.dataset.iata);
        
        const inactiveHubElements = Array.from(inactiveHubsContainer.querySelectorAll('.card'));
        const inactiveHubsOrder = inactiveHubElements.map(el => el.dataset.iata);

        // Persist to backend
        fetch('/api/hubs/update_order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ active: activeHubsOrder, inactive: inactiveHubsOrder }),
        }).catch(err => console.error("Failed to save hub order to backend:", err));

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
                p.textContent = 'Drag or use buttons to activate hubs.';
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
        const inactiveHubs = [...allHubsMap.values()].filter(hub => !activeIataSet.has(hub.iata)).sort((a, b) => a.name.localeCompare(b.name));
    
        activeHubsContainer.innerHTML = activeHubs.map(hub => renderHub(hub, true)).join('');
        inactiveHubsContainer.innerHTML = inactiveHubs.map(hub => renderHub(hub, false)).join('');
        
        saveHubOrder();
        updateMobileButtonStates();
    }

    function loadHubs(defaultActiveHubs, defaultInactiveHubs) {
        const allHubs = [...defaultActiveHubs, ...defaultInactiveHubs];
        allHubsMap = new Map(allHubs.map(h => [h.iata, h]));
        window.allHubsMap = allHubsMap; // Expose for airport_adder

        let activeHubs = [];
        let inactiveHubs = [];

        const savedOrderCookie = getCookie('card_order');
        if (getCookie("cookie_consent") === "true" && savedOrderCookie) {
            const savedOrder = savedOrderCookie.split(',');
            activeHubs = savedOrder.map(iata => allHubsMap.get(iata)).filter(Boolean);
            const activeIataSet = new Set(savedOrder);
            inactiveHubs = allHubs.filter(hub => !activeIataSet.has(hub.iata)).sort((a, b) => a.name.localeCompare(b.name));
        } else {
            activeHubs = defaultActiveHubs;
            inactiveHubs = defaultInactiveHubs;
        }

        activeHubsContainer.innerHTML = activeHubs.map(hub => renderHub(hub, true)).join('');
        inactiveHubsContainer.innerHTML = inactiveHubs.map(hub => renderHub(hub, false)).join('');

        if (activeHubs.length === 0) {
            activeHubsContainer.innerHTML = '<p class="text-muted">Drag or use buttons to activate hubs.</p>';
        }
        if (inactiveHubs.length === 0) {
            inactiveHubsContainer.innerHTML = '<p class="text-muted">All hubs are active.</p>';
        }
        updateMobileButtonStates();
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

        document.querySelectorAll('.hub-presets-dropdown').forEach(dropdown => {
            dropdown.addEventListener('click', (event) => {
                if (event.target.matches('.dropdown-item')) {
                    event.preventDefault();
                    const presetName = event.target.dataset.preset;
                    applyHubPreset(presetName, allHubsMap);
                }
            });
        });

        if (isMobile) {
            // On mobile, use buttons
            [activeHubsContainer, inactiveHubsContainer].forEach(container => {
                container.addEventListener('click', handleHubAction);
            });
        } else {
            // On desktop, use SortableJS
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
    }

    init();
});
