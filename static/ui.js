function isFAAEventRelevant(event, hubIata) {
  if (!event || !event.desc) return false;
  const desc = event.desc.toUpperCase();
  for (const key in window.FAA_EVENT_DEFINITIONS) {
    if (desc.includes(key)) return true;
  }
  if (desc.includes(hubIata)) return true;
  return false;
}

function renderBaseCard(card) {
  let groundStopHTML = '';
  if (card.groundStop) {
    groundStopHTML = `<div class="ground-stop-info">ACTIVE GROUND STOP: ${card.groundStop.reason} (until ${card.groundStop.end_time})</div>`;
  }
  let groundDelayHTML = '';
  if (card.groundDelay) {
    groundDelayHTML = `<div class="ground-delay-info">GROUND DELAY: ${card.groundDelay.reason} (avg ${card.groundDelay.avg_delay})</div>`;
  }
  let alertsHTML = '';
  if (card.alerts && card.alerts.length > 0) {
      alertsHTML = card.alerts.map(alert => {
          const properties = alert.properties;
          const severity = (properties.severity || '').toLowerCase();
          let alertClass = 'weather-alert-info-moderate';
          if (severity === 'severe' || severity === 'extreme') {
              alertClass = 'weather-alert-info-high';
          }
          return `<div class="${alertClass}" title="${properties.headline}">${properties.event}</div>`;
      }).join('');
  }

  return `
    ${alertsHTML}
    ${groundStopHTML}
    ${groundDelayHTML}
    <div class="card-header-section">
      <div class="base-title">${card.name} (${card.iata})</div>
      <div class="base-city">${card.city}</div>
    </div>
    <div class="card-body-section">
      <div class="short-forecast mb-2">${card.shortForecast || "Forecast not available."}</div>
      <div class="weather-details mb-2">
        <span><i class="bi bi-thermometer-half"></i> Temp: <b>${card.temp}</b></span>
        <span><i class="bi bi-wind"></i> Wind: <b>${card.wind}</b></span>
      </div>
      <details class="detailed-forecast-details mb-2">
        <summary class="detailed-forecast-summary">Detailed Forecast</summary>
        <div class="detailed-forecast-content">
          ${card.detailedForecast || "Detailed forecast not available."}
        </div>
      </details>
      <div class="risk-assessment ${card.riskClass} mb-2">
        <div class="risk-label">${card.riskLabel}</div>
        <div class="risk-percentages">
          <span>TS/Severe: <b>${card.percentHigh}%</b></span>
          <span>Other Hazards: <b>${card.percentPartial}%</b></span>
        </div>
      </div>
    </div>
    <div class="hourly-breakdown-section mt-auto">
      <div class="hourly-breakdown mb-1">
        ${card.hourBlocks.map(h => {
          const relevantFAAEvents = (h.faaEvents || []).filter(ev => isFAAEventRelevant(ev, card.iata));
          let exclamations = relevantFAAEvents.length
            ? ' <span class="faa-event-mark" title="' + relevantFAAEvents.map(ev =>
                  (Object.keys(window.FAA_LITERAL_TRANSLATIONS).filter(k => ev.desc.toUpperCase().includes(k))
                   .map(k => window.FAA_LITERAL_TRANSLATIONS[k]).join(', ') || translateFAAString(ev.desc))
              ).join('; ') + '">' + '❗'.repeat(relevantFAAEvents.length) + '</span>'
            : '';
          
          if (h.isGroundStop) {
            exclamations += ` <span class="ground-stop-mark" title="Ground Stop until ${card.groundStop.end_time}">🛑</span>`;
          }

          return `<div class="hour-cell ${h.hourClass} ${h.isGroundStop ? 'hour-ground-stop' : ''}" 
            title="${h.hour}:00 - ${translateFAAString(h.txt)}${h.temp ? ', ' + h.temp : ''}${h.windTxt ? ' | ' + h.windTxt : ''}${h.windKts>0?` | Wind: ${h.windKts.toFixed(0)}kts (${h.windMPH.toFixed(0)}mph)`:""}"
            onclick='${h.risk==="nodata" ? "" : `showHourModal(${JSON.stringify(h).replace(/'/g, "\\'")}, ${JSON.stringify(card).replace(/'/g, "\\'")})`}'
          >${String(h.hour).padStart(2,'0')}${exclamations}</div>`;
        }).join("")}
      </div>
    </div>
  `;
}

function renderDay(dayData, containerId, dayIdx) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!dayData || dayData.length === 0) {
        container.innerHTML = '<div class="text-center p-4">No data available for this day.</div>';
        return;
    }

    let grid = container.querySelector('.row');
    if (!grid) {
        grid = document.createElement('div');
        grid.className = 'row row-cols-1 row-cols-md-2 row-cols-lg-3 row-cols-xl-4 row-cols-xxl-6 g-4 justify-content-center';
        container.innerHTML = '';
        container.appendChild(grid);
    }

    // Build a new set of card elements in memory
    const newCardElements = dayData.map(card => {
        const cardWrapper = document.createElement('div');
        cardWrapper.className = 'col d-flex';
        cardWrapper.id = `card-${card.iata}-${dayIdx}`;
        cardWrapper.innerHTML = `
            <div class="card h-100 w-100 ${card.groundStop ? 'ground-stop-active' : (card.groundDelay ? 'ground-delay-active' : '')}">
                <div class="card-body p-3">
                    ${renderBaseCard(card)}
                </div>
            </div>
        `;
        return cardWrapper;
    });

    // Replace the grid's children with the new set, which is more efficient than innerHTML
    grid.replaceChildren(...newCardElements);
}


