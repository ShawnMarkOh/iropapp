import os
import re
import json
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import pytz
import threading
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
CORS(app)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "daily.log.json")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(DATA_DIR, "weatherlog.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class HourlyWeather(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    iata = db.Column(db.String(4), index=True, nullable=False)
    start_time = db.Column(db.String(40), index=True, nullable=False)
    data_json = db.Column(db.Text, nullable=False)
    date = db.Column(db.String(10), index=True, nullable=False)

    def as_dict(self):
        return {
            "iata": self.iata,
            "startTime": self.start_time,
            **json.loads(self.data_json)
        }

# --- NEW: HourlySnapshot model for full dashboard snapshots ---
class HourlySnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    iata = db.Column(db.String(4), index=True, nullable=False)
    date = db.Column(db.String(10), index=True, nullable=False)
    hour = db.Column(db.Integer, index=True, nullable=False)
    snapshot_json = db.Column(db.Text, nullable=False)
    def as_dict(self):
        return {
            "iata": self.iata,
            "date": self.date,
            "hour": self.hour,
            **json.loads(self.snapshot_json)
        }

with app.app_context():
    db.create_all()

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
    now = datetime.utcnow()
    cache = FAA_OPS_PLAN_URL_CACHE
    if cache.get("json") and cache.get("time") and (now - cache["time"]).total_seconds() < 600:
        return cache["json"]
    try:
        api_url = "https://nasstatus.faa.gov/api/operations-plan"
        resp = requests.get(api_url, timeout=10)
        if resp.ok:
            data = resp.json()
            FAA_OPS_PLAN_URL_CACHE.update({"json": data, "time": now})
            return data
    except Exception:
        pass
    FAA_OPS_PLAN_URL_CACHE.update({"json": None, "time": now})
    return None

def parse_faa_ops_plan_json(data, base_date=None):
    if not data or "terminalPlanned" not in data:
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
            dt_utc = datetime.utcnow()
            event_hour = int(zulu_time[:2])
            event_min = int(zulu_time[2:])
            ref_date = base_date or dt_utc.date()
            event_dt_utc = datetime(dt_utc.year, dt_utc.month, dt_utc.day, event_hour, event_min, tzinfo=pytz.utc)
            if when_type == "AFTER" and dt_utc.hour >= event_hour:
                event_dt_utc += timedelta(days=1)
            events.append({
                "iata": iata,
                "when_type": when_type,
                "zulu_time": zulu_time,
                "desc": event_str,
                "when": time_str,
                "event_dt_utc": event_dt_utc.isoformat()
            })
    return events

def get_faa_events_by_day(dt):
    data = get_latest_ops_plan_json()
    if not data:
        return []
    return parse_faa_ops_plan_json(data, base_date=dt)

def get_events_for_hub_day(hub_iata, local_dt, tz_str):
    utc_dt = local_dt.astimezone(pytz.utc)
    events = get_faa_events_by_day(utc_dt.date())
    result = []
    after_events = []
    until_events = []
    for e in events:
        if e["iata"] != hub_iata:
            continue
        z_hour = int(e["zulu_time"][:2])
        z_min = int(e["zulu_time"][2:])
        dt_utc = datetime(utc_dt.year, utc_dt.month, utc_dt.day, z_hour, z_min, tzinfo=pytz.utc)
        dt_local = dt_utc.astimezone(pytz.timezone(tz_str))
        if e["when_type"] == "AFTER":
            if local_dt.hour >= dt_local.hour:
                dt_local = dt_local + timedelta(days=1)
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
        elif e["when_type"] == "UNTIL":
            until_events.append({
                "to_hour": dt_local.hour,
                "to_minute": dt_local.minute,
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
        for hr in range(ae["from_hour"] + 1, 24):
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
    for ue in until_events:
        for hr in range(0, ue["to_hour"] + 1):
            result.append({
                "local_hour": hr,
                "local_minute": 0,
                "local_time_str": f"{hr:02d}:00",
                "z_hour": None,
                "z_minute": None,
                "desc": ue["desc"],
                "zulu_time": ue["zulu_time"],
                "when": ue["when"],
                "when_type": ue["when_type"],
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

    for period in hourly_periods:
        dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(pytz.timezone(grid["timezone"]))
        ymd = dt.strftime("%Y-%m-%d")
        key = period["startTime"]
        exists = HourlyWeather.query.filter_by(iata=iata, start_time=key).first()
        if not exists and ymd == today_str:
            db.session.add(HourlyWeather(
                iata=iata,
                start_time=key,
                data_json=json.dumps(period),
                date=ymd
            ))
    db.session.commit()

    return {
        "hourly": hourly_periods,
        "daily": daily_periods,
        "timezone": grid["timezone"]
    }

@app.route("/api/weather-archive/<iata>")
def weather_archive_api(iata):
    dates = db.session.query(HourlyWeather.date).filter_by(iata=iata.upper()).distinct().order_by(HourlyWeather.date.desc()).all()
    return jsonify([d[0] for d in dates])

@app.route("/api/weather-history/<iata>/<date>")
def weather_history_api(iata, date):
    hours = HourlyWeather.query.filter_by(iata=iata.upper(), date=date).order_by(HourlyWeather.start_time).all()
    result = [h.as_dict() for h in hours]
    return jsonify(result)

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
    req_date = request.args.get('date')
    hub = next((h for h in HUBS if h["iata"] == iata), None)
    if not hub:
        return jsonify({"error": "Unknown IATA code"}), 404
    tz = pytz.timezone(hub["tz"])

    if req_date:
        local_now = datetime.strptime(req_date, "%Y-%m-%d").replace(tzinfo=tz)
        local_today_str = req_date
    else:
        local_now = now.astimezone(tz)
        local_today_str = local_now.strftime("%Y-%m-%d")

    is_today = (local_today_str == datetime.now(tz).strftime("%Y-%m-%d"))

    db_hours = HourlyWeather.query.filter_by(iata=iata, date=local_today_str).order_by(HourlyWeather.start_time).all()
    logged_by_time = {h.start_time: h.as_dict() for h in db_hours}

    data = fetch_and_log_weather(iata) if is_today else None

    result_hourly = []
    if is_today:
        now_dt = datetime.now(tz)
        seen = set()
        if data:
            for period in data["hourly"]:
                dt = datetime.fromisoformat(period["startTime"].replace("Z", "+00:00")).astimezone(tz)
                key = period["startTime"]
                if dt <= now_dt and key in logged_by_time:
                    result_hourly.append(logged_by_time[key])
                    seen.add(key)
                else:
                    result_hourly.append(period)
                    seen.add(key)
        for key, val in logged_by_time.items():
            if key not in seen:
                result_hourly.append(val)
        result_hourly.sort(key=lambda x: x["startTime"])
        data_out = data or {}
        data_out["hourly"] = result_hourly
        data_out["timezone"] = tz.zone
    else:
        result_hourly = list(logged_by_time.values())
        result_hourly.sort(key=lambda x: x["startTime"])
        data_out = {
            "hourly": result_hourly,
            "daily": [],
            "timezone": tz.zone
        }

    merged_log = load_daily_log()
    data_out["sirs"] = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
    data_out["terminal_constraints"] = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])
    faa_events = get_events_for_hub_day(iata, local_now, hub["tz"])
    data_out["faa_events"] = faa_events

    return jsonify(data_out)

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
        elif resp.ok and resp.headers.get("Content-Type", "").startswith("application/json"):
            data = resp.json()
            output = {}
            for ap in data.get("AirportStatusList", []):
                iata = ap.get("IATA")
                for gs in ap.get("GroundStops", []):
                    if gs.get("EndTime"):
                        reason = gs.get("Reason", "Ground stop in effect")
                        output[iata] = reason
            return jsonify(output)
    except Exception:
        pass
    return jsonify({})

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory('static', filename)

@app.route('/db_status')
def db_status():
    db_path = os.path.join(DATA_DIR, "weatherlog.db")
    try:
        size_bytes = os.path.getsize(db_path)
        if size_bytes < 1024 * 1024 * 1024:
            size = round(size_bytes / (1024 * 1024), 2)
            unit = "MB"
        else:
            size = round(size_bytes / (1024 * 1024 * 1024), 2)
            unit = "GB"
    except Exception:
        size = 0
        unit = "MB"
    days = db.session.query(HourlyWeather.date).distinct().count()
    return f"The DB is {size} {unit} in size and contains {days} days worth of data"

def periodic_ops_plan_refresh():
    while True:
        try:
            get_latest_ops_plan_json()
        except Exception:
            pass
        import time
        time.sleep(600)

# --- NEW: Background thread to archive hourly dashboard snapshots for all hubs ---
def hourly_snapshot_job():
    import time
    with app.app_context():
        while True:
            now = datetime.now()
            cur_date = now.strftime('%Y-%m-%d')
            cur_hour = now.hour
            for hub in HUBS:
                iata = hub["iata"]
                weather_data = fetch_and_log_weather(iata)
                merged_log = load_daily_log()
                sirs = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
                terminal_constraints = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])
                faa_events = get_events_for_hub_day(iata, now, hub["tz"])
                snapshot = {
                    "weather": weather_data,
                    "sirs": sirs,
                    "terminal_constraints": terminal_constraints,
                    "faa_events": faa_events
                }
                exists = HourlySnapshot.query.filter_by(iata=iata, date=cur_date, hour=cur_hour).first()
                if not exists:
                    db.session.add(HourlySnapshot(
                        iata=iata,
                        date=cur_date,
                        hour=cur_hour,
                        snapshot_json=json.dumps(snapshot)
                    ))
                else:
                    exists.snapshot_json = json.dumps(snapshot)
                db.session.commit()
            time_to_next_hour = 3600 - (datetime.now().minute * 60 + datetime.now().second)
            time.sleep(time_to_next_hour)


# --- NEW: API endpoint to retrieve archived hourly dashboard snapshots ---
@app.route("/api/hourly-snapshots/<iata>/<date>")
def api_hourly_snapshots(iata, date):
    rows = HourlySnapshot.query.filter_by(iata=iata.upper(), date=date).order_by(HourlySnapshot.hour).all()
    return jsonify([r.as_dict() for r in rows])

threading.Thread(target=periodic_ops_plan_refresh, daemon=True).start()
threading.Thread(target=hourly_snapshot_job, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
