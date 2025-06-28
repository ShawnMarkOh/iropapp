// Placeholders for globals and functions not defined in the original script
window.FAA_EVENT_DEFINITIONS = window.FAA_EVENT_DEFINITIONS || {};
window.FAA_LITERAL_TRANSLATIONS = window.FAA_LITERAL_TRANSLATIONS || {};

function translateFAAString(s) {
    if (!s) return "N/A";
    // In a real scenario, this would look up definitions. For now, it just returns the string.
    return s;
}

const windDirs = {N:0, NNE:22.5, NE:45, ENE:67.5, E:90, ESE:112.5, SE:135, SSE:157.5, S:180, SSW:202.5, SW:225, WSW:247.5, W:270, WNW:292.5, NW:315, NNW:337.5};
function windDirToDeg(dir) {dir = (dir||"").toUpperCase();if (windDirs[dir] !== undefined) return windDirs[dir];if (/^\d+$/.test(dir)) return Number(dir);return null;}
function windToKts(val) {if (!val) return 0;let v = parseFloat(val);if (/mph/.test(val)) v *= 0.868976;return v;}
function windToMPH(val) {if (!val) return 0;let v = parseFloat(val);if (/mph/.test(val)) return v;return v * 1.15078;}
function crosswindComponent(runwayHeading, windDir, windKts) {let windDeg = windDirToDeg(windDir);if (windDeg === null) return 0;let angle = Math.abs(runwayHeading - windDeg);if (angle > 180) angle = 360 - angle;let rad = angle * Math.PI / 180;let cross = Math.abs(windKts * Math.sin(rad));return cross;}
function getHourWindRisk(spd, cross) {if (spd > 50) return {risk:"high", txt:"Wind > 50 kts", class:"hour-wind"};if (spd > 35) return {risk:"wind-high", txt:"High wind ("+spd+" kts)", class:"hour-wind-high"};if (spd > 0 && spd > 27) return {risk:"partial", txt:"Wind ("+spd+" kts)", class:"hour-wind"};if (cross > 27) return {risk:"high", txt:"Crosswind "+cross+" kts", class:"hour-wind"};if (cross > 20) return {risk:"wind-high", txt:"High crosswind ("+cross+" kts)", class:"hour-wind-high"};if (cross > 15) return {risk:"wind-partial", txt:"Moderate crosswind ("+cross+" kts)", class:"hour-wind-partial"};return null;}
function analyzeRunwaySafety(runways, windDir, windKts, gustKts) {
    let runwayResults = [];
    for (let rw of runways) {
        if (rw.len < 5040) continue;
        let cross = crosswindComponent(rw.heading, windDir, windKts);
        let status = "";
        let className = "";
        let safe = false;

        if (rw.len >= 5360) {
            safe = (windKts <= 50) && (cross <= 27);
            status = safe ? "SAFE" : (windKts > 50 ? "UNSAFE WIND" : "UNSAFE CROSSWIND");
            className = safe ? "runway-safe" : "runway-unsafe";
        } else if (rw.len >= 5040) {
            safe = (windKts <= 50) && (cross <= 27);
            status = safe ? "SAFE (CRJ700)" : (windKts > 50 ? "UNSAFE WIND" : "UNSAFE CROSSWIND");
            className = safe ? "runway-crj700only" : "runway-unsafe";
        }

        if (safe && gustKts) {
            if (gustKts > 50) {
                safe = false;
                status = `UNSAFE (GUSTS ${Math.round(gustKts)} KTS)`;
                className = "runway-unsafe";
            } else {
                let crossGust = crosswindComponent(rw.heading, windDir, gustKts);
                if (crossGust > 27) {
                    safe = false;
                    status = `UNSAFE (GUSTS ${Math.round(crossGust)} KTS CROSS)`;
                    className = "runway-unsafe";
                }
            }
        }

        if (rw.len >= 5040) {
            runwayResults.push({
                label: rw.label,
                cross: Math.round(cross),
                safe: safe,
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
