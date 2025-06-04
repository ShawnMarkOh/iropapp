import os
import re
import json
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
import requests
from datetime import datetime, timedelta, date
import pytz

app = Flask(__name__)
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LOG_FILE = os.path.join(DATA_DIR, "daily.log.json")
os.makedirs(DATA_DIR, exist_ok=True)

HUBS = [
    {
        "name": "Charlotte Douglas International Airport",
        "iata": "CLT",
        "city": "Charlotte, NC",
        "tz": "America/New_York",
        "runways": [
            {"label": "18L/36R", "heading": 180, "len": 10000},
            {"label": "18C/36C", "heading": 180, "len": 10000},
            {"label": "18R/36L", "heading": 180, "len": 9000},
            {"label": "5/23",    "heading": 50,  "len": 7502},
        ]
    },
    {
        "name": "Philadelphia International Airport",
        "iata": "PHL",
        "city": "Philadelphia, PA",
        "tz": "America/New_York",
        "runways": [
            {"label": "9L/27R",  "heading": 90,  "len": 10000},
            {"label": "9R/27L",  "heading": 90,  "len": 9500},
            {"label": "17/35",   "heading": 170, "len": 6500},
        ]
    },
    {
        "name": "Ronald Reagan Washington National Airport",
        "iata": "DCA",
        "city": "Washington, DC",
        "tz": "America/New_York",
        "runways": [
            {"label": "1/19",    "heading": 10,  "len": 7169},
            {"label": "15/33",   "heading": 150, "len": 5204},   # Included, CRJ700 only
        ]
    },
    {
        "name": "Dayton International Airport",
        "iata": "DAY",
        "city": "Dayton, OH",
        "tz": "America/New_York",
        "runways": [
            {"label": "6L/24R",  "heading": 60,  "len": 10500},
            {"label": "18/36",   "heading": 180, "len": 7500},
            {"label": "6R/24L",  "heading": 60,  "len": 7100},
        ]
    },
    {
        "name": "Dallas/Fort Worth International Airport",
        "iata": "DFW",
        "city": "Dallas-Fort Worth, TX",
        "tz": "America/Chicago",
        "runways": [
            {"label": "13L/31R", "heading": 130, "len": 9000},
            {"label": "13R/31L", "heading": 130, "len": 9200},
            {"label": "17L/35R", "heading": 170, "len": 8500},
            {"label": "17C/35C", "heading": 170, "len": 13400},
            {"label": "17R/35L", "heading": 170, "len": 13400},
            {"label": "18L/36R", "heading": 180, "len": 13300},
            {"label": "18R/36L", "heading": 180, "len": 13400},
        ]
    }
]


FAA_ADVZY_URL = "https://www.fly.faa.gov/adv/adv_otherdis.jsp"

def load_daily_log():
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            try:
                data = json.load(f)
                if data.get("date") == today_str:
                    return data
            except Exception:
                pass
    return {"date": today_str, "hubs": {}}

def save_daily_log(log_data):
    with open(LOG_FILE, "w") as f:
        json.dump(log_data, f)

def get_nws_grid(iata):
    for hub in HUBS:
        if hub["iata"] == iata:
            lat, lon = get_latlon_for_hub(hub["iata"])
            if lat and lon:
                resp = requests.get(f"https://api.weather.gov/points/{lat},{lon}", timeout=15)
                resp.raise_for_status()
                grid = resp.json()
                props = grid["properties"]
                return {
                    "forecast": props["forecast"],
                    "forecastHourly": props["forecastHourly"],
                    "timezone": props["timeZone"]
                }
    return None

def get_latlon_for_hub(iata):
    lookup = {
        "CLT": (35.2140, -80.9431),
        "PHL": (39.8744, -75.2424),
        "DCA": (38.8521, -77.0377),
        "DAY": (39.9024, -84.2194),
        "DFW": (32.8998, -97.0403)
    }
    return lookup.get(iata, (None, None))

