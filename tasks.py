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

def minute_snapshot_job(app, socketio):
    while True:
        with app.app_context():
            now = datetime.now()
            cur_date = now.strftime('%Y-%m-%d')
            cur_hour = now.hour
            data_changed = False
            for hub in config.HUBS:
                iata = hub["iata"]
                # Fetch fresh data
                weather_data = services.fetch_and_log_weather(iata)
                merged_log = services.load_daily_log()
                sirs = merged_log.get("hubs", {}).get(iata, {}).get("sirs", [])
                terminal_constraints = merged_log.get("hubs", {}).get(iata, {}).get("terminal_constraints", [])
                faa_events = services.get_events_for_hub_day(iata, now, hub["tz"])
                
                snapshot = {
                    "weather": weather_data,
                    "sirs": sirs,
                    "terminal_constraints": terminal_constraints,
                    "faa_events": faa_events
                }
                
                exists = HourlySnapshot.query.filter_by(iata=iata, date=cur_date, hour=cur_hour).first()
                snapshot_str = json.dumps(snapshot)

                if not exists:
                    db.session.add(HourlySnapshot(
                        iata=iata,
                        date=cur_date,
                        hour=cur_hour,
                        snapshot_json=snapshot_str
                    ))
                    data_changed = True
                else:
                    # Compare new snapshot with old one to see if an update is needed
                    if exists.snapshot_json != snapshot_str:
                        exists.snapshot_json = snapshot_str
                        data_changed = True
                
                db.session.commit()

            if data_changed:
                print("Data changed, emitting dashboard_update")
                socketio.emit('dashboard_update', {'msg': 'updated'})

        # Sleep until the start of the next minute
        time_to_next_min = 60 - datetime.now().second
        time.sleep(time_to_next_min)

def init_tasks(app, socketio):
    ops_thread = threading.Thread(target=periodic_ops_plan_refresh, daemon=True)
    snapshot_thread = threading.Thread(target=minute_snapshot_job, args=(app, socketio), daemon=True)
    ops_thread.start()
    snapshot_thread.start()
# --- END OF FILE tasks.py ---