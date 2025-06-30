# --- START OF FILE app.py ---

import os
import json
import threading
import click
import uuid
from flask import Flask
from flask.cli import with_appcontext
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

import config
from database import db, init_db, Hub, User
from routes import init_routes
from tasks import init_tasks

# --- App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_BINDS'] = config.SQLALCHEMY_BINDS
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
# MAX_CONTENT_LENGTH is removed as we are now streaming uploads

# --- Task Management for Imports ---
app.IMPORT_TASKS = {}

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

def create_or_update_admin(app_instance):
    """Creates or updates the admin user from environment variables."""
    with app_instance.app_context():
        admin_user = os.environ.get('ADMIN_USERNAME')
        admin_pass = os.environ.get('ADMIN_PASSWORD')

        if not admin_user or not admin_pass:
            if not User.query.first():
                print("WARNING: No admin credentials set in environment variables (ADMIN_USERNAME, ADMIN_PASSWORD) and no users exist in the database.")
                print("The application will not have an admin user. Please set the variables in your .env file.")
            return

        user = User.query.filter_by(username=admin_user).first()
        hashed_password = bcrypt.generate_password_hash(admin_pass).decode('utf-8')

        if user:
            # If password hash is different, update it
            if not bcrypt.check_password_hash(user.password_hash, admin_pass):
                print(f"Admin user '{admin_user}' found. Updating password.")
                user.password_hash = hashed_password
            else:
                print(f"Admin user '{admin_user}' found. Password is unchanged.")
        else:
            print(f"Creating admin user '{admin_user}'.")
            user = User(username=admin_user, password_hash=hashed_password)
            db.session.add(user)
        
        db.session.commit()
        print("Admin user configured.")

# Create database tables if they don't exist
init_db(app)
# Seed the database with hub info if it's empty
seed_database(app)
# Create or update the admin user from environment variables
create_or_update_admin(app)

# Register all the routes from routes.py
init_routes(app, bcrypt)

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
