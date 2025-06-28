# --- START OF FILE routes.py ---

import os
import pytz
from datetime import datetime

from flask import jsonify, render_template, send_from_directory, request

import config
import services
from database import db, HourlyWeather, HourlySnapshot

def init_routes(app):
    @app.route("/")
    def dashboard():
        return render_template("index.html")

    @app.route("/calendar")
    def calendar_view():
        return render_template("calendar.html")

    @app.route("/edit-hubs")
    def edit_hubs():
        return render_template("edit_hubs.html")

    @app.route("/api-docs")
    def api_docs():
        return render_template("api_docs.html")

    @app.route("/api/hubs")
    def hubs_api():
        return jsonify(config.HUBS)

    @app.route("/api/hubs/inactive")
    def inactive_hubs_api():
        return jsonify(config.INACTIVE_HUBS)

    @app.route("/api/weather/<iata>")
    def weather_api(iata):
        iata = iata.upper()
        now = datetime.now()
        req_date = request.args.get('date')
        all_hubs = config.HUBS + config.INACTIVE_HUBS
        hub = next((h for h in all_hubs if h["iata"] == iata), None)
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
        if is_today: # Corrected line: removed trailing 'and'
            now_dt = datetime.now(tz)
            seen = set()
            # Ensure data is not None and has "hourly" key before trying to iterate
            if data and "hourly" in data:
                for period in data.get("hourly", []):
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
            data_out = data or {} # if 'data' is None (e.g., fetch failed), this makes data_out = {}
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
        stops = config.GROUND_STOPS_CACHE.get("json")
        return jsonify(stops if stops is not None else {})

    @app.route("/api/grounddelays")
    def grounddelays_api():
        delays = config.GROUND_DELAYS_CACHE.get("json")
        return jsonify(delays if delays is not None else {})


    @app.route('/static/<path:filename>')
    def custom_static(filename):
        return send_from_directory('static', filename)

    @app.route('/db_status')
    def db_status():
        db_path = os.path.join(config.DATA_DIR, "weatherlog.db")
        size = 0
        unit = "B"
        days = 0
        try:
            if os.path.exists(db_path):
                size_bytes = os.path.getsize(db_path)
                if size_bytes > 1024 * 1024 * 1024:
                    size = round(size_bytes / (1024 * 1024 * 1024), 2)
                    unit = "GB"
                elif size_bytes > 1024 * 1024:
                    size = round(size_bytes / (1024 * 1024), 2)
                    unit = "MB"
                elif size_bytes > 1024:
                    size = round(size_bytes / 1024, 2)
                    unit = "KB"
                else:
                    size = size_bytes
                    unit = "B"
        except Exception as e:
            print(f"Could not get DB size: {e}")
        
        try:
            days = db.session.query(HourlyWeather.date).distinct().count()
        except Exception as e:
            print(f"Could not get DB days count: {e}")

        return jsonify({"size": size, "unit": unit, "days": days})

    @app.route("/api/archive-dates")
    def archive_dates_api():
        dates = db.session.query(HourlySnapshot.date).distinct().order_by(HourlySnapshot.date.desc()).all()
        return jsonify([d[0] for d in dates])

    @app.route("/api/hourly-snapshots/<iata>/<date>")
    def api_hourly_snapshots(iata, date):
        rows = HourlySnapshot.query.filter_by(iata=iata.upper(), date=date).order_by(HourlySnapshot.hour).all()
        return jsonify([r.as_dict() for r in rows])
