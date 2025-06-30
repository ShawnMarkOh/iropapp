# --- START OF FILE app.py ---

import os
import json
import threading
import click
import uuid
import logging
from logging.handlers import RotatingFileHandler
import time

from flask import Flask
from flask.cli import with_appcontext
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, current_user
from flask_bcrypt import Bcrypt
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import config
from database import db, init_db, Hub, User
from routes import init_routes
from tasks import init_tasks

# --- Logging Setup ---
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

# Configure root logger to write to a rotating file and the console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)

# --- App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_BINDS'] = config.SQLALCHEMY_BINDS
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
# MAX_CONTENT_LENGTH is removed as we are now streaming uploads

# --- Task Management for Imports and System Status ---
app.IMPORT_TASKS = {}
app.TASK_STATUS = {}

# --- Extensions Initialization ---
CORS(app)
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # The name of the login route
socketio = SocketIO(app, cors_allowed_origins="*")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Database and Routes Setup ---
def seed_database(app_instance):
    with app_instance.app_context():
        # Check if hubs table is empty
        if not Hub.query.first():
            logging.info("Hub table is empty. Seeding database from config.py...")
            # Seed active hubs
            for i, hub_data in enumerate(config.HUBS):
                runways_str = json.dumps(hub_data.get("runways", []))
                new_hub = Hub(
                    iata=hub_data["iata"],
                    name=hub_data["name"],
                    city=hub_data["city"],
                    tz=hub_data["tz"],
                    lat=hub_data["lat"],
                    lon=hub_data["lon"],
                    runways_json=runways_str,
                    is_active=True,
                    display_order=i
                )
                db.session.add(new_hub)
            
            # Seed inactive hubs
            for hub_data in config.INACTIVE_HUBS:
                runways_str = json.dumps(hub_data.get("runways", []))
                new_hub = Hub(
                    iata=hub_data["iata"],
                    name=hub_data["name"],
                    city=hub_data["city"],
                    tz=hub_data["tz"],
                    lat=hub_data["lat"],
                    lon=hub_data["lon"],
                    runways_json=runways_str,
                    is_active=False,
                    display_order=999 # High number for inactive
                )
                db.session.add(new_hub)
            
            db.session.commit()
            logging.info("Database seeded successfully.")

def create_or_update_admin(app_instance):
    """Creates or updates the admin user from environment variables."""
    with app_instance.app_context():
        admin_user = os.environ.get('ADMIN_USERNAME')
        admin_pass = os.environ.get('ADMIN_PASSWORD')

        if not admin_user or not admin_pass:
            if not User.query.first():
                logging.warning("WARNING: No admin credentials set in environment variables (ADMIN_USERNAME, ADMIN_PASSWORD) and no users exist in the database.")
                logging.warning("The application will not have an admin user. Please set the variables in your .env file.")
            return

        user = User.query.filter_by(username=admin_user).first()
        hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')

        if user:
            # If password hash is different, update it
            if not bcrypt.check_password_hash(user.password_hash, admin_pass):
                logging.info(f"Admin user '{admin_user}' found. Updating password.")
                user.password_hash = hashed_password
            else:
                logging.info(f"Admin user '{admin_user}' found. Password is unchanged.")
        else:
            logging.info(f"Creating admin user '{admin_user}'.")
            user = User(username=admin_user, password_hash=hashed_password)
            db.session.add(user)
        
        db.session.commit()
        logging.info("Admin user configured.")

# Create database tables if they don't exist
init_db(app)
# Seed the database with hub info if it's empty
seed_database(app)
# Create or update the admin user from environment variables
create_or_update_admin(app)

# Register all the routes from routes.py
init_routes(app, bcrypt)

# --- Live Log Streaming with Watchdog ---
class LogChangeHandler(FileSystemEventHandler):
    def __init__(self, socketio_instance, file_path):
        self.socketio = socketio_instance
        self.file_path = file_path
        try:
            self.last_pos = os.path.getsize(file_path)
        except OSError:
            self.last_pos = 0

    def on_modified(self, event):
        if event.src_path == self.file_path:
            try:
                with open(self.file_path, 'r') as f:
                    f.seek(self.last_pos)
                    new_lines = f.readlines()
                    self.last_pos = f.tell()
                    if new_lines:
                        self.socketio.emit('new_log_line', {'lines': new_lines}, namespace='/logs')
            except Exception as e:
                logging.error(f"Error reading log file for streaming: {e}")

def start_log_watcher(socketio_instance):
    if not os.path.exists(log_file):
        with open(log_file, 'w'): pass

    event_handler = LogChangeHandler(socketio_instance, log_file)
    observer = Observer()
    observer.schedule(event_handler, path=log_dir, recursive=False)
    observer.start()
    logging.info("Log file watcher started.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# --- Socket.IO Event Handlers ---
@socketio.on('hub_order_change')
def handle_hub_order_change(data):
    """
    Receives a new hub order from a client,
    and broadcasts it to all clients.
    """
    logging.info(f"Hub order change received, broadcasting to clients: {data}")
    emit('hub_order_update', data, broadcast=True)

@socketio.on('connect', namespace='/logs')
def handle_log_connect():
    if not current_user.is_authenticated:
        logging.warning("Unauthenticated user tried to connect to /logs namespace. Disconnecting.")
        return False # Reject connection
    
    logging.info("Log viewer client connected.")
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            last_100_lines = lines[-100:]
            emit('initial_logs', {'lines': last_100_lines})
    except Exception as e:
        logging.error(f"Could not send initial logs: {e}")

# --- Background Tasks ---
# Start background threads for data fetching
init_tasks(app, socketio)

# Start the log watcher in a background thread
log_watcher_thread = threading.Thread(target=start_log_watcher, args=(socketio,), daemon=True)
log_watcher_thread.start()

# --- Main Execution ---
if __name__ == "__main__":
    socketio.run(app, debug=True)
# --- END OF FILE app.py ---
