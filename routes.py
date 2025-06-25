# --- START OF FILE routes.py ---

import os
import pytz
import requests
from datetime import datetime
from xml.etree import ElementTree

from flask import jsonify, render_template, send_from_directory, request

import config
import services
from database import db, HourlyWeather, HourlySnapshot

def init_routes(app):
    @app.route("/")
    def dashboard():
        return render_template("index.html")

    @app.route("/api/hubs")
    def hubs_api():
        return jsonify(config.HUBS)

    @app.route("/api/weather/<iata>")
    def weather_api(iata):
        iata = iata.upper()
        now = datetime.now()
        req_date = request.args.get('date')
        hub = next((h for h in config.HUBS if h["iata"] == iata), None)
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

        data = services.fetch_and_log_weather(iata) if is_today else None

        result_hourly = []
        if is_today and data:
            now_dt = datetime.now(tz)
            seen = set()
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

        merged_log = services.load_daily_log()
        data_out["sirs"] = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
        data_out["terminal_constraints"] = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])
        faa_events = services.get_events_for_hub_day(iata, local_now, hub["tz"])
        data_out["faa_events"] = faa_events

        return jsonify(data_out)
    
    @app.route("/api/weather-archive/<iata>")
    def weather_archive_api(iata):
        dates = db.session.query(HourlyWeather.date).filter_by(iata=iata.upper()).distinct().order_by(HourlyWeather.date.desc()).all()
        return jsonify([d[0] for d in dates])

    @app.route("/api/weather-history/<iata>/<date>")
    def weather_history_api(iata, date):
        hours = HourlyWeather.query.filter_by(iata=iata.upper(), date=date).order_by(HourlyWeather.start_time).all()
        result = [h.as_dict() for h in hours]
        return jsonify(result)

    @app.route("/api/groundstops")
    def groundstops_api():
        url = "https://nasstatus.faa.gov/api/airport-status-information"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            if resp.text.strip().startswith("<?xml"):
                xml = ElementTree.fromstring(resp.content)
                output = {}
                for airport in xml.findall(".//airport"):
                    iata = airport.findtext("id")
                    for gs in airport.findall("ground_stop"):
                        if gs.findtext("end_time") != "":
                            reason = gs.findtext("reason") or "Ground stop in effect"
                            output[iata] = reason
                return jsonify(output)
            elif resp.headers.get("Content-Type", "").startswith("application/json"):
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
        db_path = os.path.join(config.DATA_DIR, "weatherlog.db")
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

    @app.route("/api/hourly-snapshots/<iata>/<date>")
    def api_hourly_snapshots(iata, date):
        rows = HourlySnapshot.query.filter_by(iata=iata.upper(), date=date).order_by(HourlySnapshot.hour).all()
        return jsonify([r.as_dict() for r in rows])
# --- END OF FILE routes.py ---