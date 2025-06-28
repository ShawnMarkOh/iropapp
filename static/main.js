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

// Global variables
let HUBS = [];
let allHubsMap;
let defaultActiveHubs;

async function initializeHubs() {
    let hubsToLoad = defaultActiveHubs; // Default
    if (getCookie("cookie_consent") === "true") {
        const savedOrder = getCookie("card_order");
        if (savedOrder && savedOrder.length > 0) {
            const order = savedOrder.split(',');
            hubsToLoad = order.map(iata => allHubsMap.get(iata)).filter(Boolean);
        } else {
            // If consent is given but no order is saved (or is empty), save the default.
            const defaultOrder = defaultActiveHubs.map(h => h.iata).join(',');
            setCookie("card_order", defaultOrder, 365);
            hubsToLoad = defaultActiveHubs;
        }
    }
    HUBS = hubsToLoad;
}
window.FAA_EVENT_DEFINITIONS = {};
window.FAA_LITERAL_TRANSLATIONS = {};
let FAA_EVENTS = {};
let groundStops = {};
let groundDelays = {};
let allDayBaseData = [[],[],[]]; // Store all data globally for lazy loading
let dayLabels = [];
let dailyBrief = [{}, {}, {}];
let sortable = null; // To hold the Sortable instance

async function loadDashboard(isUpdate = false) {
  const dashboard = document.getElementById('dashboard');
  if (!isUpdate) {
    dashboard.innerHTML = `<div class="text-center p-5 fs-4"><div class="spinner-border text-primary mb-3" role="status"></div><div>Loading weather data for all bases...</div></div>`;
  }
  
  let localDailyBrief = [{}, {}, {}];
  let localDayLabels = [];
  let allDone = 0;
  const dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  const isArchive = dateMatch && dateMatch[1] !== (new Date().toISOString().slice(0,10));
  
  // Reset global data
  allDayBaseData = [[],[],[]];

  const hubsToFetch = Array.from(allHubsMap.values());

  for (const hub of hubsToFetch) {
    try {
      let wx;
      let snapshots = [];
      if (isArchive) {
        // Archive logic remains the same
        snapshots = await fetchSnapshots(hub.iata, dateMatch[1]);
        let periods = Array(24).fill(null);
        let faa_events = [];
        let sirs = [];
        let terminal_constraints = [];
        let timezone = hub.tz;
        let alerts = [];
        if (snapshots.length) {
          snapshots.forEach(snap => {
            let hour = snap.hour;
            let data = snap.weather || {};
            if (data.hourly && data.hourly.length) {
              let found = data.hourly.find(p => {
                  const d = new Date(p.startTime);
                  const periodHour = parseInt(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hour12: false, timeZone: timezone }).format(d), 10) % 24;
                  return periodHour === hour;
              });
              if (found) periods[hour] = found;
            }
            if (data.alerts) alerts = data.alerts; // Get latest alerts from snapshot
            faa_events = snap.faa_events || faa_events;
            sirs = snap.sirs || sirs;
            terminal_constraints = snap.terminal_constraints || terminal_constraints;
          });
        }
        wx = { hourly: periods.filter(x => x), daily: [], timezone, sirs, terminal_constraints, faa_events, alerts };
      } else {
        wx = await fetchWeather(hub.iata);
      }
      
      window.LATEST_SIRS = wx.sirs || [];
      window.LATEST_CONSTRAINTS = wx.terminal_constraints || [];
      FAA_EVENTS[hub.iata] = wx.faa_events || [];
      const alerts = wx.alerts || [];

      const daysToProcess = isArchive ? 1 : 3;
      for (let dayIdx=0; dayIdx<daysToProcess; ++dayIdx) {
        let ymd, dayDate;
        const now = new Date();
        const todayYmdInHub = new Intl.DateTimeFormat('fr-CA', { timeZone: hub.tz }).format(now);
        const currentHourInHub = parseInt(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hour12: false, timeZone: hub.tz }).format(now), 10) % 24;

        if (isArchive) {
            ymd = dateMatch[1];
            dayDate = new Date(ymd + 'T12:00:00Z'); // Use noon UTC to avoid timezone issues
        } else {
            const d = new Date();
            d.setDate(d.getDate() + dayIdx);
            // Get YYYY-MM-DD string for the target date in the hub's timezone
            ymd = new Intl.DateTimeFormat('fr-CA', { timeZone: hub.tz }).format(d);
            dayDate = d;
        }

        let period = (wx.daily || []).find(p => {
            const periodDate = new Intl.DateTimeFormat('fr-CA', { timeZone: hub.tz }).format(new Date(p.startTime));
            return periodDate === ymd && p.isDaytime;
        }) || 
        (wx.daily || []).find(p => {
            const periodDate = new Intl.DateTimeFormat('fr-CA', { timeZone: hub.tz }).format(new Date(p.startTime));
            return periodDate === ymd;
        });

        if (!localDayLabels[dayIdx]) {
            if (isArchive) {
                localDayLabels[dayIdx] = `Archive for ${formatLocalDateOnly(dayDate, hub.tz)}`;
            } else {
                const dayName = dayIdx === 0 ? "Today" : dayIdx === 1 ? "Tomorrow" : "The Day After";
                localDayLabels[dayIdx] = `${dayName} (${formatLocalDateOnly(dayDate, hub.tz)})`;
            }
        }
        
        const highlightHour = (ymd === todayYmdInHub) ? currentHourInHub : null;
        
        let faaEventsForDay = [];
        const hubEvents = FAA_EVENTS[hub.iata] || [];
        if (hubEvents.length > 0) {
            // All events in the list are for a single day. Check if it's the day we're rendering.
            const firstEventWithDate = hubEvents.find(e => e.local_time_iso);
            let eventListDate = null;
            if (firstEventWithDate) {
                eventListDate = new Intl.DateTimeFormat('fr-CA', { timeZone: hub.tz }).format(new Date(firstEventWithDate.local_time_iso));
            } else {
                // Fallback: if no event has a date, assume the list is for "today" relative to the hub.
                const todayYmd = new Intl.DateTimeFormat('fr-CA', { timeZone: hub.tz }).format(new Date());
                if (ymd === todayYmd) {
                    eventListDate = ymd;
                }
            }
            
            if (eventListDate === ymd) {
                faaEventsForDay = hubEvents;
            }
        }

        const groundStopData = groundStops[hub.iata] || null;
        const groundDelayData = groundDelays[hub.iata] || null;
        
        let groundStopEndHour = -1;
        let groundStopCrossesMidnight = false;
        if (groundStopData && groundStopData.end_time) {
            const timeStr = groundStopData.end_time;
            const timeMatch = timeStr.match(/(\d{1,2}):(\d{2})\s*(am|pm)?/i);
            if (timeMatch) {
                let hour = parseInt(timeMatch[1], 10);
                const ampm = (timeMatch[3] || '').toLowerCase();
                if (ampm === 'pm' && hour < 12) hour += 12;
                if (ampm === 'am' && hour === 12) hour = 0;
                groundStopEndHour = hour;

                // A ground stop is active now. If its end hour is before the current hour, it must be for tomorrow.
                if (highlightHour !== null && groundStopEndHour < highlightHour) {
                    groundStopCrossesMidnight = true;
                }
            }
        }

        let effectiveGroundStopData = groundStopData;
        if (groundStopData && groundStopEndHour !== -1) { // Only apply logic if there's an end time
            if (dayIdx === 1 && !groundStopCrossesMidnight) {
                effectiveGroundStopData = null;
            } else if (dayIdx > 1) {
                effectiveGroundStopData = null;
            }
        }

        let groundStopHoursForThisDay = null;
        if (effectiveGroundStopData && groundStopEndHour !== -1) {
            if (dayIdx === 0 && highlightHour !== null) {
                if (groundStopCrossesMidnight) {
                    groundStopHoursForThisDay = { start: highlightHour, end: 23 };
                } else {
                    groundStopHoursForThisDay = { start: highlightHour, end: groundStopEndHour };
                }
            } else if (dayIdx === 1 && groundStopCrossesMidnight) {
                groundStopHoursForThisDay = { start: 0, end: groundStopEndHour };
            }
        }

        const {hourBlocks, percentHigh, percentPartial} = analyzeDayHours(wx.hourly, ymd, hub.tz, highlightHour, hub.name, ymd, hub.runways, faaEventsForDay, groundStopHoursForThisDay, (dayIdx > 0 ? null : groundDelayData), isArchive ? snapshots : null);
        let assessment = getDailyAssessment(percentHigh, percentPartial);
        
        if (effectiveGroundStopData) {
            assessment.label = "🛑 ACTIVE IROP";
            assessment.class = "risk-high";
            assessment.summary = "Active IROP";
        } else if (groundDelayData && dayIdx === 0) {
            assessment.label = "DELAY PROGRAM";
            assessment.class = "risk-moderate";
            assessment.summary = "Active Delay";
        }

        // Determine the temperature to display, defaulting to daily forecast
        let displayTemp = (period && (period.temperature + "°" + period.temperatureUnit)) || "--";
        // If it's today, try to get the current hour's temperature
        if (highlightHour !== null) {
            const currentHourBlock = hourBlocks[highlightHour];
            if (currentHourBlock && currentHourBlock.temp) {
                displayTemp = currentHourBlock.temp;
            }
        }

        // Determine the wind to display, defaulting to daily forecast
        let displayWind = (period && (period.windSpeed + (period.windGust ? `, Gusts ${period.windGust}` : ""))) || "--";
        // If it's today, try to get the current hour's wind
        if (highlightHour !== null) {
            const currentHourBlock = hourBlocks[highlightHour];
            if (currentHourBlock && currentHourBlock.windKts > 0) {
                displayWind = `${currentHourBlock.windDir} ${currentHourBlock.windKts.toFixed(0)} kts (${currentHourBlock.windMPH.toFixed(0)} mph)`;
            } else if (currentHourBlock) {
                displayWind = "Calm";
            }
        }

        const card = { isArchive, hub, name: hub.name, iata: hub.iata, city: hub.city, date: formatLocalDateOnly(dayDate, hub.tz), temp: displayTemp, shortForecast: (period && period.shortForecast) || "", detailedForecast: (period && period.detailedForecast) || "", wind: displayWind, percentHigh, percentPartial, riskLabel: assessment.label, riskClass: assessment.class, hourBlocks, summary: assessment.summary, groundStop: effectiveGroundStopData, groundDelay: (dayIdx > 0 ? null : groundDelayData), alerts: alerts };
        
        allDayBaseData[dayIdx].push(card);
        if (!localDailyBrief[dayIdx][assessment.summary]) localDailyBrief[dayIdx][assessment.summary] = [];
        localDailyBrief[dayIdx][assessment.summary].push(hub.iata);
        if (!localDailyBrief[dayIdx].details) localDailyBrief[dayIdx].details = [];
        if (percentHigh > 0) localDailyBrief[dayIdx].details.push(`${hub.iata}: ${percentHigh}% wx hours (${card.shortForecast})`);
      }
      allDone++;
      if (allDone === hubsToFetch.length) {
        dayLabels = localDayLabels;
        dailyBrief = localDailyBrief;

        const activeIatas = new Set(HUBS.map(h => h.iata));
        const activeHubOrder = HUBS.map(h => h.iata);
        const filteredData = allDayBaseData.map(dayData => {
            const filtered = dayData.filter(card => activeIatas.has(card.iata));
            filtered.sort((a, b) => activeHubOrder.indexOf(a.iata) - activeHubOrder.indexOf(b.iata));
            return filtered;
        });

        renderDashboard(filteredData, dayLabels, dailyBrief, isUpdate);
        if (!isUpdate) {
            setupAccordionListeners();
            initSortable();
        }
      }
    } catch (err) {
      console.error(`Failed to load data for ${hub.iata}:`, err);
      allDone++;
      if (allDone === hubsToFetch.length) {
        dayLabels = localDayLabels;
        dailyBrief = localDailyBrief;

        const activeIatas = new Set(HUBS.map(h => h.iata));
        const activeHubOrder = HUBS.map(h => h.iata);
        const filteredData = allDayBaseData.map(dayData => {
            const filtered = dayData.filter(card => activeIatas.has(card.iata));
            filtered.sort((a, b) => activeHubOrder.indexOf(a.iata) - activeHubOrder.indexOf(b.iata));
            return filtered;
        });

        renderDashboard(filteredData, dayLabels, dailyBrief, isUpdate);
        if (!isUpdate) {
            setupAccordionListeners();
            initSortable();
        }
      }
    }
  }
}