function renderDashboard(allDayBase, dayLabels, dailyBrief, isUpdate = false) {
    const dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
    const isArchive = dateMatch && dateMatch[1] !== (new Date().toISOString().slice(0, 10));

    // Render Briefing
    let briefingHTML = "";
    ["Today", "Tomorrow", "The day after"].forEach((when, idx) => {
        let b = dailyBrief[idx], txts = [];
        if (!b || Object.keys(b).length === 0) return;
        if (b["Active IROP"] && b["Active IROP"].length) txts.push(`<span class="risk-highlight risk-high-text">Active IROP (Ground Stop)</span> at <b>${b["Active IROP"].join(", ")}</b>`);
        if (b["Active Delay"] && b["Active Delay"].length) txts.push(`<span class="risk-highlight risk-moderate-text">Active Delay Program</span> at <b>${b["Active Delay"].join(", ")}</b>`);
        if (b["High IROPS risk"] && b["High IROPS risk"].length) txts.push(`<span class="risk-highlight risk-high-text">High IROPS risk</span> at <b>${b["High IROPS risk"].join(", ")}</b>`);
        if (b["Moderate IROPS risk"] && b["Moderate IROPS risk"].length) txts.push(`<span class="risk-highlight risk-moderate-text">Moderate IROPS risk</span> at <b>${b["Moderate IROPS risk"].join(", ")}</b>`);
        if (b["Partial IROPS risk"] && b["Partial IROPS risk"].length) txts.push(`<span class="risk-highlight risk-partial-text">Partial risk</span> at <b>${b["Partial IROPS risk"].join(", ")}</b>`);
        if (b["Slight IROPS risk"] && b["Slight IROPS risk"].length) txts.push(`<span class="risk-highlight risk-partial-text">Slight risk</span> at <b>${b["Slight IROPS risk"].join(", ")}</b>`);
        if (b["No Weather Risk"] && b["No Weather Risk"].length) txts.push(`<span class="risk-highlight risk-normal-text">No weather risk expected</span> at <b>${b["No Weather Risk"].join(", ")}</b>`);
        let detailTxt = b.details && b.details.length ? `<div style="font-size:1rem;color:var(--dim-text); margin-top:0.125rem;">Details: ${b.details.join("; ")}</div>` : "";
        briefingHTML += `<div style="margin-bottom:0.5rem;"><b>${when}'s outlook:</b> ${txts.length ? txts.join(", ") : `<span class="risk-highlight risk-normal-text">No weather risk expected.</span>`}${detailTxt}</div>`;
    });
    document.getElementById('briefing-content').innerHTML = briefingHTML;

    const dashboardEl = document.getElementById('dashboard');
    
    // Only render the main structure if it's not an update or if it's not there yet.
    if (!isUpdate || !dashboardEl.querySelector('.day-header')) {
        let dashHTML = "";

        // Day 0 (Today) - Always rendered
        if (allDayBase[0] && allDayBase[0].length > 0) {
            dashHTML += `<div class="day-header">${dayLabels[0]}</div>`;
            dashHTML += `<div id="day-0-container"></div>`; // Container for cards
        } else {
            dashHTML += `<div class="day-header">${dayLabels[0] || 'Today'}</div><div class="text-center p-5 fs-4">No data available for today.</div>`;
        }

        // Days 1 & 2 (Tomorrow, Day After) - Render as accordions if not in archive mode
        if (!isArchive) {
            dashHTML += `<div class="accordion mt-4" id="future-days-accordion">`;
            for (let dayIdx = 1; dayIdx < 3; ++dayIdx) {
                if (dayLabels[dayIdx]) {
                    dashHTML += `
                        <div class="accordion-item">
                            <h2 class="accordion-header" id="heading-day-${dayIdx}">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-day-${dayIdx}" aria-expanded="false" aria-controls="collapse-day-${dayIdx}">
                                    ${dayLabels[dayIdx]}
                                </button>
                            </h2>
                            <div id="collapse-day-${dayIdx}" class="accordion-collapse collapse" aria-labelledby="heading-day-${dayIdx}" data-bs-parent="#future-days-accordion">
                                <div class="accordion-body" id="day-${dayIdx}-container">
                                    <div class="text-center p-4">
                                        <div class="spinner-border text-primary" role="status">
                                            <span class="visually-hidden">Loading...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }
            }
            dashHTML += `</div>`;
        }
        
        dashboardEl.innerHTML = dashHTML;
    }

    // Now, render the cards for Today into its container
    if (allDayBase[0] && allDayBase[0].length > 0) {
       renderDay(allDayBase[0], 'day-0-container', 0);
    }

    // If it's an update, also re-render content for any open accordions
    if (isUpdate && !isArchive) {
        for (let dayIdx = 1; dayIdx < 3; ++dayIdx) {
            const collapseEl = document.getElementById(`collapse-day-${dayIdx}`);
            if (collapseEl && collapseEl.classList.contains('show')) {
                renderDay(allDayBase[dayIdx], `day-${dayIdx}-container`, dayIdx);
            }
        }
    }
}

function showHourModal(block, base) {
  const modalLabel = document.getElementById('hourModalLabel');
  const modalBody = document.getElementById('hourModalBody');
  let riskStr = '';
  if (block.isBrief) riskStr = `<span class="modal-risk-brief">(Brief Weather Event)</span>`;
  else if (block.riskClass === "high") riskStr = `<span class="risk-high">High IROPS risk</span>`;
  else if (block.riskClass === "risk-moderate") riskStr = `<span class="risk-moderate">Moderate IROPS risk</span>`;
  else if (block.riskClass === "partial") riskStr = `<span class="risk-partial">Partial risk</span>`;
  else if (block.riskClass === "wind-high") riskStr = `<span class="risk-wind-high">High wind warning</span>`;
  else if (block.riskClass === "wind-partial") riskStr = `<span class="risk-wind-partial">Moderate crosswind</span>`;
  else if (block.riskClass === "nodata") riskStr = `<span class="hour-nodata">No data</span>`;
  else if (block.riskClass === "wind") riskStr = `<span class="risk-wind">Wind risk</span>`;
  else riskStr = `<span class="risk-normal">No Weather Risk</span>`;
  let closedRunways = (window.LATEST_SIRS || []).map(s => s.runway.replace(/\s/g,'').toUpperCase());
  let terminalConstraints = window.LATEST_CONSTRAINTS || [];
  
  let alertsModalHTML = '';
  if (base.alerts && base.alerts.length > 0) {
      alertsModalHTML = base.alerts.map(alert => {
          const p = alert.properties;
          const severity = (p.severity || '').toLowerCase();
          let style = 'background-color: var(--risk-moderate-bg); color: white; border-left-color: #fff;';
          if (severity === 'severe' || severity === 'extreme') {
              style = 'background-color: var(--risk-high-bg); color: white; border-left-color: #fff;';
          }

          return `
            <div class="faa-event-summary" style="${style} margin-bottom: 10px;">
                <b>${p.event}</b>
                <div style="font-size: 0.95em; margin-bottom: 5px;">${p.headline}</div>
                <details>
                    <summary style="font-size: 0.9em; cursor: pointer; font-weight: 500;">Details & Instructions</summary>
                    <div style="font-size: 0.9em; white-space: pre-wrap; background: rgba(0,0,0,0.1); padding: 8px; border-radius: 4px; margin-top: 5px;">
                      <p>${p.description}</p>
                      ${p.instruction ? `<hr style="border-color: rgba(255,255,255,0.5);"><p><b>Instruction:</b> ${p.instruction}</p>` : ''}
                    </div>
                </details>
            </div>
          `;
      }).join('');
  }

  let groundStopModalHTML = '';
  if (block.isGroundStop && base.groundStop) {
      groundStopModalHTML = `
        <div class="faa-event-summary" style="background-color: var(--risk-high-bg); color: white; border-left-color: #fff;">
            <b>Active Ground Stop</b><br>
            <b>Reason:</b> ${base.groundStop.reason}<br>
            <b>Ends:</b> ${base.groundStop.end_time}
        </div>
      `;
  }

  let groundDelayModalHTML = '';
  if (base.groundDelay) {
      groundDelayModalHTML = `
        <div class="faa-event-summary" style="background-color: var(--risk-moderate-bg); color: white; border-left-color: #fff;">
            <b>Active Ground Delay Program</b><br>
            <b>Reason:</b> ${base.groundDelay.reason}<br>
            <b>Average Delay:</b> ${base.groundDelay.avg_delay}
        </div>
      `;
  }

  let runwayStatusHTML = "";
  if (block.runways && block.runways.length > 0) {
    runwayStatusHTML = `
      <h5 class="modal-section-title mt-4">Runway Status</h5>
      <div class="table-responsive">
        <table class="modal-table runway-table table table-sm">
          <thead><tr><th>Runway</th><th>Length (ft)</th><th>Crosswind (kts)</th><th>Status</th></tr></thead>
          <tbody>
            ${block.runways.map(rw => {
              let rwName = rw.label.replace(/\s/g,'').toUpperCase();
              let isClosed = closedRunways.includes(rwName);
              let status = rw.warning;
              let className = rw.className;
              if (isClosed) { status = "CLOSED"; className = "runway-unsafe"; }
              return `<tr>
                  <td>${rw.label}</td>
                  <td>${rw.len}</td>
                  <td>${rw.cross}</td>
                  <td><span class="${className}">${status}</span></td>
                </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>
      <div class="runway-legend mt-2">
        <b>Legend:</b> <span class="runway-safe">SAFE</span> = CRJ900/700 OK. <span class="runway-crj700only">SAFE (CRJ700)</span> = CRJ700 only. <span class="runway-unsafe">CLOSED/UNSAFE</span> = Unsafe/Unavailable.
      </div>
    `;
  }
  let faaEventsHTML = block.faaEvents && block.faaEvents.length > 0 ? block.faaEvents.map(ev =>
    `<div class="faa-event-summary"><a href="https://nasstatus.faa.gov/" target="_blank" rel="noopener noreferrer" title="View FAA National Airspace System Status"><b>FAA Event:</b> ${translateFAAString(ev.desc)}</a><br>
      <span class="faa-event-details">
      <b>Local Hour:</b> ${String(block.hour).padStart(2,"0")}:00<br>
      <b>FAA Event Time (Zulu):</b> ${ev.zulu_time || "N/A"}<br>
      <b>When:</b> ${ev.when || "N/A"}
      </span>
    </div>`
  ).join("") : "";
  let constraintsHTML = "";
  if (terminalConstraints && terminalConstraints.length) {
    constraintsHTML = `
      <div class="faa-event-summary terminal-constraint">
        <b>Terminal Constraints:</b><br>
        <ul class="terminal-constraint-list">
          ${terminalConstraints.map(c => `<li>${c}</li>`).join("")}
        </ul>
      </div>
    `;
  }
  modalLabel.innerHTML = `${base.name} (${base.iata})`;
  modalBody.innerHTML = `
      <h5 class="modal-section-title">${base.isArchive ? "Archived Weather Details" : "Weather Details"}</h5>
      <div class="table-responsive">
        <table class="modal-table weather-details-table table table-sm">
          <tbody>
            <tr><th>Date & Hour</th><td>${block.ymd} @ ${String(block.hour).padStart(2, "0")}:00 Local</td></tr>
            <tr><th>Risk</th><td>${riskStr}</td></tr>
            ${block.temp ? `<tr><th>Temperature</th><td>${block.temp}</td></tr>` : ""}
            ${block.windTxt ? `<tr><th>Wind Hazard</th><td>${block.windTxt}</td></tr>` : ""}
            ${(block.windKts>0)?`<tr><th>Wind</th><td><b>${block.windKts.toFixed(0)} kts</b> (${block.windMPH.toFixed(0)} mph)${block.windDir?` from ${block.windDir}`:""}</td></tr>`:""}
            <tr><th>Short Forecast</th><td>${translateFAAString(block.txt) || "No data"}</td></tr>
            ${block.detailedF ? `<tr><th>Detailed Forecast</th><td>${block.detailedF}</td></tr>` : ""}
          </tbody>
        </table>
      </div>
      ${runwayStatusHTML}
      <div class="faa-section mt-3">${alertsModalHTML}${groundStopModalHTML}${groundDelayModalHTML}${faaEventsHTML}${constraintsHTML}</div>
      <div class="modal-footnote">
        <em>“No Weather Risk” means no thunderstorms or weather hazards in the forecast. Does <u>not</u> guarantee VFR or IFR flight conditions.</em>
      </div>
  `;
  let modal = new bootstrap.Modal(document.getElementById('hourModal'));
  modal.show();
}
