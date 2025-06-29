# --- START OF FILE app.py ---

import os
import json
import threading
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit

import config
from database import db, init_db, Hub
from routes import init_routes
from tasks import init_tasks

# --- App Initialization ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_BINDS'] = config.SQLALCHEMY_BINDS
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS

# --- Extensions Initialization ---
CORS(app)
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Database and Routes Setup ---
def seed_database(app_instance):
    with app_instance.app_context():
        # Check if hubs table is empty
        if not Hub.query.first():
            print("Hub table is empty. Seeding database from config.py...")
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
            print("Database seeded successfully.")

# Create database tables if they don't exist
init_db(app)
# Seed the database if needed
seed_database(app)

# Register all the routes from routes.py
init_routes(app)

# --- Socket.IO Event Handlers ---
@socketio.on('hub_order_change')
def handle_hub_order_change(data):
    """
    Receives a new hub order from a client,
    and broadcasts it to all clients.
    """
    # The data is expected to be a dictionary, e.g., {'order': ['CLT', 'DFW']}
    print(f"Hub order change received, broadcasting to clients: {data}")
    emit('hub_order_update', data, broadcast=True)

# --- Background Tasks ---
# Start background threads for data fetching
init_tasks(app, socketio)

# --- Main Execution ---
if __name__ == "__main__":
    socketio.run(app, debug=True)
# --- END OF FILE app.py ---