function initSortable() {
    const consent = getCookie("cookie_consent");
    if (consent !== "true") return;

    const grid = document.querySelector('#day-0-container .row');
    if (grid) {
        if (sortable) {
            sortable.destroy();
        }
        sortable = new Sortable(grid, {
            animation: 150,
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            onEnd: function (evt) {
                const cardElements = Array.from(grid.children);
                const newOrder = cardElements.map(el => el.id.split('-')[1]);
                setCookie("card_order", newOrder.join(','), 365);
            }
        });
    }
}

function setupAccordionListeners() {
    const accordion = document.getElementById('future-days-accordion');
    if (!accordion) return;

    let day1Loaded = false;
    let day2Loaded = false;
    
    const collapse1 = document.getElementById('collapse-day-1');
    if (collapse1) {
        collapse1.addEventListener('show.bs.collapse', () => {
            if (!day1Loaded) {
                const activeIatas = new Set(HUBS.map(h => h.iata));
                const activeHubOrder = HUBS.map(h => h.iata);
                const filteredDayData = allDayBaseData[1].filter(card => activeIatas.has(card.iata));
                filteredDayData.sort((a, b) => activeHubOrder.indexOf(a.iata) - activeHubOrder.indexOf(b.iata));
                renderDay(filteredDayData, 'day-1-container', 1);
                day1Loaded = true;
            }
        });
    }

    const collapse2 = document.getElementById('collapse-day-2');
    if (collapse2) {
        collapse2.addEventListener('show.bs.collapse', () => {
            if (!day2Loaded) {
                const activeIatas = new Set(HUBS.map(h => h.iata));
                const activeHubOrder = HUBS.map(h => h.iata);
                const filteredDayData = allDayBaseData[2].filter(card => activeIatas.has(card.iata));
                filteredDayData.sort((a, b) => activeHubOrder.indexOf(a.iata) - activeHubOrder.indexOf(b.iata));
                renderDay(filteredDayData, 'day-2-container', 2);
                day2Loaded = true;
            }
        });
    }
}

