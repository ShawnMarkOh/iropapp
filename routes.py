# --- START OF FILE routes.py ---

import os
import pytz
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup

from flask import jsonify, render_template, send_from_directory, request, flash, redirect, url_for
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import desc, inspect
from werkzeug.utils import secure_filename

import config
import services
from database import db, HourlyWeather, HourlySnapshot, Hub, User

EDITABLE_MODELS = {
    'default': {
        'hourly_weather': HourlyWeather,
        'hourly_snapshot': HourlySnapshot,
    },
    'airports': {
        'user': User,
        'hub': Hub,
    }
}

def init_routes(app, bcrypt):
    @app.route("/login", methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('admin_panel'))
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()
            if user and bcrypt.check_password_hash(user.password_hash, password):
                login_user(user)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('admin_panel'))
            else:
                flash('Login Unsuccessful. Please check username and password.', 'danger')
        return render_template('login.html')

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('dashboard'))

    @app.route("/admin")
    @login_required
    def admin_panel():
        return render_template("admin.html")

    @app.route("/admin/edit-db")
    @login_required
    def edit_db():
        return render_template("edit_db.html")

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
        hubs = Hub.query.filter_by(is_active=True).order_by(Hub.display_order).all()
        return jsonify([h.as_dict() for h in hubs])

    @app.route("/api/hubs/inactive")
    def inactive_hubs_api():
        hubs = Hub.query.filter_by(is_active=False).order_by(Hub.name).all()
        return jsonify([h.as_dict() for h in hubs])

    @app.route("/api/hubs/add", methods=['POST'])
    @login_required
    def add_hub_api():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid request"}), 400

        required_fields = ["iata", "name", "city", "tz", "lat", "lon", "runways"]
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        if Hub.query.filter_by(iata=data['iata']).first():
            return jsonify({"error": f"Hub with IATA code {data['iata']} already exists."}), 409

        try:
            new_hub = Hub(
                iata=data['iata'],
                name=data['name'],
                city=data['city'],
                tz=data['tz'],
                lat=data['lat'],
                lon=data['lon'],
                runways_json=json.dumps(data['runways']),
                is_active=False, # Add as inactive by default
                display_order=999
            )
            db.session.add(new_hub)
            db.session.commit()

            # Immediately fetch data for the new hub to create its first snapshot
            try:
                print(f"Performing initial data snapshot for new hub: {new_hub.iata}")
                ground_stops = services.fetch_faa_ground_stops()
                ground_delays = services.fetch_faa_ground_delays()
                services.snapshot_hub_data(new_hub, ground_stops, ground_delays)
                print(f"Initial snapshot for {new_hub.iata} complete.")
            except Exception as e:
                # Log this error but don't fail the whole request,
                # the background task will pick it up eventually.
                print(f"ERROR: Could not perform initial data snapshot for {new_hub.iata}: {e}")

            return jsonify({"success": True, "hub": new_hub.as_dict()}), 201
        except Exception as e:
            db.session.rollback()
            print(f"Error adding hub: {e}")
            return jsonify({"error": "Failed to add hub to database."}), 500

    @app.route("/api/hubs/update_order", methods=['POST'])
    @login_required
    def update_hub_order_api():
        data = request.get_json()
        if not data or 'active' not in data or 'inactive' not in data:
            return jsonify({"error": "Invalid data format"}), 400

        try:
            active_iatas = data['active']
            inactive_iatas = data['inactive']

            # Update active hubs
            for i, iata in enumerate(active_iatas):
                hub = Hub.query.filter_by(iata=iata).first()
                if hub:
                    hub.is_active = True
                    hub.display_order = i

            # Update inactive hubs
            for iata in inactive_iatas:
                hub = Hub.query.filter_by(iata=iata).first()
                if hub:
                    hub.is_active = False
                    hub.display_order = 999

            db.session.commit()
            return jsonify({"success": True})
        except Exception as e:
            db.session.rollback()
            print(f"Error updating hub order: {e}")
            return jsonify({"error": "Failed to update hub order."}), 500

    @app.route("/api/airport-info/<icao>")
    def airport_info_api(icao):
        """
        Proxy for aviationweather.gov to get airport data, avoiding CORS issues.
        This proxy now parses the response and returns clean JSON.
        """
        try:
            url = f"https://aviationweather.gov/api/data/airport?ids={icao.upper()}&format=json"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            
            content_type = resp.headers.get('Content-Type', '')
            
            # The API sometimes returns JSON directly, and sometimes HTML with JSON in a <pre> tag.
            if 'application/json' in content_type:
                return jsonify(resp.json())
            
            # Handle HTML response
            soup = BeautifulSoup(resp.text, 'html.parser')
            pre_tag = soup.find('pre')
            if pre_tag:
                try:
                    json_data = json.loads(pre_tag.string)
                    return jsonify(json_data)
                except (json.JSONDecodeError, TypeError):
                    return jsonify({"error": "Failed to parse JSON from aviationweather.gov response."}), 500
            
            return jsonify({"error": "Could not find airport data in the response from aviationweather.gov."}), 502

        except requests.RequestException as e:
            error_message = f"Failed to fetch data from aviationweather.gov: {e}"
            print(error_message)
            return jsonify({"error": error_message}), 502 # Bad Gateway

    @app.route("/api/weather/<iata>")
    def weather_api(iata):
        iata = iata.upper()
        req_date = request.args.get('date')
        hub = Hub.query.filter_by(iata=iata).first()
        if not hub:
            return jsonify({"error": "Unknown IATA code"}), 404
        tz = pytz.timezone(hub.tz)

        local_date_str = req_date or datetime.now(tz).strftime("%Y-%m-%d")

        # Default structure for the output
        data_out = {
            "hourly": [], "daily": [], "timezone": tz.zone, "sirs": [],
            "terminal_constraints": [], "faa_events": [], "alerts": [],
            "aviation_forecast": None
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
                data_out["aviation_forecast"] = forecast_data.get("aviation_forecast")

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

    @app.route('/api/import-weather-db', methods=['POST'])
    @login_required
    def import_weather_db():
        if 'db_file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        file = request.files['db_file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        if file:
            filename = secure_filename(file.filename)
            temp_path = os.path.join(config.DATA_DIR, f"temp_{filename}")
            file.save(temp_path)
            
            try:
                stats = services.import_from_db_file(temp_path)
                os.remove(temp_path)
                return jsonify({"success": True, "stats": stats})
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return jsonify({"error": f"An error occurred during import: {str(e)}"}), 500
        return jsonify({"error": "File upload failed"}), 500

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

    # --- Admin DB Edit API ---
    @app.route("/api/admin/db/binds")
    @login_required
    def get_db_binds():
        binds = list(app.config.get('SQLALCHEMY_BINDS', {}).keys())
        binds.append('default') # The main DB doesn't have a bind key
        return jsonify(sorted(binds))

    @app.route("/api/admin/db/tables/<bind_key>")
    @login_required
    def get_db_tables(bind_key):
        if bind_key not in EDITABLE_MODELS:
            return jsonify({"error": "Invalid database bind"}), 404
        return jsonify(sorted(list(EDITABLE_MODELS[bind_key].keys())))

    @app.route("/api/admin/db/table/<bind_key>/<table_name>")
    @login_required
    def get_table_data(bind_key, table_name):
        if bind_key not in EDITABLE_MODELS or table_name not in EDITABLE_MODELS[bind_key]:
            return jsonify({"error": "Invalid database or table"}), 404
        
        Model = EDITABLE_MODELS[bind_key][table_name]
        page = request.args.get('page', 1, type=int)
        per_page = 20

        pagination = Model.query.order_by(Model.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
        
        columns = [c.key for c in inspect(Model).columns]
        
        items = []
        for item in pagination.items:
            item_dict = {c: getattr(item, c) for c in columns}
            items.append(item_dict)

        return jsonify({
            "columns": columns,
            "items": items,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
            "page": pagination.page,
            "total_pages": pagination.pages,
            "total_items": pagination.total
        })

    @app.route("/api/admin/db/table/<bind_key>/<table_name>/<int:entry_id>", methods=['POST'])
    @login_required
    def update_table_entry(bind_key, table_name, entry_id):
        if bind_key not in EDITABLE_MODELS or table_name not in EDITABLE_MODELS[bind_key]:
            return jsonify({"error": "Invalid database or table"}), 404
        
        Model = EDITABLE_MODELS[bind_key][table_name]
        entry = Model.query.get_or_404(entry_id)
        data = request.get_json()

        if not data:
            return jsonify({"error": "Invalid request body"}), 400

        mapper = inspect(Model)
        for key, value in data.items():
            if key in mapper.columns and key != 'id':
                column_type = mapper.columns[key].type.python_type
                try:
                    if value is None or value == '':
                        converted_value = None
                    elif column_type == bool:
                        converted_value = str(value).lower() in ['true', '1', 't', 'y', 'yes']
                    else:
                        converted_value = column_type(value)
                    setattr(entry, key, converted_value)
                except (ValueError, TypeError):
                    return jsonify({"error": f"Invalid value '{value}' for column '{key}' (expected {column_type.__name__})"}), 400
        
        db.session.commit()
        return jsonify({"success": True})

    @app.route("/api/admin/db/table/<bind_key>/<table_name>/<int:entry_id>", methods=['DELETE'])
    @login_required
    def delete_table_entry(bind_key, table_name, entry_id):
        if bind_key not in EDITABLE_MODELS or table_name not in EDITABLE_MODELS[bind_key]:
            return jsonify({"error": "Invalid database or table"}), 404
        
        Model = EDITABLE_MODELS[bind_key][table_name]
        entry = Model.query.get_or_404(entry_id)
        
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"success": True})
# --- END OF FILE routes.py ---