def parse_faa_atcscc_advzy(date_dt):
    # Only extract events under TERMINAL ACTIVE and TERMINAL PLANNED for "UNTIL ####" and "AFTER ####"
    adv_date = date_dt.strftime("%m%d%Y")
    url = f"{FAA_ADVZY_URL}?advn=33&adv_date={adv_date}&facId=ATCSCC&title=ATCSCC%20ADVZY%20033%20DCC%20OPERATIONS%20PLAN&titleDate={date_dt.strftime('%m/%d/%Y')}"
    try:
        resp = requests.get(url, timeout=30)
        if not resp.ok:
            return []
        text = resp.text

        # Only consider text between 'TERMINAL ACTIVE:' and 'TERMINAL PLANNED:' for ACTIVE,
        # and 'TERMINAL PLANNED:' to next section for PLANNED
        sections = {}
        # Normalize all line endings
        text = text.replace('\r\n', '\n')
        # Find relevant section start/ends
        m_active = re.search(r'TERMINAL ACTIVE:(.*?)(TERMINAL PLANNED:|$)', text, re.DOTALL)
        m_planned = re.search(r'TERMINAL PLANNED:(.*?)(\n\n|\r\n\r\n|$)', text, re.DOTALL)
        sections['active'] = m_active.group(1) if m_active else ''
        sections['planned'] = m_planned.group(1) if m_planned else ''

        # Helper: extract events for each section
        def extract_events(section_text, when_type):
            # Matches: "UNTIL 1859 -DEN GROUND DELAY PROGRAM", "AFTER 1400 -MIA/FLL/PBI GROUND STOPS POSSIBLE"
            pattern = re.compile(rf'\b({when_type}) (\d{{4}})\s*-([^\n]+)', re.IGNORECASE)
            events = []
            for m in pattern.finditer(section_text):
                when = m.group(1).upper()
                ztime = m.group(2)
                desc = m.group(3).strip()
                # IATAs: find all 3-letter IATA codes in the desc, allowing for groups like MIA/FLL/PBI
                iatas = re.findall(r'\b([A-Z]{3})\b', desc)
                if not iatas:
                    continue
                events.append({
                    "when_type": when,
                    "zulu_time": ztime,
                    "desc": desc,
                    "iatas": iatas,
                })
            return events

        # Only "UNTIL" and "AFTER"
        events = []
        for when_type in ("UNTIL", "AFTER"):
            events += extract_events(sections['active'], when_type)
            events += extract_events(sections['planned'], when_type)

        # Expand events for each hub
        result = []
        for event in events:
            for iata in event["iatas"]:
                result.append({
                    "iata": iata,
                    "when_type": event["when_type"],
                    "zulu_time": event["zulu_time"],
                    "desc": event["desc"],
                    "when": f"{event['when_type']} {event['zulu_time']}",
                })
        return result

    except Exception as ex:
        return []

FAA_EVENTS_CACHE = {}
FAA_EVENTS_CACHE_TIME = {}

def get_faa_events_by_day(dt):
    key = dt.strftime("%Y-%m-%d")
    now = datetime.utcnow()
    if key in FAA_EVENTS_CACHE and (now - FAA_EVENTS_CACHE_TIME.get(key, now)).total_seconds() < 60:
        return FAA_EVENTS_CACHE[key]
    events = parse_faa_atcscc_advzy(dt)
    FAA_EVENTS_CACHE[key] = events
    FAA_EVENTS_CACHE_TIME[key] = now
    return events

def get_events_for_hub_day(hub_iata, local_dt, tz_str):
    utc_dt = local_dt.astimezone(pytz.utc)
    events = get_faa_events_by_day(utc_dt.date())
    result = []
    after_events = []
    for e in events:
        if e["iata"] != hub_iata:
            continue
        z_hour = int(e["zulu_time"][:2])
        z_min = int(e["zulu_time"][2:])
        dt_utc = datetime(utc_dt.year, utc_dt.month, utc_dt.day, z_hour, z_min, tzinfo=pytz.utc)
        dt_local = dt_utc.astimezone(pytz.timezone(tz_str))
        if e["when_type"] == "AFTER":
            # Mark for all hours AFTER this local hour (inclusive or exclusive? FAA: exclusive, so start at +1)
            after_events.append({
                "from_hour": dt_local.hour,
                "from_minute": dt_local.minute,
                "desc": e["desc"],
                "zulu_time": e["zulu_time"],
                "when": e["when"],
                "when_type": e["when_type"],
                "local_time_iso": dt_local.isoformat(),
            })
        else:
            # UNTIL event (just the target hour)
            result.append({
                "local_hour": dt_local.hour,
                "local_minute": dt_local.minute,
                "local_time_str": dt_local.strftime("%H:%M"),
                "z_hour": z_hour,
                "z_minute": z_min,
                "desc": e["desc"],
                "zulu_time": e["zulu_time"],
                "when": e["when"],
                "when_type": e["when_type"],
                "local_time_iso": dt_local.isoformat(),
            })
    # Now expand AFTER events for each hour after that time
    for ae in after_events:
        # Get local date from the event time (should match local_dt)
        for hr in range(ae["from_hour"]+1, 24):
            result.append({
                "local_hour": hr,
                "local_minute": 0,
                "local_time_str": f"{hr:02d}:00",
                "z_hour": None,
                "z_minute": None,
                "desc": ae["desc"],
                "zulu_time": ae["zulu_time"],
                "when": ae["when"],
                "when_type": ae["when_type"],
                "local_time_iso": "",  # Not needed for per-hour
            })
    return result


