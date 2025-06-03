import os
import json
from datetime import datetime, timedelta
from flask import Flask, jsonify, send_from_directory, render_template
from flask_cors import CORS
import requests
import pytz

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "daily_log.json")
os.makedirs(DATA_DIR, exist_ok=True)

HUBS = [
    {
        "name": "Charlotte Douglas International Airport",
        "iata": "CLT",
        "city": "Charlotte, NC",
        "tz": "America/New_York",
        "lat": 35.214, "lon": -80.9431,
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
        "lat": 39.8744, "lon": -75.2424,
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
        "lat": 38.8521, "lon": -77.0377,
        "runways": [
            {"label": "1/19",    "heading": 10,  "len": 7169},
        ]
    },
    {
        "name": "Dayton International Airport",
        "iata": "DAY",
        "city": "Dayton, OH",
        "tz": "America/New_York",
        "lat": 39.9024, "lon": -84.2194,
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
        "lat": 32.8998, "lon": -97.0403,
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

def get_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_log(log):
    with open(LOG_FILE, "w") as f:
        json.dump(log, f)

def update_hour_data(hub_iata, date_ymd, hour, hour_data):
    log = get_log()
    if hub_iata not in log:
        log[hub_iata] = {}
    if date_ymd not in log[hub_iata]:
        log[hub_iata][date_ymd] = {}
    log[hub_iata][date_ymd][str(hour)] = hour_data
    save_log(log)

def get_day_data(hub_iata, date_ymd):
    log = get_log()
    return log.get(hub_iata, {}).get(date_ymd, {})

def parse_iso_to_local(dtstr, tz):
    try:
        dt_utc = datetime.fromisoformat(dtstr.replace("Z", "+00:00"))
        return dt_utc.astimezone(pytz.timezone(tz))
    except Exception:
        return None

def get_ymd(dt, tz):
    return dt.astimezone(pytz.timezone(tz)).strftime("%Y-%m-%d")

@app.route('/')
def dashboard():
    return render_template("index.html")

@app.route('/api/hubs')
def api_hubs():
    return jsonify(HUBS)

@app.route('/api/weather/<iata>')
def api_weather(iata):
    hub = next((h for h in HUBS if h["iata"].upper() == iata.upper()), None)
    if not hub:
        return jsonify({"error": "No such hub"}), 404
    lat, lon = hub["lat"], hub["lon"]
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    try:
        points = requests.get(points_url, timeout=7).json()
        forecast_url = points["properties"]["forecast"]
        hourly_url = points["properties"]["forecastHourly"]
    except Exception:
        return jsonify({"error": "Error with weather.gov points API"}), 502

    try:
        forecast = requests.get(forecast_url, timeout=7).json()
        hourly = requests.get(hourly_url, timeout=7).json()
    except Exception:
        return jsonify({"error": "Error fetching forecast/hourly"}), 502

    daily = forecast["properties"]["periods"]
    hourly_periods = hourly["properties"]["periods"]

    now_local = datetime.now(pytz.timezone(hub["tz"]))
    today_ymd = get_ymd(now_local, hub["tz"])

    # Merge persisted log with live hourly data to get 24h
    log = get_log()
    saved_hours = log.get(iata, {}).get(today_ymd, {})

    hourly_full = []
    for period in hourly_periods:
        local = parse_iso_to_local(period["startTime"], hub["tz"])
        if not local: continue
        hour = local.hour
        ymd = get_ymd(local, hub["tz"])
        if ymd == today_ymd:
            update_hour_data(iata, today_ymd, hour, period)
            saved_hours[str(hour)] = period
    # Fill out all 24 hours
    for hour in range(24):
        h = str(hour)
        if h in saved_hours:
            hourly_full.append(saved_hours[h])
        else:
            # look for a live period with this hour (if not in log)
            period = next((p for p in hourly_periods if parse_iso_to_local(p["startTime"], hub["tz"]) and parse_iso_to_local(p["startTime"], hub["tz"]).hour == hour), None)
            if period:
                hourly_full.append(period)
            else:
                hourly_full.append({
                    "startTime": f"{today_ymd}T{str(hour).zfill(2)}:00:00",
                    "shortForecast": "No data",
                    "detailedForecast": "",
                    "temperature": "--",
                    "temperatureUnit": "",
                    "windSpeed": "--",
                    "windDirection": "--",
                })

    return jsonify({
        "daily": daily,
        "hourly": hourly_full,
        "runways": hub["runways"]
    })

@app.route('/api/groundstops')
def api_groundstops():
    url = "https://nasstatus.faa.gov/api/airport-status-information"
    gs = {}
    try:
        r = requests.get(url, timeout=7)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        for ap in root.findall('.//airport'):
            iata = ap.findtext('iataId')
            gsmsg = ap.findtext('groundStop')
            if iata and gsmsg and "NO" not in gsmsg.upper():
                gs[iata.upper()] = gsmsg
    except Exception:
        pass
    return jsonify(gs)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
