// Placeholders for globals and functions not defined in the original script
let HUBS = [];
window.FAA_EVENT_DEFINITIONS = {};
window.FAA_LITERAL_TRANSLATIONS = {};
function translateFAAString(s) {
    if (!s) return "N/A";
    // In a real scenario, this would look up definitions. For now, it just returns the string.
    return s;
}

let FAA_EVENTS = {};
let groundstopHubs = {};
const windDirs = {N:0, NNE:22.5, NE:45, ENE:67.5, E:90, ESE:112.5, SE:135, SSE:157.5, S:180, SSW:202.5, SW:225, WSW:247.5, W:270, WNW:292.5, NW:315, NNW:337.5};
function windDirToDeg(dir) {dir = (dir||"").toUpperCase();if (windDirs[dir] !== undefined) return windDirs[dir];if (/^\d+$/.test(dir)) return Number(dir);return null;}
function windToKts(val) {if (!val) return 0;let v = parseFloat(val);if (/mph/.test(val)) v *= 0.868976;return v;}
function windToMPH(val) {if (!val) return 0;let v = parseFloat(val);if (/mph/.test(val)) return v;return v * 1.15078;}
function crosswindComponent(runwayHeading, windDir, windKts) {let windDeg = windDirToDeg(windDir);if (windDeg === null) return 0;let angle = Math.abs(runwayHeading - windDeg);if (angle > 180) angle = 360 - angle;let rad = angle * Math.PI / 180;let cross = Math.abs(windKts * Math.sin(rad));return cross;}
function getHourWindRisk(spd, cross) {if (spd > 50) return {risk:"high", txt:"Wind > 50 kts", class:"hour-wind"};if (spd > 35) return {risk:"wind-high", txt:"High wind ("+spd+" kts)", class:"hour-wind-high"};if (spd > 0 && spd > 27) return {risk:"partial", txt:"Wind ("+spd+" kts)", class:"hour-wind"};if (cross > 27) return {risk:"high", txt:"Crosswind "+cross+" kts", class:"hour-wind"};if (cross > 20) return {risk:"wind-high", txt:"High crosswind ("+cross+" kts)", class:"hour-wind-high"};if (cross > 15) return {risk:"wind-partial", txt:"Moderate crosswind ("+cross+" kts)", class:"hour-wind-partial"};return null;}
function analyzeRunwaySafety(runways, windDir, windKts) {
    let runwayResults = [];
    for (let rw of runways) {
        if (rw.len < 5040) continue;
        let cross = crosswindComponent(rw.heading, windDir, windKts);
        let status = "";
        let className = "";
        if (rw.len >= 5360) {
            let safe = (windKts <= 50) && (cross <= 27);
            status = safe ? "SAFE" : (windKts > 50 ? "UNSAFE WIND" : "UNSAFE CROSSWIND");
            className = safe ? "runway-safe" : "runway-unsafe";
        } else if (rw.len >= 5040) {
            let safe = (windKts <= 50) && (cross <= 27);
            status = safe ? "SAFE (CRJ700)" : (windKts > 50 ? "UNSAFE WIND" : "UNSAFE CROSSWIND");
            className = safe ? "runway-crj700only" : "runway-unsafe";
        }
        if (rw.len >= 5040) {
            runwayResults.push({
                label: rw.label,
                cross: Math.round(cross),
                safe: status.startsWith("SAFE"),
                warning: status,
                len: rw.len,
                className: className
            });
        }
    }
    return runwayResults;
}
function getHourRisk(forecast) {if (!forecast) return {risk:"clear", key:null, hourClass: "hour-clear"};let forecastL = forecast.toLowerCase();if (/thunderstorms likely|severe thunderstorm|severe t[- ]?storm|tstm likely|t\.storm likely|t[- ]?storm likely/.test(forecastL)) {return { risk: "high", key: "Thunder", hourClass: "hour-thunder" };}if (/thunderstorm|tstm|t-storm|t\.storm/.test(forecastL)) {if (/slight chance|chance/.test(forecastL)) {return { risk: "partial", key: "Thunder", hourClass: "hour-other" };}return { risk: "partial", key: "Thunder", hourClass: "hour-other" };}if (/severe|tornado|hail|damaging wind|squall|snow|blizzard|ice|sleet|wintry|freezing rain|freezing drizzle/.test(forecastL)) {return { risk: "high", key: "Severe", hourClass: "hour-severe" };}if (/heavy rain|flood|downpour|fog|low visibility|low clouds/.test(forecastL)) {return { risk: "partial", key: null, hourClass: "hour-other" };}return { risk: "clear", key: null, hourClass: "hour-clear" };}
function formatLocalDateOnly(dtIso, tz) {try {const d = new Date(dtIso);return new Intl.DateTimeFormat('en-US', {weekday: "short", month: "short", day: "numeric", year: "numeric",timeZone: tz}).format(d);} catch { return dtIso; }}
function getDailyAssessment(percentHigh, percentPartial) {
    if (percentHigh >= 30 || percentPartial > 50)
        return { label: "⚠️ High IROPS Risk", class: "risk-high", summary: "High IROPS risk" };
    if (percentHigh >= 25 || percentPartial > 40)
        return { label: "🟧 Moderate IROPS Risk", class: "risk-moderate", summary: "Moderate IROPS risk" };
    if (percentHigh >= 10 || percentPartial >= 30)
        return { label: "⛅ Partial IROPS Risk", class: "risk-partial", summary: "Partial IROPS risk" };
    if (percentPartial >= 10)
        return { label: "⛅ Slight IROPS Risk", class: "risk-partial", summary: "Slight IROPS risk" };
    return { label: "✔️ No Weather Risk", class: "risk-normal", summary: "No Weather Risk" };
}
async function getHubs() { const resp = await fetch('/api/hubs'); HUBS = await resp.json(); return HUBS; }
async function fetchGroundStops() { let res = await fetch('/api/groundstops'); return await res.json(); }
async function fetchWeather(iata) {
  let url = '/api/weather/' + iata;
  let dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  if (dateMatch) {
    url += '?date=' + dateMatch[1];
  }
  let res = await fetch(url);
  return await res.json();
}
async function fetchSnapshots(iata, date) {
    let url = `/api/hourly-snapshots/${iata}/${date}`;
    let res = await fetch(url);
    return await res.json();
}
async function loadDashboard() {
  const dashboard = document.getElementById('dashboard');
  dashboard.innerHTML = '<div class="text-center p-5 fs-4">Loading weather data for all bases...</div>';
  let allDayBase = [[],[],[]], dailyBrief = [{}, {}, {}], dayLabels = [], allDone = 0;
  const dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  const baseDate = dateMatch ? new Date(dateMatch[1] + "T12:00:00Z") : new Date(); // Use UTC to avoid timezone shifts
  const isArchive = dateMatch && dateMatch[1] !== (new Date().toISOString().slice(0,10));
  
  for (const hub of HUBS) {
    try {
      let wx;
      if (isArchive) {
        let snapshots = await fetchSnapshots(hub.iata, dateMatch[1]);
        let periods = Array(24).fill(null);
        let faa_events = [];
        let sirs = [];
        let terminal_constraints = [];
        let timezone = hub.tz;
        if (snapshots.length) {
          snapshots.forEach(snap => {
            let hour = snap.hour;
            let data = snap.weather || {};
            if (data.hourly && data.hourly.length) {
              let found = data.hourly.find(
                p => {
                  let pd = new Date(new Date(p.startTime).toLocaleString("en-US", {timeZone: timezone}));
                  return pd.getHours() === hour;
                }
              );
              if (found) periods[hour] = found;
            }
            faa_events = snap.faa_events || faa_events;
            sirs = snap.sirs || sirs;
            terminal_constraints = snap.terminal_constraints || terminal_constraints;
          });
        }
        wx = {
          hourly: periods.filter(x => x),
          daily: [],
          timezone,
          sirs,
          terminal_constraints,
          faa_events
        };
      } else {
        wx = await fetchWeather(hub.iata);
      }
      window.LATEST_SIRS = wx.sirs || [];
      window.LATEST_CONSTRAINTS = wx.terminal_constraints || [];
      FAA_EVENTS[hub.iata] = wx.faa_events || [];
      for (let dayIdx=0; dayIdx<3; ++dayIdx) {
        const dayDate = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate() + dayIdx);
        const ymd = dayDate.getFullYear() + "-" + String(dayDate.getMonth()+1).padStart(2,"0") + "-" + String(dayDate.getDate()).padStart(2,"0");
        let period = wx.daily && wx.daily.find(p=>{
          const pd = new Date(new Date(p.startTime).toLocaleString("en-US", {timeZone: hub.tz}));
          const p_ymd = pd.getFullYear() + "-" + String(pd.getMonth()+1).padStart(2,"0") + "-" + String(pd.getDate()).padStart(2,"0");
          return p_ymd === ymd && p.isDaytime;
        }) || (wx.daily && wx.daily.find(p=>{
          const pd = new Date(new Date(p.startTime).toLocaleString("en-US", {timeZone: hub.tz}));
          const p_ymd = pd.getFullYear() + "-" + String(pd.getMonth()+1).padStart(2,"0") + "-" + String(pd.getDate()).padStart(2,"0");
          return p_ymd === ymd;
        }));
        if (!dayLabels[dayIdx] && period) dayLabels[dayIdx] = (period.name || "Day") + " (" + formatLocalDateOnly(period.startTime, hub.tz) + ")";
        else if (!dayLabels[dayIdx]) dayLabels[dayIdx] = formatLocalDateOnly(dayDate, hub.tz);
        const highlightHour = (ymd === new Date().toLocaleDateString('sv').slice(0,10)) ? new Date().getHours() : null;
        let faaEventsForDay = (FAA_EVENTS[hub.iata]||[]).filter(e => {
          if (e.local_hour !== undefined && e.local_hour !== null) {
            let eventDate = new Date(dayDate.toLocaleString("en-US", {timeZone: hub.tz}));
            eventDate.setHours(e.local_hour,0,0,0);
            const eymd = eventDate.getFullYear() + "-" + String(eventDate.getMonth()+1).padStart(2,"0") + "-" + String(eventDate.getDate()).padStart(2,"0");
            return eymd === ymd;
          }
          return false;
        });
        const {hourBlocks, percentHigh, percentPartial, total} = analyzeDayHours(wx.hourly, ymd, hub.tz, highlightHour, hub.name, ymd, hub.runways, faaEventsForDay);
        const assessment = getDailyAssessment(percentHigh, percentPartial);
        const card = {
          hub, name: hub.name, iata: hub.iata, city: hub.city,
          label: (period && period.name) || "Day",
          date: (period && formatLocalDateOnly(period.startTime, hub.tz)) || formatLocalDateOnly(dayDate, hub.tz),
          temp: (period && (period.temperature + "°" + period.temperatureUnit)) || "--",
          shortForecast: (period && period.shortForecast) || "",
          detailedForecast: (period && period.detailedForecast) || "",
          wind: (period && (period.windSpeed + (period.windGust ? `, Gusts ${period.windGust}` : ""))) || "--",
          percentHigh, percentPartial,
          riskLabel: assessment.label,
          riskClass: assessment.class,
          hourBlocks,
          summary: assessment.summary
        };
        allDayBase[dayIdx].push(card);
        if (!dailyBrief[dayIdx][assessment.summary]) dailyBrief[dayIdx][assessment.summary] = [];
        dailyBrief[dayIdx][assessment.summary].push(hub.iata);
        if (!dailyBrief[dayIdx].details) dailyBrief[dayIdx].details = [];
        if (percentHigh>0)
          dailyBrief[dayIdx].details.push(`${hub.iata}: ${percentHigh}% wx hours (${card.shortForecast})`);
      }
      allDone++;
      if (allDone === HUBS.length) renderDashboard(allDayBase, dayLabels, dailyBrief);
    } catch (err) {
      console.error(`Failed to load data for ${hub.iata}:`, err);
      allDone++;
      if (allDone === HUBS.length) renderDashboard(allDayBase, dayLabels, dailyBrief);
    }
  }
}
function analyzeDayHours(hourlyPeriods, dateYMD, tz, highlightHour, baseLabel, ymdStr, runways, faaEventsForDay) {
  let hourData = {};
  for (const period of hourlyPeriods) {
    const local = new Date(new Date(period.startTime).toLocaleString("en-US", {timeZone: tz}));
    const ymd = local.getFullYear() + "-" + String(local.getMonth()+1).padStart(2, "0") + "-" + String(local.getDate()).padStart(2, "0");
    if (ymd !== dateYMD) continue;
    hourData[local.getHours()] = { ...period, local };
  }
  let faaEventsIndexed = {};
  if (faaEventsForDay && faaEventsForDay.length) {
    for (let event of faaEventsForDay) {
      if (event.local_hour !== null && event.local_hour !== undefined)
        faaEventsIndexed[event.local_hour] = faaEventsIndexed[event.local_hour] || [];
      if (event.local_hour !== null && event.local_hour !== undefined)
        faaEventsIndexed[event.local_hour].push(event);
    }
  }
  let hourBlocks = [];
  let rawRisks = [];
  for (let h = 0; h < 24; h++) {
    let period = hourData[h];
    let riskObj, txt, shortF="", detailedF="", windRisk=null, windTxt="", spdKts=0, spdMPH=0, dir="", temp="";
    let runwayStatus = [];
    let faaEvent = faaEventsIndexed[h] || [];
    if (period) {
      riskObj = getHourRisk((period.shortForecast || "") + " " + (period.detailedForecast || ""));
      txt = period.shortForecast || "";
      shortF = period.shortForecast || "";
      detailedF = period.detailedForecast || "";
      if (period.windSpeed && period.windSpeed !== "--") {
        spdKts = windToKts(period.windSpeed);
        spdMPH = windToMPH(period.windSpeed);
      }
      if (period.windDirection) dir = period.windDirection;
      if (period.temperature !== undefined && period.temperatureUnit) {
        temp = `${period.temperature}°${period.temperatureUnit}`;
      }
      runwayStatus = analyzeRunwaySafety(runways, dir, spdKts);
      let crossMax = Math.max(0, ...runwayStatus.map(rw=>rw.cross));
      let windRiskObj = getHourWindRisk(spdKts, crossMax);

      if (windRiskObj) {
          windRisk = windRiskObj.risk;
          windTxt = windRiskObj.txt;
          if (windRiskObj.risk === "high" || (windRiskObj.risk === "wind-high" && riskObj.risk !== "high") || (windRiskObj.risk === "wind-partial" && riskObj.risk === "clear")) {
              riskObj = { risk: windRiskObj.risk, key: "Wind", hourClass: windRiskObj.class };
          }
      }

    } else {
      riskObj = { risk: "nodata", key: null, hourClass: "hour-nodata" };
      txt = "No data"; shortF = ""; detailedF = ""; temp = "";
    }
    rawRisks.push(riskObj.risk);
    hourBlocks.push({
      hour: h,
      txt: txt,
      risk: riskObj.risk,
      hourClass: riskObj.hourClass + (highlightHour === h ? " hour-current" : ""),
      isCurrent: (highlightHour === h),
      baseLabel: baseLabel || "",
      ymd: ymdStr,
      shortF: shortF,
      detailedF: detailedF,
      riskClass: riskObj.risk,
      windRisk, windTxt, windDir: dir, windKts: spdKts, windMPH: spdMPH,
      runways: runwayStatus,
      isBrief: false,
      faaEvents: faaEvent,
      temp: temp
    });
  }
  let countHigh = 0, countPartial = 0, total = 0;
  let curType = null, curLen = 0, curStart = 0;
  let highMark = Array(24).fill(false), partialMark = Array(24).fill(false);
  for (let i=0; i<=24; i++) {
    let r = i<24 ? rawRisks[i] : null;
    if (r === curType) { curLen++; }
    else {
      if ((curType === "high" || curType === "partial") && curLen > 1) {
        for (let j=curStart; j<curStart+curLen; j++) {
          if (curType === "high") highMark[j] = true;
          else if (curType === "partial") partialMark[j] = true;
        }
      }
      curType = r; curLen = 1; curStart = i;
    }
  }
  for (let h=0; h<24; h++) {
    if (rawRisks[h] !== "nodata") total++;
    if (h < 1 || h > 3) {
      if (highMark[h]) countHigh++;
      else if (partialMark[h]) countPartial++;
    }
  }
  for (let h=0; h<24; h++) {
    if ((rawRisks[h]==="high" || rawRisks[h]==="partial") && !highMark[h] && !partialMark[h]) {
      hourBlocks[h].hourClass += " hour-brief"; hourBlocks[h].isBrief = true;
    }
  }
  return {hourBlocks,percentHigh: total ? Math.round((countHigh/total)*100) : 0,percentPartial: total ? Math.round((countPartial/total)*100) : 0,total};
}
function renderDashboard(allDayBase, dayLabels, dailyBrief) {
  const dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  const isArchive = dateMatch && dateMatch[1] !== (new Date().toISOString().slice(0,10));
  let briefingHTML = "";
  ["Today", "Tomorrow", "The day after"].forEach((when, idx) => {
    let b = dailyBrief[idx], txts = [];
    if (!b || Object.keys(b).length === 0) return;
    if (b["High IROPS risk"] && b["High IROPS risk"].length) {
      txts.push(`<b>High IROPS risk</b> at <b>${b["High IROPS risk"].join(", ")}</b>`);
    }
    if (b["Moderate IROPS risk"] && b["Moderate IROPS risk"].length) {
      txts.push(`<b>Moderate IROPS risk</b> at <b>${b["Moderate IROPS risk"].join(", ")}</b>`);
    }
    if (b["Partial IROPS risk"] && b["Partial IROPS risk"].length) {
      txts.push(`<b>Partial risk</b> at <b>${b["Partial IROPS risk"].join(", ")}</b>`);
    }
    if (b["Slight IROPS risk"] && b["Slight IROPS risk"].length) {
      txts.push(`Slight risk at <b>${b["Slight IROPS risk"].join(", ")}</b>`);
    }
    if (b["No Weather Risk"] && b["No Weather Risk"].length) {
      txts.push(`No weather risk expected at <b>${b["No Weather Risk"].join(", ")}</b>`);
    }
    let detailTxt = b.details && b.details.length ? `<div style="font-size:1rem;color:#c0a060; margin-top:2px;">Details: ${b.details.join("; ")}</div>` : "";
    briefingHTML += `<div style="margin-bottom:8px;"><b>${when}'s outlook:</b> ${txts.length ? txts.join(", ") : "No weather risk expected."}${detailTxt}</div>`;
  });
  document.getElementById('briefing-content').innerHTML = briefingHTML;

  let dashHTML = "";
  const daysToRender = isArchive ? 1 : 3;

  for (let dayIdx=0; dayIdx<daysToRender; ++dayIdx) {
    if (!allDayBase[dayIdx] || allDayBase[dayIdx].length === 0) continue;
    dashHTML += `<div class="day-header">${dayLabels[dayIdx]}</div>`;
    dashHTML += `<div class="container-fluid px-2">
      <div class="row g-3">
        ${allDayBase[dayIdx].map(card => `
          <div class="col-12 col-md-6 col-lg-4 col-xl-2 d-flex">
            <div class="card h-100 w-100 shadow-sm">
              <div class="card-body p-2 p-lg-3">
                ${renderBaseCard(card)}
              </div>
            </div>
          </div>
        `).join("")}
      </div>
    </div>`;
  }
  document.getElementById('dashboard').innerHTML = dashHTML || '<div class="text-center p-5 fs-4">No data available for the selected date.</div>';
}
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
  return `
    <div class="base-title mb-1">${card.name} (${card.iata})<span style="font-size:.93rem;font-weight:400;color:#6a788a;"> – ${card.city}</span></div>
    <div class="short-forecast mb-1">${card.shortForecast}</div>
    <div style="font-size:0.97rem;margin-bottom:4px;">Temp: ${card.temp}</div>
    <div class="base-details mb-2"><b>Wind:</b> ${card.wind}</div>
    <details class="mb-2">
      <summary style="color:#3463c4;font-size:0.93rem;cursor:pointer;">Detailed Forecast</summary>
      <div style="font-size:0.94rem;color:#ccc;margin-top:5px;">${card.detailedForecast}</div>
    </details>
    <div class="${card.riskClass} mb-2" style="margin-bottom:5px;">
      ${card.riskLabel}
      <span style="font-weight:normal;color:#eee;font-size:0.97rem;display:block;">
        Thunderstorm/severe wx hours: <b>${card.percentHigh}%</b><br>
        Other hazard hours: <b>${card.percentPartial}%</b>
      </span>
    </div>
    <div class="hourly-breakdown mb-1">
      ${card.hourBlocks.map(h => {
        const relevantFAAEvents = (h.faaEvents || []).filter(ev => isFAAEventRelevant(ev, card.iata));
        const exclamations = relevantFAAEvents.length
          ? ' <span class="faa-event-mark" title="' + relevantFAAEvents.map(ev =>
                (Object.keys(window.FAA_LITERAL_TRANSLATIONS).filter(k => ev.desc.toUpperCase().includes(k))
                 .map(k => window.FAA_LITERAL_TRANSLATIONS[k]).join(', ') || translateFAAString(ev.desc))
            ).join('; ') + '">' + '❗'.repeat(relevantFAAEvents.length) + '</span>'
          : '';
        return `<div class="hour-cell ${h.hourClass}" 
          title="${h.hour}:00 - ${translateFAAString(h.txt)}${h.temp ? ', ' + h.temp : ''}${h.windTxt ? ' | ' + h.windTxt : ''}${h.windKts>0?` | Wind: ${h.windKts.toFixed(0)}kts (${h.windMPH.toFixed(0)}mph)`:""}"
          onclick='${h.risk==="nodata" ? "" : `showHourModal(${JSON.stringify(h).replace(/'/g, "\\u0027")},${JSON.stringify(card.hub).replace(/'/g, "\\u0027")})`}'
        >${String(h.hour).padStart(2,'0')}${exclamations}</div>`;
      }).join("")}
    </div>
  `;
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
  
  let runwayStatusHTML = "";
  if (block.runways && block.runways.length > 0) {
    runwayStatusHTML = `
      <h5 class="mt-3">Runway Status</h5>
      <table class="modal-table runway-table">
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
      <div class="mt-2" style="font-size:0.9em;color:var(--dim-text);">
        <b>Legend:</b> <span class="runway-safe">SAFE</span> = CRJ900/700 OK. <span class="runway-crj700only">SAFE (CRJ700)</span> = CRJ700 only. <span class="runway-unsafe">CLOSED/UNSAFE</span> = Unsafe/Unavailable.
      </div>
    `;
  }
  let faaEventsHTML = block.faaEvents && block.faaEvents.length > 0 ? block.faaEvents.map(ev =>
    `<div class="faa-event-summary"><b>FAA Event:</b> ${translateFAAString(ev.desc)}<br>
      <span style="color:#ddd;">
      <b>Local Hour:</b> ${String(block.hour).padStart(2,"0")}:00<br>
      <b>FAA Event Time (Zulu):</b> ${ev.zulu_time || "N/A"}<br>
      <b>When:</b> ${ev.when || "N/A"}
      </span>
    </div>`
  ).join("") : "";
  let constraintsHTML = "";
  if (terminalConstraints && terminalConstraints.length) {
    constraintsHTML = `
      <div class="faa-event-summary" style="background:#cbe7f8;color:#204060;border-left:4px solid #2274c7;margin-bottom:6px;">
        <b>Terminal Constraints:</b><br>
        <ul style="margin:0 0 0 12px;padding:0;">
          ${terminalConstraints.map(c => `<li>${c}</li>`).join("")}
        </ul>
      </div>
    `;
  }
  modalLabel.innerHTML = `${base.name} (${base.iata})`;
  modalBody.innerHTML = `
      <h5>Weather Details</h5>
      <table class="modal-table">
        <tr><th>Date & Hour</th><td>${block.ymd} @ ${String(block.hour).padStart(2, "0")}:00 Local</td></tr>
        <tr><th>Risk</th><td>${riskStr}</td></tr>
        ${block.temp ? `<tr><th>Temperature</th><td>${block.temp}</td></tr>` : ""}
        ${block.windTxt ? `<tr><th>Wind Hazard</th><td>${block.windTxt}</td></tr>` : ""}
        ${(block.windKts>0)?`<tr><th>Wind</th><td><b>${block.windKts.toFixed(0)} kts</b> (${block.windMPH.toFixed(0)} mph)${block.windDir?` from ${block.windDir}`:""}</td></tr>`:""}
        <tr><th>Short Forecast</th><td>${translateFAAString(block.txt) || "No data"}</td></tr>
        ${block.detailedF ? `<tr><th>Detailed Forecast</th><td>${block.detailedF}</td></tr>` : ""}
      </table>
      ${runwayStatusHTML}
      <div class="mt-3">${faaEventsHTML}${constraintsHTML}</div>
      <div style="margin-top:14px; color:var(--dim-text); font-size:.95rem;">
        <em>“No Weather Risk” means no thunderstorms or weather hazards in the forecast. Does <u>not</u> guarantee VFR or IFR flight conditions.</em>
      </div>
  `;
  let modal = new bootstrap.Modal(document.getElementById('hourModal'));
  modal.show();
}

document.addEventListener('DOMContentLoaded', async () => {
  HUBS = await getHubs();
  const groundstops = await fetchGroundStops();
  let watched = HUBS.map(h => h.iata);
  let stopped = Object.keys(groundstops).filter(iata => watched.includes(iata));
  let banner = document.getElementById('groundstop-banner');
  if (stopped.length > 0) {
    banner.innerHTML = `⚠️ <b>IMMEDIATE IROPS:</b> <span style="font-weight:600;">${stopped.join(", ")}</span> ground stop active. <span style="font-size:1rem;">${stopped.map(iata=>groundstops[iata]).join("; ")}</span>`;
    banner.style.display = "block";
  } else {
    banner.style.display = "none";
  }
  await loadDashboard();
  
  document.getElementById('weatherHistoryBtn').onclick = function() {
    let modal = new bootstrap.Modal(document.getElementById('dateModal'));
    modal.show();
  };
  
  document.getElementById('pickDateBtn').onclick = function() {
    const picker = document.getElementById('datePicker');
    if (picker && picker.value) {
      window.location = `/?date=${picker.value}`;
    }
  }
  
  let dateMatch = window.location.search.match(/[?&]date=([0-9]{4}-[0-9]{2}-[0-9]{2})/);
  if (dateMatch && dateMatch[1] !== (new Date().toISOString().slice(0,10))) {
    let bannerContainer = document.getElementById('archive-banner-container');
    bannerContainer.innerHTML = `<div class="archive-banner">Viewing archived weather for ${dateMatch[1]}</div>`;
  }

  if (typeof io !== "undefined") {
    const socket = io();
    socket.on('dashboard_update', function(data) {
      console.log('Dashboard update received via websocket.');
      loadDashboard();
    });
  }
});
