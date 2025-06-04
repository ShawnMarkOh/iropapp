import os
import re
import json
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import pytz
import threading

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
            {"label": "15/33",   "heading": 150, "len": 5204},
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

FAA_EVENTS_CACHE = {}
FAA_EVENTS_CACHE_TIME = {}
FAA_OPS_PLAN_URL_CACHE = {"json": None, "time": None}

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

def get_latest_ops_plan_json():
    """Fetch the current FAA Operations Plan from the official API."""
    now = datetime.utcnow()
    cache = FAA_OPS_PLAN_URL_CACHE
    if cache.get("json") and cache.get("time") and (now - cache["time"]).total_seconds() < 600:
        print("USING CACHED FAA OPS PLAN JSON.")
        return cache["json"]
    try:
        api_url = "https://nasstatus.faa.gov/api/operations-plan"
        resp = requests.get(api_url, timeout=10)
        if resp.ok:
            data = resp.json()
            FAA_OPS_PLAN_URL_CACHE.update({"json": data, "time": now})
            print("Fetched FAA OPS PLAN JSON.")
            print("OPS PLAN LINK:", data.get("link"))
            return data
    except Exception as e:
        print("OPS plan API error:", e)
    FAA_OPS_PLAN_URL_CACHE.update({"json": None, "time": now})
    return None

def parse_faa_ops_plan_json(data):
    """Convert terminal planned FAA events to a standard format for the dashboard."""
    if not data or "terminalPlanned" not in data:
        print("No terminal planned data in FAA OPS PLAN JSON.")
        return []
    events = []
    for item in data["terminalPlanned"]:
        time_str = item.get("time", "")
        event_str = item.get("event", "")
        iatas = re.findall(r'\b([A-Z]{3})\b', event_str)
        for iata in iatas:
            m = re.match(r"(AFTER|UNTIL) (\d{4})", time_str)
            if not m:
                continue
            when_type, zulu_time = m.group(1), m.group(2)
            events.append({
                "iata": iata,
                "when_type": when_type,
                "zulu_time": zulu_time,
                "desc": event_str,
                "when": time_str,
            })
    print(f"\n--- FAA EVENTS FROM JSON ---")
    for e in events:
        print(e)
    print("--- END FAA EVENTS ---\n")
    return events

def get_faa_events_by_day(dt):
    data = get_latest_ops_plan_json()
    if not data:
        print("No FAA OPS PLAN JSON data to parse!")
        return []
    return parse_faa_ops_plan_json(data)

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
    for ae in after_events:
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
                "local_time_iso": "",
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

    merged_log = load_daily_log()
    result_hourly = []
    if merged_log.get("date") == local_today_str and iata in merged_log.get("hubs", {}):
        log_entry = merged_log["hubs"][iata]
        log_hours_by_start = {h["startTime"]: h for h in log_entry.get("hourly", [])}
        for period in data["hourly"]:
            dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(tz)
            is_past = dt <= local_now
            key = period["startTime"]
            if is_past and key in log_hours_by_start:
                result_hourly.append(log_hours_by_start[key])
            else:
                result_hourly.append(period)
        data["hourly"] = result_hourly

    data["sirs"] = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
    data["terminal_constraints"] = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])
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

def periodic_ops_plan_refresh():
    while True:
        try:
            get_latest_ops_plan_json()
        except Exception:
            pass
        import time
        time.sleep(600)

threading.Thread(target=periodic_ops_plan_refresh, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