def fetch_and_log_weather(iata):
    grid = get_nws_grid(iata)
    if not grid:
        return None
    resp_hourly = requests.get(grid["forecastHourly"], timeout=15)
    resp_hourly.raise_for_status()
    hourly = resp_hourly.json()
    hourly_periods = hourly["properties"]["periods"]

    resp_daily = requests.get(grid["forecast"], timeout=15)
    resp_daily.raise_for_status()
    daily = resp_daily.json()
    daily_periods = daily["properties"]["periods"]

    now = datetime.now(pytz.timezone(grid["timezone"]))
    today_str = now.strftime("%Y-%m-%d")

    daily_log = load_daily_log()
    if "hubs" not in daily_log:
        daily_log["hubs"] = {}
    daily_log["date"] = today_str
    if iata not in daily_log["hubs"]:
        daily_log["hubs"][iata] = {
            "hourly": [],
            "last_updated": now.isoformat()
        }

    logged = daily_log["hubs"][iata]["hourly"]
    logged_by_time = {}
    for entry in logged:
        try:
            dt = datetime.fromisoformat(entry["startTime"].replace("Z", "+00:00")).astimezone(pytz.timezone(grid["timezone"]))
            key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
            logged_by_time[key] = entry
        except Exception:
            continue

    merged_hours = []
    for period in hourly_periods:
        dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(pytz.timezone(grid["timezone"]))
        key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
        if dt.strftime("%Y-%m-%d") == today_str:
            merged_hours.append(period)
            logged_by_time[key] = period

    merged_keys = set()
    for period in merged_hours:
        dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(pytz.timezone(grid["timezone"]))
        key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
        merged_keys.add(key)
    for key, entry in logged_by_time.items():
        dt = datetime.fromisoformat(entry["startTime"].replace("Z", "+00:00")).astimezone(pytz.timezone(grid["timezone"]))
        if key not in merged_keys and dt.strftime("%Y-%m-%d") == today_str:
            merged_hours.append(entry)
    merged_hours.sort(key=lambda x: x["startTime"])

    daily_log["hubs"][iata]["hourly"] = merged_hours
    daily_log["hubs"][iata]["last_updated"] = now.isoformat()
    save_daily_log(daily_log)

    return {
        "hourly": hourly_periods,
        "daily": daily_periods,
        "timezone": grid["timezone"]
    }

@app.route("/")
def dashboard():
    return render_template("index.html")

@app.route("/api/hubs")
def hubs_api():
    return jsonify(HUBS)
def parse_faa_sirs(text, hubs_iata, now_dt):
    """
    Parse RUNWAY/EQUIPMENT/POSSIBLE SYSTEM IMPACT REPORTS (SIRs):
    For each hub, list any closed runways with their closure windows.
    """
    sirs_section = re.search(r'RUNWAY/EQUIPMENT/POSSIBLE SYSTEM IMPACT REPORTS \(SIRs\):(.*?)(\n\n|\r\n\r\n|$)', text, re.DOTALL)
    if not sirs_section:
        return []
    sirs_text = sirs_section.group(1)
    # Ex: DEN - RWY 17R/35L CLOSED UNTIL 06/24/25 2300Z
    #     PHL - RWY 09R/27L NIGHTLY CLOSURES UNTIL 09/17/25 1000Z
    sirs = []
    for line in sirs_text.splitlines():
        m = re.match(r'\s*([A-Z]{3})\s*-\s*(RWY\s*\d+[LRC]?/\d+[LRC]?)\s*(.*?)(CLOSED|CLOSURE).*UNTIL\s+(\d{2}/\d{2}/\d{2}(?:\s+\d{4}Z)?)', line, re.IGNORECASE)
        if m:
            iata = m.group(1)
            runway = m.group(2).replace("RWY ", "").strip()
            status = m.group(4).upper()
            until = m.group(5)
            # Parse until datetime
            until_dt = None
            until_parts = re.match(r'(\d{2})/(\d{2})/(\d{2})(?:\s+(\d{4})Z)?', until)
            if until_parts:
                mm, dd, yy, zulu = until_parts.groups()
                year = int(yy)
                if year < 100: year += 2000
                month = int(mm)
                day = int(dd)
                if zulu:
                    hour = int(zulu[:2])
                    minute = int(zulu[2:])
                else:
                    hour = 23
                    minute = 59
                until_dt = datetime(year, month, day, hour, minute, tzinfo=pytz.utc)
            sirs.append({
                "iata": iata,
                "runway": runway,
                "status": status,
                "until_dt": until_dt.isoformat() if until_dt else None,
                "until": until
            })
    # For hubs, return only matching runways that are closed and still within closure window
    relevant = []
    for s in sirs:
        if s["iata"] in hubs_iata and s["status"] == "CLOSED":
            if not s["until_dt"]:
                relevant.append(s)
            else:
                # Still in effect?
                until = datetime.fromisoformat(s["until_dt"])
                if now_dt < until:
                    relevant.append(s)
    return relevant

