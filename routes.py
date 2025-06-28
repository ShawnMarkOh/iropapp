# --- START OF FILE routes.py ---

import os
import pytz
import json
from datetime import datetime

from flask import jsonify, render_template, send_from_directory, request
from sqlalchemy import desc

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
        req_date = request.args.get('date')
        all_hubs = config.HUBS + config.INACTIVE_HUBS
        hub = next((h for h in all_hubs if h["iata"] == iata), None)
        if not hub:
            return jsonify({"error": "Unknown IATA code"}), 404
        tz = pytz.timezone(hub["tz"])

        local_date_str = req_date or datetime.now(tz).strftime("%Y-%m-%d")

        # Default structure for the output
        data_out = {
            "hourly": [], "daily": [], "timezone": tz.zone, "sirs": [],
            "terminal_constraints": [], "faa_events": [], "alerts": []
        }

        # Get all historically logged hours for the requested date from HourlyWeather
        db_hours = HourlyWeather.query.filter_by(iata=iata, date=local_date_str).order_by(HourlyWeather.start_time).all()
        logged_by_time = {h.start_time: h.as_dict() for h in db_hours}

        # For both today and archive views, we now primarily rely on snapshots.
        # This prevents slow, on-demand external API calls from this route.
        latest_snapshot = HourlySnapshot.query.filter_by(
            iata=iata, date=local_date_str
        ).order_by(desc(HourlySnapshot.hour)).first()

        forecast_data = None
        if latest_snapshot:
            snapshot_content = json.loads(latest_snapshot.snapshot_json)
            forecast_data = snapshot_content.get("weather")
            data_out["sirs"] = snapshot_content.get("sirs", [])
            data_out["terminal_constraints"] = snapshot_content.get("terminal_constraints", [])
            data_out["faa_events"] = snapshot_content.get("faa_events", [])
            if forecast_data:
                data_out["daily"] = forecast_data.get("daily", [])
                data_out["alerts"] = forecast_data.get("alerts", [])

        # --- MERGE LOGIC ---
        # This logic combines past data (from HourlyWeather) with the most recent forecast
        # (from the latest snapshot of the day), prioritizing the actual logged data.
        result_hourly = []
        seen = set()

        # 1. Prioritize all logged historical data for the day.
        for key, val in logged_by_time.items():
            result_hourly.append(val)
            seen.add(key)

        # 2. Fill in the rest from the snapshot's forecast, avoiding duplicates.
        if forecast_data and "hourly" in forecast_data:
            for period in forecast_data.get("hourly", []):
                key = period["startTime"]
                if key not in seen:
                    result_hourly.append(period)
                    # No need to add to seen, as we won't loop over forecast_data again.

        result_hourly.sort(key=lambda x: x["startTime"])
        data_out["hourly"] = result_hourly

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