async function fetchDbStatus() {
    try {
        const response = await fetch('/db_status');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        const dbStatusEl = document.getElementById('db-status');
        if (dbStatusEl) dbStatusEl.textContent = `Database size: ${data.size} ${data.unit}, containing ${data.days} days of data.`;
    } catch (error) {
        console.error("Could not fetch DB status:", error);
        const dbStatusEl = document.getElementById('db-status');
        if (dbStatusEl) dbStatusEl.textContent = 'Could not load database status.';
    }
}

async function updateAdvisories() {
    groundStops = await fetchGroundStops();
    groundDelays = await fetchGroundDelays();
    let watched = HUBS.map(h => h.iata);
    
    let stopped = Object.keys(groundStops).filter(iata => watched.includes(iata));
    let banner = document.getElementById('groundstop-banner');
    if (stopped.length > 0) {
        banner.innerHTML = `⚠️ <b>IMMEDIATE IROPS:</b> <span style="font-weight:600;">${stopped.join(", ")}</span> ground stop active. <span style="font-size:1rem;">${stopped.map(iata => groundStops[iata].reason).join("; ")}</span>`;
        banner.style.display = "block";
    } else {
        banner.style.display = "none";
    }

    let delayBanner = document.getElementById('grounddelay-banner');
    let delayed = Object.keys(groundDelays).filter(iata => watched.includes(iata) && !stopped.includes(iata));
    if (delayed.length > 0) {
        delayBanner.innerHTML = `DELAY ADVISORY: ${delayed.map(iata => `<b>${iata}</b> (${groundDelays[iata].reason}, avg ${groundDelays[iata].avg_delay})`).join("; ")}`;
        delayBanner.style.display = "block";
    } else {
        delayBanner.style.display = "none";
    }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Fetch all possible hubs first
  const activeHubsPromise = getHubs();
  const inactiveHubsPromise = fetch('/api/hubs/inactive').then(res => res.json());
  const [dActiveHubs, defaultInactiveHubs] = await Promise.all([activeHubsPromise, inactiveHubsPromise]);
  defaultActiveHubs = dActiveHubs;
  allHubsMap = new Map([...defaultActiveHubs, ...defaultInactiveHubs].map(h => [h.iata, h]));

  // Cookie consent check
  const consent = getCookie("cookie_consent");
  if (consent === null) {
      const banner = document.getElementById('cookie-consent-banner');
      if(banner) banner.style.display = 'block';

      document.getElementById('cookie-accept')?.addEventListener('click', () => {
          setCookie("cookie_consent", "true", 365);
          if(banner) banner.style.display = 'none';
          // Save default order on accept
          const defaultOrder = defaultActiveHubs.map(h => h.iata).join(',');
          setCookie("card_order", defaultOrder, 365);
      });

      document.getElementById('cookie-decline')?.addEventListener('click', () => {
          setCookie("cookie_consent", "false", 365);
          if(banner) banner.style.display = 'none';
      });
  }

  await initializeHubs();

  // Main dashboard logic
  await updateAdvisories();
  await loadDashboard();
  await fetchDbStatus();
  
  let dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  if (dateMatch && dateMatch[1] !== (new Date().toISOString().slice(0,10))) {
    let bannerContainer = document.getElementById('archive-banner-container');
    bannerContainer.innerHTML = `<div class="archive-banner">Viewing archived weather for ${dateMatch[1]}</div>`;
  }

  if (typeof io !== "undefined") {
    const socket = io();
    socket.on('dashboard_update', async function(data) {
      console.log('Dashboard update received via websocket.');
      await updateAdvisories();
      await loadDashboard(true);
      await fetchDbStatus();
    });

    socket.on('hub_order_update', async function(data) {
      console.log('Hub order update received via websocket.', data);
      const newOrder = data.order;
      if (newOrder && Array.isArray(newOrder)) {
        // Update the cookie for this user if they've consented
        if (getCookie("cookie_consent") === "true") {
            setCookie("card_order", newOrder.join(','), 365);
        }
        // Re-initialize hubs based on the new order
        await initializeHubs();
        
        // Re-render the dashboard with the new hub order from existing data
        const activeIatas = new Set(HUBS.map(h => h.iata));
        const activeHubOrder = HUBS.map(h => h.iata);
        const filteredData = allDayBaseData.map(dayData => {
            const filtered = dayData.filter(card => activeIatas.has(card.iata));
            filtered.sort((a, b) => activeHubOrder.indexOf(a.iata) - activeHubOrder.indexOf(b.iata));
            return filtered;
        });
        
        renderDashboard(filteredData, dayLabels, dailyBrief, true);
        initSortable();
      }
    });
  }
});
