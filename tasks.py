# --- START OF FILE tasks.py ---

import threading
import time
import json
import traceback
import logging
from datetime import datetime

import services
import config
from database import db, HourlySnapshot, Hub

def periodic_ops_plan_refresh(app):
    task_name = 'ops_plan_refresh'
    with app.app_context():
        app.TASK_STATUS[task_name] = {'status': 'running', 'last_success': None, 'last_error': None, 'last_runtime': None}
    
    while True:
        start_time = time.time()
        try:
            with app.app_context():
                services.get_latest_ops_plan_json()
                app.TASK_STATUS[task_name]['last_success'] = datetime.utcnow().isoformat() + 'Z'
                app.TASK_STATUS[task_name]['status'] = 'running'
                app.TASK_STATUS[task_name]['last_error'] = None
        except Exception as e:
            error_str = traceback.format_exc()
            logging.error(f"Error in periodic_ops_plan_refresh: {e}\n{error_str}")
            with app.app_context():
                app.TASK_STATUS[task_name]['status'] = 'error'
                app.TASK_STATUS[task_name]['last_error'] = error_str
        finally:
            with app.app_context():
                app.TASK_STATUS[task_name]['last_runtime'] = f"{time.time() - start_time:.2f}s"
            time.sleep(600)

def data_refresh_job(app, socketio):
    task_name = 'data_refresh'
    with app.app_context():
        app.TASK_STATUS[task_name] = {'status': 'running', 'last_success': None, 'last_error': None, 'last_runtime': None}

    while True:
        start_time = time.time()
        try:
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
                        logging.error(f"Error snapshotting data for {hub.iata}: {e}")
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
                    logging.info("Data changed, emitting dashboard_update")
                    socketio.emit('dashboard_update', {'msg': 'updated'})
                
                app.TASK_STATUS[task_name]['last_success'] = datetime.utcnow().isoformat() + 'Z'
                app.TASK_STATUS[task_name]['status'] = 'running'
                app.TASK_STATUS[task_name]['last_error'] = None

        except Exception as e:
            error_str = traceback.format_exc()
            logging.error(f"Error in data_refresh_job: {e}\n{error_str}")
            with app.app_context():
                app.TASK_STATUS[task_name]['status'] = 'error'
                app.TASK_STATUS[task_name]['last_error'] = error_str
        finally:
            with app.app_context():
                app.TASK_STATUS[task_name]['last_runtime'] = f"{time.time() - start_time:.2f}s"
            time.sleep(30)

def init_tasks(app, socketio):
    ops_thread = threading.Thread(target=periodic_ops_plan_refresh, args=(app,), daemon=True)
    snapshot_thread = threading.Thread(target=data_refresh_job, args=(app, socketio), daemon=True)
    ops_thread.start()
    snapshot_thread.start()
# --- END OF FILE tasks.py ---
