import os
import re
import json
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
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
            {"label": "17C/35C", "heading": 170, "len": 13400},
            {"label": "17L/35R", "heading": 170, "len": 8500},
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
    # date_dt is a datetime.date or datetime.datetime
    adv_date = date_dt.strftime("%m%d%Y")
    url = f"{FAA_ADVZY_URL}?advn=33&adv_date={adv_date}&facId=ATCSCC&title=ATCSCC%20ADVZY%20033%20DCC%20OPERATIONS%20PLAN&titleDate={date_dt.strftime('%m/%d/%Y')}"
    try:
        resp = requests.get(url, timeout=30)
        if not resp.ok:
            return []
        text = resp.text
        # Simple regex-based parse for each hub
        events = []

        # Compose IATA regex for all hubs, also allow city names, case-insensitive
        pattern = re.compile(r'((?:After|Until|from|at)\s+(\d{4})Z.*?)((CLT|PHL|DCA|DAY|DFW)[^\n.]*?(Ground Stop|Delay Program|SWAP|thunderstorm|severe|closure|runway|equipment|impact|recovery|VIP|possible|expected|probable|capping|tunneling|hotline|diversion|SWAP|CDR))', re.I)
        # Find time-tagged hub-specific events
        for match in pattern.finditer(text):
            when_full, hour_z, event_desc = match.group(1), match.group(2), match.group(3)
            affected_iatas = [iata for iata in ["CLT","PHL","DCA","DAY","DFW"] if iata in event_desc.upper()]
            for iata in affected_iatas:
                events.append({
                    "iata": iata,
                    "hour_z": int(hour_z[:2]),  # e.g. "1900" -> 19
                    "desc": event_desc.strip(),
                    "when": when_full.strip(),
                    "zulu_time": f"{hour_z}Z",
                })
        # Simpler parse for "VIP Movement" and "Runway Closure"
        for iata in ["CLT","PHL","DCA","DAY","DFW"]:
            # Look for any lines with the IATA code
            for m in re.finditer(rf'({iata}[^.]*?(Ground Stop|Delay Program|closure|runway|VIP|impact|possible|expected|probable|capping|tunneling|hotline|diversion|SWAP|CDR)[^.]*\.)', text, re.I):
                events.append({
                    "iata": iata,
                    "hour_z": None,
                    "desc": m.group(0).strip(),
                    "when": "",
                    "zulu_time": "",
                })
        return events
    except Exception:
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
    # Return a list of events for this hub on this day, with mapping to local hours
    utc_dt = local_dt.astimezone(pytz.utc)
    events = get_faa_events_by_day(utc_dt.date())
    result = []
    for e in events:
        if e["iata"] != hub_iata:
            continue
        # If the event is for a specific hour, map that hour (Zulu) to local
        if e["hour_z"] is not None:
            z_hour = e["hour_z"]
            local_hour = (z_hour + pytz.timezone(tz_str).utcoffset(local_dt.replace(hour=0,minute=0,second=0, microsecond=0)).total_seconds() // 3600) % 24
            result.append({
                "local_hour": int(local_hour),
                "z_hour": z_hour,
                "desc": e["desc"],
                "zulu_time": e["zulu_time"],
                "when": e["when"]
            })
        else:
            result.append({
                "local_hour": None,
                "z_hour": None,
                "desc": e["desc"],
                "zulu_time": "",
                "when": e["when"]
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

@app.route("/api/weather/<iata>")
def weather_api(iata):
    iata = iata.upper()
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    hub = next((h for h in HUBS if h["iata"] == iata), None)
    if not hub:
        return jsonify({"error": "Unknown IATA code"}), 404
    tz = pytz.timezone(hub["tz"])
    local_now = now.astimezone(tz)
    local_today_str = local_now.strftime("%Y-%m-%d")
    daily_log = load_daily_log()

    if daily_log.get("date") == local_today_str and iata in daily_log.get("hubs", {}):
        log_entry = daily_log["hubs"][iata]
        grid = get_nws_grid(iata)
        resp_daily = requests.get(grid["forecast"], timeout=15)
        resp_daily.raise_for_status()
        daily_periods = resp_daily.json()["properties"]["periods"]
        resp_hourly = requests.get(grid["forecastHourly"], timeout=15)
        resp_hourly.raise_for_status()
        hourly_periods = resp_hourly.json()["properties"]["periods"]
        result_hourly = []
        for period in hourly_periods:
            dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(tz)
            if dt.strftime("%Y-%m-%d") == local_today_str:
                found = next((h for h in log_entry["hourly"] if h["startTime"] == period["startTime"]), None)
                result_hourly.append(found if found else period)
            else:
                result_hourly.append(period)
        # Add FAA events for this hub and date
        faa_events = get_events_for_hub_day(iata, local_now, hub["tz"])
        return jsonify({
            "hourly": result_hourly,
            "daily": daily_periods,
            "timezone": grid["timezone"],
            "faa_events": faa_events
        })

    data = fetch_and_log_weather(iata)
    if data:
        merged_log = load_daily_log()
        if merged_log.get("date") == local_today_str and iata in merged_log.get("hubs", {}):
            log_entry = merged_log["hubs"][iata]
            tz = pytz.timezone(hub["tz"])
            result_hourly = []
            for period in data["hourly"]:
                dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(tz)
                if dt.strftime("%Y-%m-%d") == local_today_str:
                    found = next((h for h in log_entry["hourly"] if h["startTime"] == period["startTime"]), None)
                    result_hourly.append(found if found else period)
                else:
                    result_hourly.append(period)
            data["hourly"] = result_hourly
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
