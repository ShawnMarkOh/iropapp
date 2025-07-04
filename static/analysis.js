function analyzeDayHours(hourlyPeriods, dateYMD, tz, highlightHour, baseLabel, ymdStr, runways, faaEventsForDay, groundStopHours = null, groundDelayData = null, snapshots = null) {
  let hourData = {};
  for (const period of hourlyPeriods) {
    const d = new Date(period.startTime);
    // Use a locale that gives YYYY-MM-DD format
    const ymd = new Intl.DateTimeFormat('fr-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
    if (ymd !== dateYMD) continue;
    
    // Get hour in the specified timezone, ensuring it's 0-23
    const hour = parseInt(new Intl.DateTimeFormat('en-US', { hour: 'numeric', hour12: false, timeZone: tz }).format(d), 10) % 24;
    hourData[hour] = { ...period };
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
  let groundStopIndexed = {};
  let groundDelayIndexed = {};
  if (snapshots) {
    snapshots.forEach(s => {
        if (s.ground_stop) groundStopIndexed[s.hour] = s.ground_stop;
        if (s.ground_delay) groundDelayIndexed[s.hour] = s.ground_delay;
    });
  }
  let hourBlocks = [];
  let rawRisks = [];
  let riskObjects = []; // Store full risk objects for later analysis
  for (let h = 0; h < 24; h++) {
    let period = hourData[h];
    let riskObj, txt, shortF="", detailedF="", windRisk=null, windTxt="", spdKts=0, spdMPH=0, dir="", temp="";
    let runwayStatus = [];
    let faaEvent = faaEventsIndexed[h] || [];
    let groundStopForHour = snapshots ? (groundStopIndexed[h] || null) : null;
    let groundDelayForHour = snapshots ? (groundDelayIndexed[h] || null) : null;

    const isPast = (highlightHour !== null && h < highlightHour);

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
      const gustKts = period.windGust ? windToKts(period.windGust) : 0;
      runwayStatus = analyzeRunwaySafety(runways, dir, spdKts, gustKts);
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

    let isGroundStopHour = false;
    if (snapshots) {
        isGroundStopHour = !!groundStopForHour;
    } else if (groundStopHours) {
        // For live view, only apply ground stop to current and future hours
        if (!isPast && h >= groundStopHours.start && h <= groundStopHours.end) {
            isGroundStopHour = true;
        }
    }

    let hasGroundDelay = false;
    if (snapshots) {
        hasGroundDelay = !!groundDelayForHour;
    } else if (groundDelayData && !isPast) {
        // For live view, only apply ground delay to current and future hours
        hasGroundDelay = true;
    }

    // If there's a ground stop, delay program, or FAA event, upgrade risk to high
    if ((isGroundStopHour || hasGroundDelay || faaEvent.length > 0) && riskObj.risk !== 'nodata') {
        riskObj = { risk: "high", key: "FAA Event", hourClass: "hour-severe" };
    }

    rawRisks.push(riskObj.risk);
    riskObjects.push(riskObj); // Populate the array of risk objects

    hourBlocks.push({
      hour: h,
      txt: txt,
      risk: riskObj.risk,
      hourClass: riskObj.hourClass + (highlightHour === h ? " hour-current" : ""),
      isCurrent: (highlightHour === h),
      isPast: isPast,
      baseLabel: baseLabel || "",
      ymd: ymdStr,
      shortF: shortF,
      detailedF: detailedF,
      riskClass: riskObj.risk,
      windRisk, windTxt, windDir: dir, windKts: spdKts, windMPH: spdMPH,
      runways: runwayStatus,
      isBrief: false,
      faaEvents: faaEvent,
      temp: temp,
      isGroundStop: isGroundStopHour,
      groundStop: groundStopForHour,
      groundDelay: hasGroundDelay ? (snapshots ? groundDelayForHour : groundDelayData) : null
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
      // This is a potential brief event. Check neighbors for thunderstorms.
      let isTrulyBrief = true;
      
      // Check previous hour for any thunderstorm risk
      if (h > 0 && riskObjects[h-1].key === "Thunder") {
        isTrulyBrief = false;
      }
      
      // Check next hour for any thunderstorm risk
      if (h < 23 && riskObjects[h+1].key === "Thunder") {
        isTrulyBrief = false;
      }

      if (isTrulyBrief) {
        hourBlocks[h].hourClass += " hour-brief";
        hourBlocks[h].isBrief = true;
      }
    }
  }
  return {hourBlocks,percentHigh: total ? Math.round((countHigh/total)*100) : 0,percentPartial: total ? Math.round((countPartial/total)*100) : 0,total};
}