def parse_terminal_constraints(text, hubs_iata):
    # Extract TERMINAL CONSTRAINTS: ... section
    constraints_section = re.search(r'TERMINAL CONSTRAINTS:(.*?)(\n\n|\r\n\r\n|$)', text, re.DOTALL)
    if not constraints_section:
        return []
    constraints_text = constraints_section.group(1)
    results = []
    for line in constraints_text.splitlines():
        m = re.match(r'\s*([A-Z]{3})\s*-\s*(.*)', line)
        if m:
            iata = m.group(1)
            if iata in hubs_iata:
                desc = m.group(2).strip()
                results.append({
                    "iata": iata,
                    "desc": desc
                })
    return results

# Download and process acronyms (once at startup, or cache as needed)
import requests
ACRONYM_GLOSSARY = {}

def load_acronym_glossary():
    url = "https://www.fly.faa.gov/FAQ/Acronyms/acronyms.jsp"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        glossary = {}
        # The page is an HTML table; parse it
        for row in re.findall(r'<tr>\s*<td.*?>(.*?)</td>\s*<td.*?>(.*?)</td>', resp.text, re.DOTALL):
            key, meaning = row
            key = re.sub(r'<.*?>', '', key).strip()
            meaning = re.sub(r'<.*?>', '', meaning).strip()
            glossary[key.upper()] = meaning
        return glossary
    except Exception as ex:
        return {}
ACRONYM_GLOSSARY = load_acronym_glossary()

def expand_acronyms(text):
    # For each known acronym, replace with its full meaning (simple version)
    def repl(match):
        acronym = match.group(0)
        return f"{acronym} ({ACRONYM_GLOSSARY.get(acronym, '')})" if acronym in ACRONYM_GLOSSARY else acronym
    return re.sub(r'\b[A-Z]{2,}\b', repl, text)
    
@app.route("/api/weather/<iata>")
def weather_api(iata):
    iata = iata.upper()
    now = datetime.now()
    hub = next((h for h in HUBS if h["iata"] == iata), None)
    if not hub:
        return jsonify({"error": "Unknown IATA code"}), 404
    tz = pytz.timezone(hub["tz"])
    local_now = now.astimezone(tz)
    local_today_str = local_now.strftime("%Y-%m-%d")
    daily_log = load_daily_log()

    data = fetch_and_log_weather(iata)
    if not data:
        return jsonify({"error": "Failed to fetch weather data"}), 500

    # Reload the log to get what was just saved
    merged_log = load_daily_log()
    result_hourly = []

    if merged_log.get("date") == local_today_str and iata in merged_log.get("hubs", {}):
        log_entry = merged_log["hubs"][iata]
        log_hours_by_start = {h["startTime"]: h for h in log_entry.get("hourly", [])}
        for period in data["hourly"]:
            dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(tz)
            is_past = dt <= local_now  # mark hour as 'past' if <= now
            key = period["startTime"]
            # For past hours, use log value if available
            if is_past and key in log_hours_by_start:
                result_hourly.append(log_hours_by_start[key])
            else:
                result_hourly.append(period)
        data["hourly"] = result_hourly

    # Always safe, never KeyError:
    data["sirs"] = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
    data["terminal_constraints"] = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])

    # FAA events as before
    faa_events = get_events_for_hub_day(iata, local_now, hub["tz"])
    data["faa_events"] = faa_events

    return jsonify(data)




@app.route("/api/groundstops")
def groundstops_api():
    url = "https://nasstatus.faa.gov/api/airport-status-information"
    try:
        resp = requests.get(url, timeout=15)
        if resp.ok and resp.text.strip().startswith("<?xml"):
            from xml.etree import ElementTree
            xml = ElementTree.fromstring(resp.content)
            output = {}
            for airport in xml.findall(".//airport"):
                iata = airport.findtext("id")
                for gs in airport.findall("ground_stop"):
                    if gs.findtext("end_time") != "":
                        reason = gs.findtext("reason") or "Ground stop in effect"
                        output[iata] = reason
            return jsonify(output)
    except Exception:
        pass
    return jsonify({})

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory('static', filename)

if __name__ == "__main__":
    app.run(debug=True)
