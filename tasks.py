# --- START OF FILE tasks.py ---

import threading
import time
import json
from datetime import datetime

import services
import config
from database import db, HourlySnapshot, Hub

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
            all_hubs = Hub.query.all()
            for hub in all_hubs:
                try:
                    if services.snapshot_hub_data(hub, new_ground_stops, new_ground_delays):
                        data_changed_snapshot = True
                except Exception as e:
                    print(f"Error snapshotting data for {hub.iata}: {e}")
                    db.session.rollback()

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
