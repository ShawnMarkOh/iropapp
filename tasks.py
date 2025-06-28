# --- START OF FILE tasks.py ---

import threading
import time
import json
from datetime import datetime

import services
import config
from database import db, HourlySnapshot

def periodic_ops_plan_refresh():
    while True:
        try:
            services.get_latest_ops_plan_json()
        except Exception as e:
            print(f"Error in periodic_ops_plan_refresh: {e}")
        time.sleep(600)

def data_refresh_job(app, socketio):
    while True:
        with app.app_context():
            now = datetime.now()
            
            # --- Fetch all external data ---
            new_ground_stops = services.fetch_faa_ground_stops()
            new_ground_delays = services.fetch_faa_ground_delays()

            data_changed_snapshot = False
            for hub in config.HUBS:
                iata = hub["iata"]
                # Fetch fresh weather data
                weather_data = services.fetch_and_log_weather(iata)
                
                # Load other data for snapshot
                merged_log = services.load_daily_log()
                sirs = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
                terminal_constraints = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])
                faa_events = services.get_events_for_hub_day(iata, now, hub["tz"])
                
                snapshot = {
                    "weather": weather_data,
                    "sirs": sirs,
                    "terminal_constraints": terminal_constraints,
                    "faa_events": faa_events,
                    "ground_stop": new_ground_stops.get(iata),
                    "ground_delay": new_ground_delays.get(iata)
                }
                
                cur_date = now.strftime('%Y-%m-%d')
                cur_hour = now.hour
                exists = HourlySnapshot.query.filter_by(iata=iata, date=cur_date, hour=cur_hour).first()
                snapshot_str = json.dumps(snapshot)

                if not exists:
                    db.session.add(HourlySnapshot(
                        iata=iata,
                        date=cur_date,
                        hour=cur_hour,
                        snapshot_json=snapshot_str
                    ))
                    data_changed_snapshot = True
                else:
                    # Compare new snapshot with old one to see if an update is needed
                    if exists.snapshot_json != snapshot_str:
                        exists.snapshot_json = snapshot_str
                        data_changed_snapshot = True
                
                db.session.commit()

            # --- Check for changes in advisories and update caches ---
            data_changed_advisory = False
            if config.GROUND_STOPS_CACHE.get("json") != new_ground_stops:
                config.GROUND_STOPS_CACHE["json"] = new_ground_stops
                config.GROUND_STOPS_CACHE["time"] = now
                data_changed_advisory = True
            
            if config.GROUND_DELAYS_CACHE.get("json") != new_ground_delays:
                config.GROUND_DELAYS_CACHE["json"] = new_ground_delays
                config.GROUND_DELAYS_CACHE["time"] = now
                data_changed_advisory = True

            if data_changed_snapshot or data_changed_advisory:
                print("Data changed, emitting dashboard_update")
                socketio.emit('dashboard_update', {'msg': 'updated'})

        time.sleep(30)

def init_tasks(app, socketio):
    ops_thread = threading.Thread(target=periodic_ops_plan_refresh, daemon=True)
    snapshot_thread = threading.Thread(target=data_refresh_job, args=(app, socketio), daemon=True)
    ops_thread.start()
    snapshot_thread.start()
# --- END OF FILE tasks.py ---
